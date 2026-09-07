<p align="center">
  <img src="assets/beethovenly-logo.svg" alt="Beethovenly" width="160" height="160" />
</p>

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

5. Store secrets in GitHub (recommended):
   - Repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
   - Required: `DISCORD_TOKEN`
   - Optional: `COMMAND_GUILD_ID` (immediate slash-command sync on one guild)
6. Deploy with the included workflow (self-hosted runner with Docker), or run locally:

```bash
# Local fallback (do not commit .env)
cp .env.example .env
# set DISCORD_TOKEN=...
# optional: COMMAND_GUILD_ID=your_server_id

docker compose up -d --build
docker compose logs -f
```

On push to `main` (or via **Actions → Deploy → Run workflow**), GitHub Actions writes `.env` from those secrets and runs `docker compose up -d --build` on your self-hosted runner.

Join a voice channel and run `/play never gonna give you up`. The control panel appears on the text channel.

## Features

- `/play` — URL or search (YouTube, SoundCloud, Bandcamp, plain audio URLs)
- Spotify links → finds a YouTube match (no Spotify API)
- playlists (capped by `PLAYLIST_LIMIT`) — YouTube/external URLs via `/play`, plus saved server playlists via `/playlist`
- `/playlist create|save|add|load|list|show|delete` — create and reuse named playlists (stored under `data/playlists/`)
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

Use **GitHub Actions secrets** (same names) for deploy, or a local `.env` for manual runs.

| Variable / secret | Purpose |
|---|---|
| `DISCORD_TOKEN` | bot token (**required**) |
| `COMMAND_GUILD_ID` | sync slash commands to one guild (immediate) |
| `BOT_STATUS` | text shown in the “Listening to …” status |
| `IDLE_DISCONNECT_SECONDS` | leave voice after this many idle seconds (`0` = never) |
| `PLAYLIST_LIMIT` | max tracks from a playlist (1–200) |
| `COOKIES_FILE` | `/app/data/cookies.txt` when YouTube blocks or age-gates |
| `SKIP_YTDLP_UPDATE` | `1` = do not update yt-dlp on container start |

### GitHub Secrets

1. Open [repository secrets](https://github.com/M455YN/beethovenly/settings/secrets/actions).
2. Add `DISCORD_TOKEN` (required) and optionally `COMMAND_GUILD_ID`.
3. Register a [self-hosted runner](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/adding-self-hosted-runners) on the machine that should run Docker, then push to `main` or run **Deploy** manually.

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

`/play` `/search` `/join` `/leave` `/skip` `/pause` `/stop` `/queue` `/nowplaying` `/volume` `/shuffle` `/loop` `/remove` `/clear` `/playlist` `/help`

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
