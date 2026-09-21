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

### Portainer

1. **Stacks** → **Add stack** → **Repository**: `https://github.com/M455YN/beethovenly.git`, compose path `docker-compose.yml`.
2. In **Environment variables**, add at least `DISCORD_TOKEN` (same names as `.env.example`).
3. Redeploy the stack. Chromium UI is bound to **localhost only** (`127.0.0.1:3000`). Connect to the server over VNC (or SSH), open `http://127.0.0.1:3000` on the host, log into YouTube once, then restart `beethovenly` so it dumps cookies.
4. Compose uses `network_mode: host` on the bot (Linux) so Discord Voice UDP works. To expose Chromium on the LAN (not recommended), set `CHROMIUM_BIND=0.0.0.0`.

If audio still fails, check container logs for `yt-dlp:` / `mpv:` / `Cookies` lines and re-login in Chromium.

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
| `COOKIES_FILE` | `/app/data/cookies.txt` (auto-filled from stack Chromium) |
| `COOKIES_FROM_BROWSER` | default: `chromium+basictext:/chrome-profile/.config/chromium` |
| `CHROMIUM_BIND` | address for Chromium UI (default `127.0.0.1` = VNC/localhost only) |
| `CHROMIUM_HTTP_PORT` / `CHROMIUM_HTTPS_PORT` | Chromium web UI ports (default `3000` / `3001`) |
| `CHROMIUM_USER` / `CHROMIUM_PASSWORD` | optional basic auth for the Chromium UI |
| `SKIP_YTDLP_UPDATE` | `1` = do not update yt-dlp on container start |

### GitHub Secrets

1. Open [repository secrets](https://github.com/M455YN/beethovenly/settings/secrets/actions).
2. Add `DISCORD_TOKEN` (required) and optionally `COMMAND_GUILD_ID`.
3. Register a [self-hosted runner](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/adding-self-hosted-runners) on the machine that should run Docker, then push to `main` or run **Deploy** manually.

### YouTube cookies (stack Chromium)

Compose runs a **Chromium** sidecar (`lscr.io/linuxserver/chromium`) with a persistent profile. The bot dumps cookies from that profile into `COOKIES_FILE` on every start (`COOKIES_FROM_BROWSER` is set in compose — you do not need a host cron).

1. Deploy the stack.
2. Connect to the server with VNC (or SSH). On the host open `http://127.0.0.1:3000` → log into YouTube. The UI is not published on the LAN (`CHROMIUM_BIND=127.0.0.1`).
3. Restart container `beethovenly` (entrypoint refreshes `cookies.txt`).
4. Optional: still set `CHROMIUM_USER` / `CHROMIUM_PASSWORD` for extra protection.

Use a throwaway Google account if possible — cookies are powerful credentials.

**Fallback (host browser / cron):** `scripts/refresh-youtube-cookies.sh` can still write into the stack data volume if you prefer not to use the sidecar.## No audio?

Compose already sets `network_mode: host` on Linux so Discord Voice UDP works. Also confirm the bot has Speak / Connect and is not server-muted.

If the bot shows an offline panel and logs `WebSocket closed with 4006`, update voice deps:

```bash
.venv/bin/python -m pip install -U 'discord.py[voice]==2.7.1'
```

If tracks skip immediately, check logs for YouTube bot-checks and refresh `COOKIES_FILE`.

## Commands

`/play` `/search` `/join` `/leave` `/skip` `/pause` `/stop` `/queue` `/nowplaying` `/volume` `/shuffle` `/loop` `/remove` `/clear` `/playlist` `/help`

Most controls are on the panel — slash commands are a fallback.

## How playback works

```
/play  →  yt-dlp (metadata)
       →  yt-dlp -o - | mpv -   (stream + decode to PCM s16le 48 kHz stereo)
       →  discord.py sends frames to Voice
```

There is no ffmpeg in the playback pipeline. `yt-dlp` is updated on container start because YouTube breaks often. The image includes **Deno** and `yt-dlp[default]` (EJS) so logged-in cookies can solve YouTube JS challenges.

## Tests

```bash
pip install -r requirements.txt
python -m pytest -q
```
