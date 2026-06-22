python3 scripts/preprocess/file_concat_base.py en
python3 scripts/preprocess/file_concat.py en

python3 scripts/preprocess/preprocess.py en train
python3 scripts/preprocess/preprocess.py en dev
python3 scripts/preprocess/preprocess.py en test