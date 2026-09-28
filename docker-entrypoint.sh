#!/bin/sh
set -eu

if [ "${SKIP_YTDLP_UPDATE:-0}" != "1" ]; then
  echo "Aktualizacja yt-dlp (+ ejs + pot plugin)…"
  pip install --user -U "yt-dlp[default]" bgutil-ytdlp-pot-provider \
    || echo "Nie udało się zaktualizować yt-dlp — jadę na wersji z obrazu."
fi

if command -v deno >/dev/null 2>&1; then
  echo "Deno JS runtime: $(deno --version | head -n 1)"
else
  echo "INFO: brak deno — OK dla mpv+ytdl / anon; potrzebny tylko przy cookies/web clients."
fi

COOKIES_OUT="${COOKIES_FILE:-/app/data/cookies.txt}"

# Find Chromium user-data dir under the shared volume (layout varies by image/version).
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
      case "$db" in
        */Default/Network/Cookies) dirname "$(dirname "$(dirname "$db")")" ;;
        */Default/Cookies) dirname "$(dirname "$db")" ;;
      esac
      return 0
    fi
  done
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

cookies_look_logged_in() {
  f="$1"
  [ -f "$f" ] || return 1
  # LOGIN_INFO or __Secure-1PSID ≈ logged-in YouTube session
  grep -qiE '(^|\t)LOGIN_INFO($|\t)|__Secure-1PSID' "$f"
}

# Optional cookie dump — only when COOKIES_FROM_BROWSER is explicitly set.
# Default compose leaves it empty so playback uses mpv+ytdl / anon (Wagner-style).
# Correct one-shot flow (yt-dlp wiki) when you DO need cookies:
#   1) docker compose --profile cookies up -d
#   2) VNC → http://127.0.0.1:3000 → YouTube login → robots.txt only
#   3) Set COOKIES_FROM_BROWSER + COOKIES_REFRESH=1, restart beethovenly once
if [ -n "${COOKIES_FROM_BROWSER:-}" ]; then
  mkdir -p "$(dirname "$COOKIES_OUT")"
  profile="$(find_chromium_profile /chrome-profile || true)"
  need_refresh=0
  if [ "${COOKIES_REFRESH:-0}" = "1" ]; then
    need_refresh=1
    echo "COOKIES_REFRESH=1 — wymuszam dump z Chromium."
  elif [ ! -f "$COOKIES_OUT" ]; then
    need_refresh=1
    echo "Brak $COOKIES_OUT — dump z Chromium."
  elif ! cookies_look_logged_in "$COOKIES_OUT"; then
    need_refresh=1
    echo "Cookies bez sesji logowania — dump z Chromium."
  else
    echo "Zostawiam istniejące cookies ($COOKIES_OUT)."
  fi

  if [ "$need_refresh" -eq 1 ]; then
    if [ -z "$profile" ]; then
      echo "WARN: brak profilu Chromium pod /chrome-profile."
      echo "      docker compose --profile cookies up -d → login → robots.txt → COOKIES_REFRESH=1."
    else
      export COOKIES_FROM_BROWSER="chromium+basictext:${profile}"
      tmp="${COOKIES_OUT}.new"
      log="${COOKIES_OUT}.dump.log"
      echo "Dump cookies z $COOKIES_FROM_BROWSER (URL=robots.txt)…"
      set +e
      python -m yt_dlp --cookies-from-browser "$COOKIES_FROM_BROWSER" --cookies "$tmp" \
        --skip-download "https://www.youtube.com/robots.txt" >"$log" 2>&1
      rc=$?
      set -e
      if [ "$rc" -ne 0 ] || [ ! -f "$tmp" ]; then
        echo "WARN: dump nieudany (rc=$rc) — jadę bez cookies."
        tail -n 20 "$log" 2>/dev/null || true
        rm -f "$tmp"
      elif grep -qi 'no longer valid\|cookies are no longer valid' "$log"; then
        echo "WARN: cookies z przeglądarki nieważne — jadę bez cookies."
        tail -n 5 "$log" || true
        rm -f "$tmp"
      else
        mv "$tmp" "$COOKIES_OUT"
        yt_n="$(grep -ci 'youtube\.com' "$COOKIES_OUT" 2>/dev/null || echo 0)"
        echo "Cookies zapisane ($yt_n youtube.com rows)."
        export COOKIES_FILE="$COOKIES_OUT"
      fi
      rm -f "$log"
    fi
  else
    export COOKIES_FILE="$COOKIES_OUT"
  fi
elif [ -n "${COOKIES_FILE:-}" ] && [ -f "${COOKIES_FILE}" ]; then
  echo "Używam COOKIES_FILE=${COOKIES_FILE} (opcjonalny fallback)."
else
  echo "Cookies wyłączone (domyślnie) — pot-provider + anon clients."
fi

exec python -m bot
