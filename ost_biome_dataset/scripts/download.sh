#!/usr/bin/env bash
# 분류된 카테고리 CSV 하나를 받아 오디오 다운로드 (audio/<category>/, metadata/<category>.csv)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

if [ $# -lt 1 ]; then
  echo "사용법: $0 <category> [wiki_api_fallback] [-- yt-dlp/download_tracks.py 추가 옵션...]"
  echo "예:     $0 cave_underground"
  echo "예:     $0 cave_underground https://terraria.wiki.gg/api.php -- --cookies-from-browser chrome"
  echo "예:     $0 cave_underground -- --dry-run --limit 5"
  exit 1
fi

CATEGORY="$1"
shift

WIKI_API_ARGS=()
if [ $# -gt 0 ] && [ "$1" != "--" ]; then
  WIKI_API_ARGS=(--wiki-api "$1")
  shift
fi
if [ $# -gt 0 ] && [ "$1" = "--" ]; then
  shift
fi

IN_CSV="$ROOT_DIR/classified/${CATEGORY}.csv"
OUT_DIR="$ROOT_DIR/audio/${CATEGORY}"
META_OUT="$ROOT_DIR/metadata/${CATEGORY}.csv"
mkdir -p "$ROOT_DIR/metadata"

if [ ! -f "$IN_CSV" ]; then
  echo "[!] $IN_CSV 가 없습니다. classify.sh로 먼저 분류하세요."
  exit 1
fi

# 유튜브 봇 차단 회피용 쿠키를 매번 손으로 안 넘겨도 되게, ROOT_DIR에 쿠키 파일이
# 있고 사용자가 이미 --cookies-file/--cookies-from-browser를 직접 안 줬으면 자동으로 붙인다.
COOKIE_ARGS=()
HAS_COOKIE_ARG=false
for arg in "$@"; do
  case "$arg" in
    --cookies-file|--cookies-from-browser) HAS_COOKIE_ARG=true ;;
  esac
done
if [ "$HAS_COOKIE_ARG" = false ]; then
  DEFAULT_COOKIES=$(find "$ROOT_DIR" -maxdepth 1 -iname "*cookies*.txt" 2>/dev/null | head -1)
  if [ -n "$DEFAULT_COOKIES" ]; then
    COOKIE_ARGS=(--cookies-file "$DEFAULT_COOKIES")
    echo "[download] 쿠키 자동 사용: $DEFAULT_COOKIES"
  fi
fi

echo "[download] $CATEGORY: $IN_CSV -> $OUT_DIR"
python3 "$ROOT_DIR/download_tracks.py" \
  --in "$IN_CSV" \
  --out-dir "$OUT_DIR" \
  --metadata-out "$META_OUT" \
  "${WIKI_API_ARGS[@]}" \
  "${COOKIE_ARGS[@]}" \
  "$@"
