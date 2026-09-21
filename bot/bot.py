from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord.ext import commands

from bot.audio.player import GuildPlayer
from bot.config import settings

log = logging.getLogger("beethovenly")

INTENTS = discord.Intents.default()
INTENTS.guilds = True
INTENTS.voice_states = True
INTENTS.message_content = False


class Beethovenly(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix=commands.when_mentioned, intents=INTENTS, help_command=None)
        self.players: dict[int, GuildPlayer] = {}

    def get_player(self, guild: discord.Guild | None) -> GuildPlayer:
        if guild is None:
            raise commands.NoPrivateMessage("Beethovenly działa tylko na serwerze.")
        player = self.players.get(guild.id)
        if player is None:
            player = GuildPlayer(self, guild)
            self.players[guild.id] = player
        return player

    async def setup_hook(self) -> None:
        await self.load_extension("bot.cogs.music")
        if settings.command_guild_id:
            guild = discord.Object(id=settings.command_guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Zsynchronizowano %s komend na serwerze %s", len(synced), settings.command_guild_id)
        else:
            synced = await self.tree.sync()
            log.info("Zsynchronizowano %s komend globalnie (może zająć do godziny)", len(synced))

    async def on_ready(self) -> None:
        activity = discord.Activity(type=discord.ActivityType.listening, name=settings.bot_status)
        await self.change_presence(activity=activity)
        log.info("Zalogowany jako %s (%s)", self.user, self.user.id if self.user else "?")
        if settings.cookies_file:
            try:
                raw = Path(settings.cookies_file).read_text(encoding="utf-8", errors="replace")
                yt_lines = sum(
                    1
                    for line in raw.splitlines()
                    if line and not line.startswith("#") and "youtube.com" in line.lower()
                )
            except OSError:
                yt_lines = -1
            log.info("YouTube cookies: %s (%s youtube.com entries)", settings.cookies_file, yt_lines)
            if yt_lines == 0:
                log.warning(
                    "cookies file has no youtube.com rows — re-export while logged into YouTube"
                )
        elif settings.cookies_from_browser:
            log.info("YouTube cookies: from browser (%s)", settings.cookies_from_browser)
        else:
            log.warning(
                "YouTube cookies: OFF — set COOKIES_FILE=/app/data/cookies.txt "
                "or COOKIES_FROM_BROWSER=chrome (see README)"
            )


def create_bot() -> Beethovenly:
    return Beethovenly()
