from __future__ import annotations

import logging
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import IO

import discord

from bot.audio.youtube_opts import ytdlp_extractor_args_cli
from bot.config import settings

log = logging.getLogger("beethovenly.mpv")

FRAME_SIZE = 3840  # 20 ms * 48000 Hz * 2 ch * 2 B


@dataclass(frozen=True)
class _StreamStrategy:
    name: str
    clients: str
    use_cookies: bool


# Order: cookies+web (needs PO/EJS) → anon android_vr → cookies+android_vr last resort.
_STRATEGIES: tuple[_StreamStrategy, ...] = (
    _StreamStrategy("cookies+mweb", "mweb,tv,web_safari,web", True),
    _StreamStrategy("cookies+tv", "tv,tv_simply,mweb", True),
    _StreamStrategy("anon+android_vr", "android_vr,tv,web_safari", False),
    _StreamStrategy("cookies+android_vr", "android_vr", True),
)


class MPVPCMSource(discord.AudioSource):
    """Stream with ``yt-dlp -o - URL | mpv -`` into PCM for Discord voice.

    Uses the Python yt-dlp (cookies + updates) and pipes media into mpv for
    decode — same idea as the yt-dlp FAQ stdout streaming example.
    """

    def __init__(self, url: str) -> None:
        self.url = url
        self.proc: subprocess.Popen[bytes] | None = None
        self._ytdlp: subprocess.Popen[bytes] | None = None
        self._stderr_thread: threading.Thread | None = None
        self._ytdlp_stderr_thread: threading.Thread | None = None
        self._stderr_tail: list[str] = []
        self._started = False
        self.failed = False
        self.fail_reason = ""
        self._strategy: _StreamStrategy | None = None

    def _ytdlp_common(self, strategy: _StreamStrategy) -> list[str]:
        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "-f",
            "bestaudio/best",
            "--no-playlist",
            "--no-progress",
            "--js-runtimes",
            "deno",
            "--remote-components",
            "ejs:github",
            *ytdlp_extractor_args_cli(player_clients=strategy.clients, cookies=strategy.use_cookies),
        ]
        if strategy.use_cookies and settings.cookies_file:
            cmd.extend(["--cookies", settings.cookies_file])
        elif strategy.use_cookies and settings.cookies_from_browser:
            cmd.extend(["--cookies-from-browser", settings.cookies_from_browser])
        return cmd

    def _ytdlp_command(self, strategy: _StreamStrategy | None = None) -> list[str]:
        strategy = strategy or self._strategy or _STRATEGIES[0]
        cmd = self._ytdlp_common(strategy)
        # Insert stream flags after module name args: quiet + stdout.
        # Rebuild cleanly for streaming.
        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "-f",
            "bestaudio/best",
            "-o",
            "-",
            "--quiet",
            "--no-warnings",
            "--no-playlist",
            "--no-progress",
            "--js-runtimes",
            "deno",
            "--remote-components",
            "ejs:github",
            *ytdlp_extractor_args_cli(player_clients=strategy.clients, cookies=strategy.use_cookies),
        ]
        if strategy.use_cookies and settings.cookies_file:
            cmd.extend(["--cookies", settings.cookies_file])
        elif strategy.use_cookies and settings.cookies_from_browser:
            cmd.extend(["--cookies-from-browser", settings.cookies_from_browser])
        cmd.extend(["--", self.url])
        return cmd

    def _pick_strategy(self) -> _StreamStrategy:
        """Probe with ``yt-dlp -g`` until one strategy yields a media URL."""
        available = [
            s
            for s in _STRATEGIES
            if (not s.use_cookies) or settings.cookies_file or settings.cookies_from_browser
        ]

        errors: list[str] = []
        for strategy in available:
            cmd = [
                *self._ytdlp_common(strategy),
                "-g",
                "--",
                self.url,
            ]
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=90,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                errors.append(f"{strategy.name}: timeout")
                continue
            if proc.returncode == 0 and proc.stdout.strip():
                log.info("yt-dlp strategy ok: %s", strategy.name)
                return strategy
            err = (proc.stderr or proc.stdout or "").strip().splitlines()
            brief = err[-1] if err else f"exit {proc.returncode}"
            errors.append(f"{strategy.name}: {brief}")
            log.warning("yt-dlp strategy failed (%s): %s", strategy.name, brief)

        raise RuntimeError("all yt-dlp strategies failed:\n" + "\n".join(errors))

    def _mpv_command(self) -> list[str]:
        return [
            "mpv",
            "--no-config",
            "--no-video",
            "--vo=null",
            "--no-terminal",
            "--really-quiet",
            "--idle=no",
            "--force-window=no",
            "--gapless-audio=no",
            "--audio-display=no",
            "--load-scripts=no",
            "--ytdl=no",
            "--ao=pcm",
            "--ao-pcm-waveheader=no",
            "--ao-pcm-file=/dev/stdout",
            "--audio-format=s16",
            "--audio-channels=stereo",
            "--audio-samplerate=48000",
            "--audio-fallback-to-null=no",
            "--cache=yes",
            "--demuxer-max-bytes=64MiB",
            "--network-timeout=30",
            "-",  # read media stream from stdin
        ]

    def _ensure_started(self) -> None:
        if self._started:
            return
        self._started = True
        log.info("yt-dlp | mpv pipe start: %s", self.url)
        try:
            self._strategy = self._pick_strategy()
        except RuntimeError as exc:
            self.failed = True
            self.fail_reason = str(exc)
            log.warning("%s", exc)
            raise

        self._ytdlp = subprocess.Popen(
            self._ytdlp_command(self._strategy),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            bufsize=0,
        )
        assert self._ytdlp.stdout is not None
        self.proc = subprocess.Popen(
            self._mpv_command(),
            stdin=self._ytdlp.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        # Allow yt-dlp to receive SIGPIPE if mpv exits first.
        self._ytdlp.stdout.close()

        self._stderr_thread = threading.Thread(target=self._drain_mpv_stderr, daemon=True)
        self._stderr_thread.start()
        self._ytdlp_stderr_thread = threading.Thread(target=self._drain_ytdlp_stderr, daemon=True)
        self._ytdlp_stderr_thread.start()

    def _note_stderr(self, prefix: str, line: str) -> None:
        self._stderr_tail.append(f"{prefix}{line}")
        if len(self._stderr_tail) > 40:
            self._stderr_tail = self._stderr_tail[-40:]
        lower = line.lower()
        if any(token in lower for token in ("error", "failed", "forbidden", "403", "sign in", "bot")):
            log.warning("%s%s", prefix, line)
        else:
            log.debug("%s%s", prefix, line)

    def _drain_mpv_stderr(self) -> None:
        assert self.proc is not None
        stderr: IO[bytes] | None = self.proc.stderr
        if stderr is None:
            return
        for raw in stderr:
            line = raw.decode("utf-8", errors="replace").rstrip()
            if line:
                self._note_stderr("mpv: ", line)

    def _drain_ytdlp_stderr(self) -> None:
        assert self._ytdlp is not None
        stderr: IO[bytes] | None = self._ytdlp.stderr
        if stderr is None:
            return
        for raw in stderr:
            line = raw.decode("utf-8", errors="replace").rstrip()
            if line:
                self._note_stderr("yt-dlp: ", line)

    def read(self) -> bytes:
        self._ensure_started()
        assert self.proc is not None
        stdout = self.proc.stdout
        if stdout is None:
            return b""
        data = b""
        while len(data) < FRAME_SIZE:
            chunk = stdout.read(FRAME_SIZE - len(data))
            if not chunk:
                if data:
                    return data + b"\x00" * (FRAME_SIZE - len(data))
                ytdlp_code = self._ytdlp.poll() if self._ytdlp else None
                mpv_code = self.proc.poll()
                bad_ytdlp = ytdlp_code not in (0, None, -signal.SIGTERM, -signal.SIGKILL, -signal.SIGPIPE)
                bad_mpv = mpv_code not in (0, None, -signal.SIGTERM, -signal.SIGKILL)
                if bad_ytdlp or bad_mpv:
                    self.failed = True
                    tail = "\n".join(self._stderr_tail[-10:])
                    self.fail_reason = f"pipe exit yt-dlp={ytdlp_code} mpv={mpv_code}"
                    if tail:
                        self.fail_reason += f"\n{tail}"
                        log.warning("stream pipe stderr:\n%s", tail)
                    raise RuntimeError(self.fail_reason)
                return b""
            data += chunk
        return data

    def is_opus(self) -> bool:
        return False

    def _stop_proc(self, proc: subprocess.Popen[bytes] | None) -> None:
        if proc is None:
            return
        try:
            proc.terminate()
        except Exception:  # noqa: BLE001
            pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass
            try:
                proc.wait(timeout=1)
            except Exception:  # noqa: BLE001
                pass

    def cleanup(self) -> None:
        mpv = self.proc
        ytdlp = self._ytdlp
        self.proc = None
        self._ytdlp = None
        # Stop mpv first so yt-dlp gets SIGPIPE / closes cleanly.
        self._stop_proc(mpv)
        self._stop_proc(ytdlp)
        if mpv is not None:
            log.debug("mpv zakończony (kod %s)", mpv.returncode)
        if ytdlp is not None and ytdlp.returncode not in (0, None, -signal.SIGTERM, -signal.SIGKILL, -signal.SIGPIPE):
            self.failed = True
            tail = "\n".join(self._stderr_tail[-10:])
            if tail:
                log.warning("yt-dlp/mpv stderr:\n%s", tail)
