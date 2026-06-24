import json
import os
import re
import time
import urllib.parse
import urllib.request

from bs4 import BeautifulSoup

BASE_URL = "https://www.msdmanuals.com"
PRO_TOPICS_URL = f"{BASE_URL}/professional/health-topics"
HOME_TOPICS_URL = f"{BASE_URL}/home/health-topics"

OUTPUT_DIR = "raw_data"
ALL_LANGS = ["en"]

RE_TOPIC_URL = re.compile(r'"TopicUrl":{"path":"(.*?)"}')

SECTION_BODY_SELECTOR = (
    "span[class*=TopicHHead], span[class*=TopicGHead], span.TopicPara_topicText__CUB0d, "
    "span.TopicXLink_formatText__5UPAp, span[class*=TopicPara], span[class*=topicText]"
)
PRO_LINK_SELECTOR = "a[class*=professional]"
HOME_LINK_SELECTOR = "a[class*=home]"

# ENG-5: section headings to keep, matched against TopicFHead titles (case-insensitive).
PATHOPHYSIOLOGY_SECTION_PATTERN = re.compile(r"^pathophysiology\b", re.IGNORECASE)
ETIOLOGY_SECTION_PATTERN = re.compile(r"^etiology\b", re.IGNORECASE)
DIAGNOSIS_SECTION_PATTERN = re.compile(r"^diagnosis\b", re.IGNORECASE)
SYMPTOMS_AND_SIGNS_SECTION_PATTERN = re.compile(r"^symptoms and signs\b", re.IGNORECASE)
EVALUATION_SECTION_PATTERN = re.compile(r"^evaluation\b", re.IGNORECASE)
CAUSES_SECTION_PATTERN = re.compile(r"^causes\b", re.IGNORECASE)
SYMPTOMS_SECTION_PATTERN = re.compile(r"^symptoms\b", re.IGNORECASE)
PRO_HEALTH_SECTION_PATTERNS = (
    PATHOPHYSIOLOGY_SECTION_PATTERN,
    ETIOLOGY_SECTION_PATTERN,
    DIAGNOSIS_SECTION_PATTERN,
    SYMPTOMS_AND_SIGNS_SECTION_PATTERN,
    EVALUATION_SECTION_PATTERN,
)
HOME_HEALTH_SECTION_PATTERNS = (
    CAUSES_SECTION_PATTERN,
    DIAGNOSIS_SECTION_PATTERN,
    SYMPTOMS_SECTION_PATTERN,
    EVALUATION_SECTION_PATTERN,
)

# MSD reference blocks use section headings like "General references" or
# "Immune response references". Match the heading title only, not body text.
REFERENCE_SECTION_TITLE_RE = re.compile(
    r"^references$|^general\s+references$|^.+\s+references$",
    re.IGNORECASE,
)
# Inline footnote bibliographies under a section, e.g. "Etiology reference".
INLINE_REFERENCE_SUBSECTION_TITLE_RE = re.compile(r"^.+\s+reference$", re.IGNORECASE)
DID_YOU_KNOW_TITLE_RE = re.compile(r"^did you know", re.IGNORECASE)

# Markdown-style prefixes so sentence split can keep headers on their own lines.
PAGE_TITLE_PREFIX = "# "
SECTION_TITLE_PREFIX = "## "
SUBSECTION_TITLE_PREFIX = "### "
MARKDOWN_TABLE_PLACEHOLDER_CLASS = "MultiMSD-md-table"
MARKDOWN_LIST_PLACEHOLDER_CLASS = "MultiMSD-md-list"
LIST_SELECTOR = "ul[class*=TopicList], ol[class*=TopicList]"


def encode_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(parts.path, safe="/%")
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, path, parts.query, parts.fragment)
    )


