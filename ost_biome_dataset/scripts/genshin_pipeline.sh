#!/usr/bin/env bash
# Genshin Impact 전용 파이프라인: 트랙별 위치 트리 스크랩 -> 위치 Overview 텍스트
# 확보 -> LLM 분류(카테고리 5개: snow_ice, underwater, cave_underground, desert_rock,
# city_machine) -> 카테고리별 CSV. 다른 게임들(classify.sh 등)과 카테고리 체계가
# 다른 원신 전용 파이프라인이라 별도 스크립트로 분리되어 있다.
#
# 1단계(트랙 문서별 위치 트리 파싱)는 실제 위키 구조를 100% 검증하지 못했다.
# 먼저 아래처럼 소량만 확인해보는 걸 강력히 권장:
#   python3 genshin/scrape_locations.py --limit 5 --dry-run
# 이후 단계(특히 3단계 LLM 분류)는 API 비용이 드니, 1단계 결과가 말이 되는지
# 확인한 뒤에 이 스크립트 전체를 돌릴 것. 트랙 문서 수가 많아 1단계가 오래 걸릴 수
# 있는데, 중간에 끊겨도 재실행하면 이미 받은 트랙은 건너뛰고 이어서 한다.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
GENSHIN_DIR="$ROOT_DIR/genshin"

WIKI_API="https://genshin-impact.fandom.com/api.php"
RAW_DIR="$ROOT_DIR/genshin_raw"
OUT_DIR="$ROOT_DIR/genshin_classified"

echo "[1/4] 트랙별 위치 스크랩 (Category:Soundtracks 멤버 전체 순회, 시간 걸림)"
python3 "$GENSHIN_DIR/scrape_locations.py" \
  --wiki-api "$WIKI_API" \
  --out "$RAW_DIR/track_locations.csv"

echo
echo "[2/4] 위치별 Overview 텍스트 확보"
python3 "$GENSHIN_DIR/fetch_overviews.py" \
  --wiki-api "$WIKI_API" \
  --in "$RAW_DIR/track_locations.csv" \
  --out "$RAW_DIR/location_overviews.csv"

echo
echo "[3/4] LLM 분류 (API 비용 발생)"
python3 "$GENSHIN_DIR/llm_classify.py" \
  --in "$RAW_DIR/location_overviews.csv" \
  --out "$RAW_DIR/location_categories.csv"

echo
echo "[4/4] 카테고리별 CSV 생성"
python3 "$GENSHIN_DIR/build_dataset.py" \
  --tracks "$RAW_DIR/track_locations.csv" \
  --categories "$RAW_DIR/location_categories.csv" \
  --out-dir "$OUT_DIR"

echo
echo "완료. 예: python3 download_tracks.py --in $OUT_DIR/snow_ice.csv \\"
echo "  --out-dir audio_genshin/snow_ice --metadata-out metadata_genshin/snow_ice.csv"
