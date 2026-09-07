from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import TYPE_CHECKING, Deque

import discord

from bot.audio.mpv_source import MPVPCMSource
from bot.audio.track import LoopMode, Track
from bot.config import settings

if TYPE_CHECKING:
    from bot.bot import Beethovenly

log = logging.getLogger("beethovenly.player")


class NotInVoice(RuntimeError):
    pass


class GuildPlayer:
    def __init__(self, bot: Beethovenly, guild: discord.Guild) -> None:
        self.bot = bot
        self.guild = guild
        self.queue: Deque[Track] = deque()
        self.history: Deque[Track] = deque(maxlen=50)
        self.current: Track | None = None
        self.loop = LoopMode.OFF
        self.shuffle_on_add = False
        self.volume = 0.65
        self.text_channel: discord.abc.MessageableChannel | None = None
        self.controller_message: discord.Message | None = None
        self._lock = asyncio.Lock()
        self._play_started_at: float | None = None
        self._elapsed_offset = 0.0
        self._idle_task: asyncio.Task[None] | None = None
        self._ui_task: asyncio.Task[None] | None = None
        self._skip_requested = False
        self._stopped = False
        self._fail_streak = 0

    @property
    def voice(self) -> discord.VoiceClient | None:
        vc = self.guild.voice_client
        return vc if isinstance(vc, discord.VoiceClient) else None

    @property
    def is_playing(self) -> bool:
        voice = self.voice
        return bool(voice and voice.is_playing())

    @property
    def is_paused(self) -> bool:
        voice = self.voice
        return bool(voice and voice.is_paused())

    @property
    def position(self) -> float:
        if self.current is None:
            return 0.0
        extra = 0.0
        if self._play_started_at is not None and not self.is_paused:
            extra = max(0.0, time.monotonic() - self._play_started_at)
        pos = self._elapsed_offset + extra
        if self.current.duration:
            return min(pos, float(self.current.duration))
        return pos

    def queue_snapshot(self) -> list[Track]:
        return list(self.queue)

    async def connect(self, channel: discord.VoiceChannel | discord.StageChannel) -> discord.VoiceClient:
        voice = self.voice
        if voice and voice.channel and voice.channel.id == channel.id:
            return voice
        if voice:
            await voice.move_to(channel)
            return voice
        return await channel.connect(self_deaf=True, reconnect=True)

    async def enqueue(
        self,
        tracks: list[Track],
        *,
        text_channel: discord.abc.MessageableChannel | None = None,
        play_now: bool = False,
    ) -> int:
        if text_channel is not None:
            self.text_channel = text_channel
        added = 0
        async with self._lock:
            for track in tracks:
                if play_now and added == 0:
                    self.queue.appendleft(track)
                else:
                    self.queue.append(track)
                added += 1
            if self.shuffle_on_add and len(self.queue) > 1:
                import random

                items = list(self.queue)
                random.shuffle(items)
                self.queue = deque(items)
        self._cancel_idle()
        if play_now and self.voice and (self.is_playing or self.is_paused):
            self._skip_requested = True
            self.voice.stop()
        elif not self.is_playing and not self.is_paused:
            await self._ensure_playback()
        else:
            await self.refresh_controller()
        return added

    async def _ensure_playback(self) -> None:
        voice = self.voice
        if voice is None or not voice.is_connected():
            return
        if self.is_playing or self.is_paused:
            return
        await self._play_next()

    async def _play_next(self, failed: Track | None = None) -> None:
        async with self._lock:
            finished = self.current
            skip = self._skip_requested
            stopped = self._stopped
            self._skip_requested = False
            self._stopped = False

            if failed:
                self._fail_streak += 1
            else:
                self._fail_streak = 0

            nxt: Track | None = None
            if stopped or self._fail_streak > 5:
                self.queue.clear()
                nxt = None
            elif self.loop == LoopMode.ONE and finished and not skip:
                nxt = finished
            else:
                if self.loop == LoopMode.ALL and finished and failed is None and not stopped:
                    self.queue.append(finished)
                nxt = self.queue.popleft() if self.queue else None

            if nxt is None:
                if finished:
                    self.history.appendleft(finished)
                self.current = None
                self._play_started_at = None
                self._elapsed_offset = 0.0
                idle = True
            else:
                if finished and finished is not nxt:
                    self.history.appendleft(finished)
                self.current = nxt
                self._elapsed_offset = 0.0
                self._play_started_at = time.monotonic()
                idle = False

        if idle:
            self._arm_idle()
            await self.refresh_controller()
            return

        assert nxt is not None
        voice = self.voice
        if voice is None:
            return

        source = discord.PCMVolumeTransformer(MPVPCMSource(nxt.webpage_url), volume=self.volume)

        def after(error: Exception | None) -> None:
            if error:
                log.warning("Błąd odtwarzania %s: %s", nxt.display_title, error)
            # Nie czekaj na future — wątek audio nie może blokować się na event loop.
            asyncio.run_coroutine_threadsafe(self._after_track(nxt, error), self.bot.loop)

        try:
            voice.play(source, after=after)
        except Exception:
            log.exception("Nie udało się wystartować mpv dla %s", nxt.webpage_url)
            await self._play_next(failed=nxt)
            return

        self._start_ui_loop()
        await self.refresh_controller()

    async def _after_track(self, track: Track, error: Exception | None) -> None:
        if error:
            log.info("Utwór przerwał się z błędem: %s", error)
        await self._play_next(failed=track if error else None)

    async def skip(self) -> Track | None:
        current = self.current
        voice = self.voice
        self._skip_requested = True
        if voice and (voice.is_playing() or voice.is_paused()):
            voice.stop()
        else:
            await self._play_next()
        return current

    async def previous(self) -> Track | None:
        async with self._lock:
            if not self.history:
                return None
            prev = self.history.popleft()
            if self.current:
                self.queue.appendleft(self.current)
            self.queue.appendleft(prev)
            self.current = None
        self._skip_requested = True
        voice = self.voice
        if voice and (voice.is_playing() or voice.is_paused()):
            voice.stop()
        else:
            await self._play_next()
        return prev

    async def stop(self) -> None:
        async with self._lock:
            self.queue.clear()
            self._stopped = True
            self._skip_requested = True
        voice = self.voice
        if voice and (voice.is_playing() or voice.is_paused()):
            voice.stop()
        else:
            self.current = None
            await self.refresh_controller()

    async def pause(self) -> bool:
        voice = self.voice
        if not voice or not voice.is_playing():
            return False
        self._elapsed_offset = self.position
        self._play_started_at = None
        voice.pause()
        await self.refresh_controller()
        return True

    async def resume(self) -> bool:
        voice = self.voice
        if not voice or not voice.is_paused():
            return False
        self._play_started_at = time.monotonic()
        voice.resume()
        await self.refresh_controller()
        return True

    async def toggle_pause(self) -> str:
        if self.is_paused:
            await self.resume()
            return "resume"
        if self.is_playing:
            await self.pause()
            return "pause"
        return "noop"

    async def set_volume(self, volume: float) -> float:
        self.volume = min(max(volume, 0.0), 1.5)
        voice = self.voice
        if voice and voice.source and isinstance(voice.source, discord.PCMVolumeTransformer):
            voice.source.volume = self.volume
        await self.refresh_controller()
        return self.volume

    def bump_volume(self, delta: float) -> float:
        self.volume = min(max(self.volume + delta, 0.0), 1.5)
        voice = self.voice
        if voice and voice.source and isinstance(voice.source, discord.PCMVolumeTransformer):
            voice.source.volume = self.volume
        return self.volume

    async def cycle_loop(self) -> LoopMode:
        self.loop = self.loop.next()
        await self.refresh_controller()
        return self.loop

    async def toggle_shuffle(self) -> bool:
        self.shuffle_on_add = not self.shuffle_on_add
        if self.shuffle_on_add and self.queue:
            import random

            items = list(self.queue)
            random.shuffle(items)
            self.queue = deque(items)
        await self.refresh_controller()
        return self.shuffle_on_add

    async def clear_queue(self) -> int:
        async with self._lock:
            n = len(self.queue)
            self.queue.clear()
        await self.refresh_controller()
        return n

    async def remove_at(self, index: int) -> Track | None:
        async with self._lock:
            if index < 0 or index >= len(self.queue):
                return None
            items = list(self.queue)
            track = items.pop(index)
            self.queue = deque(items)
        await self.refresh_controller()
        return track

    async def jump_to(self, index: int) -> Track | None:
        async with self._lock:
            if index < 0 or index >= len(self.queue):
                return None
            items = list(self.queue)
            track = items[index]
            self.queue = deque(items[index:])
        self._skip_requested = True
        voice = self.voice
        if voice and (voice.is_playing() or voice.is_paused()):
            voice.stop()
        else:
            await self._play_next()
        return track

    async def disconnect(self) -> None:
        await self.stop()
        voice = self.voice
        if voice:
            await voice.disconnect(force=True)
        self._cancel_idle()
        self._stop_ui_loop()
        await self.refresh_controller(disabled=True)
        self.controller_message = None
        self.current = None

    def _arm_idle(self) -> None:
        self._cancel_idle()
        seconds = settings.idle_disconnect_seconds
        if seconds <= 0:
            return

        async def idle() -> None:
            try:
                await asyncio.sleep(seconds)
            except asyncio.CancelledError:
                return
            if self.is_playing or self.is_paused or self.queue or self.current:
                return
            log.info("Idle disconnect na serwerze %s", self.guild.id)
            voice = self.voice
            if voice:
                await voice.disconnect(force=True)
            await self.refresh_controller(disabled=True)

        self._idle_task = asyncio.create_task(idle())

    def _cancel_idle(self) -> None:
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
        self._idle_task = None

    def _start_ui_loop(self) -> None:
        if self._ui_task and not self._ui_task.done():
            return

        async def loop() -> None:
            try:
                while self.current and (self.is_playing or self.is_paused):
                    await asyncio.sleep(12)
                    if self.current:
                        await self.refresh_controller()
            except asyncio.CancelledError:
                return
            except Exception:  # noqa: BLE001
                log.exception("UI loop")

        self._ui_task = asyncio.create_task(loop())

    def _stop_ui_loop(self) -> None:
        if self._ui_task and not self._ui_task.done():
            self._ui_task.cancel()
        self._ui_task = None

    async def bind_controller(self, message: discord.Message) -> None:
        self.controller_message = message
        await self.refresh_controller()

    async def refresh_controller(self, *, disabled: bool = False) -> None:
        from bot.ui.player_view import PlayerView, build_player_embed

        message = self.controller_message
        if message is None:
            return
        embed = build_player_embed(self, disconnected=disabled and self.voice is None)
        view = PlayerView(self, disabled=disabled or self.voice is None)
        try:
            self.controller_message = await message.edit(embed=embed, view=view)
        except discord.HTTPException as exc:
            log.debug("Nie udało się odświeżyć panelu: %s", exc)

    async def ensure_controller(self, channel: discord.abc.Messageable | None) -> discord.Message | None:
        from bot.ui.player_view import PlayerView, build_player_embed

        if channel is None:
            return self.controller_message
        self.text_channel = channel  # type: ignore[assignment]
        embed = build_player_embed(self)
        view = PlayerView(self)
        if self.controller_message:
            try:
                msg = await self.controller_message.edit(embed=embed, view=view)
                self.controller_message = msg
                return msg
            except discord.HTTPException:
                self.controller_message = None
        msg = await channel.send(embed=embed, view=view)
        self.controller_message = msg
        return msg