def fetch_url(url: str) -> bytes:
    request = urllib.request.Request(
        encode_url(url),
        headers={"User-Agent": "Mozilla/5.0 (compatible; MultiMSDcorpus/1.0)"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def get_next_data(url: str) -> dict:
    soup = BeautifulSoup(fetch_url(url), "html.parser")
    script_tag = soup.select_one('script[id="__NEXT_DATA__"]')
    if script_tag is None or not script_tag.string:
        raise ValueError(f"No __NEXT_DATA__ found at {url}")
    return json.loads(script_tag.string)


def get_health_sections(url: str) -> list[dict]:
    data = get_next_data(url)
    for component in data["props"]["pageProps"]["componentProps"].values():
        if not isinstance(component, dict):
            continue
        items = component.get("data")
        if isinstance(items, list) and len(items) >= 20:
            return items
    return []


def get_topic_paths(section_path: str) -> list[str]:
    page_bytes = fetch_url(f"{BASE_URL}{section_path}")
    return RE_TOPIC_URL.findall(page_bytes.decode("utf-8"))


def topic_slug(path: str) -> str:
    return path.strip("/").split("/")[-1]


def build_topic_index(sections: list[dict]) -> dict[str, str]:
    by_slug: dict[str, str] = {}
    for section in sections:
        for path in get_topic_paths(section["relativeurlcomputed_s"]):
            slug = topic_slug(path)
            if slug not in by_slug:
                by_slug[slug] = path
    return by_slug


def section_patterns(is_professional: bool) -> tuple[re.Pattern[str], ...]:
    return (
        PRO_HEALTH_SECTION_PATTERNS if is_professional else HOME_HEALTH_SECTION_PATTERNS
    )


def ordered_section_slugs(pro_topics: list[str], home_topics: list[str]) -> list[str]:
    slugs: list[str] = []
    seen: set[str] = set()
    for path in pro_topics + home_topics:
        slug = topic_slug(path)
        if slug in seen:
            continue
        seen.add(slug)
        slugs.append(slug)
    return slugs


def resolve_section_paths(
    slug: str,
    pro_topics: list[str],
    home_topics: list[str],
    pro_by_slug: dict[str, str],
    home_by_slug: dict[str, str],
) -> tuple[str | None, str | None]:
    pro_path = next((path for path in pro_topics if topic_slug(path) == slug), None)
    if pro_path is None:
        pro_path = pro_by_slug.get(slug)

    home_path = next((path for path in home_topics if topic_slug(path) == slug), None)
    if home_path is None:
        home_path = home_by_slug.get(slug)

    return pro_path, home_path


def section_title_matches(title: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(title.strip()) for pattern in patterns)


def is_topic_fhead_header(element) -> bool:
    return element.name == "h2" and any(
        "TopicFHead" in class_name for class_name in element.get("class", [])
    )


def append_unique(lines: list[str], text: str, previous_line: str) -> str:
    if text and text != previous_line:
        lines.append(text)
        return text
    return previous_line


def format_element_line(element) -> str | None:
    text = element.get_text(strip=True)
    if not text:
        return None
    if element.name == "a":
        return text
    class_str = " ".join(element.get("class", []))
    if "TopicHHead" in class_str or "TopicGHead" in class_str:
        return f"{SUBSECTION_TITLE_PREFIX}{text}"
    return text


def escape_markdown_cell(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text.replace("|", "\\|")


def table_title(table) -> str:
    caption = table.select_one("caption")
    if caption is not None:
        title = caption.get_text(" ", strip=True)
        if title:
            return title

    wrap = table.find_parent(
        "div",
        class_=lambda class_names: bool(
            class_names
            and any("TopicTableView_tableWrap" in name for name in class_names)
        ),
    )
    if wrap is not None:
        previous = wrap.find_previous_sibling("div")
        if previous is not None:
            return previous.get_text(" ", strip=True)
    return ""


def table_to_markdown_lines(table) -> list[str]:
    rows: list[list[str]] = []
    for row in table.select("tr"):
        cells: list[str] = []
        for cell in row.select("th, td"):
            text = escape_markdown_cell(cell.get_text(" ", strip=True))
            colspan = int(cell.get("colspan", 1) or 1)
            cells.append(text)
            cells.extend([""] * (colspan - 1))
        if any(cell.strip() for cell in cells):
            rows.append(cells)

    if not rows:
        return []

    column_count = max(len(row) for row in rows)
    normalized_rows = [row + [""] * (column_count - len(row)) for row in rows]

    lines: list[str] = []
    title = table_title(table)
    if title and DID_YOU_KNOW_TITLE_RE.match(title.strip()):
        return []
    if title:
        lines.append(f"{SUBSECTION_TITLE_PREFIX}{title}")

    header = normalized_rows[0]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join("---" for _ in range(column_count)) + " |")
    for body_row in normalized_rows[1:]:
        lines.append("| " + " | ".join(body_row) + " |")
    return lines


def make_markdown_table_placeholder(table) -> BeautifulSoup:
    placeholder_soup = BeautifulSoup("", "html.parser")
    placeholder = placeholder_soup.new_tag("div")
    placeholder["class"] = [MARKDOWN_TABLE_PLACEHOLDER_CLASS]
    placeholder["data-md"] = "\n".join(table_to_markdown_lines(table))
    return placeholder


def list_item_text(list_item) -> str:
    item_soup = BeautifulSoup(str(list_item), "html.parser")
    item = item_soup.find("li")
    if item is None:
        return ""
    for nested_list in item.find_all(["ul", "ol"]):
        nested_list.decompose()
    return re.sub(r"\s+", " ", item.get_text(" ", strip=True))


def list_to_markdown_lines(list_element, depth: int = 0) -> list[str]:
    lines: list[str] = []
    indent = "  " * depth
    for index, list_item in enumerate(
        list_element.find_all("li", recursive=False), start=1
    ):
        text = list_item_text(list_item)
        if text:
            marker = f"{index}." if list_element.name == "ol" else "-"
            lines.append(f"{indent}{marker} {text}")
        for nested_list in list_item.find_all(["ul", "ol"], recursive=False):
            if not any(
                "TopicList" in class_name for class_name in nested_list.get("class", [])
            ):
                continue
            lines.extend(list_to_markdown_lines(nested_list, depth + 1))
    return lines


def make_markdown_list_placeholder(list_element) -> BeautifulSoup:
    placeholder_soup = BeautifulSoup("", "html.parser")
    placeholder = placeholder_soup.new_tag("div")
    placeholder["class"] = [MARKDOWN_LIST_PLACEHOLDER_CLASS]
    placeholder["data-md"] = "\n".join(list_to_markdown_lines(list_element))
    return placeholder


def is_nested_topic_list(list_element) -> bool:
    parent_list = list_element.find_parent(["ul", "ol"])
    if parent_list is None:
        return False
    return any("TopicList" in class_name for class_name in parent_list.get("class", []))


def is_did_you_know_table(table) -> bool:
    class_names = " ".join(table.get("class", []))
    if "didYouKnow" in class_names:
        return True
    title = table_title(table)
    return bool(title and DID_YOU_KNOW_TITLE_RE.match(title.strip()))


def inject_markdown_table_placeholders(nodes) -> None:
    for node in nodes:
        for popup in list(node.select("div[class*=PopupTable_container]")):
            table = popup.select_one("table[class*=TopicTableView]")
            if table is None:
                continue
            if is_did_you_know_table(table):
                popup.decompose()
                continue
            popup.replace_with(make_markdown_table_placeholder(table))

        for table in list(node.select("table[class*=TopicTableView]")):
            if is_did_you_know_table(table):
                table.decompose()
                continue
            table.replace_with(make_markdown_table_placeholder(table))


def inject_markdown_list_placeholders(nodes) -> None:
    for node in nodes:
        for list_element in list(node.select(LIST_SELECTOR)):
            if is_nested_topic_list(list_element):
                continue
            list_element.replace_with(make_markdown_list_placeholder(list_element))


def extract_lines_from_nodes(nodes, link_selector: str) -> list[str]:
    lines: list[str] = []
    previous_line = ""
    inject_markdown_table_placeholders(nodes)
    inject_markdown_list_placeholders(nodes)
    selector = (
        f"div.{MARKDOWN_TABLE_PLACEHOLDER_CLASS}, div.{MARKDOWN_LIST_PLACEHOLDER_CLASS}, "
        f"span[class*=TopicHHead], span[class*=TopicGHead], "
        f"{SECTION_BODY_SELECTOR}, {link_selector}"
    )
    for node in nodes:
        for element in node.select(selector):
            placeholder_classes = element.get("class", [])
            if MARKDOWN_TABLE_PLACEHOLDER_CLASS in placeholder_classes or (
                MARKDOWN_LIST_PLACEHOLDER_CLASS in placeholder_classes
            ):
                for line in element.get("data-md", "").split("\n"):
                    if not line:
                        continue
                    plain = line.removeprefix(SUBSECTION_TITLE_PREFIX).strip()
                    if DID_YOU_KNOW_TITLE_RE.match(plain):
                        continue
                    previous_line = append_unique(lines, line, previous_line)
                continue

            line = format_element_line(element)
            if line is None:
                continue
            if DID_YOU_KNOW_TITLE_RE.match(line.strip()):
                continue
            previous_line = append_unique(lines, line, previous_line)
    return lines


def extract_target_sections(
    soup: BeautifulSoup,
    is_professional: bool,
) -> list[str]:
    patterns = section_patterns(is_professional)
    main_content = soup.select_one("div[class*=TopicMainContent]")
    if main_content is None:
        return []

    link_selector = PRO_LINK_SELECTOR if is_professional else HOME_LINK_SELECTOR

    section_lines: list[str] = []
    previous_line = ""

    for header in main_content.select("h2[class*=TopicFHead]"):
        title = header.get_text(strip=True)
        if not section_title_matches(title, patterns):
            continue

        previous_line = append_unique(
            section_lines, f"{SECTION_TITLE_PREFIX}{title}", previous_line
        )

        section_nodes = []
        for sibling in header.find_next_siblings():
            if is_topic_fhead_header(sibling):
                break
            section_nodes.append(sibling)

        for line in extract_lines_from_nodes(section_nodes, link_selector):
            previous_line = append_unique(section_lines, line, previous_line)

    if not section_lines:
        return []

    page_title = soup.select_one("span[class*=TopicHead_content]")
    if page_title is None:
        return section_lines

    return [f"{PAGE_TITLE_PREFIX}{page_title.get_text(strip=True)}", *section_lines]


def remove_reference_sections(soup: BeautifulSoup) -> None:
    for section in soup.select("section[class*=TopicGHead_topicGHeadSection]"):
        header = section.select_one("h2, h3")
        if header is None:
            continue
        title = header.get_text(strip=True)
        if REFERENCE_SECTION_TITLE_RE.match(
            title
        ) or INLINE_REFERENCE_SUBSECTION_TITLE_RE.match(title):
            section.decompose()


def remove_did_you_know_blocks(soup: BeautifulSoup) -> None:
    for block in soup.select(
        'div[data-testid="pearlDidyouknow"], div[class*="TopicPearlDidYouKnow"]'
    ):
        block.decompose()


def write_lines(filepath: str, lines: list[str]) -> None:
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as output_file:
        for line in lines:
            output_file.write(line + "\n")


def get_data(
    section_name: str,
    file_stem: str,
    pro_path: str | None,
    home_path: str | None,
    lang: str,
) -> bool:
    pro_lines: list[str] = []
    home_lines: list[str] = []

    if pro_path:
        pro_soup = BeautifulSoup(fetch_url(f"{BASE_URL}{pro_path}"), "html.parser")
        remove_reference_sections(pro_soup)
        remove_did_you_know_blocks(pro_soup)
        pro_lines = extract_target_sections(pro_soup, is_professional=True)

    if home_path:
        home_soup = BeautifulSoup(fetch_url(f"{BASE_URL}{home_path}"), "html.parser")
        remove_reference_sections(home_soup)
        remove_did_you_know_blocks(home_soup)
        home_lines = extract_target_sections(home_soup, is_professional=False)

    if not pro_lines and not home_lines:
        return False

    pro_filepath = os.path.join(
        OUTPUT_DIR, lang, "professional", section_name, f"{file_stem}.pro"
    )
    home_filepath = os.path.join(
        OUTPUT_DIR, lang, "amateur", section_name, f"{file_stem}.ama"
    )

    if pro_lines:
        write_lines(pro_filepath, pro_lines)
    if home_lines:
        write_lines(home_filepath, home_lines)
    return True


def scrape_section(
    section_index: int,
    pro_section_path: str,
    home_section_path: str,
    pro_by_slug: dict[str, str],
    home_by_slug: dict[str, str],
    scraped_slugs: set[str],
) -> int:
    pro_topics = get_topic_paths(pro_section_path)
    home_topics = get_topic_paths(home_section_path)
    saved = 0
    skipped = 0
    section_name = f"section{section_index + 1}"

    for topic_index, slug in enumerate(ordered_section_slugs(pro_topics, home_topics)):
        if slug in scraped_slugs:
            continue

        pro_path, home_path = resolve_section_paths(
            slug, pro_topics, home_topics, pro_by_slug, home_by_slug
        )
        if not pro_path and not home_path:
            continue

        try:
            if get_data(
                section_name,
                f"{section_index + 1}-{topic_index + 1}",
                pro_path,
                home_path,
                "en",
            ):
                saved += 1
                scraped_slugs.add(slug)
            else:
                skipped += 1
        except Exception as exc:
            print(
                f"section {section_index + 1} topic {topic_index + 1} ({slug}): {exc}"
            )
            continue
        time.sleep(0.5)

    if skipped:
        print(f"  skipped {skipped} topics with no ENG-5 sections on either side")
    return saved


def main():
    pro_sections = get_health_sections(PRO_TOPICS_URL)
    home_sections = get_health_sections(HOME_TOPICS_URL)
    if not pro_sections:
        raise RuntimeError(
            "No professional sections found. The MSD Manuals page structure may have changed again."
        )
    if not home_sections:
        raise RuntimeError(
            "No consumer sections found. The MSD Manuals page structure may have changed again."
        )

    section_count = len(pro_sections)
    print(f"Found {section_count} professional sections to scrape.")
    print("Building professional and consumer topic indexes...")
    pro_by_slug = build_topic_index(pro_sections)
    home_by_slug = build_topic_index(home_sections)
    print(
        f"Indexed {len(pro_by_slug)} professional and "
        f"{len(home_by_slug)} consumer topics."
    )

    total_saved = 0
    scraped_slugs: set[str] = set()
    for section_index in range(section_count):
        pro_section_path = pro_sections[section_index]["relativeurlcomputed_s"]
        home_section_path = home_sections[section_index]["relativeurlcomputed_s"]
        for lang in ALL_LANGS:
            os.makedirs(
                os.path.join(
                    OUTPUT_DIR, lang, "professional", f"section{section_index + 1}"
                ),
                exist_ok=True,
            )
            os.makedirs(
                os.path.join(
                    OUTPUT_DIR, lang, "amateur", f"section{section_index + 1}"
                ),
                exist_ok=True,
            )

        print(
            f"section {section_index + 1}: "
            f"{pro_sections[section_index].get('titlecomputed_t', '?')}"
        )
        saved = scrape_section(
            section_index,
            pro_section_path,
            home_section_path,
            pro_by_slug,
            home_by_slug,
            scraped_slugs,
        )
        print(f"  saved {saved} articles")
        total_saved += saved

    if total_saved == 0:
        raise RuntimeError("Scraping finished but no articles were saved.")
    print(f"Saved {total_saved} professional/consumer articles.")


if __name__ == "__main__":
    main()
