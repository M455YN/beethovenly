#!/bin/sh
set -eu

if [ "${SKIP_YTDLP_UPDATE:-0}" != "1" ]; then
  echo "Aktualizacja yt-dlp (+ ejs)…"
  pip install --user -U "yt-dlp[default]" || echo "Nie udało się zaktualizować yt-dlp — jadę na wersji z obrazu."
fi

if command -v deno >/dev/null 2>&1; then
  echo "Deno JS runtime: $(deno --version | head -n 1)"
else
  echo "WARN: brak deno w PATH — YouTube z cookies może padać (The page needs to be reloaded)."
fi

COOKIES_OUT="${COOKIES_FILE:-/app/data/cookies.txt}"

# Find Chromium user-data dir under the shared volume (layout varies by image/version).
# Newer Chromium: Default/Network/Cookies ; older: Default/Cookies
find_chromium_profile() {
  root="${1:-/chrome-profile}"
  [ -d "$root" ] || return 1
  for db in \
    "$root/.config/chromium/Default/Network/Cookies" \
    "$root/.config/chromium/Default/Cookies" \
    "$root/chromium/Default/Network/Cookies" \
    "$root/chromium/Default/Cookies" \
    "$root/Default/Network/Cookies" \
    "$root/Default/Cookies"
  do
    if [ -f "$db" ]; then
      # user-data-dir is two levels above Default/.../Cookies or Default/Cookies
      case "$db" in
        */Default/Network/Cookies) dirname "$(dirname "$(dirname "$db")")" ;;
        */Default/Cookies) dirname "$(dirname "$db")" ;;
      esac
      return 0
    fi
  done
  # Last resort: any Cookies sqlite under the volume
  found="$(find "$root" -type f \( -path '*/Default/Network/Cookies' -o -path '*/Default/Cookies' \) 2>/dev/null | head -n 1 || true)"
  if [ -n "$found" ]; then
    case "$found" in
      */Default/Network/Cookies) dirname "$(dirname "$(dirname "$found")")" ;;
      */Default/Cookies) dirname "$(dirname "$found")" ;;
    esac
    return 0
  fi
  return 1
}

if [ -n "${COOKIES_FROM_BROWSER:-}" ]; then
  mkdir -p "$(dirname "$COOKIES_OUT")"
  profile="$(find_chromium_profile /chrome-profile || true)"
  if [ -z "$profile" ]; then
    echo "WARN: brak profilu Chromium pod /chrome-profile."
    echo "      1) Portainer: upewnij się, że kontener beethovenly-chromium działa"
    echo "      2) Po VNC: http://127.0.0.1:3000 → zaloguj YouTube"
    echo "      3) Restart beethovenly"
    if [ -f "$COOKIES_OUT" ]; then
      echo "WARN: używam starego $COOKIES_OUT (może być nieważny / bot-check)."
    fi
  else
    # Prefer auto-detected profile + basictext (matches CHROME_CLI --password-store=basic).
    export COOKIES_FROM_BROWSER="chromium+basictext:${profile}"
    echo "Odświeżanie cookies z $COOKIES_FROM_BROWSER → $COOKIES_OUT"
    if python -m yt_dlp --cookies-from-browser "$COOKIES_FROM_BROWSER" --cookies "$COOKIES_OUT" \
        --skip-download --quiet "https://www.youtube.com/"; then
      yt_n="$(grep -ci 'youtube\.com' "$COOKIES_OUT" 2>/dev/null || echo 0)"
      echo "Cookies zapisane ($yt_n youtube.com rows)."
      if [ "${yt_n:-0}" -eq 0 ]; then
        echo "WARN: brak youtube.com w dumpie — w Chromium (127.0.0.1:3000) zaloguj się na YouTube i zrestartuj bota."
      fi
    else
      echo "WARN: cookies-from-browser nie zadziałało (keyring/decrypt?)."
      echo "      Zaloguj YouTube w UI i upewnij się, że CHROME_CLI zawiera --password-store=basic."
    fi
  fi
  export COOKIES_FILE="$COOKIES_OUT"
fi

exec python -m bot
