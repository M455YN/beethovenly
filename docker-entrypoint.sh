#!/bin/sh
set -eu

if [ "${SKIP_YTDLP_UPDATE:-0}" != "1" ]; then
  echo "Aktualizacja yt-dlp…"
  pip install --user -U yt-dlp || echo "Nie udało się zaktualizować yt-dlp — jadę na wersji z obrazu."
fi

# Optional: dump browser cookies → Netscape file once per container start.
# Mount the browser profile into the container and set COOKIES_FROM_BROWSER
# (e.g. chrome:/chrome-profile or firefox:/firefox-profile). Prefer a host
# cron + scripts/refresh-youtube-cookies.sh when Chrome keyring blocks decrypt.
COOKIES_OUT="${COOKIES_FILE:-/app/data/cookies.txt}"
if [ -n "${COOKIES_FROM_BROWSER:-}" ]; then
  mkdir -p "$(dirname "$COOKIES_OUT")"
  echo "Odświeżanie cookies z przeglądarki ($COOKIES_FROM_BROWSER) → $COOKIES_OUT"
  if python -m yt_dlp --cookies-from-browser "$COOKIES_FROM_BROWSER" --cookies "$COOKIES_OUT" \
      --skip-download --quiet "https://www.youtube.com/"; then
    echo "Cookies zapisane."
  else
    echo "WARN: cookies-from-browser nie zadziałało (Chrome + keyring w Dockerze bywa zepsute)."
    echo "      Użyj Firefoxa albo crona na hoście: scripts/refresh-youtube-cookies.sh"
  fi
  export COOKIES_FILE="$COOKIES_OUT"
fi

exec python -m bot
