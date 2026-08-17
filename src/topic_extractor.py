from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

RUST_NEWS_URL = "https://rust.facepunch.com/news"
USER_AGENT = "RustDiscordUpdater/4.3"
CATEGORY_NAMES = {"features", "improvements", "fixed", "removed", "known issues", "changes"}
CATEGORY_PRIORITY = {
    "features": 0,
    "improvements": 1,
    "changes": 2,
    "known issues": 3,
    "fixed": 4,
    "removed": 5,
}
TECHNICAL_NOISE = {
    "entity", "jobs", "job", "parallel", "benchmark", "profiling", "profiler",
    "performance", "optimization", "optimisation", "fps", "frame time", "memory",
    "gc", "garbage collection", "serialization", "serialisation", "latency",
    "server performance", "client performance", "debug", "developer notes",
}


@dataclass(frozen=True)
class MainTopic:
    title: str
    description: str


def _clean(value: str) -> str:
    return " ".join(value.split()).strip()


def _slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower().strip())
    return value.strip("-")


def _resolve_article_url(patch_name: str) -> str:
    direct = f"https://rust.facepunch.com/news/{_slugify(patch_name)}/"
    response = requests.get(direct, timeout=30, headers={"User-Agent": USER_AGENT})
    if response.ok:
        return direct

    news = requests.get(RUST_NEWS_URL, timeout=30, headers={"User-Agent": USER_AGENT})
    news.raise_for_status()
    soup = BeautifulSoup(news.text, "html.parser")
    wanted = _clean(patch_name).casefold()
    for anchor in soup.find_all("a", href=True):
        text = _clean(anchor.get_text(" ", strip=True)).casefold()
        if text == wanted:
            return urljoin(RUST_NEWS_URL, anchor["href"])
    return direct


def _heading_level(tag: Tag) -> int:
    return int(tag.name[1])


def _is_category(text: str) -> bool:
    return _clean(text).casefold().strip(" :") in CATEGORY_NAMES


def _is_noise_heading(text: str) -> bool:
    low = _clean(text).casefold()
    if not low or len(low) < 4 or len(low) > 100:
        return True
    if low in CATEGORY_NAMES:
        return True
    if low in {"image", "images", "video", "videos", "author", "credits", "follow us", "stay up to date"}:
        return True
    if any(term in low for term in TECHNICAL_NOISE):
        return True
    if re.fullmatch(r"[\W_]+", low):
        return True
    return False


def _node_text(node: Tag) -> str:
    return _clean(node.get_text(" ", strip=True))


def _collect_description(heading: Tag, limit: int = 1200) -> str:
    parts: list[str] = []
    level = _heading_level(heading)

    for node in heading.next_elements:
        if isinstance(node, Tag) and node.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            next_level = _heading_level(node)
            if next_level <= level:
                break

        if isinstance(node, Tag) and node.name in {"p", "li"}:
            text = _node_text(node)
            if not text or text in parts:
                continue
            parts.append(text)
            if sum(len(x) + 1 for x in parts) >= limit:
                break

    return "\n".join(parts)


def _extract_topics_from_categories(soup: BeautifulSoup) -> list[MainTopic]:
    headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    topics: list[tuple[int, int, MainTopic]] = []

    for i, category in enumerate(headings):
        category_name = _clean(category.get_text(" ", strip=True)).casefold().strip(" :")
        if category_name not in CATEGORY_NAMES:
            continue

        category_level = _heading_level(category)
        section_end = len(headings)
        for j in range(i + 1, len(headings)):
            candidate_level = _heading_level(headings[j])
            candidate_text = _clean(headings[j].get_text(" ", strip=True)).casefold().strip(" :")
            if candidate_level <= category_level and candidate_text in CATEGORY_NAMES:
                section_end = j
                break
            if candidate_level <= category_level and candidate_text not in CATEGORY_NAMES:
                section_end = j
                break

        local_index = 0
        for topic_heading in headings[i + 1:section_end]:
            level = _heading_level(topic_heading)
            title = _clean(topic_heading.get_text(" ", strip=True))
            if level <= category_level or _is_noise_heading(title):
                continue

            description = _collect_description(topic_heading)
            if not description:
                continue

            topics.append(
                (
                    CATEGORY_PRIORITY.get(category_name, 99),
                    local_index,
                    MainTopic(title=title, description=description),
                )
            )
            local_index += 1

    topics.sort(key=lambda row: (row[0], row[1]))
    return [topic for _, _, topic in topics]


def _fallback_topics(soup: BeautifulSoup) -> list[MainTopic]:
    result: list[MainTopic] = []
    for heading in soup.find_all(["h2", "h3", "h4"]):
        title = _clean(heading.get_text(" ", strip=True))
        if _is_noise_heading(title):
            continue
        description = _collect_description(heading)
        if description:
            result.append(MainTopic(title=title, description=description))
        if len(result) >= 8:
            break
    return result


def fetch_main_topics(patch_name: str, max_topics: int = 6) -> list[MainTopic]:
    """Return real user-facing Rust article topics, not developer/performance notes."""
    try:
        url = _resolve_article_url(patch_name)
        response = requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"Could not load Rust Devblog topics: {exc}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    topics = _extract_topics_from_categories(soup)
    if not topics:
        topics = _fallback_topics(soup)

    deduped: list[MainTopic] = []
    seen: set[str] = set()
    for topic in topics:
        key = topic.title.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(topic)
        if len(deduped) >= max_topics:
            break

    print(f"User-facing main topics found: {len(deduped)}")
    for topic in deduped:
        print(f"Main topic: {topic.title}")
    return deduped
