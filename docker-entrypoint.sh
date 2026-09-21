#!/bin/sh
set -eu

if [ "${SKIP_YTDLP_UPDATE:-0}" != "1" ]; then
  echo "Aktualizacja yt-dlp…"
  pip install --user -U yt-dlp || echo "Nie udało się zaktualizować yt-dlp — jadę na wersji z obrazu."
fi

# Dump browser cookies → Netscape file once per container start.
COOKIES_OUT="${COOKIES_FILE:-/app/data/cookies.txt}"
CHROMIUM_COOKIES_DB="/chrome-profile/.config/chromium/Default/Cookies"

if [ -n "${COOKIES_FROM_BROWSER:-}" ]; then
  mkdir -p "$(dirname "$COOKIES_OUT")"
  if [ ! -f "$CHROMIUM_COOKIES_DB" ]; then
    echo "WARN: brak profilu Chromium ($CHROMIUM_COOKIES_DB)."
    echo "      Po VNC/SSH na host: http://127.0.0.1:3000 → YouTube login → restart beethovenly."
  else
    echo "Odświeżanie cookies z przeglądarki ($COOKIES_FROM_BROWSER) → $COOKIES_OUT"
    if python -m yt_dlp --cookies-from-browser "$COOKIES_FROM_BROWSER" --cookies "$COOKIES_OUT" \
        --skip-download --quiet "https://www.youtube.com/"; then
      echo "Cookies zapisane."
    else
      echo "WARN: cookies-from-browser nie zadziałało."
      echo "      Sprawdź logowanie na YouTube w Chromium (port 3000) i czy CHROME_CLI ma --password-store=basic."
    fi
  fi
  export COOKIES_FILE="$COOKIES_OUT"
fi

exec python -m bot
