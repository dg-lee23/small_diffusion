#!/usr/bin/env bash
# 스크랩 CSV 하나를 카테고리별로 자동/반자동 분류 (classified/<category>.csv + _review.csv)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

if [ $# -lt 1 ]; then
  echo "사용법: $0 <scraped_csv> [classified_dir]"
  echo "예:     $0 csv_raw/terraria.csv"
  exit 1
fi

IN_CSV="$1"
CLASSIFIED_DIR="${2:-$ROOT_DIR/classified}"

python3 "$ROOT_DIR/classify_tracks.py" --in "$IN_CSV" --classified-dir "$CLASSIFIED_DIR"

echo
echo "[classify] $CLASSIFIED_DIR/_review.csv 를 열어 final_category를 채운 뒤 review.sh를 실행하세요."
