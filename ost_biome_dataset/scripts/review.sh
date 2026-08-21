#!/usr/bin/env bash
# classified/_review.csv에서 사람이 final_category를 채운 행들을 해당 카테고리 CSV로 반영
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# 사용법: ./review.sh [classified_dir] [--default-drop]
# --default-drop: final_category를 안 채운 행도 남겨두지 않고 drop 처리.
#   다 판단 끝났고 나머지는 버려도 될 때만 붙일 것 (아직 안 본 행까지 같이 사라짐).
CLASSIFIED_DIR="$ROOT_DIR/classified"
EXTRA_ARGS=()
for arg in "$@"; do
  if [ "$arg" = "--default-drop" ]; then
    EXTRA_ARGS+=(--default-drop)
  else
    CLASSIFIED_DIR="$arg"
  fi
done
REVIEW_CSV="$CLASSIFIED_DIR/_review.csv"

if [ ! -f "$REVIEW_CSV" ]; then
  echo "[!] $REVIEW_CSV 가 없습니다. classify.sh를 먼저 실행하세요."
  exit 1
fi

echo "[review] $REVIEW_CSV 반영 중..."
python3 "$ROOT_DIR/classify_tracks.py" --apply-review "$REVIEW_CSV" --classified-dir "$CLASSIFIED_DIR" "${EXTRA_ARGS[@]}"
