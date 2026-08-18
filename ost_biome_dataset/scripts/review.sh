#!/usr/bin/env bash
# classified/_review.csv에서 사람이 final_category를 채운 행들을 해당 카테고리 CSV로 반영
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

CLASSIFIED_DIR="${1:-$ROOT_DIR/classified}"
REVIEW_CSV="$CLASSIFIED_DIR/_review.csv"

if [ ! -f "$REVIEW_CSV" ]; then
  echo "[!] $REVIEW_CSV 가 없습니다. classify.sh를 먼저 실행하세요."
  exit 1
fi

echo "[review] $REVIEW_CSV 반영 중..."
python3 "$ROOT_DIR/classify_tracks.py" --apply-review "$REVIEW_CSV" --classified-dir "$CLASSIFIED_DIR"
