"""MediaWiki 기반 게임 위키에서 OST 트랙 목록을 뽑아내는 스크래퍼.

Fandom(*.fandom.com)과 wiki.gg는 모두 MediaWiki 엔진이라 같은 API로 다룰 수 있다.
문서 제목을 하드코딩하지 않고 검색 API로 찾는 이유는, 위키 문서 제목이 종종
"Music", "Original Soundtrack", "<Game> Original Soundtrack" 등으로 게임마다
달라서 미리 확정하기 어렵기 때문이다 (games.yaml 참고).

사용 예:
    python wiki_scraper.py --wiki-api https://terraria.wiki.gg/api.php \
        --game "Terraria" --biome-category cave_underground --out tracks.csv

주의: 위키텍스트 표 파싱은 위키마다 컬럼 구성이 달라 완벽할 수 없다.
    --dry-run 으로 먼저 소량 확인 후 games.yaml의 zone_map을 다듬어 쓰는 것을 권장.
"""

import argparse
import csv
import re
import sys
import time
from typing import Optional

import requests

USER_AGENT = "ost-biome-dataset-bot/0.1 (research/personal dataset project)"


def _api_get(wiki_api: str, params: dict) -> dict:
    params = {**params, "format": "json"}
    resp = requests.get(wiki_api, params=params, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def search_music_pages(wiki_api: str, query: str = "Music OR Soundtrack OR OST", limit: int = 10) -> list[str]:
    """게임 위키에서 음악/사운드트랙 관련 문서 제목 후보를 검색한다."""
    data = _api_get(
        wiki_api,
        {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srlimit": limit,
        },
    )
    return [hit["title"] for hit in data.get("query", {}).get("search", [])]


def get_wikitext(wiki_api: str, title: str) -> Optional[str]:
    """문서의 원본 위키텍스트를 가져온다."""
    data = _api_get(
        wiki_api,
        {
            "action": "parse",
            "page": title,
            "prop": "wikitext",
            "redirects": 1,
        },
    )
    if "error" in data:
        return None
    return data["parse"]["wikitext"]["*"]


_ROW_SPLIT = re.compile(r"\n\|-")
_CELL_SPLIT = re.compile(r"\n\|(?!\|)|\|\|")
_WIKILINK = re.compile(r"\[\[(?:[^\|\]]*\|)?([^\]]+)\]\]")
_EXTLINK = re.compile(r"\[(https?://\S+)\s*([^\]]*)\]")
_FILELINK = re.compile(r"\[\[File:([^\|\]]+)")
_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
_CELL_ATTR = re.compile(r"^[^|]*\|(?!\|)")  # 셀 맨 앞의 'style="..." |' 같은 속성 prefix


def _clean_cell(cell: str) -> str:
    cell = cell.strip().lstrip("|!").strip()
    # {{anchor|...}}, {{footnote|...}} 같은 템플릿은 반복 제거 (단순 템플릿 중첩까지만 처리)
    prev = None
    while prev != cell:
        prev = cell
        cell = _TEMPLATE.sub("", cell)
    if _CELL_ATTR.match(cell) and "=" in cell.split("|", 1)[0]:
        cell = cell.split("|", 1)[1]
    cell = _WIKILINK.sub(r"\1", cell)
    cell = re.sub(r"'''?", "", cell)
    return cell.strip()


def parse_wikitables(wikitext: str) -> list[dict]:
    """위키텍스트 안의 {| ... |} 표들을 파싱해 행(row)을 dict 리스트로 반환.

    첫 행을 헤더로 사용한다. 위키마다 표 형식이 조금씩 달라 완벽하지 않으므로,
    반환값을 그대로 신뢰하지 말고 --dry-run으로 눈으로 확인할 것.
    """
    rows_out = []
    for table_match in re.finditer(r"\{\|(.*?)\n\|\}", wikitext, re.DOTALL):
        table_body = table_match.group(1)
        raw_rows = _ROW_SPLIT.split(table_body)
        header: list[str] = []
        for raw_row in raw_rows:
            raw_row = raw_row.strip()
            if not raw_row:
                continue
            # 첫 행은 "|- 이전 표 속성(class=... 등) + ! 헤더" 형태로 붙어 나올 수 있으므로
            # 줄 시작에 "!"가 있는지로 헤더 여부를 판단하고, 속성 접두부는 잘라낸다.
            is_header = bool(re.search(r"(?:^|\n)\s*!", raw_row))
            if is_header:
                first_bang = raw_row.find("!")
                raw_row = raw_row[first_bang:]
                cells_raw = re.split(r"\n!|\!\!", raw_row)
            else:
                cells_raw = _CELL_SPLIT.split(raw_row)
            cells = [_clean_cell(c) for c in cells_raw if _clean_cell(c)]
            if not cells:
                continue
            if is_header:
                header = cells
                continue
            if not header:
                continue
            row = {header[i] if i < len(header) else f"col{i}": v for i, v in enumerate(cells)}
            # 파일 링크(오디오 샘플)와 외부 링크(유튜브 등)는 별도로 보존
            file_links = _FILELINK.findall(raw_row)
            ext_links = [m.group(1) for m in _EXTLINK.finditer(raw_row)]
            if file_links:
                row["_file_links"] = file_links
            if ext_links:
                row["_ext_links"] = ext_links
            rows_out.append(row)
    return rows_out


def extract_tracks(wiki_api: str, title: str) -> list[dict]:
    wikitext = get_wikitext(wiki_api, title)
    if wikitext is None:
        return []
    return parse_wikitables(wikitext)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wiki-api", required=True, help="예: https://terraria.wiki.gg/api.php")
    ap.add_argument("--game", required=True)
    ap.add_argument("--biome-category", required=True, help="games.yaml의 카테고리 ID")
    ap.add_argument("--page-title", help="문서 제목을 알고 있으면 검색을 건너뛰고 바로 사용")
    ap.add_argument("--out", default="tracks.csv")
    ap.add_argument("--dry-run", action="store_true", help="CSV로 저장하지 않고 콘솔에 미리보기만 출력")
    args = ap.parse_args()

    titles = [args.page_title] if args.page_title else search_music_pages(args.wiki_api)
    if not titles:
        print(f"[!] '{args.game}' 위키에서 음악 관련 문서를 찾지 못함 ({args.wiki_api})", file=sys.stderr)
        sys.exit(1)

    all_rows = []
    for title in titles:
        rows = extract_tracks(args.wiki_api, title)
        for r in rows:
            r["_source_page"] = title
        all_rows.extend(rows)
        time.sleep(0.5)  # 위키 서버 예의상 rate limit

    if args.dry_run:
        for r in all_rows[:20]:
            print(r)
        print(f"\n총 {len(all_rows)}개 행 파싱됨 (문서: {titles})")
        return

    fieldnames = sorted({k for r in all_rows for k in r.keys()} | {"game", "biome_category", "_wiki_api"})
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in all_rows:
            r["game"] = args.game
            r["biome_category"] = args.biome_category
            r["_wiki_api"] = args.wiki_api  # download_tracks.py가 _file_links를 직접 다운로드할 때 필요
            writer.writerow(r)
    print(f"{len(all_rows)}개 행을 {args.out}에 저장함")


if __name__ == "__main__":
    main()
