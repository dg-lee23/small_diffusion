"""Genshin Impact 전용: scrape_locations.py(트랙->리프 위치) + llm_classify.py
(위치->카테고리) 결과를 합쳐서 카테고리별 CSV를 만든다.

다른 게임들이 쓰는 것과 같은 스키마로 나오므로 download_tracks.py에 바로 넣을 수
있다. LLM이 NONE으로 판단했거나 아직 분류 결과가 없는 위치의 트랙은 포함하지
않는다(억지로 하나 고르지 않는다는 규칙 그대로 반영).

사용 예:
    python build_dataset.py --tracks genshin_raw/track_locations.csv \
        --categories genshin_raw/location_categories.csv --out-dir genshin_classified
"""

import argparse
import csv
import os

FIELDNAMES = [
    "Title",
    "LeafLocation",
    "_file_links",
    "_ext_links",
    "_source_page",
    "_wiki_api",
    "biome_category",
    "game",
]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tracks", required=True)
    ap.add_argument("--categories", required=True)
    ap.add_argument("--out-dir", default="genshin_classified")
    args = ap.parse_args()

    with open(args.categories, newline="", encoding="utf-8") as f:
        cat_by_location = {r["LocationName"]: r["Category"] for r in csv.DictReader(f)}

    with open(args.tracks, newline="", encoding="utf-8") as f:
        tracks = list(csv.DictReader(f))

    by_category: dict[str, list[dict]] = {}
    skipped_none = 0
    skipped_no_category_data = 0
    for t in tracks:
        loc = t.get("LeafLocation", "")
        category = cat_by_location.get(loc)
        if category is None:
            skipped_no_category_data += 1
            continue
        if category == "NONE":
            skipped_none += 1
            continue
        row = dict(t)
        row["biome_category"] = category
        by_category.setdefault(category, []).append(row)

    os.makedirs(args.out_dir, exist_ok=True)
    for category, rows in sorted(by_category.items()):
        path = os.path.join(args.out_dir, f"{category}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
        print(f"  {category}: {len(rows)}")

    print(f"\nLLM이 NONE으로 판단(제외): {skipped_none}")
    print(f"아직 분류 안 된 위치라 제외(location_categories.csv에 없음, llm_classify.py 먼저 돌릴 것): {skipped_no_category_data}")
    total = sum(len(v) for v in by_category.values())
    print(f"총 {total}개 트랙을 {args.out_dir}/에 저장함")


if __name__ == "__main__":
    main()
