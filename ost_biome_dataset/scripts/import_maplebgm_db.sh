#!/usr/bin/env bash
# maplestory-music/maplebgm-db 저장소(트랙마다 검증된 유튜브 링크 보유)를
# csv_raw/maplestory.csv로 변환. wiki_scraper.py 대신 이걸 써서 MapleStory를
# 스크랩하면 ytsearch 검색 폴백 없이 바로 정확한 링크로 다운로드 가능.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

if [ $# -lt 1 ]; then
  echo "사용법: $0 <maplebgm-db_repo_경로> [out_csv]"
  echo "먼저 clone: git clone https://github.com/maplestory-music/maplebgm-db"
  echo "예:     $0 ../maplebgm-db"
  exit 1
fi

REPO_DIR="$1"
OUT="${2:-$ROOT_DIR/csv_raw/maplestory.csv}"

python3 "$ROOT_DIR/maplebgm_db_import.py" --repo-dir "$REPO_DIR" --out "$OUT"
echo
echo "[import] 다음: ./scripts/classify.sh $OUT"
