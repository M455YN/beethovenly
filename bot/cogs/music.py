from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.audio.ytdlp import ExtractionError, extract_tracks
from bot.bot import Beethovenly
from bot.ui.embeds import build_queue_embed
from bot.ui.search_view import SearchView
from bot.utils import format_duration, truncate

log = logging.getLogger("beethovenly.music")


class Music(commands.Cog):
    def __init__(self, bot: Beethovenly) -> None:
        self.bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            raise app_commands.CheckFailure("Beethovenly działa tylko na serwerze.")
        return True

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        message = str(error) if isinstance(error, app_commands.CheckFailure) else "Coś poszło nie tak."
        if not isinstance(error, app_commands.CheckFailure):
            log.exception("Błąd komendy /%s", getattr(interaction.command, "name", "?"), exc_info=error)
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    def _member_channel(self, interaction: discord.Interaction) -> discord.VoiceChannel | discord.StageChannel | None:
        user = interaction.user
        if not isinstance(user, discord.Member) or not user.voice:
            return None
        return user.voice.channel

    async def _require_voice(self, interaction: discord.Interaction) -> discord.VoiceChannel | discord.StageChannel:
        channel = self._member_channel(interaction)
        if channel is None:
            raise app_commands.CheckFailure("Wejdź na kanał głosowy, żebym wiedział dokąd iść.")
        return channel

    @app_commands.command(name="play", description="Odtwórz utwór z YouTube / linku albo dodaj do kolejki")
    @app_commands.describe(query="Tytuł, link YouTube, SoundCloud, Bandcamp albo Spotify")
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        channel = await self._require_voice(interaction)
        await interaction.response.defer()
        try:
            tracks = await extract_tracks(query, requester=interaction.user, search_count=1)
        except ExtractionError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        player = self.bot.get_player(interaction.guild)
        await player.connect(channel)
        panel_channel = interaction.channel
        added = await player.enqueue(tracks, text_channel=panel_channel)
        if panel_channel is not None:
            await player.ensure_controller(panel_channel)

        if added == 1:
            track = tracks[0]
            await interaction.followup.send(
                f"**{truncate(track.display_title, 80)}** · `{format_duration(track.duration)}` · {track.uploader}",
            )
        else:
            await interaction.followup.send(f"Dodałem **{added}** utworów z playlisty.")

    @app_commands.command(name="search", description="Pokaż kilka wyników i wybierz z listy")
    @app_commands.describe(query="Czego szukamy")
    async def search(self, interaction: discord.Interaction, query: str) -> None:
        await self._require_voice(interaction)
        await interaction.response.defer(ephemeral=True)
        try:
            tracks = await extract_tracks(query, requester=interaction.user, search_count=8)
        except ExtractionError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        view = SearchView(tracks)
        lines = []
        for i, track in enumerate(tracks, start=1):
            lines.append(
                f"`{i}.` [{truncate(track.display_title, 70)}]({track.webpage_url}) · `{format_duration(track.duration)}`"
            )
        embed = discord.Embed(
            title=f"Wyniki: {truncate(query, 80)}",
            description="\n".join(lines),
            color=0x5EEAD4,
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="join", description="Dołącz na Twój kanał głosowy")
    async def join(self, interaction: discord.Interaction) -> None:
        channel = await self._require_voice(interaction)
        player = self.bot.get_player(interaction.guild)
        await player.connect(channel)
        await player.ensure_controller(interaction.channel)
        await interaction.response.send_message(f"Wchodzę na {channel.mention}.")

    @app_commands.command(name="leave", description="Wyjdź z kanału głosowego")
    async def leave(self, interaction: discord.Interaction) -> None:
        player = self.bot.get_player(interaction.guild)
        if player.voice is None:
            await interaction.response.send_message("I tak nigdzie nie siedziałem.", ephemeral=True)
            return
        await player.disconnect()
        await interaction.response.send_message("Wychodzę. Do usłyszenia.")

    @app_commands.command(name="skip", description="Pomiń aktualny utwór")
    async def skip(self, interaction: discord.Interaction) -> None:
        player = self.bot.get_player(interaction.guild)
        track = await player.skip()
        if track is None:
            await interaction.response.send_message("Nic nie leci.", ephemeral=True)
            return
        await interaction.response.send_message(f"Pomijam **{truncate(track.display_title, 80)}**.")

    @app_commands.command(name="pause", description="Pauza / wznów")
    async def pause(self, interaction: discord.Interaction) -> None:
        player = self.bot.get_player(interaction.guild)
        state = await player.toggle_pause()
        labels = {"pause": "Pauza.", "resume": "Lecimy dalej.", "noop": "Nie mam czego pauzować."}
        await interaction.response.send_message(labels[state], ephemeral=state == "noop")

    @app_commands.command(name="stop", description="Zatrzymaj i wyczyść kolejkę")
    async def stop(self, interaction: discord.Interaction) -> None:
        player = self.bot.get_player(interaction.guild)
        await player.stop()
        await interaction.response.send_message("Stop. Kolejka wyczyszczona.")

    @app_commands.command(name="queue", description="Pokaż kolejkę")
    async def queue(self, interaction: discord.Interaction) -> None:
        player = self.bot.get_player(interaction.guild)
        await interaction.response.send_message(embed=build_queue_embed(player), ephemeral=True)

    @app_commands.command(name="nowplaying", description="Pokaż / odśwież panel sterowania")
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        player = self.bot.get_player(interaction.guild)
        await player.ensure_controller(interaction.channel)
        await interaction.response.send_message("Panel jest na kanale.", ephemeral=True)

    @app_commands.command(name="volume", description="Ustaw głośność (0–150)")
    @app_commands.describe(percent="Procent głośności")
    async def volume(self, interaction: discord.Interaction, percent: app_commands.Range[int, 0, 150]) -> None:
        player = self.bot.get_player(interaction.guild)
        vol = await player.set_volume(percent / 100)
        await interaction.response.send_message(f"Głośność: **{int(vol * 100)}%**")

    @app_commands.command(name="shuffle", description="Przetasuj kolejkę")
    async def shuffle(self, interaction: discord.Interaction) -> None:
        player = self.bot.get_player(interaction.guild)
        on = await player.toggle_shuffle()
        await interaction.response.send_message("Losowo: **włączone**." if on else "Losowo: **wyłączone**.")

    @app_commands.command(name="loop", description="Przełącz pętlę: wył → kolejka → utwór")
    async def loop(self, interaction: discord.Interaction) -> None:
        player = self.bot.get_player(interaction.guild)
        mode = await player.cycle_loop()
        await interaction.response.send_message(f"Pętla: **{mode.label()}**")

    @app_commands.command(name="remove", description="Usuń utwór z kolejki po numerze")
    @app_commands.describe(numer="Numer z /queue (od 1)")
    async def remove(self, interaction: discord.Interaction, numer: app_commands.Range[int, 1, 200]) -> None:
        player = self.bot.get_player(interaction.guild)
        track = await player.remove_at(numer - 1)
        if track is None:
            await interaction.response.send_message("Nie ma takiego numeru w kolejce.", ephemeral=True)
            return
        await interaction.response.send_message(f"Wyrzuciłem **{truncate(track.display_title, 80)}**.")

    @app_commands.command(name="clear", description="Wyczyść kolejkę (aktualny utwór zostaje)")
    async def clear(self, interaction: discord.Interaction) -> None:
        player = self.bot.get_player(interaction.guild)
        n = await player.clear_queue()
        await interaction.response.send_message(f"Wyrzuciłem {n} utworów z kolejki.")

    @app_commands.command(name="help", description="Jak sterować Beethovenly")
    async def help(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Beethovenly — odtwarzacz na Discorda",
            description=(
                "Bot wchodzi na voice, ciągnie dźwięk przez **yt-dlp** i dekoduje go **mpv**.\n"
                "Na czacie zostaje panel z przyciskami — pauza, skip, głośność, pętla, kolejka."
            ),
            color=0x5EEAD4,
        )
        embed.add_field(
            name="Start",
            value="Wejdź na kanał głosowy i wpisz `/play despacito` albo wklej link.",
            inline=False,
        )
        embed.add_field(
            name="Komendy",
            value=(
                "`/play` `/search` `/skip` `/pause` `/stop`\n"
                "`/queue` `/nowplaying` `/volume` `/loop` `/shuffle`\n"
                "`/join` `/leave` `/remove` `/clear`"
            ),
            inline=False,
        )
        embed.add_field(
            name="Źródła",
            value="YouTube, SoundCloud, Bandcamp, bezpośrednie linki audio. Spotify → szuka odpowiednika na YT.",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.id == self.bot.user.id and after.channel is None:
            player = self.bot.players.get(member.guild.id)
            if player:
                player.current = None
                await player.refresh_controller(disabled=True)


async def setup(bot: Beethovenly) -> None:
    await bot.add_cog(Music(bot))
