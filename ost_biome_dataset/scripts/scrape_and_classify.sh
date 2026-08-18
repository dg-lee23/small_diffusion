#!/usr/bin/env bash
# scrape.sh + classify.sh를 한 번에 (게임 하나 기준)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

if [ $# -lt 2 ]; then
  echo "사용법: $0 <wiki_api_url> <game_name> [page_title]"
  echo "예:     $0 https://terraria.wiki.gg/api.php \"Terraria\""
  exit 1
fi

"$SCRIPT_DIR/scrape.sh" "$@"

GAME="$2"
SLUG=$(echo "$GAME" | tr '[:upper:] ' '[:lower:]_' | tr -cd '[:alnum:]_')
"$SCRIPT_DIR/classify.sh" "$ROOT_DIR/csv_raw/${SLUG}.csv"
