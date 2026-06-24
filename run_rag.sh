#!/usr/bin/env bash
set -e

# Scrape ENG-5 sections from MSD Manuals (pro and/or consumer, no pairing required).
python3 scripts/collection/get_multidata.py

# Sentence-split each file independently for RAG chunking (no pro/ama pairing).
python3 scripts/sentence_split/sentence_split_rag_en.py
