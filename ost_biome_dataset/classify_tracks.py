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
나뉘지 않음), 실제 오디오 파일/링크(_file_links 우선, 없으면 _ext_links, 그것도 없으면
game+제목) 기준으로 중복을 걸러내 같은 스크립트를 여러 번 돌려도 중복 추가되지 않는다.
같은 곡이 위키의 서로 다른 문서(예: Terraria의 "Music" 페이지와, 그 곡을 재생하는
아이템을 설명하는 "Music Boxes" 페이지)에 각각 설명되어 있어도 실제 파일이 같으면
하나로 취급한다.

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
import ast
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


def _parse_list_cell(value) -> list[str]:
    """CSV에 str(list)로 저장된 값을 복원."""
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = ast.literal_eval(value)
        if isinstance(parsed, list):
            return [str(v) for v in parsed]
    except (ValueError, SyntaxError):
        pass
    return [v.strip(" '\"") for v in value.strip("[]").split(",") if v.strip()]


def _dedup_key(row: dict) -> tuple:
    """같은 실제 오디오를 가리키는 행은 다른 위키 문서(예: Terraria의 "Music" vs
    "Music Boxes")에서 왔더라도 같은 트랙으로 취급한다. _file_links(위키가 호스팅하는
    실제 파일명)를 최우선 식별자로 쓰고, 그게 없으면 외부 링크, 그것도 없으면
    (game, title)로 폴백한다. 페이지 제목(_source_page)은 더 이상 키에 포함하지 않음 —
    같은 곡이 여러 문서에 걸쳐 설명되는 경우가 흔해서 오히려 중복을 만들었었다."""
    game = row.get("game", "")
    file_links = _parse_list_cell(row.get("_file_links"))
    if file_links:
        return (game, "file", file_links[0])
    ext_links = _parse_list_cell(row.get("_ext_links"))
    if ext_links:
        return (game, "ext", ext_links[0])
    return (game, "title", _guess_title(row))


def _read_csv_rows(path) -> list[dict]:
    """CSV를 읽되 UTF-8이 아니어도 최대한 읽어낸다.

    사람이 Excel 등에서 review CSV를 편집하고 저장하면 "CSV UTF-8"이 아니라
    시스템 기본 인코딩(Windows면 보통 cp1252)으로 저장되는 경우가 흔해서,
    악센트 문자 등이 들어간 트랙명에서 UnicodeDecodeError가 난다. utf-8이
    안 되면 cp1252, 그것도 안 되면 latin-1(모든 바이트를 항상 읽어낼 수 있음)
    순으로 재시도한다."""
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(path, newline="", encoding=encoding) as f:
                rows = list(csv.DictReader(f))
            if encoding != "utf-8-sig":
                print(f"[!] {path}: UTF-8이 아니어서 {encoding}로 읽음 (Excel로 저장했다면 'CSV UTF-8'로 다시 저장 권장)")
            return rows
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"{path}를 어떤 인코딩으로도 읽지 못함")


def _load_existing_keys(path: Path) -> set:
    if not path.exists():
        return set()
    return {_dedup_key(r) for r in _read_csv_rows(path)}


def _append_rows(path: Path, rows: list[dict], fieldnames: list[str]):
    """rows를 path에 append한다.

    서로 다른 위키(게임)를 스크랩하면 원본 표의 컬럼 구성 자체가 다르다
    (예: Terraria는 Condition/Title/Description, Subnautica는 Coordinates/
    Location/Played when/Track Name 등). 기존 파일이 이미 다른 컬럼 구성으로
    만들어져 있는데 그냥 append하면, csv.DictWriter는 위치 기반이 아니라
    fieldnames 기준으로 쓰지만 실제 파일에 이미 적힌 헤더 줄은 안 바뀌므로
    "다른 헤더 밑에 다른 컬럼 값이 깔리는" 심각한 데이터 손상이 생긴다
    (실제로 Subnautica 트랙 제목이 Terraria 헤더의 다른 컬럼 자리에 들어가
    game/title이 뒤섞이는 사고가 있었음). 그래서 기존 헤더에 없는 새 컬럼이
    있으면 파일 전체를 "기존 헤더 + 새 컬럼" 합집합으로 재작성한다.
    """
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)

    if not path.exists():
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows:
                writer.writerow({k: r.get(k, "") for k in fieldnames})
        return

    existing_rows = _read_csv_rows(path)
    existing_header = list(existing_rows[0].keys()) if existing_rows else []
    if not existing_header:
        with open(path, newline="", encoding="utf-8") as f:
            existing_header = next(csv.reader(f), [])

    merged_header = existing_header + [f for f in fieldnames if f not in existing_header]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=merged_header)
        writer.writeheader()
        for r in existing_rows:
            writer.writerow({k: r.get(k, "") for k in merged_header})
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in merged_header})


