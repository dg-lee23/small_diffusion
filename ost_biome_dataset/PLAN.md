# 게임 OST 바이옴 데이터셋 구축 계획

## 0. 이 문서의 목적

기존 브레인스토밍(TV Tropes / 플레이리스트 / regex / 위키 4가지 전략, 게임 15선)을 검토하고,
"biome/테마 구분 명확 + OST 퀄리티 + 위키 정리 수준" 3가지 조건에 맞춰 구체적으로
좁힌 실행 계획이다. 4가지 전략 중에서는 **게임 위키 스크래핑이 압도적으로 우월**하다 —
TV Tropes는 트랙-바이옴 매핑이 산문 형태라 파싱이 지저분하고, 플레이리스트/regex는
큐레이터의 주관과 트랙명 표기 불일치에 좌우된다. 위키(특히 Fandom/wiki.gg류 MediaWiki
기반 위키)는 지역(Zone)-바이옴-트랙명이 이미 표/리스트로 구조화되어 있어 스크래핑
난이도가 가장 낮고 정확도가 가장 높다.

## 1. 카테고리 재정리 제안

원안의 7개 슬롯(숲/정글/설원,얼음산/사막,바위산/동굴,지하,폐광/바다,항구,수중,심해/현대도시,기계)은
"숲"과 "정글"이 음악적으로 뚜렷이 구분되지 않는 경우가 많아 **6개로 병합**할 것을 제안한다.
필요하면 나중에 세부 태그(하위 라벨)로 다시 쪼개면 된다.

| 카테고리 ID | 한글 라벨 | 비고 |
|---|---|---|
| `forest_jungle` | 숲 / 정글 | |
| `snow_ice` | 설원 / 얼음산 | |
| `desert_rock` | 사막 / 바위산 | |
| `cave_underground` | 동굴 / 지하 / 폐광 | |
| `sea_underwater` | 바다 / 항구 / 수중 / 심해 | |
| `city_machine` | 현대도시 / 기계 | 나머지 5개와 성격이 다름 (자연 바이옴이 아니라 인공물) — 아래 3번 참고 |

## 2. 카테고리별 추천 게임 (기준 재적용)

기준: **① 바이옴/구역 구분이 명확 ② OST가 잘 만들어짐 ③ 규모가 커서 위키에 곡이 체계적으로
정리됨.** 원안의 15선 중 조건에 약한 것(예: 동물의 숲 — 바이옴 구분 없음, 마비노기/테일즈위버 —
위키 정리 수준이 상대적으로 낮음)은 빼고, 조건에 강한 게임을 추가했다.

| 카테고리 | 1순위 추천 (바이옴=트랙이 사실상 1:1) | 보강용 (대형 MMORPG/시리즈로 물량 확보) |
|---|---|---|
| 숲/정글 | Ori and the Blind Forest/Will of the Wisps, Hollow Knight(Greenpath) | World of Warcraft, FFXIV, Genshin Impact, Xenoblade Chronicles, Monster Hunter, Pokémon |
| 설원/얼음산 | Ori(눈 지역), Celeste(설산 전체) | World of Warcraft, FFXIV, Genshin Impact, Monster Hunter, Xenoblade, Pokémon |
| 사막/바위산 | Journey(사막 전체), Zelda BOTW/TOTK(게루도) | World of Warcraft, FFXIV, Genshin Impact, Monster Hunter, Pokémon |
| 동굴/지하/폐광 | **Terraria (위키 Music 페이지가 문자 그대로 바이옴별로 정리됨)**, Hollow Knight | World of Warcraft(던전), Metroid Prime, Monster Hunter |
| 바다/항구/수중/심해 | **Subnautica (거의 완벽하게 바이옴=트랙 매핑)**, Zelda Wind Waker(게임 전체가 바다) | World of Warcraft(바슈지르), FFXIV, Genshin(폰타인), Endless Ocean |
| 현대도시/기계 | Mirror's Edge, Persona 5(도쿄), NieR:Automata(폐허도시/기계) | Final Fantasy VII Remake(미드가르), Cyberpunk 2077, Splatoon(잉코폴리스), World of Warcraft(스톰윈드/노움리건) |

**"현대도시/기계"는 다른 5개와 성격이 다르다.** 나머지는 자연 바이옴이라 대형 오픈월드/MMORPG
한두 개만으로도 100곡을 채우기 쉽지만, 이 카테고리는 자연 지형이 아니라 인공적 테마라
해당 게임 자체가 적다. **여기만 "게임 수를 늘리는" 전략이 아니라 "SF/도시 배경 JRPG·미소녀
게임의 개별 던전/구역 트랙까지 긁어모으는" 전략이 필요**하다. 100곡 목표가 가장 늦게
채워질 카테고리로 예상하고 우선순위를 낮게 잡는 게 현실적이다.

