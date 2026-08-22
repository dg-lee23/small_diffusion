"""Genshin Impact 전용: scrape_locations.py 출력(트랙별 리프 로케이션)을 받아 각
로케이션 문서의 "Overview" 섹션 텍스트를 가져온다.

여러 트랙이 같은 로케이션을 공유하는 경우가 많아서, 로케이션당 한 번만 조회하고
결과를 캐싱한다(이미 --out 파일에 있는 로케이션은 다시 안 가져옴 — 재실행해도
새로 추가된 로케이션만 조회).

사용 예:
    python fetch_overviews.py --wiki-api https://genshin-impact.fandom.com/api.php \
        --in genshin_raw/track_locations.csv --out genshin_raw/location_overviews.csv
"""

import argparse
import csv
import re
import sys
import time
from pathlib import Path

import requests

USER_AGENT = "ost-biome-dataset-bot/0.1 (research/personal dataset project)"


def _api_get(wiki_api: str, params: dict) -> dict:
    params = {**params, "format": "json"}
    resp = requests.get(wiki_api, params=params, headers={"User-Agent": USER_AGENT}, timeout=60)
    resp.raise_for_status()
    return resp.json()


def get_wikitext(wiki_api: str, title: str):
    data = _api_get(wiki_api, {"action": "parse", "page": title, "prop": "wikitext", "redirects": 1})
    if "error" in data:
        return None
    return data["parse"]["wikitext"]["*"]


_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
_WIKILINK = re.compile(r"\[\[(?:[^\|\]]*\|)?([^\]]+)\]\]")
_HEADING = re.compile(r"\n==+\s*([^=\n]+?)\s*==+\n")


def extract_overview(wikitext: str) -> str:
    """"Overview" 섹션(레벨 무관) 본문을 다음 헤더 전까지 뽑아 평문화."""
    text_with_nl = "\n" + wikitext
    matches = list(_HEADING.finditer(text_with_nl))
    for i, m in enumerate(matches):
        if m.group(1).strip().lower() == "overview":
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text_with_nl)
            section = text_with_nl[start:end]
            prev = None
            while prev != section:
                prev = section
                section = _TEMPLATE.sub("", section)
            section = _WIKILINK.sub(r"\1", section)
            section = re.sub(r"'''?", "", section)
            return section.strip()
    return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wiki-api", default="https://genshin-impact.fandom.com/api.php")
    ap.add_argument("--in", dest="in_csv", required=True)
    ap.add_argument("--out", default="genshin_raw/location_overviews.csv")
    args = ap.parse_args()

    with open(args.in_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    locations = sorted({r["LeafLocation"] for r in rows if r.get("LeafLocation")})
    print(f"[fetch] 고유 위치 {len(locations)}개")

    out_path = Path(args.out)
    results = {}
    if out_path.exists():
        with open(out_path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                results[r["LocationName"]] = r["OverviewText"]

    to_fetch = [loc for loc in locations if loc not in results]
    print(f"[fetch] 새로 조회할 위치: {len(to_fetch)}개 (캐시됨: {len(locations) - len(to_fetch)}개)")

    for i, loc in enumerate(to_fetch):
        try:
            wikitext = get_wikitext(args.wiki_api, loc)
        except requests.RequestException as e:
            print(f"  [{i+1}/{len(to_fetch)}] {loc} -> 요청 실패({e}), 다음 실행 때 재시도", file=sys.stderr)
            continue
        overview = extract_overview(wikitext) if wikitext else ""
        results[loc] = overview
        status = "OK" if overview else "[Overview 섹션 없음]"
        print(f"  [{i+1}/{len(to_fetch)}] {loc} -> {status}")
        time.sleep(0.3)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["LocationName", "OverviewText"])
        writer.writeheader()
        for loc, text in results.items():
            writer.writerow({"LocationName": loc, "OverviewText": text})
    print(f"[fetch] {len(results)}개 위치를 {args.out}에 저장함")


if __name__ == "__main__":
    main()
