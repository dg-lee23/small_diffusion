#!/usr/bin/env bash
# 1회성 환경 준비: pip 패키지 설치 + ffmpeg/yt-dlp 존재 확인
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo "[setup] Python 패키지 설치..."
pip install -r "$ROOT_DIR/requirements.txt"

if command -v ffmpeg >/dev/null 2>&1; then
  echo "[setup] ffmpeg 확인됨: $(command -v ffmpeg)"
else
  echo "[!] ffmpeg가 없습니다 (yt-dlp 오디오 추출에 필요)."
  echo "    macOS: brew install ffmpeg"
  echo "    Ubuntu/Debian: sudo apt install ffmpeg"
fi

if command -v yt-dlp >/dev/null 2>&1; then
  echo "[setup] yt-dlp 확인됨: $(command -v yt-dlp)"
else
  echo "[!] yt-dlp가 PATH에 없습니다 (pip install은 됐어도 PATH 문제일 수 있음)"
fi

echo "[setup] 완료."
