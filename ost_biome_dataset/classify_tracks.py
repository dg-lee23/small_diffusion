"""wiki_scraper.py가 만든 CSV를 8개 바이옴 카테고리로 자동/반자동 분류한다.

동작 방식:
    1. (기본 모드) --in으로 스크랩 CSV를 넣으면, 각 행의 모든 텍스트 컬럼에서
       카테고리별 키워드를 찾는다.
         - 정확히 1개 카테고리만 매칭 -> 자동으로 classified/<category>.csv에 append
         - 0개 또는 2개 이상 매칭 -> classified/_review.csv에 append (사람 판단 필요)
    2. 사람이 classified/_review.csv를 열어 각 행의 final_category 컬럼에
       카테고리 ID(예: cave_underground)를 적거나, 버릴 곡이면 "drop"을 적는다.
       아직 결정 못 한 행은 비워두면 된다.
    3. (--apply-review 모드) 그 CSV를 다시 넣으면, final_category가 채워진 행만
       해당 카테고리 CSV로 옮기고 _review.csv에서는 제거한다. 비어있는 행은 그대로
       _review.csv에 남는다.

여러 게임을 스크랩해도 classified/<category>.csv 하나에 계속 쌓이며(게임별로 CSV가
나뉘지 않음), (game, track_title, source_page) 조합으로 중복을 걸러내 같은 스크립트를
여러 번 돌려도 중복 추가되지 않는다.

주의: 컬럼 구성이 위키마다 다르므로(wiki_scraper.py가 위키 표 헤더를 그대로 씀)
    이 스크립트는 메타데이터 컬럼(game, _wiki_api 등)을 제외한 "모든" 텍스트 컬럼을
    훑어서 키워드를 찾는다. Description처럼 바이옴과 무관한 서술이 섞인 컬럼도
    같이 스캔되므로 오탐 가능성이 있다 — 정확히 1개만 매칭된 자동분류 결과도
    가끔 검수해볼 것을 권장.

사용 예:
    python classify_tracks.py --in tracks_terraria.csv --classified-dir classified
    # classified/_review.csv를 사람이 채운 뒤:
    python classify_tracks.py --apply-review classified/_review.csv --classified-dir classified
"""

import argparse
import csv
from pathlib import Path

EXCLUDE_COLUMNS = {
    "game", "biome_category", "_source_page", "_wiki_api",
    "_file_links", "_ext_links", "#",
}
# 컬럼 헤더에 이 단어가 들어있으면 스캔에서 제외 (곡 설명/가사 등 산문 텍스트라
# 다른 게임/작품 언급 등으로 키워드 오탐이 나기 쉬움 — 예: "Dungeon Defenders" 언급 때문에
# "dungeon"이 걸려 cave_underground로 잘못 분류되는 사례가 실제로 있었음)
SKIP_HEADER_SUBSTRINGS = ("description", "desc", "listen", "notes", "lyrics", "trivia")
TITLE_KEYS = ["Track", "Title", "Name", "Song", "title"]

CATEGORY_KEYWORDS = {
    "forest_jungle": ["forest", "jungle", "woods", "woodland", "grove", "rainforest", "greenwood"],
    "snow_ice": ["snow", "ice biome", " ice", "frost", "glacier", "tundra", "blizzard", "frozen", "winter"],
    "desert_rock": ["desert", "sand", "dune", "canyon", "badlands", "mesa", "sandstorm"],
    "cave_underground": ["cave", "cavern", "underground", "dungeon", "mine", "tunnel", "grotto", "catacomb"],
    "sea_underwater": ["ocean", " sea", "underwater", "coast", "beach", "harbor", "harbour", "reef", "lagoon", "abyss"],
    "city_machine": ["city", "town", "urban", "factory", "machine", "industrial", "metropolis", "cyber", "robot"],
    "hell": ["hell", "underworld", "lava", "inferno", "demon", "brimstone", "volcan", "abyss"],
    "space": ["space", "cosmos", "galaxy", "planet", "orbit", "nebula", "asteroid", "cosmic"],
}


def _guess_title(row: dict) -> str:
    for key in TITLE_KEYS:
        if row.get(key):
            return row[key]
    for k, v in row.items():
        if k.startswith("_") or k in EXCLUDE_COLUMNS:
            continue
        if v:
            return v
    return ""


def classify_row(row: dict) -> list[str]:
    text = " ".join(
        str(v).lower() for k, v in row.items()
        if v and k not in EXCLUDE_COLUMNS and not k.startswith("_")
        and not any(skip in k.lower() for skip in SKIP_HEADER_SUBSTRINGS)
    )
    matched = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            matched.append(category)
    return matched


