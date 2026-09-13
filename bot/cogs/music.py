from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.audio.track import Track
from bot.audio.ytdlp import ExtractionError, extract_tracks
from bot.bot import Beethovenly
from bot.config import settings
from bot.storage.playlists import (
    PlaylistError,
    append_tracks,
    create_playlist,
    delete_playlist,
    list_playlists,
    load_playlist,
    save_playlist,
)
from bot.ui.embeds import build_queue_embed
from bot.ui.search_view import SearchView
from bot.utils import format_duration, truncate

log = logging.getLogger("beethovenly.music")


class Music(commands.Cog):
    playlist = app_commands.Group(name="playlist", description="Create and play saved playlists")

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

    @app_commands.command(name="play", description="Play a track from YouTube / a URL, or add it to the queue")
    @app_commands.describe(query="Title or YouTube, SoundCloud, Bandcamp, or Spotify link")
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        channel = await self._require_voice(interaction)
        await interaction.response.defer(ephemeral=True)
        try:
            tracks = await extract_tracks(query, requester=interaction.user, search_count=1)
        except ExtractionError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        player = self.bot.get_player(interaction.guild)
        try:
            await player.connect(channel)
        except Exception:
            log.exception("Voice connect failed in /play")
            await interaction.followup.send(
                "Could not join voice (Discord closed the connection). "
                "Make sure the bot has **Connect** + **Speak**, then try `/play` again.",
                ephemeral=True,
            )
            return
        panel_channel = interaction.channel
        added = await player.enqueue(tracks, text_channel=panel_channel)
        if panel_channel is not None:
            await player.ensure_controller(panel_channel)

        if added == 1:
            track = tracks[0]
            await interaction.followup.send(
                f"**{truncate(track.display_title, 80)}** · `{format_duration(track.duration)}` · {track.uploader}",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(f"Dodałem **{added}** utworów z playlisty.", ephemeral=True)

    @app_commands.command(name="search", description="Show search results and pick from a list")
    @app_commands.describe(query="What to search for")
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

    @app_commands.command(name="join", description="Join your voice channel")
    async def join(self, interaction: discord.Interaction) -> None:
        channel = await self._require_voice(interaction)
        player = self.bot.get_player(interaction.guild)
        await player.connect(channel)
        await player.ensure_controller(interaction.channel)
        await interaction.response.send_message(f"Joined {channel.mention}.", ephemeral=True)

    @app_commands.command(name="leave", description="Leave the voice channel")
    async def leave(self, interaction: discord.Interaction) -> None:
        player = self.bot.get_player(interaction.guild)
        if player.voice is None:
            await interaction.response.send_message("I'm not in a voice channel.", ephemeral=True)
            return
        await player.disconnect()
        await interaction.response.send_message("Left voice.", ephemeral=True)

    @app_commands.command(name="skip", description="Skip the current track")
    async def skip(self, interaction: discord.Interaction) -> None:
        player = self.bot.get_player(interaction.guild)
        track = await player.skip()
        if track is None:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        await player.refresh_controller()
        await interaction.response.send_message(
            f"Skipped **{truncate(track.display_title, 80)}**.",
            ephemeral=True,
        )

    @app_commands.command(name="pause", description="Pause / resume playback")
    async def pause(self, interaction: discord.Interaction) -> None:
        player = self.bot.get_player(interaction.guild)
        state = await player.toggle_pause()
        labels = {"pause": "Paused.", "resume": "Resumed.", "noop": "Nothing to pause."}
        await player.refresh_controller()
        await interaction.response.send_message(labels[state], ephemeral=True)

    @app_commands.command(name="stop", description="Stop playback and clear the queue")
    async def stop(self, interaction: discord.Interaction) -> None:
        player = self.bot.get_player(interaction.guild)
        await player.stop()
        await interaction.response.send_message("Stopped. Queue cleared.", ephemeral=True)

    @app_commands.command(name="queue", description="Show the queue")
    async def queue(self, interaction: discord.Interaction) -> None:
        player = self.bot.get_player(interaction.guild)
        await interaction.response.send_message(embed=build_queue_embed(player), ephemeral=True)

    @app_commands.command(name="nowplaying", description="Show / refresh the control panel")
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        player = self.bot.get_player(interaction.guild)
        await player.ensure_controller(interaction.channel)
        await interaction.response.send_message("Panel refreshed.", ephemeral=True)

    @app_commands.command(name="volume", description="Set volume (0–150)")
    @app_commands.describe(percent="Volume percent")
    async def volume(self, interaction: discord.Interaction, percent: app_commands.Range[int, 0, 150]) -> None:
        player = self.bot.get_player(interaction.guild)
        vol = await player.set_volume(percent / 100)
        await interaction.response.send_message(f"Volume: **{int(vol * 100)}%**", ephemeral=True)

    @app_commands.command(name="shuffle", description="Shuffle the queue")
    async def shuffle(self, interaction: discord.Interaction) -> None:
        player = self.bot.get_player(interaction.guild)
        on = await player.toggle_shuffle()
        await interaction.response.send_message(
            "Shuffle **on**." if on else "Shuffle **off**.",
            ephemeral=True,
        )

    @app_commands.command(name="loop", description="Cycle loop: off → queue → track")
    async def loop(self, interaction: discord.Interaction) -> None:
        player = self.bot.get_player(interaction.guild)
        mode = await player.cycle_loop()
        await interaction.response.send_message(f"Loop: **{mode.label()}**", ephemeral=True)

    @app_commands.command(name="remove", description="Remove a track from the queue by number")
    @app_commands.describe(numer="Number from /queue (starting at 1)")
    async def remove(self, interaction: discord.Interaction, numer: app_commands.Range[int, 1, 200]) -> None:
        player = self.bot.get_player(interaction.guild)
        track = await player.remove_at(numer - 1)
        if track is None:
            await interaction.response.send_message("No track with that number.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Removed **{truncate(track.display_title, 80)}**.",
            ephemeral=True,
        )

    @app_commands.command(name="clear", description="Clear the queue (current track keeps playing)")
    async def clear(self, interaction: discord.Interaction) -> None:
        player = self.bot.get_player(interaction.guild)
        n = await player.clear_queue()
        await interaction.response.send_message(f"Cleared {n} queued tracks.", ephemeral=True)

    def _queue_tracks_for_save(self, player) -> list[Track]:
        tracks: list[Track] = []
        if player.current is not None:
            tracks.append(player.current)
        tracks.extend(player.queue_snapshot())
        return tracks[: settings.playlist_limit]

    @playlist.command(name="create", description="Create an empty playlist")
    @app_commands.describe(name="Playlist name")
    async def playlist_create(self, interaction: discord.Interaction, name: str) -> None:
        assert interaction.guild is not None
        try:
            saved = create_playlist(
                guild_id=interaction.guild.id,
                owner_id=interaction.user.id,
                name=name,
            )
        except PlaylistError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message(
            f"Utworzyłem playlistę **{saved.name}**. Dodawaj utwory przez `/playlist add` albo `/playlist save`."
        )

    @playlist.command(name="save", description="Save the current track + queue as a playlist")
    @app_commands.describe(name="Playlist name (overwrites if it exists)")
    async def playlist_save(self, interaction: discord.Interaction, name: str) -> None:
        assert interaction.guild is not None
        player = self.bot.get_player(interaction.guild)
        tracks = self._queue_tracks_for_save(player)
        try:
            saved = save_playlist(
                guild_id=interaction.guild.id,
                owner_id=interaction.user.id,
                name=name,
                tracks=tracks,
                overwrite=True,
            )
        except PlaylistError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message(
            f"Zapisano **{saved.name}** ({saved.track_count} utw.)."
        )

    @playlist.command(name="add", description="Add the current track (or a search) to a playlist")
    @app_commands.describe(name="Playlist name", query="Optional title / URL instead of the current track")
    async def playlist_add(
        self,
        interaction: discord.Interaction,
        name: str,
        query: str | None = None,
    ) -> None:
        assert interaction.guild is not None
        player = self.bot.get_player(interaction.guild)
        tracks: list[Track] = []
        if query:
            await interaction.response.defer(ephemeral=True)
            try:
                tracks = await extract_tracks(query, requester=interaction.user, search_count=1)
            except ExtractionError as exc:
                await interaction.followup.send(str(exc), ephemeral=True)
                return
        elif player.current is not None:
            tracks = [player.current]
        else:
            await interaction.response.send_message(
                "Nic nie leci. Podaj `query` albo odtwórz coś najpierw.",
                ephemeral=True,
            )
            return

        try:
            saved = append_tracks(
                interaction.guild.id,
                name,
                tracks,
                max_tracks=settings.playlist_limit,
            )
        except PlaylistError as exc:
            if interaction.response.is_done():
                await interaction.followup.send(str(exc), ephemeral=True)
            else:
                await interaction.response.send_message(str(exc), ephemeral=True)
            return

        msg = f"Dodałem do **{saved.name}** (teraz {saved.track_count} utw.)."
        if interaction.response.is_done():
            await interaction.followup.send(msg)
        else:
            await interaction.response.send_message(msg)

    @playlist.command(name="load", description="Load a playlist into the queue and play")
    @app_commands.describe(name="Playlist name")
    async def playlist_load(self, interaction: discord.Interaction, name: str) -> None:
        assert interaction.guild is not None
        channel = await self._require_voice(interaction)
        try:
            saved = load_playlist(interaction.guild.id, name)
        except PlaylistError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        if not saved.tracks:
            await interaction.response.send_message(
                f"Playlista **{saved.name}** jest pusta. Użyj `/playlist add` albo `/playlist save`.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        tracks = [
            Track.from_dict(item, requester=interaction.user)
            for item in saved.tracks[: settings.playlist_limit]
            if item.get("webpage_url")
        ]
        if not tracks:
            await interaction.followup.send("Playlista nie ma poprawnych linków.", ephemeral=True)
            return

        player = self.bot.get_player(interaction.guild)
        await player.connect(channel)
        panel_channel = interaction.channel
        added = await player.enqueue(tracks, text_channel=panel_channel)
        if panel_channel is not None:
            await player.ensure_controller(panel_channel)
        await interaction.followup.send(
            f"Wczytałem **{saved.name}** — dodałem **{added}** utw.",
            ephemeral=True,
        )

    @playlist.command(name="list", description="List saved playlists on this server")
    async def playlist_list(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        items = list_playlists(interaction.guild.id)
        if not items:
            await interaction.response.send_message(
                "Brak zapisanych playlist. Utwórz: `/playlist create` albo `/playlist save`.",
                ephemeral=True,
            )
            return
        lines = [f"• **{p.name}** — {p.track_count} utw." for p in items]
        embed = discord.Embed(
            title="Zapisane playlisty",
            description="\n".join(lines),
            color=0x5EEAD4,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @playlist.command(name="show", description="Show tracks in a playlist")
    @app_commands.describe(name="Playlist name")
    async def playlist_show(self, interaction: discord.Interaction, name: str) -> None:
        assert interaction.guild is not None
        try:
            saved = load_playlist(interaction.guild.id, name)
        except PlaylistError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        if not saved.tracks:
            await interaction.response.send_message(f"**{saved.name}** jest pusta.", ephemeral=True)
            return
        lines = []
        for i, item in enumerate(saved.tracks[:25], start=1):
            title = truncate(str(item.get("title") or "Nieznany utwór"), 70)
            url = item.get("webpage_url")
            dur = format_duration(item.get("duration"))  # type: ignore[arg-type]
            if url:
                lines.append(f"`{i}.` [{title}]({url}) · `{dur}`")
            else:
                lines.append(f"`{i}.` {title} · `{dur}`")
        extra = saved.track_count - len(lines)
        desc = "\n".join(lines)
        if extra > 0:
            desc += f"\n…i jeszcze {extra}."
        embed = discord.Embed(title=f"Playlista: {saved.name}", description=desc, color=0x5EEAD4)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @playlist.command(name="delete", description="Delete a saved playlist")
    @app_commands.describe(name="Playlist name")
    async def playlist_delete(self, interaction: discord.Interaction, name: str) -> None:
        assert interaction.guild is not None
        try:
            deleted = delete_playlist(interaction.guild.id, name)
        except PlaylistError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message(f"Usunąłem playlistę **{deleted}**.")

    @app_commands.command(name="help", description="How to use Beethovenly")
    async def help(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Beethovenly — Discord music player",
            description=(
                "The bot joins voice, pulls audio with **yt-dlp**, and decodes it with **mpv**.\n"
                "A button panel stays on the text channel for pause, skip, volume, loop, and queue."
            ),
            color=0x5EEAD4,
        )
        embed.add_field(
            name="Start",
            value="Join a voice channel and run `/play despacito` or paste a link.",
            inline=False,
        )
        embed.add_field(
            name="Commands",
            value=(
                "`/play` `/search` `/skip` `/pause` `/stop`\n"
                "`/queue` `/nowplaying` `/volume` `/loop` `/shuffle`\n"
                "`/join` `/leave` `/remove` `/clear`\n"
                "`/playlist create|save|add|load|list|show|delete`"
            ),
            inline=False,
        )
        embed.add_field(
            name="Sources",
            value="YouTube, SoundCloud, Bandcamp, direct audio URLs. Spotify → finds a YouTube match.",
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
