"""wiki_scraper.py가 만든 트랙 CSV를 받아 실제 오디오를 내려받는다.

소스 우선순위 (오탐/봇차단 위험이 낮은 순, 실패하면 자동으로 다음 순위 시도):
    1. _file_links — 위키에 업로드된 오디오 파일([[File:...]]). MediaWiki API로
       실제 파일 URL을 알아내 requests로 직접 받는다. yt-dlp도, 유튜브 봇 체크도
       필요 없고 검색 오탐 위험도 없다. (단, 일부 위키는 저작권상 전체 트랙이 아니라
       짧은 프리뷰 클립만 올려두기도 하니 다운로드 후 길이를 확인할 것)
    2. _ext_links — 위키 문서에 적힌 유튜브 등 외부 링크. yt-dlp로 그대로 받는다.
       (오래된 위키 문서면 이 링크가 죽어있는 경우가 흔함 — "Video unavailable",
       "Private video" 등. 실패하면 3번으로 자동 폴백한다.)
    3. 위 둘 다 없거나 실패하면 "{game} {track_title} official soundtrack"으로
       유튜브를 검색해 최대 SEARCH_CANDIDATES개(기본 5개) 후보를 살펴보고, 그 중
       제목을 정규화(공백/구두점 제거, 대소문자 무시)했을 때 트랙 제목을 그대로
       포함하면서 길이가 MAX_SEARCH_RESULT_DURATION_SEC(기본 10분) 미만인 첫
       후보만 받는다. 엉뚱한 영상(모음집, 커버, 무관 영상)을 피하려는 엄격한
       제목 매칭이라, 조건에 맞는 후보가 하나도 없으면 억지로 고르지 않고
       건너뛴다.

요구사항: yt-dlp가 PATH에 설치되어 있어야 함 (pip install yt-dlp).

여기 정의되지 않은 옵션은 에러 없이 그대로 yt-dlp에 전달된다. 예를 들어 유튜브의
n-challenge 관련 에러("n challenge solving failed", "The page needs to be reloaded")가
나면 yt-dlp를 최신으로 업데이트한 뒤(pip install -U yt-dlp) 그래도 안 되면 아래처럼
클라이언트를 바꿔서 우회할 수 있다:
    python download_tracks.py --in tracks.csv --out-dir audio/cave_underground \
        --extractor-args "youtube:player_client=android"

사용 예:
    python download_tracks.py --in tracks.csv --out-dir audio/cave_underground \
        --metadata-out metadata.csv --dry-run
"""

import argparse
import ast
import csv
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

import requests

USER_AGENT = "ost-biome-dataset-bot/0.1 (research/personal dataset project)"
TRACK_TITLE_KEYS = ["Track", "Title", "Name", "Song", "title"]


def _read_csv_rows(path) -> list[dict]:
    """CSV를 읽되 UTF-8이 아니어도 최대한 읽어낸다 (Excel 등에서 편집 후 cp1252로
    저장되는 경우가 흔함 — classify_tracks.py의 동명 함수와 동일한 로직)."""
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


def _guess_title(row: dict) -> str:
    for key in TRACK_TITLE_KEYS:
        if row.get(key):
            return row[key]
    # fallback: 첫 번째 값이 그럴듯한 컬럼
    for k, v in row.items():
        if k.startswith("_") or k in ("game", "biome_category", "_source_page"):
            continue
        if v:
            return v
    return ""


def _parse_list_cell(value) -> list[str]:
    """CSV에 str(list)로 저장된 값을 복원. 이미 list면 그대로."""
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


def _mediawiki_file_url(wiki_api: str, filename: str) -> Optional[str]:
    """위키에 업로드된 File:filename의 실제 다운로드 URL을 조회."""
    resp = requests.get(
        wiki_api,
        params={
            "action": "query",
            "titles": f"File:{filename}",
            "prop": "imageinfo",
            "iiprop": "url",
            "format": "json",
        },
        headers={"User-Agent": USER_AGENT},
        timeout=30,
    )
    resp.raise_for_status()
    pages = resp.json().get("query", {}).get("pages", {})
    for page in pages.values():
        info = page.get("imageinfo")
        if info:
            return info[0]["url"]
    return None


