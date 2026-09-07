from __future__ import annotations

import discord

from bot.audio.player import GuildPlayer
from bot.ui.embeds import build_player_embed, build_queue_embed


def _same_voice(interaction: discord.Interaction, player: GuildPlayer) -> str | None:
    if interaction.user is None or not isinstance(interaction.user, discord.Member):
        return "Te przyciski działają tylko na serwerze."
    voice = player.voice
    user_voice = interaction.user.voice
    if voice is None or voice.channel is None:
        return "Nie siedzę na kanale głosowym."
    if user_voice is None or user_voice.channel is None:
        return "Najpierw wejdź na kanał głosowy."
    if user_voice.channel.id != voice.channel.id:
        return f"Musisz być na {voice.channel.mention}."
    return None


class PlayerView(discord.ui.View):
    def __init__(self, player: GuildPlayer, *, disabled: bool = False) -> None:
        super().__init__(timeout=None)
        self.player = player
        paused = player.is_paused
        playing = player.is_playing
        empty = player.current is None and not player.queue

        self.playpause.label = "Wznów" if paused else "Pauza"
        self.playpause.emoji = "▶️" if paused else "⏸️"
        self.playpause.disabled = disabled or (not playing and not paused)

        self.prev.disabled = disabled or not player.history
        self.skip.disabled = disabled or player.current is None
        self.stop.disabled = disabled or empty
        self.loop.label = f"Pętla · {player.loop.label()}"
        self.loop.emoji = player.loop.emoji()
        self.loop.disabled = disabled

        self.shuffle.style = (
            discord.ButtonStyle.success if player.shuffle_on_add else discord.ButtonStyle.secondary
        )
        self.shuffle.disabled = disabled
        self.vol_down.disabled = disabled or player.volume <= 0.0
        self.vol_up.disabled = disabled or player.volume >= 1.5
        self.queue_btn.disabled = disabled
        self.leave.disabled = disabled

        self.jump.options = self._jump_options()
        self.jump.disabled = disabled or not player.queue
        self.jump.placeholder = "Skocz do utworu z kolejki…" if player.queue else "Kolejka jest pusta"

        if disabled:
            for item in self.children:
                item.disabled = True

    def _jump_options(self) -> list[discord.SelectOption]:
        options: list[discord.SelectOption] = []
        for i, track in enumerate(self.player.queue_snapshot()[:25]):
            options.append(
                discord.SelectOption(
                    label=track.to_choice_label(i + 1),
                    description=track.uploader[:100],
                    value=str(i),
                )
            )
        if not options:
            options.append(discord.SelectOption(label="Brak utworów", value="none"))
        return options

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        error = _same_voice(interaction, self.player)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return False
        return True

    async def _ack(self, interaction: discord.Interaction) -> None:
        embed = build_player_embed(self.player)
        view = PlayerView(self.player)
        await interaction.response.edit_message(embed=embed, view=view)
        self.player.controller_message = interaction.message

    @discord.ui.button(label="Poprzedni", emoji="⏮️", style=discord.ButtonStyle.secondary, row=0)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        track = await self.player.previous()
        await self._ack(interaction)
        if track is None:
            await interaction.followup.send("Nie mam nic wcześniejszego.", ephemeral=True)

    @discord.ui.button(label="Pauza", emoji="⏸️", style=discord.ButtonStyle.primary, row=0)
    async def playpause(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.player.toggle_pause()
        await self._ack(interaction)

    @discord.ui.button(label="Pomiń", emoji="⏭️", style=discord.ButtonStyle.secondary, row=0)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.player.skip()
        await self._ack(interaction)

    @discord.ui.button(label="Stop", emoji="⏹️", style=discord.ButtonStyle.danger, row=0)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.player.stop()
        await self._ack(interaction)

    @discord.ui.button(label="Pętla", emoji="🔁", style=discord.ButtonStyle.secondary, row=0)
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        mode = await self.player.cycle_loop()
        await self._ack(interaction)
        await interaction.followup.send(f"Pętla: **{mode.label()}**", ephemeral=True)

    @discord.ui.button(label="Losowo", emoji="🔀", style=discord.ButtonStyle.secondary, row=1)
    async def shuffle(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        on = await self.player.toggle_shuffle()
        await self._ack(interaction)
        await interaction.followup.send("Losowa kolejka włączona." if on else "Losowa kolejka wyłączona.", ephemeral=True)

    @discord.ui.button(label="Ciszej", emoji="🔉", style=discord.ButtonStyle.secondary, row=1)
    async def vol_down(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.player.bump_volume(-0.1)
        await self._ack(interaction)

    @discord.ui.button(label="Głośniej", emoji="🔊", style=discord.ButtonStyle.secondary, row=1)
    async def vol_up(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.player.bump_volume(0.1)
        await self._ack(interaction)

    @discord.ui.button(label="Kolejka", emoji="📜", style=discord.ButtonStyle.secondary, row=1)
    async def queue_btn(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message(embed=build_queue_embed(self.player), ephemeral=True)

    @discord.ui.button(label="Wyjdź", emoji="⏏", style=discord.ButtonStyle.danger, row=1)
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self.player.disconnect()
        embed = build_player_embed(self.player, disconnected=True)
        view = PlayerView(self.player, disabled=True)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.select(placeholder="Skocz do utworu z kolejki…", min_values=1, max_values=1, row=2)
    async def jump(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        value = select.values[0]
        if value == "none":
            await interaction.response.send_message("Kolejka jest pusta.", ephemeral=True)
            return
        track = await self.player.jump_to(int(value))
        await self._ack(interaction)
        if track:
            await interaction.followup.send(f"Skaczę do **{track.display_title}**", ephemeral=True)
