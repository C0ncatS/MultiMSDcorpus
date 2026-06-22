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
PRO_TEXT_SELECTOR = (
    "span[class*=TopicHead_content], span[class*=TopicFHead], span[class*=TopicHHead], "
    "span[class*=TopicGHead], span.TopicPara_topicText__CUB0d, span.TopicXLink_formatText__5UPAp, "
    "span[class*=TopicPara], span[class*=topicText], a[class*=professional]"
)
HOME_TEXT_SELECTOR = (
    "span[class*=TopicHead_content], span[class*=TopicFHead], span[class*=TopicHHead], "
    "span[class*=TopicGHead], span.TopicPara_topicText__CUB0d, span.TopicXLink_formatText__5UPAp, "
    "span[class*=TopicPara], span[class*=topicText], a[class*=home]"
)

# MSD reference blocks use section headings like "General references" or
# "Immune response references". Match the heading title only, not body text.
REFERENCE_SECTION_TITLE_RE = re.compile(
    r"^references$|^general\s+references$|^.+\s+references$",
    re.IGNORECASE,
)


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


def build_home_topic_index(home_sections: list[dict]) -> dict[str, str]:
    home_by_slug: dict[str, str] = {}
    for section in home_sections:
        for path in get_topic_paths(section["relativeurlcomputed_s"]):
            slug = topic_slug(path)
            if slug not in home_by_slug:
                home_by_slug[slug] = path
    return home_by_slug


def match_consumer_path(pro_path: str, home_by_slug: dict[str, str]) -> str | None:
    return home_by_slug.get(topic_slug(pro_path))


def remove_reference_sections(soup: BeautifulSoup) -> None:
    for section in soup.select("section[class*=TopicGHead_topicGHeadSection]"):
        header = section.select_one("h2, h3")
        if header is None:
            continue
        title = header.get_text(strip=True)
        if REFERENCE_SECTION_TITLE_RE.match(title):
            section.decompose()


def extract_text(soup: BeautifulSoup, selector: str) -> list[str]:
    lines = []
    previous_line = ""
    for element in soup.select(selector):
        text_data = element.get_text(strip=True)
        if text_data and text_data != previous_line:
            lines.append(text_data)
            previous_line = text_data
    return lines


def write_lines(filepath: str, lines: list[str]) -> None:
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as output_file:
        for line in lines:
            output_file.write(line + "\n")


def get_data(
    section_index: int,
    topic_index: int,
    pro_path: str,
    home_path: str,
    lang: str,
) -> None:
    pro_soup = BeautifulSoup(fetch_url(f"{BASE_URL}{pro_path}"), "html.parser")
    home_soup = BeautifulSoup(fetch_url(f"{BASE_URL}{home_path}"), "html.parser")
    remove_reference_sections(pro_soup)
    remove_reference_sections(home_soup)

    section_name = f"section{section_index + 1}"
    file_stem = f"{section_index + 1}-{topic_index + 1}"
    pro_filepath = os.path.join(
        OUTPUT_DIR, lang, "professional", section_name, f"{file_stem}.pro"
    )
    home_filepath = os.path.join(
        OUTPUT_DIR, lang, "amateur", section_name, f"{file_stem}.ama"
    )

    pro_lines = extract_text(pro_soup, PRO_TEXT_SELECTOR)
    home_lines = extract_text(home_soup, HOME_TEXT_SELECTOR)
    if not pro_lines or not home_lines:
        return

    write_lines(pro_filepath, pro_lines)
    write_lines(home_filepath, home_lines)


def scrape_section(
    section_index: int,
    pro_section_path: str,
    home_by_slug: dict[str, str],
) -> int:
    pro_topics = get_topic_paths(pro_section_path)
    saved = 0

    for topic_index, pro_path in enumerate(pro_topics):
        home_path = match_consumer_path(pro_path, home_by_slug)
        if not home_path:
            continue
        try:
            get_data(section_index, topic_index, pro_path, home_path, "en")
            saved += 1
        except Exception as exc:
            print(f"section {section_index + 1} topic {topic_index + 1}: {exc}")
            continue
        time.sleep(0.5)

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
    print("Building consumer topic index...")
    home_by_slug = build_home_topic_index(home_sections)
    print(f"Indexed {len(home_by_slug)} consumer topics.")

    total_saved = 0
    for section_index in range(section_count):
        pro_section_path = pro_sections[section_index]["relativeurlcomputed_s"]
        for lang in ALL_LANGS:
            os.makedirs(
                os.path.join(OUTPUT_DIR, lang, "professional", f"section{section_index + 1}"),
                exist_ok=True,
            )
            os.makedirs(
                os.path.join(OUTPUT_DIR, lang, "amateur", f"section{section_index + 1}"),
                exist_ok=True,
            )

        print(
            f"section {section_index + 1}: "
            f"{pro_sections[section_index].get('titlecomputed_t', '?')}"
        )
        saved = scrape_section(section_index, pro_section_path, home_by_slug)
        print(f"  saved {saved} article pairs")
        total_saved += saved

    if total_saved == 0:
        raise RuntimeError("Scraping finished but no article pairs were saved.")
    print(f"Saved {total_saved} professional/consumer article pairs.")


if __name__ == "__main__":
    main()
