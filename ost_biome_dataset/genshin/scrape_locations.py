"""Genshin Impact 전용: 트랙별 재생 위치(리프 로케이션)를 추출한다.

실제 구조(사용자가 보내준 원본 위키텍스트로 확인함): "Soundtrack/List" 페이지는
트랙을 직접 나열하지 않고 {{Soundtracks by Category Table|Soundtracks|...}}
템플릿으로 "Category:Soundtracks" 분류에 속한 문서 목록을 동적으로 렌더링만 한다.
즉 실제 트랙별 "Open-World Locations" 트리는 각 트랙의 "개별 문서"에 있다.

그래서 이 스크립트는:
    1. MediaWiki API로 "Category:Soundtracks" 분류 멤버(=트랙 문서 제목) 목록을
       가져옴. "Category:Unreleased Soundtracks" 멤버는 기본적으로 제외 —
       Soundtrack/List 페이지의 "Released Soundtracks" 절과 동일한 필터.
    2. 트랙 문서마다 위키텍스트를 가져와 "Open-World Locations" 문구 다음에 나오는
       중첩 위키 불릿 리스트(*, **, ***...)에서 리프 위치를 추출한다. "리프 노드"는
       바로 다음 줄이 더 깊은 들여쓰기가 아닌 마지막 노드로 판정한다 — 이 부분은
       (다른 페이지 구조였을 때 짠) 원래 가정 그대로라 검증이 더 필요할 수 있다.
       --dump-sample-title로 트랙 하나의 원본 위키텍스트를 저장해 확인 가능.

트랙 수가 많아 문서를 하나씩 가져오는 데 시간이 걸린다. --out 파일이 이미 있으면
거기 있는 Title은 재조회하지 않아서(캐싱) 중간에 끊겨도 이어서 할 수 있다.

규칙:
    1. 리프 로케이션이 여러 개(한 트랙이 여러 지역에서 재생)면 건너뜀 — 포함 안 함
    2. 위치 정보를 아예 못 찾은 트랙도 건너뜀

사용 예:
    # 먼저 트랙 하나로 구조 확인
    python scrape_locations.py --limit 5 --dry-run --dump-sample-title
    # 본실행
    python scrape_locations.py --out genshin_raw/track_locations.csv
"""

import argparse
import csv
import os
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


def get_category_members(wiki_api: str, category: str, limit: int = 5000) -> list[str]:
    """"Category:<category>"에 속한 문서 제목 목록을 (필요하면 이어서 요청해) 가져온다."""
    titles: list[str] = []
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": f"Category:{category}",
        "cmlimit": min(limit, 500),
    }
    while True:
        data = _api_get(wiki_api, params)
        members = data.get("query", {}).get("categorymembers", [])
        titles.extend(m["title"] for m in members)
        cont = data.get("continue", {}).get("cmcontinue")
        if cont is None or len(titles) >= limit:
            break
        params["cmcontinue"] = cont
    return titles[:limit]


_BULLET_LINE = re.compile(r"^(\*+)\s*(.*)$")
_WIKILINK = re.compile(r"\[\[(?:[^\|\]]*\|)?([^\]]+)\]\]")
_FILELINK = re.compile(r"\[\[File:([^\|\]]+)")
_EXTLINK = re.compile(r"\[(https?://\S+)\s*([^\]]*)\]")


def extract_leaf_locations(wikitext: str) -> list[str]:
    """"Open-World Locations" 아래 중첩 불릿 리스트에서 리프 노드 이름들을 추출."""
    idx = wikitext.find("Open-World Locations")
    if idx == -1:
        return []
    after = wikitext[idx:]
    lines = after.splitlines()[1:]
    bullet_lines = []
    for line in lines:
        stripped = line.strip()
        if _BULLET_LINE.match(stripped):
            bullet_lines.append(stripped)
        elif bullet_lines:
            break  # 불릿 블록이 끝남
    parsed = []
    for line in bullet_lines:
        m = _BULLET_LINE.match(line)
        depth = len(m.group(1))
        rest = m.group(2)
        link_m = _WIKILINK.search(rest)
        name = link_m.group(1) if link_m else rest.strip()
        if name:
            parsed.append((depth, name))
    leaves = []
    for i, (depth, name) in enumerate(parsed):
        next_depth = parsed[i + 1][0] if i + 1 < len(parsed) else 0
        if next_depth <= depth:
            leaves.append(name)
    return leaves


