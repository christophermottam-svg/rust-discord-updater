from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

RUST_CHANGES_URL = "https://rust.facepunch.com/changes/1"
RUST_NEWS_URL = "https://rust.facepunch.com/news"
USER_AGENT = "RustDiscordUpdater/3.0"
IGNORED_MARKERS = {"add_circle", "arrow_circle_up", "remove_circle", "error", "handyman"}
SECTION_NAMES = {"Features", "Improvements", "Fixed", "Removed", "Known Issues", "Changes"}


@dataclass(frozen=True)
class PatchSection:
    title: str
    items: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Patch:
    patch_id: str
    name: str
    changelist: str
    date: str
    sections: list[PatchSection]
    source_url: str = RUST_CHANGES_URL


@dataclass(frozen=True)
class ArticleImage:
    url: str
    context: str


def fetch_html(url: str, timeout: int = 30) -> str:
    response = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.text


def _clean_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        line = " ".join(raw.split()).strip()
        if not line or line in IGNORED_MARKERS:
            continue
        lines.append(line)
    return lines


def _first_index(lines: list[str], value: str, start: int = 0) -> int | None:
    try:
        return lines.index(value, start)
    except ValueError:
        return None


def _extract_section_items(lines: list[str]) -> list[PatchSection]:
    sections: list[PatchSection] = []
    current: PatchSection | None = None
    for line in lines:
        if line in SECTION_NAMES:
            if current and current.items:
                sections.append(current)
            current = PatchSection(line, [])
            continue
        if current is not None and line:
            current.items.append(line.lstrip("• ").strip())
    if current and current.items:
        sections.append(current)
    return sections


def extract_latest_patch(html: str) -> Patch:
    soup = BeautifulSoup(html, "html.parser")
    lines = _clean_lines(soup.get_text("\n", strip=True))
    patch_index = _first_index(lines, "Patch Name")
    if patch_index is None:
        raise RuntimeError("Could not find 'Patch Name' on the Rust changes page.")
    if patch_index + 1 >= len(lines):
        raise RuntimeError("The latest patch name is missing.")

    patch_name = lines[patch_index + 1]
    changelist_index = _first_index(lines, "Changelist Title", patch_index + 2)
    date_index = _first_index(lines, "date_range", patch_index + 2)
    changelist = lines[changelist_index + 1] if changelist_index is not None and changelist_index + 1 < len(lines) else ""
    patch_date = lines[date_index + 1] if date_index is not None and date_index + 1 < len(lines) else ""

    next_patch_index = _first_index(lines, "Patch Name", patch_index + 2)
    end = next_patch_index if next_patch_index is not None else len(lines)
    sections = _extract_section_items(lines[patch_index + 2:end])
    if not sections:
        raise RuntimeError(f"Patch '{patch_name}' has no changelog sections.")

    return Patch(
        patch_id=f"{patch_name}|{patch_date}|{changelist}",
        name=patch_name,
        changelist=changelist,
        date=patch_date,
        sections=sections,
    )


def _slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower().strip())
    return value.strip("-")


def _find_news_article(soup: BeautifulSoup, patch_name: str) -> str | None:
    wanted = " ".join(patch_name.split()).casefold()
    for anchor in soup.find_all("a", href=True):
        text = " ".join(anchor.get_text(" ", strip=True).split()).casefold()
        if text == wanted:
            return urljoin(RUST_NEWS_URL, anchor["href"])
    return None


def _image_url(img: Tag, base_url: str) -> str | None:
    for attribute in ("src", "data-src", "data-lazy-src", "data-original"):
        value = img.get(attribute)
        if isinstance(value, str) and value and not value.startswith("data:"):
            return urljoin(base_url, value)
    srcset = img.get("srcset")
    if isinstance(srcset, str) and srcset.strip():
        return urljoin(base_url, srcset.split(",")[-1].strip().split(" ")[0])
    return None


def _image_context(img: Tag) -> str:
    pieces: list[str] = []
    alt = img.get("alt")
    if isinstance(alt, str):
        pieces.append(alt)
    heading = img.find_previous(["h1", "h2", "h3", "h4"])
    if heading:
        pieces.append(heading.get_text(" ", strip=True))
    if img.parent:
        nearby = img.parent.get_text(" ", strip=True)
        if nearby:
            pieces.append(nearby[:500])
    return " ".join(pieces)


def fetch_article_images(patch_name: str) -> list[ArticleImage]:
    article_url = f"https://rust.facepunch.com/news/{_slugify(patch_name)}"
    try:
        article_html = fetch_html(article_url)
    except requests.HTTPError:
        try:
            news_html = fetch_html(RUST_NEWS_URL)
            news_soup = BeautifulSoup(news_html, "html.parser")
            article_url = _find_news_article(news_soup, patch_name) or article_url
            article_html = fetch_html(article_url)
        except requests.RequestException:
            return []
    except requests.RequestException:
        return []

    soup = BeautifulSoup(article_html, "html.parser")
    images: list[ArticleImage] = []
    seen: set[str] = set()
    for img in soup.find_all("img"):
        url = _image_url(img, article_url)
        if not url or url in seen or "facepunch.com" not in url:
            continue
        seen.add(url)
        images.append(ArticleImage(url=url, context=_image_context(img)))
    return images


def _words(value: str) -> set[str]:
    stopwords = {"the", "and", "for", "with", "from", "this", "that"}
    return {w for w in re.findall(r"[a-z0-9]{3,}", value.casefold()) if w not in stopwords}


def match_section_images(sections: Iterable[PatchSection], images: list[ArticleImage]) -> dict[str, str]:
    if not images:
        return {}
    remaining = list(images)
    matches: dict[str, str] = {}
    for section in sections:
        section_words = _words(section.title + " " + " ".join(section.items[:8]))
        best_image: ArticleImage | None = None
        best_score = -1
        best_index = 0
        for index, image in enumerate(remaining):
            score = len(section_words & _words(image.context))
            if score > best_score:
                best_score = score
                best_image = image
                best_index = index
        if best_image is not None and best_score > 0:
            matches[section.title] = best_image.url
            remaining.pop(best_index)
    hero = images[0].url
    for section in sections:
        matches.setdefault(section.title, hero)
    return matches
