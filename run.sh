set -e

# data collection
python3 scripts/collection/get_multidata.py

# sentence split
for lang in en;
do
    python3 scripts/sentence_split/sentence_split_$lang.py
done

# alignment
for lang in en;
do
    python3 scripts/alignment/auto_alignment.py $lang 0.7
done

# preprocess
bash scripts/preprocess/preprocess.sh
