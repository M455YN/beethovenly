#!/usr/bin/env bash
# Refresh Netscape cookies.txt from a browser profile on the *host*.
# Point the output at the Docker/Portainer data volume so the bot picks it up
# without rebuilding the image or regenerating cookies by hand.
#
# Examples:
#   ./scripts/refresh-youtube-cookies.sh /data/compose/31/data/cookies.txt
#   COOKIES_FROM_BROWSER=chrome:~/.var/app/com.google.Chrome/ \
#     ./scripts/refresh-youtube-cookies.sh ./data/cookies.txt
#   COOKIES_FROM_BROWSER=firefox ./scripts/refresh-youtube-cookies.sh ./data/cookies.txt
#
# Cron (daily, while you're logged into YouTube in that browser):
#   15 8 * * * /path/to/beethovenly/scripts/refresh-youtube-cookies.sh /data/compose/31/data/cookies.txt

set -euo pipefail

OUT="${1:-${COOKIES_FILE:-./data/cookies.txt}}"
BROWSER="${COOKIES_FROM_BROWSER:-chrome}"

mkdir -p "$(dirname "$OUT")"

if command -v yt-dlp >/dev/null 2>&1; then
  YTDLP=(yt-dlp)
elif command -v python3 >/dev/null 2>&1; then
  YTDLP=(python3 -m yt_dlp)
else
  echo "Need yt-dlp or python3 -m yt_dlp on PATH" >&2
  exit 1
fi

echo "Exporting cookies from browser ($BROWSER) → $OUT"
"${YTDLP[@]}" --cookies-from-browser "$BROWSER" --cookies "$OUT" --skip-download --quiet \
  "https://www.youtube.com/" || \
  "${YTDLP[@]}" --cookies-from-browser "$BROWSER" --cookies "$OUT"

# Keep only YouTube-related rows so the file is smaller and less sensitive.
tmp="$(mktemp)"
{
  echo "# Netscape HTTP Cookie File"
  awk -F'\t' 'NF >= 7 && $1 !~ /^#/ && tolower($1) ~ /youtube\.com|google\.com/ { print }' "$OUT"
} >"$tmp"
mv "$tmp" "$OUT"
chmod 600 "$OUT" 2>/dev/null || true

yt_rows=$(grep -ci 'youtube\.com' "$OUT" || true)
echo "Wrote $OUT ($yt_rows youtube.com cookie rows)"
if [ "${yt_rows:-0}" -eq 0 ]; then
  echo "WARNING: no youtube.com cookies — log into YouTube in that browser and retry" >&2
  exit 2
fi
