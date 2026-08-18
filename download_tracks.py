"""wiki_scraper.py가 만든 트랙 CSV를 받아 실제 오디오를 내려받는다.

각 행에 유튜브 등 외부 링크(_ext_links)가 있으면 그 링크를 그대로 사용하고,
없으면 "{game} {track_title} official soundtrack"으로 yt-dlp 검색을 돌려
최상위 결과를 사용한다. 검색 폴백은 오탐 가능성이 있으므로 --dry-run으로
먼저 어떤 URL이 골라지는지 확인할 것을 권장.

요구사항: yt-dlp가 PATH에 설치되어 있어야 함 (pip install yt-dlp).

사용 예:
    python download_tracks.py --in tracks.csv --out-dir audio/cave_underground \
        --metadata-out metadata.csv --dry-run
"""

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

TRACK_TITLE_KEYS = ["Track", "Title", "Name", "Song"]


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


def _resolve_source_url(row: dict) -> str:
    ext_links = row.get("_ext_links")
    if ext_links:
        # CSV에는 문자열로 저장되어 있을 수 있음 (리스트를 str()로 찍은 경우) — 첫 URL만 추출
        if isinstance(ext_links, str):
            ext_links = [u.strip(" '\"[]") for u in ext_links.split(",") if u.strip()]
        if ext_links:
            return ext_links[0]
    game = row.get("game", "")
    title = _guess_title(row)
    return f"ytsearch1:{game} {title} official soundtrack"


def download_one(source: str, out_path: Path, dry_run: bool) -> Optional[dict]:
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
        source = _resolve_source_url(row)
        out_path = out_dir / safe_name

        print(f"[{i+1}/{len(rows)}] {row.get('game','?')} :: {title}  <- {source}")
        info = download_one(source, out_path, args.dry_run)

        metadata_rows.append(
            {
                "game": row.get("game", ""),
                "biome_category": row.get("biome_category", ""),
                "source_page": row.get("_source_page", ""),
                "track_title": title,
                "source": source,
                "resolved_title": info.get("title", "") if info else "",
                "duration_sec": info.get("duration", "") if info else "",
                "local_path": "" if args.dry_run else str(out_path.with_suffix(".mp3")),
            }
        )

    with open(args.metadata_out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(metadata_rows[0].keys()) if metadata_rows else [])
        writer.writeheader()
        writer.writerows(metadata_rows)
    print(f"\n메타데이터 {len(metadata_rows)}건을 {args.metadata_out}에 저장함")


if __name__ == "__main__":
    main()