def _download_direct(url: str, out_path: Path, dry_run: bool) -> Optional[dict]:
    """위키가 직접 호스팅하는 오디오 파일을 requests로 그대로 받는다."""
    ext = Path(url.split("?")[0]).suffix or ".mp3"
    final_path = out_path.with_suffix(ext)
    if dry_run:
        resp = requests.head(url, allow_redirects=True, timeout=30, headers={"User-Agent": USER_AGENT})
        return {"title": final_path.stem, "duration": "", "_local_path": ""}
    resp = requests.get(url, timeout=60, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    final_path.write_bytes(resp.content)
    return {"title": final_path.stem, "duration": "", "_local_path": str(final_path)}


MAX_SEARCH_RESULT_DURATION_SEC = 600  # 검색 폴백에서 받을 최대 길이 (10분)
SEARCH_CANDIDATES = 5  # 검색 폴백에서 제목/길이 조건을 확인할 최대 후보 수 (검색 깊이)


def _normalize_title(s: str) -> str:
    """공백/구두점 차이, 대소문자 차이를 무시하고 비교하기 위한 정규화."""
    return re.sub(r"\W+", "", s or "").lower()


def download_one(
    source: str,
    out_path: Path,
    dry_run: bool,
    cookies_from_browser: str = None,
    cookies_file: str = None,
    extra_yt_dlp_args: list = None,
) -> Optional[dict]:
    """이미 확정된 단일 영상 URL(source)의 오디오를 내려받는다. 검색이나 제목/길이
    매칭은 이 함수 밖(_search_candidates/_pick_matching_candidate)에서 끝내고,
    검증된 구체 URL만 여기로 넘어와야 한다."""
    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "-o", str(out_path.with_suffix(".%(ext)s")),
        "--print-json",
        "--no-playlist",
        source,
    ]
    if cookies_from_browser:
        cmd += ["--cookies-from-browser", cookies_from_browser]
    if cookies_file:
        cmd += ["--cookies", cookies_file]
    if extra_yt_dlp_args:
        cmd += extra_yt_dlp_args
    if dry_run:
        cmd.insert(1, "--simulate")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except FileNotFoundError:
        print("[!] yt-dlp가 설치되어 있지 않습니다: pip install yt-dlp", file=sys.stderr)
        sys.exit(1)
    if result.returncode != 0:
        print(f"[!] 다운로드 실패: {source}\n{result.stderr[-500:]}", file=sys.stderr)
        return None
    for line in reversed(result.stdout.strip().splitlines()):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


def _search_candidates(
    game: str,
    title: str,
    num_candidates: int,
    cookies_from_browser: str = None,
    cookies_file: str = None,
    extra_yt_dlp_args: list = None,
) -> list[dict]:
    """"{game} {title} official soundtrack"으로 유튜브를 검색해 상위 num_candidates개의
    메타데이터(제목/길이/URL)를 가져온다. --no-playlist를 주지 않아야 ytsearchN:의
    N개 결과를 전부 순회한다(--no-playlist를 주면 사실상 1개짜리 검색이 되어버림)."""
    query = f"ytsearch{num_candidates}:{game} {title} official soundtrack"
    cmd = ["yt-dlp", "--simulate", "--print-json", "--no-warnings"]
    if cookies_from_browser:
        cmd += ["--cookies-from-browser", cookies_from_browser]
    if cookies_file:
        cmd += ["--cookies", cookies_file]
    if extra_yt_dlp_args:
        cmd += extra_yt_dlp_args
    cmd.append(query)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        print("[!] yt-dlp가 설치되어 있지 않습니다: pip install yt-dlp", file=sys.stderr)
        sys.exit(1)
    candidates = []
    for line in result.stdout.strip().splitlines():
        try:
            candidates.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return candidates


def _pick_matching_candidate(candidates: list[dict], title: str) -> Optional[dict]:
    """정규화한 제목이 그대로 포함되고(느슨한 키워드/토큰 매칭이 아님) 길이가
    MAX_SEARCH_RESULT_DURATION_SEC 미만인 첫 후보만 고른다. 엉뚱한 영상(전체 OST
    모음집, 커버, 무관 영상)을 억지로 고르지 않기 위한 엄격 매칭 — 조건에 맞는
    후보가 없으면 None을 반환하고 호출부가 건너뛰게 한다."""
    wanted = _normalize_title(title)
    if not wanted:
        return None
    for c in candidates:
        duration = c.get("duration") or 0
        if duration and duration >= MAX_SEARCH_RESULT_DURATION_SEC:
            continue
        if wanted not in _normalize_title(c.get("title", "")):
            continue
        return c
    return None


