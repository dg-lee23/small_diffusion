

./scripts/scrape_and_classify.sh https://subnautica.fandom.com/api.php "Subnautica"  # 스크랩+분류 한 번에

#   -> classified/_review.csv 열어서 final_category 채우기
./scripts/review.sh --default-drop                                                # review 반영

./scripts/download.sh city_machine 
./scripts/download.sh cave_underground                             
./scripts/download.sh desert_rock
./scripts/download.sh forest_jungle 
./scripts/download.sh hell 
./scripts/download.sh sea_underwater
./scripts/download.sh snow_ice
./scripts/download.sh space 