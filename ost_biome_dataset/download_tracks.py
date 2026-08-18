"""wiki_scraper.py가 만든 트랙 CSV를 받아 실제 오디오를 내려받는다.

소스 우선순위 (오탐/봇차단 위험이 낮은 순):
    1. _file_links — 위키에 업로드된 오디오 파일([[File:...]]). MediaWiki API로
       실제 파일 URL을 알아내 requests로 직접 받는다. yt-dlp도, 유튜브 봇 체크도
       필요 없고 검색 오탐 위험도 없다. (단, 일부 위키는 저작권상 전체 트랙이 아니라
       짧은 프리뷰 클립만 올려두기도 하니 다운로드 후 길이를 확인할 것)
    2. _ext_links — 위키 문서에 적힌 유튜브 등 외부 링크. yt-dlp로 그대로 받는다.
    3. 위 둘 다 없으면 "{game} {track_title} official soundtrack"으로 yt-dlp 검색
       (ytsearch1:)을 돌려 최상위 결과를 받는다. 오탐 가능성이 가장 크므로 --dry-run
       으로 먼저 어떤 결과가 골라지는지 확인할 것을 권장.

요구사항: yt-dlp가 PATH에 설치되어 있어야 함 (pip install yt-dlp).

사용 예:
    python download_tracks.py --in tracks.csv --out-dir audio/cave_underground \
        --metadata-out metadata.csv --dry-run
"""

import argparse
import ast
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

import requests

USER_AGENT = "ost-biome-dataset-bot/0.1 (research/personal dataset project)"
TRACK_TITLE_KEYS = ["Track", "Title", "Name", "Song", "title"]


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


def _resolve_source_url(row: dict) -> str:
    ext_links = _parse_list_cell(row.get("_ext_links"))
    if ext_links:
        return ext_links[0]
    game = row.get("game", "")
    title = _guess_title(row)
    return f"ytsearch1:{game} {title} official soundtrack"


def download_one(source: str, out_path: Path, dry_run: bool, cookies_from_browser: str = None, cookies_file: str = None) -> Optional[dict]:
    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--no-playlist",
        "-o", str(out_path.with_suffix(".%(ext)s")),
        "--print-json",
        source,
    ]
    if cookies_from_browser:
        cmd += ["--cookies-from-browser", cookies_from_browser]
    if cookies_file:
        cmd += ["--cookies", cookies_file]
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
    # --print-json은 여러 줄을 낼 수 있음(플레이리스트류); 마지막 유효 JSON 줄 사용
    for line in reversed(result.stdout.strip().splitlines()):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


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
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(args.in_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.limit:
        rows = rows[: args.limit]

    metadata_rows = []
    for i, row in enumerate(rows):
        title = _guess_title(row) or f"track_{i}"
        safe_name = "".join(c for c in title if c.isalnum() or c in " _-").strip()[:80] or f"track_{i}"
        out_path = out_dir / safe_name

        wiki_api = row.get("_wiki_api") or args.wiki_api
        filenames = _parse_list_cell(row.get("_file_links"))
        kind, source, info = "ytdlp", None, None

        if filenames and wiki_api:
            try:
                direct_url = _mediawiki_file_url(wiki_api, filenames[0])
            except requests.RequestException as e:
                print(f"[!] 위키 파일 조회 실패({filenames[0]}): {e}", file=sys.stderr)
                direct_url = None
            if direct_url:
                kind, source = "direct", direct_url

        if source is None:
            source = _resolve_source_url(row)

        print(f"[{i+1}/{len(rows)}] {row.get('game','?')} :: {title}  <- [{kind}] {source}")

        if kind == "direct":
            try:
                info = _download_direct(source, out_path, args.dry_run)
            except requests.RequestException as e:
                print(f"[!] 직접 다운로드 실패: {source}\n{e}", file=sys.stderr)
                info = None
        else:
            info = download_one(source, out_path, args.dry_run, args.cookies_from_browser, args.cookies_file)

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