def extract_ext_and_file_links(wikitext: str) -> tuple[list[str], list[str]]:
    file_links = _FILELINK.findall(wikitext)
    ext_links = [m.group(1) for m in _EXTLINK.finditer(wikitext)]
    return file_links, ext_links


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wiki-api", default="https://genshin-impact.fandom.com/api.php")
    ap.add_argument("--category", default="Soundtracks", help="트랙 문서 분류명 (Category: 접두어 제외)")
    ap.add_argument(
        "--exclude-category",
        default="Unreleased Soundtracks",
        help="여기 속한 트랙은 제외 (빈 문자열이면 제외 안 함)",
    )
    ap.add_argument("--out", default="genshin_raw/track_locations.csv")
    ap.add_argument("--limit", type=int, default=5000, help="테스트용: 트랙 문서 조회 개수 상한")
    ap.add_argument("--dump-sample-title", action="store_true", help="첫 트랙 하나의 원본 위키텍스트를 콘솔에 출력하고 종료 (구조 확인용)")
    ap.add_argument("--game", default="Genshin Impact")
    ap.add_argument("--dry-run", action="store_true", help="CSV로 저장하지 않고 콘솔에 미리보기만 출력")
    args = ap.parse_args()

    titles = get_category_members(args.wiki_api, args.category, limit=args.limit)
    print(f"[scrape] Category:{args.category} 멤버 {len(titles)}개")

    if args.exclude_category:
        excluded = set(get_category_members(args.wiki_api, args.exclude_category, limit=5000))
        before = len(titles)
        titles = [t for t in titles if t not in excluded]
        print(f"[scrape] Category:{args.exclude_category} {len(excluded)}개 제외 ({before} -> {len(titles)})")

    if not titles:
        print(f"[!] Category:{args.category}에서 트랙을 못 찾음", file=sys.stderr)
        sys.exit(1)

    if args.dump_sample_title:
        sample = titles[0]
        wikitext = get_wikitext(args.wiki_api, sample)
        print(f"=== '{sample}' 원본 위키텍스트 ===")
        print(wikitext)
        return

    out_path = Path(args.out)
    existing_titles: set[str] = set()
    if not args.dry_run and out_path.exists():
        with open(out_path, newline="", encoding="utf-8") as f:
            existing_titles = {r["Title"] for r in csv.DictReader(f)}
        print(f"[scrape] 이미 처리된 트랙 {len(existing_titles)}개는 건너뜀(캐시)")

    rows = []
    skipped_multi = 0
    skipped_none = 0
    to_process = [t for t in titles if t not in existing_titles]
    for i, title in enumerate(to_process):
        try:
            wikitext = get_wikitext(args.wiki_api, title)
        except requests.RequestException as e:
            print(f"  [{i+1}/{len(to_process)}] {title} -> 요청 실패({e}), 다음 실행 때 재시도", file=sys.stderr)
            continue
        if wikitext is None:
            skipped_none += 1
            continue
        leaves = extract_leaf_locations(wikitext)
        file_links, ext_links = extract_ext_and_file_links(wikitext)
        if len(leaves) == 0:
            skipped_none += 1
            status = "위치 정보 없음"
        elif len(leaves) > 1:
            skipped_multi += 1
            status = f"여러 위치({len(leaves)}개) - 건너뜀"
        else:
            status = f"-> {leaves[0]}"
            rows.append(
                {
                    "Title": title,
                    "LeafLocation": leaves[0],
                    "_file_links": str(file_links),
                    "_ext_links": str(ext_links),
                    "_source_page": title,
                    "_wiki_api": args.wiki_api,
                    "biome_category": "unclassified",
                    "game": args.game,
                }
            )
        print(f"  [{i+1}/{len(to_process)}] {title} {status}")
        time.sleep(0.2)

    print(
        f"\n[scrape] 이번 실행: 리프 위치 1개: {len(rows)} / 여러 개라 건너뜀: {skipped_multi} "
        f"/ 위치 정보 없어서 건너뜀: {skipped_none}"
    )

    if args.dry_run:
        for r in rows[:20]:
            print(r)
        return

    fieldnames = [
        "Title",
        "LeafLocation",
        "_file_links",
        "_ext_links",
        "_source_page",
        "_wiki_api",
        "biome_category",
        "game",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not out_path.exists() or not existing_titles
    with open(out_path, "a" if not is_new else "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if is_new:
            writer.writeheader()
        writer.writerows(rows)
    total = len(existing_titles) + len(rows)
    print(f"[scrape] {len(rows)}개 신규 추가, 누적 {total}개 트랙을 {args.out}에 저장함")


if __name__ == "__main__":
    main()
