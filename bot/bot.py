from __future__ import annotations

import logging
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
            log.info("YouTube cookies: %s", settings.cookies_file)
        else:
            log.warning(
                "YouTube cookies: OFF (set COOKIES_FILE=/app/data/cookies.txt and mount the file)"
            )


def create_bot() -> Beethovenly:
    return Beethovenly()
