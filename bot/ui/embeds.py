from __future__ import annotations

import discord

from bot.audio.player import GuildPlayer
from bot.audio.track import LoopMode
from bot.utils import format_duration, progress_slider, truncate

ACCENT_PLAY = 0x5EEAD4
ACCENT_PAUSE = 0xFBBF24
ACCENT_IDLE = 0x64748B
ACCENT_STOP = 0x1E293B

LOOP_LABELS = {
    LoopMode.OFF: "wyłączona",
    LoopMode.ONE: "jeden utwór",
    LoopMode.ALL: "cała kolejka",
}


def build_player_embed(player: GuildPlayer, *, disconnected: bool = False) -> discord.Embed:
    track = player.current
    if disconnected or player.voice is None:
        embed = discord.Embed(
            title="Beethovenly jest offline",
            description="Wejdź na kanał głosowy i użyj `/play`, żebym do Ciebie dołączył.",
            color=ACCENT_STOP,
        )
        embed.set_footer(text="mpv • yt-dlp • Discord Voice")
        return embed

    if track is None:
        embed = discord.Embed(
            title="Kolejka jest pusta",
            description="Nic teraz nie leci. Wrzucaj link albo szukaj przez `/play`.",
            color=ACCENT_IDLE,
        )
        voice = player.voice
        if voice and voice.channel:
            embed.add_field(name="Kanał", value=voice.channel.mention, inline=True)
        embed.add_field(name="Głośność", value=f"{int(player.volume * 100)}%", inline=True)
        embed.add_field(name="Pętla", value=LOOP_LABELS[player.loop], inline=True)
        embed.set_footer(text="Panel sterowania zostaje tutaj — nie musisz pisać komend.")
        return embed

    paused = player.is_paused
    color = ACCENT_PAUSE if paused else ACCENT_PLAY
    status = "Wstrzymane" if paused else "Teraz leci"
    if track.is_live:
        status = "Na żywo"

    title = truncate(track.display_title, 240)
    embed = discord.Embed(
        title=f"{status}",
        description=f"**[{title}]({track.webpage_url})**\n{truncate(track.uploader, 120)}",
        color=color,
        url=track.webpage_url,
    )
    if track.thumbnail:
        embed.set_thumbnail(url=track.thumbnail)

    pos = player.position
    duration = track.duration
    slider = progress_slider(pos, duration)
    time_line = f"`{format_duration(pos)} / {'na żywo' if track.is_live else format_duration(duration)}`"
    embed.add_field(name="Postęp", value=f"{slider}\n{time_line}", inline=False)

    upcoming = player.queue_snapshot()
    next_line = "—"
    if upcoming:
        nxt = upcoming[0]
        next_line = truncate(nxt.display_title, 60)

    embed.add_field(name="Dalej", value=next_line, inline=True)
    embed.add_field(name="Kolejka", value=str(len(upcoming)), inline=True)
    embed.add_field(name="Głośność", value=f"{int(player.volume * 100)}%", inline=True)
    embed.add_field(name="Pętla", value=f"{player.loop.emoji()} {LOOP_LABELS[player.loop]}", inline=True)
    embed.add_field(name="Losowo", value="wł" if player.shuffle_on_add else "wył", inline=True)
    embed.add_field(name="Dodał", value=f"<@{track.requester_id}>", inline=True)

    voice = player.voice
    footer_bits = ["mpv + yt-dlp"]
    if voice and voice.channel:
        footer_bits.append(f"#{voice.channel.name}")
    embed.set_footer(text=" • ".join(footer_bits))
    return embed


def build_queue_embed(player: GuildPlayer) -> discord.Embed:
    tracks = player.queue_snapshot()
    embed = discord.Embed(title="Kolejka", color=ACCENT_PLAY)
    if player.current:
        embed.add_field(
            name="Teraz",
            value=truncate(f"{player.current.display_title}", 90),
            inline=False,
        )
    if not tracks:
        embed.description = "Kolejka jest pusta."
        return embed

    lines: list[str] = []
    total = 0.0
    for i, track in enumerate(tracks[:10], start=1):
        dur = format_duration(track.duration)
        lines.append(f"`{i}.` [{truncate(track.display_title, 48)}]({track.webpage_url}) · `{dur}`")
        if track.duration:
            total += track.duration
    extra = len(tracks) - min(len(tracks), 10)
    body = "\n".join(lines)
    if extra > 0:
        body += f"\n…i jeszcze **{extra}**"
    embed.description = body
    embed.set_footer(text=f"{len(tracks)} utworów · ~{format_duration(total)} przed Tobą")
    return embed
