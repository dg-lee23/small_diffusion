"""Genshin Impact 전용: scrape_locations.py 출력(트랙별 리프 로케이션)을 받아 각
로케이션 문서의 설명 텍스트를 가져온다.

실제 구조(사용자가 보내준 실제 위치 문서 위키텍스트로 확인함 — "Mondstadt"): 이
위키는 "Overview" 같은 별도 섹션 헤딩이 없고, 문서 최상단의
{{Location Intro|...|description=<p>...</p>}} 템플릿의 description 파라미터에
설명 텍스트가 들어있다. 예:
    {{Location Intro|'''Mondstadt''', also known as ...<ref>...</ref>
    |description=<p>Located in the west part of Starfell Valley ...
    {{w|Curtain wall (fortification)|castle wall}}...</p>}}
<ref>...</ref>(각주)와 {{w|Target|Display}}(위키백과 등 외부 위키 링크 템플릿,
Display 텍스트만 씀) 처리가 필요하다.

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

from scrape_locations import _WIKILINK, find_template_call, parse_template_params

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
_REF = re.compile(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", re.IGNORECASE | re.DOTALL)
_W_TEMPLATE = re.compile(r"\{\{w\|([^|}]*)(?:\|([^}]*))?\}\}", re.IGNORECASE)
_EXT_LINK = re.compile(r"\[https?://\S+\s+([^\]]+)\]|\[https?://\S+\]")
_HTML_TAG = re.compile(r"</?p>|<br\s*/?>", re.IGNORECASE)


def extract_overview(wikitext: str) -> str:
    """{{Location Intro}}의 description 파라미터에서 위치 설명 텍스트를 뽑아 평문화."""
    call = find_template_call(wikitext, "Location Intro")
    if not call:
        return ""
    params = parse_template_params(call)
    desc = params.get("description", "").strip()
    if not desc:
        return ""
    desc = _REF.sub("", desc)
    # {{w|Target|Display}}는 외부 위키(위키백과 등) 링크 템플릿 — Display만 남김
    # (없으면 Target). 아래 일반 템플릿 제거 루프보다 먼저 처리해야 함.
    desc = _W_TEMPLATE.sub(lambda m: (m.group(2) or m.group(1)).strip(), desc)
    prev = None
    while prev != desc:
        prev = desc
        desc = _TEMPLATE.sub("", desc)
    desc = _WIKILINK.sub(r"\1", desc)
    desc = _EXT_LINK.sub(r"\1", desc)
    desc = _HTML_TAG.sub(" ", desc)
    desc = re.sub(r"'''?", "", desc)
    return re.sub(r"\s+", " ", desc).strip()


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
