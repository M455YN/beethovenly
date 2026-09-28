from __future__ import annotations

import logging
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import IO

import discord

from bot.audio.youtube_opts import cookies_look_usable, ytdlp_extractor_args_cli
from bot.config import settings

log = logging.getLogger("beethovenly.mpv")

FRAME_SIZE = 3840  # 20 ms * 48000 Hz * 2 ch * 2 B

# Prefer HLS (web_safari GVS often needs no PO) then pot-backed clients.
# Never mix cookies with android_vr — yt-dlp warns / bot-checks.
_FORMAT = "bestaudio[protocol^=m3u8]/bestaudio/best"


@dataclass(frozen=True)
class _StreamStrategy:
    name: str
    clients: str
    use_cookies: bool = False


_STRATEGIES: tuple[_StreamStrategy, ...] = (
    _StreamStrategy("anon+web_safari", "web_safari"),
    _StreamStrategy("anon+android_vr", "android_vr,tv"),
    _StreamStrategy("anon+mweb", "mweb,web_safari"),
    _StreamStrategy("anon+tv", "tv,tv_simply"),
    _StreamStrategy("cookies+mweb", "mweb,web_safari,web", True),
    _StreamStrategy("cookies+tv", "tv,mweb", True),
)


class MPVPCMSource(discord.AudioSource):
    """Resolve a direct media URL with yt-dlp, then decode with mpv → PCM.

    Pipe ``yt-dlp -o -`` breaks HLS (m3u8). Instead: ``yt-dlp -g`` then
    ``mpv --ytdl=no <cdn-url>`` — works with and without PO tokens.
    """

    def __init__(self, url: str) -> None:
        self.url = url
        self.proc: subprocess.Popen[bytes] | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr_tail: list[str] = []
        self._started = False
        self.failed = False
        self.fail_reason = ""
        self._strategy: _StreamStrategy | None = None
        self._media_url: str | None = None

    def _available_strategies(self) -> list[_StreamStrategy]:
        out: list[_StreamStrategy] = []
        for s in _STRATEGIES:
            if s.use_cookies and not cookies_look_usable():
                continue
            out.append(s)
        return out

    def _ytdlp_base(self, strategy: _StreamStrategy) -> list[str]:
        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "-f",
            _FORMAT,
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

    def _resolve_media_url(self, strategy: _StreamStrategy) -> str | None:
        cmd = [*self._ytdlp_base(strategy), "-g", "--", self.url]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
        except subprocess.TimeoutExpired:
            log.warning("yt-dlp strategy timeout (%s)", strategy.name)
            return None
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip().splitlines()
            brief = err[-1] if err else f"exit {proc.returncode}"
            log.warning("yt-dlp strategy failed (%s): %s", strategy.name, brief)
            return None
        lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
        if not lines:
            log.warning("yt-dlp strategy failed (%s): empty -g output", strategy.name)
            return None
        # bestaudio should be a single URL; if multiple, take the first (audio).
        return lines[0]

    def _pick_strategy(self) -> tuple[_StreamStrategy, str]:
        errors: list[str] = []
        for strategy in self._available_strategies():
            media = self._resolve_media_url(strategy)
            if media:
                log.info("yt-dlp strategy ok: %s", strategy.name)
                return strategy, media
            errors.append(strategy.name)
        raise RuntimeError(
            "all yt-dlp strategies failed (need pot-provider on :4416; "
            "cookies only with YOUTUBE_USE_COOKIES=1):\n" + "\n".join(errors)
        )

    def _mpv_command(self, media_url: str) -> list[str]:
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
            "--",
            media_url,
        ]

    def _ensure_started(self) -> None:
        if self._started:
            return
        self._started = True
        log.info("stream start: %s", self.url)
        try:
            self._strategy, self._media_url = self._pick_strategy()
        except RuntimeError as exc:
            self.failed = True
            self.fail_reason = str(exc)
            log.warning("%s", exc)
            raise

        assert self._media_url is not None
        log.info(
            "mpv decode (%s): %s",
            self._strategy.name if self._strategy else "?",
            self._media_url[:120],
        )
        self.proc = subprocess.Popen(
            self._mpv_command(self._media_url),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            bufsize=0,
        )
        self._stderr_thread = threading.Thread(target=self._drain_mpv_stderr, daemon=True)
        self._stderr_thread.start()

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
                mpv_code = self.proc.poll()
                bad_mpv = mpv_code not in (0, None, -signal.SIGTERM, -signal.SIGKILL)
                if bad_mpv:
                    self.failed = True
                    tail = "\n".join(self._stderr_tail[-10:])
                    self.fail_reason = f"mpv exit={mpv_code}"
                    if tail:
                        self.fail_reason += f"\n{tail}"
                        log.warning("mpv stderr:\n%s", tail)
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
        self.proc = None
        self._stop_proc(mpv)
        if mpv is not None:
            log.debug("mpv zakończony (kod %s)", mpv.returncode)
