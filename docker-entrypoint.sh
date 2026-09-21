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
  echo "WARN: brak deno w PATH — YouTube z cookies może padać (The page needs to be reloaded)."
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

# YouTube rotates cookies on open youtube.com tabs. Dumping from a live Chromium
# session often yields INVALID cookies. Only refresh when forced or missing.
# Correct one-shot flow (yt-dlp wiki):
#   1) VNC → http://127.0.0.1:3000
#   2) Log into YouTube
#   3) SAME tab → https://www.youtube.com/robots.txt  (leave only this tab)
#   4) Set COOKIES_REFRESH=1, restart beethovenly once
#   5) Do NOT open YouTube again in that Chromium profile
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
    echo "Zostawiam istniejące cookies ($COOKIES_OUT). Ustaw COOKIES_REFRESH=1 po eksporcie z robots.txt."
  fi

  if [ "$need_refresh" -eq 1 ]; then
    if [ -z "$profile" ]; then
      echo "WARN: brak profilu Chromium pod /chrome-profile."
      echo "      Po VNC: http://127.0.0.1:3000 → YouTube login → robots.txt → COOKIES_REFRESH=1 + restart."
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
        echo "WARN: dump nieudany (rc=$rc)."
        tail -n 20 "$log" 2>/dev/null || true
        rm -f "$tmp"
      elif grep -qi 'no longer valid\|cookies are no longer valid' "$log"; then
        echo "WARN: yt-dlp mówi, że cookies z przeglądarki są NIEWAŻNE (rotacja)."
        echo "      W Chromium: zaloguj → https://www.youtube.com/robots.txt (jedyna karta),"
        echo "      NIE otwieraj z powrotem youtube.com, ustaw COOKIES_REFRESH=1 i zrestartuj bota."
        tail -n 5 "$log" || true
        rm -f "$tmp"
      else
        mv "$tmp" "$COOKIES_OUT"
        yt_n="$(grep -ci 'youtube\.com' "$COOKIES_OUT" 2>/dev/null || echo 0)"
        echo "Cookies zapisane ($yt_n youtube.com rows)."
        if ! cookies_look_logged_in "$COOKIES_OUT"; then
          echo "WARN: dump bez LOGIN_INFO / __Secure-1PSID — sesja nie wygląda na zalogowaną."
        fi
      fi
      rm -f "$log"
    fi
  fi
  export COOKIES_FILE="$COOKIES_OUT"
fi

exec python -m bot
