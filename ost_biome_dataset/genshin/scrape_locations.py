"""Genshin Impact 전용: Soundtrack/List 페이지에서 트랙별 재생 위치(리프 로케이션)를 추출한다.

위키 구조 가정(검증 안 됨 — 이 세션은 genshin-impact.fandom.com 접속이 막혀 있어서
실제 페이지를 못 보고 짰다. --dry-run으로 먼저 소량 확인 필수):
    각 트랙이 레벨2 헤더("==트랙명==")로 구분되고, 그 본문 안에 "Open-World Locations"
    라는 문구 다음에 중첩된 위키 불릿 리스트(*, **, ***...)로 지역 계층
    (예: Fontaine > Sea of Bygone Eras)이 나온다고 가정한다. "리프 노드"는 바로 다음
    줄이 더 깊은 들여쓰기가 아닌 마지막 노드로 판정한다.

    이 가정이 틀리면 --dump-wikitext로 원본을 저장해서 실제 구조를 확인한 뒤
    split_track_chunks()/extract_leaf_locations()만 고치면 된다 — 이후 단계
    (fetch_overviews.py, llm_classify.py, build_dataset.py)는 이 스크립트가 만드는
    CSV 형식만 맞으면 안 건드려도 된다.

규칙:
    1. 리프 로케이션이 여러 개(한 트랙이 여러 지역에서 재생)면 건너뜀 — 포함 안 함
    2. 위치 정보를 아예 못 찾은 트랙도 건너뜀

사용 예:
    python scrape_locations.py --wiki-api https://genshin-impact.fandom.com/api.php \
        --page-title "Soundtrack/List" --dry-run
    python scrape_locations.py --wiki-api https://genshin-impact.fandom.com/api.php \
        --page-title "Soundtrack/List" --out genshin_raw/track_locations.csv \
        --dump-wikitext genshin_raw/soundtrack_list_wikitext.txt
"""

import argparse
import csv
import os
import re
import sys

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


_HEADING2 = re.compile(r"\n==\s*([^=\n]+?)\s*==\n")
_BULLET_LINE = re.compile(r"^(\*+)\s*(.*)$")
_WIKILINK = re.compile(r"\[\[(?:[^\|\]]*\|)?([^\]]+)\]\]")
_FILELINK = re.compile(r"\[\[File:([^\|\]]+)")
_EXTLINK = re.compile(r"\[(https?://\S+)\s*([^\]]*)\]")


def split_track_chunks(wikitext: str) -> list[tuple[str, str]]:
    """레벨2 헤더(==...==) 기준으로 트랙 단위 청크를 나눈다. (제목, 본문) 리스트."""
    wikitext = "\n" + wikitext  # 첫 헤더도 잡히도록
    matches = list(_HEADING2.finditer(wikitext))
    chunks = []
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(wikitext)
        chunks.append((title, wikitext[start:end]))
    return chunks


def extract_leaf_locations(chunk_text: str) -> list[str]:
    """"Open-World Locations" 아래 중첩 불릿 리스트에서 리프 노드 이름들을 추출."""
    idx = chunk_text.find("Open-World Locations")
    if idx == -1:
        return []
    after = chunk_text[idx:]
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


def extract_ext_and_file_links(chunk_text: str) -> tuple[list[str], list[str]]:
    file_links = _FILELINK.findall(chunk_text)
    ext_links = [m.group(1) for m in _EXTLINK.finditer(chunk_text)]
    return file_links, ext_links


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wiki-api", default="https://genshin-impact.fandom.com/api.php")
    ap.add_argument("--page-title", default="Soundtrack/List")
    ap.add_argument("--out", default="genshin_raw/track_locations.csv")
    ap.add_argument("--dump-wikitext", help="파싱 전에 원본 위키텍스트를 이 경로에 저장 (구조 확인/디버깅용)")
    ap.add_argument("--game", default="Genshin Impact")
    ap.add_argument("--dry-run", action="store_true", help="CSV로 저장하지 않고 콘솔에 미리보기만 출력")
    args = ap.parse_args()

    wikitext = get_wikitext(args.wiki_api, args.page_title)
    if wikitext is None:
        print(f"[!] '{args.page_title}' 문서를 못 찾음", file=sys.stderr)
        sys.exit(1)

    if args.dump_wikitext:
        os.makedirs(os.path.dirname(args.dump_wikitext) or ".", exist_ok=True)
        with open(args.dump_wikitext, "w", encoding="utf-8") as f:
            f.write(wikitext)
        print(f"[dump] 원본 위키텍스트를 {args.dump_wikitext}에 저장함 ({len(wikitext)}자)")

    chunks = split_track_chunks(wikitext)
    print(f"[scrape] 레벨2 헤더 기준 트랙 후보 {len(chunks)}개 발견")

    rows = []
    skipped_multi = 0
    skipped_none = 0
    for title, body in chunks:
        leaves = extract_leaf_locations(body)
        file_links, ext_links = extract_ext_and_file_links(body)
        if len(leaves) == 0:
            skipped_none += 1
            continue
        if len(leaves) > 1:
            skipped_multi += 1
            continue
        rows.append(
            {
                "Title": title,
                "LeafLocation": leaves[0],
                "_file_links": str(file_links),
                "_ext_links": str(ext_links),
                "_source_page": args.page_title,
                "_wiki_api": args.wiki_api,
                "biome_category": "unclassified",
                "game": args.game,
            }
        )

    print(
        f"[scrape] 리프 위치 1개인 트랙: {len(rows)} / 여러 개라 건너뜀: {skipped_multi} "
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
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"[scrape] {len(rows)}개 트랙을 {args.out}에 저장함")


if __name__ == "__main__":
    main()
