# Beethovenly

A Discord music bot that joins voice, pulls audio with **yt-dlp**, decodes it with **mpv**, and streams it to the voice channel. A button panel stays on the text channel for pause, skip, volume, loop, and queue.

## Quick start (Docker)

1. Create an application in the [Discord Developer Portal](https://discord.com/developers/applications).
2. Open the **Bot** tab → Reset Token → copy the token.
3. Message Content Intent is **not** required.
4. OAuth2 → URL Generator:
   - scopes: `bot`, `applications.commands`
   - permissions: View Channel, Send Messages, Embed Links, Read Message History, Connect, Speak
   - or use this invite link (replace `CLIENT_ID`):

```
https://discord.com/oauth2/authorize?client_id=CLIENT_ID&permissions=3230720&scope=bot%20applications.commands
```

5. In the project directory:

```bash
cp .env.example .env
# set DISCORD_TOKEN=...

# optional: sync slash commands to one guild immediately
# COMMAND_GUILD_ID=your_server_id

docker compose up -d --build
docker compose logs -f
```

Join a voice channel and run `/play never gonna give you up`. The control panel appears on the text channel.

## Features

- `/play` — URL or search (YouTube, SoundCloud, Bandcamp, plain audio URLs)
- Spotify links → finds a YouTube match (no Spotify API)
- playlists (capped by `PLAYLIST_LIMIT`)
- `/search` — clickable result list
- channel panel: ⏮️ pause ⏭️ stop 🔁 🔀 🔉 🔊 queue, plus a “jump to track” list
- loop modes: off / queue / one track
- leaves voice after idle silence (`IDLE_DISCONNECT_SECONDS`)

## Without Docker

You need Python 3.12+, `mpv`, `yt-dlp`, and `libopus`.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in the token
python -m bot
```

## Configuration

| Variable | Purpose |
|---|---|
| `DISCORD_TOKEN` | bot token (**required**) |
| `COMMAND_GUILD_ID` | sync slash commands to one guild (immediate) |
| `BOT_STATUS` | text shown in the “Listening to …” status |
| `IDLE_DISCONNECT_SECONDS` | leave voice after this many idle seconds (`0` = never) |
| `PLAYLIST_LIMIT` | max tracks from a playlist (1–200) |
| `COOKIES_FILE` | `/app/data/cookies.txt` when YouTube blocks or age-gates |
| `SKIP_YTDLP_UPDATE` | `1` = do not update yt-dlp on container start |

Cookies: export a `cookies.txt` (browser extension) and place it at `data/cookies.txt`. In `.env`:

```
COOKIES_FILE=/app/data/cookies.txt
```

## No audio?

On some hosts NAT breaks UDP to Discord Voice. In `docker-compose.yml`, uncomment:

```yaml
network_mode: host
```

(Linux). Also confirm the bot has Speak / Connect and is not server-muted.

## Commands

`/play` `/search` `/join` `/leave` `/skip` `/pause` `/stop` `/queue` `/nowplaying` `/volume` `/shuffle` `/loop` `/remove` `/clear` `/help`

Most controls are on the panel — slash commands are a fallback.

## How playback works

```
/play  →  yt-dlp (metadata + URL)
       →  mpv decodes to PCM s16le 48 kHz stereo on stdout
       →  discord.py sends frames to Voice
```

There is no ffmpeg in the playback pipeline. `yt-dlp` is updated on container start because YouTube breaks often.

## Tests

```bash
pip install -r requirements.txt
python -m pytest -q
```
