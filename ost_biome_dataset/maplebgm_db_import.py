"""maplestory-music/maplebgm-db 저장소(bgm/*.json)를 다른 스크립트들이 쓰는 것과
같은 형태의 CSV로 변환한다.

이 DB는 MapleWiki(fandom)보다 나은 소스다 — MapleWiki의 Music 페이지는 실제 오디오
없이 다른 위키(maplestory-music.fandom.com)로 링크만 걸어놔서 트랙마다 그 위키를
또 조회해야 했는데, 이 저장소는 트랙마다 이미 검증된 정확한 유튜브 영상 ID를 갖고
있다(_ext_links에 그대로 채워짐). download_tracks.py가 불안정한 ytsearch 검색
폴백 대신 그 링크를 바로 쓸 수 있어 정확도가 훨씬 높다.

먼저 저장소를 clone:
    git clone https://github.com/maplestory-music/maplebgm-db

사용 예:
    python maplebgm_db_import.py --repo-dir maplebgm-db --out csv_raw/maplestory.csv

출력 CSV는 wiki_scraper.py 출력과 같은 방식으로 classify.sh에 바로 넣을 수 있다
(중간에 wiki_scraper.py 단계는 필요 없음).
"""

import argparse
import csv
import glob
import json
import os


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo-dir", required=True, help="git clone한 maplebgm-db 저장소 경로")
    ap.add_argument("--out", default="csv_raw/maplestory.csv")
    ap.add_argument("--game", default="MapleStory")
    args = ap.parse_args()

    bgm_files = sorted(glob.glob(os.path.join(args.repo_dir, "bgm", "*.json")))
    if not bgm_files:
        raise SystemExit(f"[!] {args.repo_dir}/bgm/*.json 을 못 찾음 — --repo-dir 경로 확인")

    rows = []
    for path in bgm_files:
        group = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as f:
            tracks = json.load(f)
        for t in tracks:
            yt = t.get("youtube")
            ext_links = [f"https://www.youtube.com/watch?v={yt}"] if yt else []
            meta = t.get("metadata", {})
            rows.append(
                {
                    "Title": meta.get("title") or t.get("filename", ""),
                    # "Location"이라는 이름을 씀 — classify_tracks.py가 "description"류
                    # 컬럼은 서술형 텍스트로 보고 키워드 스캔에서 제외하는데, 여기 값은
                    # 사실 지역명이라 스캔 대상에 남아있어야 함.
                    "Location": t.get("description", ""),
                    "Mark": t.get("mark", ""),
                    "Artist": meta.get("artist", ""),
                    "Year": meta.get("year", ""),
                    "_ext_links": str(ext_links),
                    "_source_page": group,
                    "_wiki_api": "",
                    "biome_category": "unclassified",
                    "game": args.game,
                }
            )

    fieldnames = ["Title", "Location", "Mark", "Artist", "Year", "_ext_links", "_source_page", "_wiki_api", "biome_category", "game"]
    out_dir = os.path.dirname(args.out)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    no_yt = sum(1 for r in rows if r["_ext_links"] == "[]")
    print(f"{len(rows)}개 트랙을 {args.out}에 저장함 (유튜브 링크 없는 트랙: {no_yt}개)")


if __name__ == "__main__":
    main()