def _resolve_and_download(
    row: dict, title: str, out_path: Path, args, extra_yt_dlp_args: list
) -> tuple[str, str, Optional[dict]]:
    """소스 우선순위(직접 파일 -> 위키 외부 링크 -> 제목/길이 엄격 매칭 검색)대로
    시도하고, 앞 단계가 실패하면 자동으로 다음 단계로 폴백한다.
    반환값: (kind, source, info) — info가 None이면 최종적으로도 실패한 것."""
    game = row.get("game", "")
    wiki_api = row.get("_wiki_api") or args.wiki_api
    filenames = _parse_list_cell(row.get("_file_links"))
    ext_links = _parse_list_cell(row.get("_ext_links"))

    if filenames and wiki_api:
        direct_url = None
        try:
            direct_url = _mediawiki_file_url(wiki_api, filenames[0])
        except requests.RequestException as e:
            print(f"[!] 위키 파일 조회 실패({filenames[0]}): {e}", file=sys.stderr)
        if direct_url:
            try:
                info = _download_direct(direct_url, out_path, args.dry_run)
            except requests.RequestException as e:
                print(f"[!] 직접 다운로드 실패: {direct_url}\n{e}", file=sys.stderr)
                info = None
            if info is not None:
                return "direct", direct_url, info
            print(f"  [!] 위키 파일 다운로드 실패, 다음 순위로 폴백: {title}", file=sys.stderr)

    if ext_links:
        source = ext_links[0]
        info = download_one(
            source, out_path, args.dry_run, args.cookies_from_browser, args.cookies_file, extra_yt_dlp_args
        )
        if info is not None:
            return "ext_link", source, info
        print(f"  [!] 위키 외부 링크 다운로드 실패({source}), 검색으로 폴백: {title}", file=sys.stderr)

    candidates = _search_candidates(
        game, title, SEARCH_CANDIDATES, args.cookies_from_browser, args.cookies_file, extra_yt_dlp_args
    )
    match = _pick_matching_candidate(candidates, title)
    if match is None:
        print(
            f"  [!] 제목이 정확히 포함되고 {MAX_SEARCH_RESULT_DURATION_SEC // 60}분 미만인 검색 결과를 "
            f"못 찾음(후보 {len(candidates)}개 확인): {title}",
            file=sys.stderr,
        )
        return "search_failed", "", None
    source = match.get("webpage_url") or f"https://www.youtube.com/watch?v={match.get('id')}"
    info = download_one(
        source, out_path, args.dry_run, args.cookies_from_browser, args.cookies_file, extra_yt_dlp_args
    )
    return "search", source, info


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="in_csv", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--metadata-out", default="metadata.csv")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None, help="테스트용: 상위 N개만 처리")
    ap.add_argument(
        "--cookies-from-browser",
        help="유튜브 봇 차단(Sign in to confirm you're not a bot) 회피용. 예: chrome, firefox, edge, brave. "
        "해당 브라우저에 유튜브 로그인이 되어 있어야 함.",
    )
    ap.add_argument("--cookies-file", help="브라우저 확장으로 내보낸 cookies.txt 경로 (위 옵션 대안)")
    ap.add_argument(
        "--wiki-api",
        help="CSV에 _wiki_api 컬럼이 없는 경우(예: 구버전 스크래퍼로 만든 CSV)를 위한 폴백 값",
    )
    # 여기 정의 안 된 옵션은 에러 내지 않고 그대로 yt-dlp에 전달한다
    # (예: --extractor-args "youtube:player_client=android" 같은 우회 옵션).
    args, extra_yt_dlp_args = ap.parse_known_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = _read_csv_rows(args.in_csv)
    if args.limit:
        rows = rows[: args.limit]

    metadata_rows = []
    for i, row in enumerate(rows):
        title = _guess_title(row) or f"track_{i}"
        safe_name = "".join(c for c in title if c.isalnum() or c in " _-").strip()[:80] or f"track_{i}"
        out_path = out_dir / safe_name

        print(f"[{i+1}/{len(rows)}] {row.get('game','?')} :: {title}")
        kind, source, info = _resolve_and_download(row, title, out_path, args, extra_yt_dlp_args)
        print(f"  -> [{kind}] {source or '(없음)'}")

        local_path = ""
        if not args.dry_run and info:
            local_path = info.get("_local_path") or str(out_path.with_suffix(".mp3"))

        metadata_rows.append(
            {
                "game": row.get("game", ""),
                "biome_category": row.get("biome_category", ""),
                "source_page": row.get("_source_page", ""),
                "track_title": title,
                "source_kind": kind,
                "source": source,
                "resolved_title": info.get("title", "") if info else "",
                "duration_sec": info.get("duration", "") if info else "",
                "local_path": local_path,
            }
        )

    with open(args.metadata_out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(metadata_rows[0].keys()) if metadata_rows else [])
        writer.writeheader()
        writer.writerows(metadata_rows)
    print(f"\n메타데이터 {len(metadata_rows)}건을 {args.metadata_out}에 저장함")


if __name__ == "__main__":
    main()