def _dedup_key(row: dict) -> tuple:
    return (row.get("game", ""), _guess_title(row), row.get("_source_page", ""))


def _load_existing_keys(path: Path) -> set:
    if not path.exists():
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        return {_dedup_key(r) for r in csv.DictReader(f)}


def _append_rows(path: Path, rows: list[dict], fieldnames: list[str]):
    if not rows:
        return
    is_new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if is_new:
            writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})


def run_classify(in_csv: str, classified_dir: str):
    with open(in_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("[!] 입력 CSV가 비어있음")
        return

    out_dir = Path(classified_dir)
    review_path = out_dir / "_review.csv"
    existing_review_keys = _load_existing_keys(review_path)
    existing_category_keys = {
        cat: _load_existing_keys(out_dir / f"{cat}.csv") for cat in CATEGORY_KEYWORDS
    }

    by_category: dict[str, list[dict]] = {cat: [] for cat in CATEGORY_KEYWORDS}
    review_rows: list[dict] = []

    for row in rows:
        key = _dedup_key(row)
        matched = classify_row(row)
        if len(matched) == 1:
            cat = matched[0]
            if key not in existing_category_keys[cat]:
                out_row = dict(row)
                out_row["biome_category"] = cat  # 스크랩 시점 값(있다면)을 실제 분류로 덮어씀
                by_category[cat].append(out_row)
                existing_category_keys[cat].add(key)
        else:
            if key not in existing_review_keys:
                review_row = dict(row)
                review_row["_matched_categories"] = "|".join(matched) if matched else ""
                review_row["final_category"] = ""
                review_rows.append(review_row)
                existing_review_keys.add(key)

    orig_fields = list(rows[0].keys())
    for cat, cat_rows in by_category.items():
        if cat_rows:
            _append_rows(out_dir / f"{cat}.csv", cat_rows, orig_fields)
            print(f"  {cat}: +{len(cat_rows)}")

    if review_rows:
        review_fields = orig_fields + ["_matched_categories", "final_category"]
        _append_rows(review_path, review_rows, review_fields)
        print(f"  review (사람 판단 필요): +{len(review_rows)}")

    print(f"\n총 {len(rows)}행 처리 완료. 결과: {out_dir}/")


def run_apply_review(review_csv: str, classified_dir: str):
    review_path = Path(review_csv)
    with open(review_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("[!] review CSV가 비어있음")
        return

    review_fieldnames = list(rows[0].keys())
    orig_fields = [c for c in review_fieldnames if c not in ("_matched_categories", "final_category")]
    out_dir = Path(classified_dir)

    decided_by_category: dict[str, list[dict]] = {}
    still_pending: list[dict] = []
    dropped = 0

    for row in rows:
        decision = (row.get("final_category") or "").strip().lower()
        if not decision:
            still_pending.append(row)
        elif decision in ("drop", "skip", "exclude"):
            dropped += 1
        elif decision in CATEGORY_KEYWORDS:
            out_row = dict(row)
            out_row["biome_category"] = decision
            decided_by_category.setdefault(decision, []).append(out_row)
        else:
            print(f"[!] 알 수 없는 카테고리 '{decision}' (행: {_guess_title(row)}) -> review에 남겨둠", )
            still_pending.append(row)

    for cat, cat_rows in decided_by_category.items():
        existing = _load_existing_keys(out_dir / f"{cat}.csv")
        new_rows = [r for r in cat_rows if _dedup_key(r) not in existing]
        _append_rows(out_dir / f"{cat}.csv", new_rows, orig_fields)
        print(f"  {cat}: +{len(new_rows)} (review에서 이동)")

    with open(review_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=review_fieldnames)
        writer.writeheader()
        writer.writerows(still_pending)

    print(f"  drop: {dropped}개 제외")
    print(f"  아직 미결정: {len(still_pending)}개 (review CSV에 남아있음)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="in_csv", help="wiki_scraper.py 출력 CSV (기본 분류 모드)")
    ap.add_argument("--apply-review", dest="apply_review", help="사람이 final_category를 채운 review CSV (반영 모드)")
    ap.add_argument("--classified-dir", default="classified", help="카테고리별 CSV를 저장/조회할 디렉터리")
    args = ap.parse_args()

    if bool(args.in_csv) == bool(args.apply_review):
        ap.error("--in 또는 --apply-review 중 하나만 지정하세요")

    if args.in_csv:
        run_classify(args.in_csv, args.classified_dir)
    else:
        run_apply_review(args.apply_review, args.classified_dir)


if __name__ == "__main__":
    main()
