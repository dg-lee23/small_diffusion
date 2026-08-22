"""Genshin Impact 전용: 위치 설명(Overview 텍스트)을 LLM으로 5개 바이옴 카테고리 중
하나로 분류하거나, 명확히 안 맞으면 NONE으로 건너뛴다 (억지로 고르지 않음).

키워드 매칭 대신 Claude에게 설명 텍스트를 그대로 주고 판단하게 한다 — 다른 게임
데이터에서 실제로 있었던 키워드 오탐(예: "Frost Legion" 보스 이름 때문에 snow_ice로
잘못 걸리는 것) 문제를 피하기 위함.

로케이션당 한 번만 호출하고 결과를 캐싱한다(재실행해도 새 위치만 호출).

요구사항: pip install anthropic
    인증: ANTHROPIC_API_KEY 환경변수 또는 `ant auth login` 프로필.

사용 예:
    python llm_classify.py --in genshin_raw/location_overviews.csv \
        --out genshin_raw/location_categories.csv
"""

import argparse
import csv
import sys
from pathlib import Path

import anthropic

CATEGORIES = {
    "snow_ice": "Snow-covered, icy, glacial, or frozen mountain/tundra environments.",
    "underwater": "Submerged, underwater, undersea, or deep-sea environments (below the water's surface).",
    "cave_underground": "Caves, underground tunnels, dungeons, mines, or other subterranean areas.",
    "desert_rock": "Deserts, sand dunes, arid rocky terrain, or canyons.",
    "city_machine": "Modern or futuristic cities, industrial facilities, or mechanical/technological structures.",
}

SYSTEM_PROMPT = f"""You classify a game location's description into exactly one biome category, \
or NONE if it does not clearly and unambiguously match exactly one category.

Categories:
{chr(10).join(f"- {k}: {v}" for k, v in CATEGORIES.items())}

Rules:
- Only pick a category if the description clearly matches it. If it's ambiguous, generic \
(e.g. a plain town/village/forest/plaza that isn't specifically any of the above), or could \
fit multiple categories, answer NONE. When in doubt, answer NONE — do not force a pick.
- Respond with ONLY the category id (one of: {", ".join(CATEGORIES)}) or NONE. \
No explanation, no punctuation, nothing else."""


def classify_one(client: anthropic.Anthropic, model: str, name: str, overview: str) -> str:
    if not overview.strip():
        return "NONE"
    response = client.messages.create(
        model=model,
        max_tokens=20,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Location: {name}\n\nDescription:\n{overview}"}],
    )
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return text if text in CATEGORIES else "NONE"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="in_csv", required=True)
    ap.add_argument("--out", default="genshin_raw/location_categories.csv")
    ap.add_argument(
        "--model",
        default="claude-opus-5",
        help="분류에 쓸 모델. 대량 호출이라 비용/속도 신경쓰이면 claude-haiku-4-5로 낮춰도 됨.",
    )
    args = ap.parse_args()

    with open(args.in_csv, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    out_path = Path(args.out)
    results = {}
    if out_path.exists():
        with open(out_path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                results[r["LocationName"]] = r["Category"]

    to_classify = [r for r in rows if r["LocationName"] not in results]
    print(f"[classify] 새로 분류할 위치: {len(to_classify)}개 (캐시됨: {len(rows) - len(to_classify)}개)")

    client = anthropic.Anthropic()
    counts = {}
    for i, row in enumerate(to_classify):
        name = row["LocationName"]
        try:
            category = classify_one(client, args.model, name, row.get("OverviewText", ""))
        except anthropic.AuthenticationError:
            print("[!] API 키 인증 실패 — 중단합니다. ANTHROPIC_API_KEY를 확인하세요.", file=sys.stderr)
            break
        except anthropic.PermissionDeniedError:
            print("[!] API 키 권한 부족 — 중단합니다.", file=sys.stderr)
            break
        except (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            # 판단 실패일 뿐 "NONE 판단"이 아니므로 결과에 안 남기고 다음 실행 때 재시도되게 둔다.
            print(f"  [{i+1}/{len(to_classify)}] {name} -> 호출 실패({e}), 다음 실행 때 재시도", file=sys.stderr)
            continue

        results[name] = category
        counts[category] = counts.get(category, 0) + 1
        print(f"  [{i+1}/{len(to_classify)}] {name} -> {category}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["LocationName", "Category"])
        writer.writeheader()
        for name, category in results.items():
            writer.writerow({"LocationName": name, "Category": category})

    print(f"\n이번 실행 분류 결과: {counts}")
    print(f"누적 {len(results)}개 위치를 {args.out}에 저장함")


if __name__ == "__main__":
    main()
