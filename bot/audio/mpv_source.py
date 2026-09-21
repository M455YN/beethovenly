from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
from typing import IO

import discord

from bot.config import settings

log = logging.getLogger("beethovenly.mpv")

FRAME_SIZE = 3840  # 20 ms * 48000 Hz * 2 ch * 2 B


class MPVPCMSource(discord.AudioSource):
    """Dekoduje utwór przez mpv (+ wbudowany yt-dlp) do PCM s16le 48 kHz stereo."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.proc: subprocess.Popen[bytes] | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr_tail: list[str] = []
        self._started = False

    def _command(self) -> list[str]:
        cmd = [
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
            "--ytdl=yes",
            "--ytdl-format=bestaudio/best",
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
        ]
        if settings.cookies_file:
            # Pass Netscape cookies.txt into mpv's embedded yt-dlp.
            # Must be a single ytdl-raw-options value (not a bare "--cookies …" argv).
            cmd.append(f"--ytdl-raw-options=cookies={settings.cookies_file}")
        cmd.append(self.url)
        return cmd

    def _ensure_started(self) -> None:
        if self._started:
            return
        self._started = True
        log.info("mpv start: %s", self.url)
        self.proc = subprocess.Popen(
            self._command(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            bufsize=0,
            start_new_session=True,
        )
        self._stderr_thread = threading.Thread(target=self._drain_stderr, daemon=True)
        self._stderr_thread.start()

    def _drain_stderr(self) -> None:
        assert self.proc is not None
        stderr: IO[bytes] | None = self.proc.stderr
        if stderr is None:
            return
        for raw in stderr:
            line = raw.decode("utf-8", errors="replace").rstrip()
            if not line:
                continue
            self._stderr_tail.append(line)
            if len(self._stderr_tail) > 30:
                self._stderr_tail = self._stderr_tail[-30:]
            log.debug("mpv: %s", line)

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
                return b""
            data += chunk
        return data

    def is_opus(self) -> bool:
        return False

    def cleanup(self) -> None:
        proc = self.proc
        self.proc = None
        if proc is None:
            return
        pid = proc.pid
        try:
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                proc.terminate()
            except Exception:  # noqa: BLE001
                pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
            try:
                proc.wait(timeout=1)
            except Exception:  # noqa: BLE001
                pass
        log.debug("mpv zakończony (kod %s)", proc.returncode)
        if proc.returncode not in (0, None, -signal.SIGTERM, -signal.SIGKILL):
            tail = "\n".join(self._stderr_tail[-8:])
            if tail:
                log.warning("mpv stderr:\n%s", tail)
