#!/usr/bin/env bash
# 게임 위키 하나를 스크랩해서 csv_raw/<game>.csv로 저장
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

if [ $# -lt 2 ]; then
  echo "사용법: $0 <wiki_api_url> <game_name> [page_title] [-- wiki_scraper.py 추가 옵션...]"
  echo "예:     $0 https://terraria.wiki.gg/api.php \"Terraria\""
  echo "예:     $0 https://terraria.wiki.gg/api.php \"Terraria\" Music"
  echo "예:     $0 https://genshin-impact.fandom.com/api.php \"Genshin Impact\" -- --search-limit 200"
  exit 1
fi

WIKI_API="$1"
GAME="$2"
shift 2

PAGE_TITLE=""
if [ $# -gt 0 ] && [ "$1" != "--" ]; then
  PAGE_TITLE="$1"
  shift
fi
if [ $# -gt 0 ] && [ "$1" = "--" ]; then
  shift
fi

OUT_DIR="$ROOT_DIR/csv_raw"
mkdir -p "$OUT_DIR"
SLUG=$(echo "$GAME" | tr '[:upper:] ' '[:lower:]_' | tr -cd '[:alnum:]_')
OUT_FILE="$OUT_DIR/${SLUG}.csv"

ARGS=(--wiki-api "$WIKI_API" --game "$GAME" --out "$OUT_FILE")
if [ -n "$PAGE_TITLE" ]; then
  ARGS+=(--page-title "$PAGE_TITLE")
fi
ARGS+=("$@")

echo "[scrape] $GAME <- $WIKI_API"
python3 "$ROOT_DIR/wiki_scraper.py" "${ARGS[@]}"
echo "[scrape] -> $OUT_FILE"
