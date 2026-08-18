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

echo "[download] $CATEGORY: $IN_CSV -> $OUT_DIR"
python3 "$ROOT_DIR/download_tracks.py" \
  --in "$IN_CSV" \
  --out-dir "$OUT_DIR" \
  --metadata-out "$META_OUT" \
  "${WIKI_API_ARGS[@]}" \
  "$@"