원안에 있던 메이플스토리/원신/WoW/FFXIV/라그나로크/테일즈위버/마비노기 중에서는
**원신, WoW, FFXIV**가 조건을 가장 잘 만족한다 (위키가 매우 체계적, 지역별 OST 앨범이
공식적으로 발매되어 앨범명=지역명=바이옴인 경우가 많음). 나머지 한국 MMORPG는 위키
정리 수준이 상대적으로 낮아 스크래핑 대비 수확이 적다.

## 3. Semi-Autonomous 파이프라인 설계

수작업이 필요한 지점을 최소 1곳(2단계)으로 줄이는 것이 핵심이다.

```
[1] 위키 문서 탐색 (자동)
     MediaWiki API(action=query&list=search)로 게임 위키에서
     "Music"/"Soundtrack"/"OST" 관련 문서를 검색 → 문서 제목 후보 확보

[2] 트랙-구역(Zone) 목록 추출 (자동) + 바이옴 라벨링 (반자동, 유일한 수작업)
     action=parse로 위키텍스트/표를 가져와 트랙명·구역명 파싱.
     Terraria/Subnautica처럼 구역명이 곧 바이옴이면 라벨링 불필요.
     WoW/FFXIV/원신처럼 구역명(예: "Dun Morogh")만 있으면
     게임당 1회, 구역→바이옴 매핑표(zone_map)를 사람이 작성.
     → 이 매핑표만 사람이 만들면, 그 게임의 수백 곡이 전부 자동 태깅됨
       (재사용 가능한 1회성 투자, 곡당 수작업이 아니라 "게임당" 수작업)

[3] 실제 오디오 확보 (자동)
     위키 문서에 트랙별 유튜브/공식 링크가 있으면 그대로 사용.
     없으면 yt-dlp로 "{게임명} OST {트랙명}"을 검색해 최상위 결과를 다운로드.
     (공식 채널/사운드트랙 재생목록 우선 필터링 권장)

[4] 메타데이터 정합 (자동)
     {game, zone, biome_category, track_title, source_url, local_path, duration}
     형태로 CSV/JSON 생성, 중복·리믹스·트레일러 음원 등을 제목 기반으로 1차 필터링.
```

**사람이 반드시 해야 하는 일**: 게임별 zone→biome 매핑표 작성(게임당 1회, 표 하나),
그리고 다운로드된 오디오 샘플 일부의 QA(잘못 매칭된 유튜브 검색 결과 솎아내기).
나머지(문서 탐색, 파싱, 다운로드, 메타데이터 생성)는 자동화 가능.

## 4. 현실적 타협

- 카테고리당 100곡 × 6카테고리 = 총 600곡 목표는 **forest_jungle / snow_ice / desert_rock /
  cave_underground**의 경우 WoW나 FFXIV 하나만으로도 충분히 채울 수 있을 만큼 여유롭다.
- **sea_underwater**는 Subnautica + WoW(바슈지르) + FFXIV + Genshin(폰타인)을 합치면 100곡
  달성 가능하나, 게임 수를 3~4개로 늘려야 한다.
- **city_machine**은 100곡이 빠듯할 수 있다 — 70~80곡 선에서 타협하거나, 조건을 살짝
  완화해 "네온/사이버펑크풍" 오리지널 게임 음악(비-OST, 라이선스 이슈 있음)까지 포함할지
  검토가 필요하다. 지금 단계에서는 우선순위를 가장 낮게 두고 나머지 5개 카테고리를
  먼저 채우는 순서를 권장.

## 5. 이 레포에 추가한 스타터 코드

`ost_biome_dataset/` 아래:
- `games.yaml` — 카테고리별 추천 게임과 위키 도메인 초안 (문서 제목은 하드코딩하지 않고
  런타임에 검색하도록 설계 — 위키 문서 제목은 자주 바뀌므로)
- `wiki_scraper.py` — MediaWiki API로 문서 검색 + 위키텍스트 파싱, 표에서 트랙/구역 추출
- `download_tracks.py` — 추출된 트랙 목록을 받아 yt-dlp로 오디오 다운로드 + 메타데이터 CSV 생성
- `requirements.txt`

**한계**: 이 세션의 샌드박스는 fandom.com / wiki.gg 등에 대한 아웃바운드 네트워크가
차단되어 있어(egress proxy) 실제 실행/검증을 하지 못했다. 코드는 MediaWiki API 스펙
기준으로 작성했으나, 로컬/네트워크가 열린 환경에서 먼저 `--dry-run`으로 소량 테스트해
보길 권장한다.
