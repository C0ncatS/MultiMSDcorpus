import os
import re
import stanza

DATA_DIR = "raw_data/en"
CLEANED_DIR = "cleaned_data/en"

HEADER_LINE_RE = re.compile(r"^#+\s")
MARKDOWN_TABLE_LINE_RE = re.compile(r"^\|")
MARKDOWN_LIST_LINE_RE = re.compile(r"^\s*(-|\d+\.)\s")

stanza.download("en")
segmenter = stanza.Pipeline(
    "en",
    processors="tokenize",
    download_method=stanza.DownloadMethod.REUSE_RESOURCES,
)


def _normalize_body_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s([?.!,:;])", r"\1", text)
    text = re.sub(r"(\() ", r"\1", text)
    text = re.sub(r" (\))", r"\1", text)
    return text.strip()


def _ends_sentence(text: str) -> bool:
    stripped = text.rstrip()
    return bool(stripped) and stripped[-1] in ".?!"


def _write_stanza_sentences(text: str, output_file) -> None:
    text = _normalize_body_text(text)
    if not text:
        return
    doc = segmenter(text)
    for sentence in doc.sentences:
        sentence_text = sentence.text
        sentence_text = re.sub(
            r": [A-Z]", lambda match: match.group(0).replace(" ", "\n"), sentence_text
        )
        output_file.write(sentence_text + "\n")


def _flush_body(accumulator: str, output_file) -> str:
    if accumulator.strip():
        _write_stanza_sentences(accumulator, output_file)
    return ""


def _process_and_write(input_file, output_file) -> None:
    accumulator = ""
    for raw_line in input_file:
        line = raw_line.rstrip("\n")
        if not line.strip():
            continue

        if HEADER_LINE_RE.match(line):
            accumulator = _flush_body(accumulator, output_file)
            header_text = HEADER_LINE_RE.sub("", line, count=1).strip()
            output_file.write(header_text + "\n")
            continue

        if MARKDOWN_TABLE_LINE_RE.match(line):
            accumulator = _flush_body(accumulator, output_file)
            output_file.write(line + "\n")
            continue

        if MARKDOWN_LIST_LINE_RE.match(line):
            accumulator = _flush_body(accumulator, output_file)
            output_file.write(line + "\n")
            continue

        if accumulator and not _ends_sentence(accumulator):
            accumulator = f"{accumulator} {line.strip()}"
            if _ends_sentence(accumulator):
                accumulator = _flush_body(accumulator, output_file)
            continue

        if accumulator:
            accumulator = _flush_body(accumulator, output_file)

        accumulator = line.strip()
        if _ends_sentence(accumulator):
            accumulator = _flush_body(accumulator, output_file)

    _flush_body(accumulator, output_file)


def process_side(side: str, section_name: str) -> int:
    input_dir = os.path.join(DATA_DIR, side, section_name)
    output_dir = os.path.join(CLEANED_DIR, side, section_name)
    if not os.path.isdir(input_dir):
        return 0

    os.makedirs(output_dir, exist_ok=True)
    processed = 0
    for filename in sorted(os.listdir(input_dir)):
        input_path = os.path.join(input_dir, filename)
        if not os.path.isfile(input_path):
            continue
        output_path = os.path.join(output_dir, filename)
        with open(input_path, "r", encoding="utf-8") as input_file, open(
            output_path, "w", encoding="utf-8"
        ) as output_file:
            _process_and_write(input_file, output_file)
        processed += 1
    return processed


def discover_sections() -> list[str]:
    sections: set[str] = set()
    for side in ("professional", "amateur"):
        side_dir = os.path.join(DATA_DIR, side)
        if not os.path.isdir(side_dir):
            continue
        for name in os.listdir(side_dir):
            if name.startswith("section"):
                sections.add(name)

    def sort_key(section_name: str) -> tuple[int, str | int]:
        suffix = section_name.removeprefix("section")
        if suffix.isdigit():
            return (0, int(suffix))
        return (1, section_name)

    return sorted(sections, key=sort_key)


def main():
    for section_name in discover_sections():
        pro_count = process_side("professional", section_name)
        ama_count = process_side("amateur", section_name)
        if pro_count or ama_count:
            print(f"{section_name}: {pro_count} pro, {ama_count} ama")


if __name__ == "__main__":
    main()
