from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from bot.audio.track import Track
from bot.utils import format_duration, truncate

if TYPE_CHECKING:
    from bot.bot import Beethovenly


class SearchSelect(discord.ui.Select):
    def __init__(self, tracks: list[Track]) -> None:
        options = [
            discord.SelectOption(
                label=track.to_choice_label(i + 1),
                description=truncate(f"{track.uploader} · {format_duration(track.duration)}", 100),
                value=str(i),
            )
            for i, track in enumerate(tracks[:10])
        ]
        super().__init__(
            placeholder="Wybierz utwór do kolejki…",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.tracks = tracks

    async def callback(self, interaction: discord.Interaction) -> None:
        assert interaction.client
        bot: Beethovenly = interaction.client  # type: ignore[assignment]
        member = interaction.user
        if not isinstance(member, discord.Member) or not member.voice or not member.voice.channel:
            await interaction.response.send_message("Wejdź najpierw na kanał głosowy.", ephemeral=True)
            return
        index = int(self.values[0])
        track = self.tracks[index]
        player = bot.get_player(interaction.guild)
        await player.connect(member.voice.channel)
        await player.enqueue([track], text_channel=interaction.channel, play_now=False)
        await player.ensure_controller(interaction.channel)
        await interaction.response.edit_message(
            content=f"Dodałem **{track.display_title}** do kolejki.",
            view=None,
            embed=None,
        )


class SearchView(discord.ui.View):
    def __init__(self, tracks: list[Track]) -> None:
        super().__init__(timeout=60)
        self.add_item(SearchSelect(tracks))

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