def run_classify(in_csv: str, classified_dir: str):
    rows = _read_csv_rows(in_csv)
    if not rows:
        print("[!] 입력 CSV가 비어있음")
        return

    out_dir = Path(classified_dir)
    review_path = out_dir / "_review.csv"
    # 전체 카테고리 + review를 통틀어 "이미 처리된 트랙"을 하나의 집합으로 관리한다.
    # 카테고리별로 따로 관리하면, 같은 트랙이 서로 다른 위키 문서(예: Terraria의
    # "Music" 페이지와 "Music Boxes" 페이지)에서 미묘하게 다른 텍스트로 두 번 나올 때
    # 우연히 다른 카테고리로 갈리면서 중복 투입될 수 있다.
    seen_keys = _load_existing_keys(review_path)
    for cat in CATEGORY_KEYWORDS:
        seen_keys |= _load_existing_keys(out_dir / f"{cat}.csv")

    by_category: dict[str, list[dict]] = {cat: [] for cat in CATEGORY_KEYWORDS}
    review_rows: list[dict] = []
    skipped_dupes = 0

    for row in rows:
        key = _dedup_key(row)
        if key in seen_keys:
            skipped_dupes += 1
            continue
        seen_keys.add(key)
        matched = classify_row(row)
        if len(matched) == 1:
            cat = matched[0]
            out_row = dict(row)
            out_row["biome_category"] = cat  # 스크랩 시점 값(있다면)을 실제 분류로 덮어씀
            by_category[cat].append(out_row)
        else:
            review_row = dict(row)
            review_row["_matched_categories"] = "|".join(matched) if matched else ""
            review_row["final_category"] = ""
            review_rows.append(review_row)

    # rows[0]만 보면 같은 배치 안에서도 행마다 컬럼이 다를 때(예: 검색으로 여러
    # 위키 문서를 긁어와 문서마다 표 구성이 다른 경우) 일부 컬럼을 놓칠 수 있어
    # 전체 행의 컬럼을 합집합으로 모은다.
    orig_fields = []
    for r in rows:
        for k in r.keys():
            if k not in orig_fields:
                orig_fields.append(k)
    for cat, cat_rows in by_category.items():
        if cat_rows:
            _append_rows(out_dir / f"{cat}.csv", cat_rows, orig_fields)
            print(f"  {cat}: +{len(cat_rows)}")

    if review_rows:
        review_fields = orig_fields + ["_matched_categories", "final_category"]
        _append_rows(review_path, review_rows, review_fields)
        print(f"  review (사람 판단 필요): +{len(review_rows)}")

    if skipped_dupes:
        print(f"  (중복으로 건너뜀: {skipped_dupes}개 — 같은 오디오 파일/링크를 가리키는 행)")

    print(f"\n총 {len(rows)}행 처리 완료. 결과: {out_dir}/")


def run_apply_review(review_csv: str, classified_dir: str, default_drop: bool = False):
    review_path = Path(review_csv)
    rows = _read_csv_rows(review_path)
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
            if default_drop:
                dropped += 1
            else:
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
    ap.add_argument(
        "--default-drop",
        action="store_true",
        help="--apply-review 전용. final_category를 안 채운 행도 review에 남겨두지 않고 "
        "drop(제외) 처리한다. 실제로 다 판단한 뒤 나머지를 한번에 정리할 때만 켤 것 — "
        "아직 안 본 행까지 같이 버려질 수 있음.",
    )
    args = ap.parse_args()

    if bool(args.in_csv) == bool(args.apply_review):
        ap.error("--in 또는 --apply-review 중 하나만 지정하세요")

    if args.in_csv:
        run_classify(args.in_csv, args.classified_dir)
    else:
        run_apply_review(args.apply_review, args.classified_dir, args.default_drop)


if __name__ == "__main__":
    main()
