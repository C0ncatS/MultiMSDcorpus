# MultiMSD Corpus

* This corpus was constructed by collecting article pairs from the professional and consumer versions of the [MSD Manuals](https://www.msdmanuals.com/) and performing embedding-based sentence alignment.
* The original [MultiMSD paper](https://aclanthology.org/2025.findings-acl.481.pdf) covers nine languages (German, English, Spanish, French, Italian, Japanese, Portuguese, Russian, and Chinese). **This repository currently supports English only.**
* Here, we release the code to automatically build the corpus.

# Directory Structure

Place `run.sh`, `run_rag.sh`, and the `scripts` directory in the same root directory as shown below.

```
├── pyproject.toml
├── uv.lock
├── run.sh
├── run_rag.sh
└── scripts
    ├── alignment
    ├── collection
    ├── preprocess
    └── sentence_split
```

After scraping, raw text is written under `raw_data/en/`. Sentence splitting writes to `cleaned_data/en/`. Both use the same layout:

```
raw_data/en/  (or cleaned_data/en/)
├── professional/
│   └── section{N}/
│       └── {N}-{i}.pro
└── amateur/
    └── section{N}/
        └── {N}-{i}.ama
```

# Usage

Install dependencies with [uv](https://docs.astral.sh/uv/):

```
uv sync
```

## RAG pipeline (`run_rag.sh`)

Recommended path for building an English MSD corpus for RAG. Scrapes health-topics articles, keeps ENG-5 sections only, and sentence-splits each file independently (no professional/consumer pairing or alignment):

```
bash ./run_rag.sh
```

This runs:

1. `scripts/collection/get_multidata.py` — scrape MSD Manual health-topics
2. `scripts/sentence_split/sentence_split_rag_en.py` — sentence-split each `.pro` / `.ama` file on its own

### Collection (`get_multidata.py`)

* **Source:** professional and consumer [health-topics](https://www.msdmanuals.com/home/health-topics) section lists only (no separate symptoms-index crawl).
* **Pairing:** walks matching pro/consumer sections by index. Each topic is saved as `.pro` and/or `.ama` when that side exists; a matching slug on the other side is not required.
* **Sections kept:** ENG-5 `TopicFHead` headings only (case-insensitive):

| Professional | Consumer |
|---|---|
| Pathophysiology | Causes |
| Etiology | Diagnosis |
| Diagnosis | Symptoms |
| Symptoms and signs | Evaluation |
| Evaluation | |

* **Excluded from scraped text:** reference blocks (`References`, `General references`, inline `… reference` subsections), consumer **Did You Know** pearl callouts, and subsections titled **Physical examination**, **Interpretation of findings**, **Staging**, or **Screening**.
* **Raw file format:** `#` page title, `##` section headings, `###` subsections; MSD tables and lists are converted to markdown-style lines.

### Sentence splitting (`sentence_split_rag_en.py`)

Headers (`#` / `##` / `###`), markdown table lines (`| … |`), and list lines (`- …` / `1. …`) are kept as-is. Body paragraphs are tokenized with Stanza.

## Alignment pipeline (`run.sh`)

Original MultiMSD flow: scrape, sentence-split, align professional/consumer pairs, and write train/dev/test TSV files under `results/`:

```
bash ./run.sh
```

This runs `get_multidata.py`, then `sentence_split_en.py` (zips matching `.pro` / `.ama` filenames per section), alignment, and preprocessing.

> **Note:** `get_multidata.py` is shared with the RAG pipeline and applies the same ENG-5 health-topics filtering described above. One-sided articles (only `.pro` or only `.ama`) are not paired by `sentence_split_en.py`. The alignment pipeline was designed for the full paired corpus in the paper; results may differ from the original English dataset.

> The HTML structure of MSD Manuals may have changed since the original data collection, so the dataset you obtain may not be identical to the one used in the paper.

# References

* Koki Horiguchi, Tomoyuki Kajiwara, Takashi Ninomiya, Shoko Wakamiya, Eiji Aramaki.  
  MultiMSD: A Corpus for Multilingual Medical Text Simplification from Online Medical References.  
  ACL 2025 Findings. Vienna, Austria. July 2025. [[PDF](https://aclanthology.org/2025.findings-acl.481.pdf)]

* 堀口 航輝, 梶原 智之, 二宮 崇, 若宮 翔子, 荒牧 英治.  
  日本語医療テキスト平易化の訓練用データセットの構築.  
  人工知能学会第38回全国大会, 3S1-OS-7b, 2024. [[PDF](https://confit.atlas.jp/guide/event-img/jsai2024/3S1-OS-7b-04/public/pdf?type=in)]
