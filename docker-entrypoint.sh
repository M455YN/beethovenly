#!/bin/sh
set -eu

if [ "${SKIP_YTDLP_UPDATE:-0}" != "1" ]; then
  echo "Aktualizacja yt-dlp…"
  pip install --user -U yt-dlp || echo "Nie udało się zaktualizować yt-dlp — jadę na wersji z obrazu."
fi

exec python -m bot
