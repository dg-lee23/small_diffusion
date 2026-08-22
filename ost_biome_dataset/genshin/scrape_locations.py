"""Genshin Impact 전용: 트랙별 재생 위치(리프 로케이션)를 추출한다.

실제 구조(사용자가 보내준 실제 트랙 문서 위키텍스트로 확인함 — "A Day in Mondstadt"):
불릿 트리가 아니라 {{Soundtrack Usage}} 템플릿의 location 파라미터에 지역명과
시간대가 "//"로 붙은 단순 문자열로 들어있다. 예:
    {{Soundtrack Usage
    |quest    = City of Freedom//cutscene
    |location = Mondstadt City//day
    |eventgameplay = ...
    |teapot   = 4
    }}
"Mondstadt City//day"에서 앞부분(지역명)만 리프 위치로 쓰고, 뒷부분(day/night 등
시간대)은 버린다. (사용자가 브라우저에서 본 "트리"는 위키가 렌더링할 때 상위
지역 계층을 자동으로 붙여 보여준 것으로 보이고, 원본 위키텍스트 자체엔 계층이 없다.)

오디오 링크도 페이지 전체에서 URL을 긁으면 각주/참고링크(트위터, NetEase 등)까지
섞여 들어가므로, {{Soundtrack Infobox}} 템플릿의 youtube_id 파라미터에서 직접
정확한 유튜브 링크를 만든다. (이 위키는 공식 음반이라 [[File:...]] 오디오 파일을
직접 호스팅하지 않는 것으로 보임 — Terraria/MapleStory와 다름.)

이 스크립트는:
    1. MediaWiki API로 "Category:Soundtracks" 분류 멤버(=트랙 문서 제목) 목록을
       가져옴. "Category:Unreleased Soundtracks" 멤버는 기본적으로 제외 —
       Soundtrack/List 페이지의 "Released Soundtracks" 절과 동일한 필터.
       (참고: 이 분류엔 실제 탐험용 배경음악 외에 전투 테마/캐릭터 데모/스토리
       씬/프로모션 영상 음악도 섞여 있고, 그런 트랙은 애초에 location이 없어서
       정상적으로 건너뛰어진다 — 버그 아님.)
    2. 트랙 문서마다 위키텍스트를 가져와 위 template 파라미터들을 추출.

트랙 수가 많아 문서를 하나씩 가져오는 데 시간이 걸린다. --out 파일이 이미 있으면
거기 있는 Title은 재조회하지 않아서(캐싱) 중간에 끊겨도 이어서 할 수 있다.

규칙:
    1. 리프 로케이션이 여러 개(한 트랙이 여러 지역에서 재생)면 건너뜀 — 포함 안 함
    2. 위치 정보를 아예 못 찾은 트랙도 건너뜀

사용 예:
    # 먼저 트랙 하나로 구조 확인
    python scrape_locations.py --dump-sample-title "A Day in Mondstadt"
    # 본실행
    python scrape_locations.py --out genshin_raw/track_locations.csv
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


_WIKILINK = re.compile(r"\[\[(?:[^\|\]]*\|)?([^\]]+)\]\]")


def find_template_call(wikitext: str, template_name: str) -> str | None:
    """{{template_name ... }} 전체 호출부(중첩 {{}} 포함)를 텍스트로 찾아 반환."""
    m = re.search(r"\{\{\s*" + re.escape(template_name) + r"\s*[\|\n}]", wikitext, re.IGNORECASE)
    if not m:
        return None
    start = m.start()
    depth = 0
    i = start
    n = len(wikitext)
    while i < n - 1:
        two = wikitext[i : i + 2]
        if two == "{{":
            depth += 1
            i += 2
            continue
        if two == "}}":
            depth -= 1
            i += 2
            if depth == 0:
                return wikitext[start:i]
            continue
        i += 1
    return None


def _split_top_level_pipe(text: str) -> list[str]:
    """중첩된 {{...}}/[[...]] 안의 |는 무시하고 최상위 |로만 나눈다."""
    parts, buf, depth, i, n = [], [], 0, 0, len(text)
    while i < n:
        two = text[i : i + 2]
        if two in ("{{", "[["):
            depth += 1
            buf.append(two)
            i += 2
            continue
        if two in ("}}", "]]"):
            depth = max(0, depth - 1)
            buf.append(two)
            i += 2
            continue
        if text[i] == "|" and depth == 0:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(text[i])
        i += 1
    parts.append("".join(buf))
    return parts


def parse_template_params(template_call_text: str) -> dict[str, str]:
    """{{Name|k1=v1|k2=v2}}(멀티라인 가능)에서 파라미터 dict를 만든다."""
    inner = template_call_text.strip()
    if inner.startswith("{{") and inner.endswith("}}"):
        inner = inner[2:-2]
    parts = _split_top_level_pipe(inner)
    params = {}
    for part in parts[1:]:  # parts[0]은 템플릿 이름
        if "=" in part:
            k, v = part.split("=", 1)
            params[k.strip()] = v.strip()
    return params


_TIME_WORDS = {"day", "night", "dawn", "dusk", "morning", "evening", "afternoon"}


def extract_leaf_locations(wikitext: str) -> list[str]:
    """{{Soundtrack Usage}}의 location 파라미터에서 리프 위치를 뽑는다.
    "AreaName//day"처럼 //로 시간대가 붙어있으면 떼고 지역명만 쓴다. 시간대로
    보이지 않는 다른 구분이 있으면(여러 지역일 수 있음) 전부 별개 리프로 반환해서
    main()이 "여러 개"로 판단해 건너뛰게 한다."""
    call = find_template_call(wikitext, "Soundtrack Usage")
    if not call:
        return []
    params = parse_template_params(call)
    loc = params.get("location", "").strip()
    loc = _WIKILINK.sub(r"\1", loc)
    if not loc:
        return []
    parts = [p.strip() for p in loc.split("//") if p.strip()]
    if not parts:
        return []
    if len(parts) == 1:
        return [parts[0]]
    if len(parts) == 2 and parts[1].lower() in _TIME_WORDS:
        return [parts[0]]
    return parts


def extract_audio_link(wikitext: str) -> list[str]:
    """{{Soundtrack Infobox}}의 youtube_id로 정확한 유튜브 링크를 만든다."""
    call = find_template_call(wikitext, "Soundtrack Infobox")
    if not call:
        return []
    params = parse_template_params(call)
    yt = params.get("youtube_id", "").strip()
    if not yt:
        return []
    return [f"https://www.youtube.com/watch?v={yt}"]


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
    ap.add_argument(
        "--dump-sample-title",
        nargs="?",
        const="__first__",
        default=None,
        help="트랙 하나의 원본 위키텍스트를 콘솔에 출력하고 종료 (구조 확인용). "
        "값 없이 쓰면 카테고리의 첫 멤버, 특정 제목을 주면 그 문서를 바로 가져옴 "
        "(카테고리 멤버 목록 조회를 건너뛰므로 훨씬 빠름). "
        '예: --dump-sample-title "A Day in Mondstadt"',
    )
    ap.add_argument("--game", default="Genshin Impact")
    ap.add_argument("--dry-run", action="store_true", help="CSV로 저장하지 않고 콘솔에 미리보기만 출력")
    args = ap.parse_args()

    if args.dump_sample_title and args.dump_sample_title != "__first__":
        sample = args.dump_sample_title
        wikitext = get_wikitext(args.wiki_api, sample)
        print(f"=== '{sample}' 원본 위키텍스트 ===")
        print(wikitext if wikitext is not None else "[!] 문서를 못 찾음")
        return

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

    if args.dump_sample_title == "__first__":
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
        ext_links = extract_audio_link(wikitext)
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
                    "_file_links": "[]",
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
