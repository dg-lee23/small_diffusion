./scripts/setup.sh                                                # 1회, 의존성/ffmpeg/yt-dlp 확인

./scripts/scrape_and_classify.sh https://terraria.wiki.gg/api.php "Terraria"   # 스크랩+분류 한 번에

#   -> classified/_review.csv 열어서 final_category 채우기
./scripts/review.sh                                                # review 반영

./scripts/download.sh cave_underground                             # 카테고리별 오디오 다운로드