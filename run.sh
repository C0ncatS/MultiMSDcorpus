set -e

# data collection
python3 scripts/collection/get_multidata.py

# sentence split
python3 scripts/sentence_split/sentence_split_en.py

# alignment
python3 scripts/alignment/auto_alignment.py en 0.7

# preprocess
bash scripts/preprocess/preprocess.sh
