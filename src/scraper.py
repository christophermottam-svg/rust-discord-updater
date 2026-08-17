from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

RUST_CHANGES_URL = "https://rust.facepunch.com/changes/1"
RUST_NEWS_URL = "https://rust.facepunch.com/news"
STEAM_NEWS_API = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v0002/"
STEAM_APP_ID = 252490
USER_AGENT = "RustDiscordUpdater/4.1"
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
    width: int | None = None
    height: int | None = None
    is_og_image: bool = False


# ---------- Rust patch scraping ----------


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
            item = re.sub(r"^[•\-*]\s*", "", line).strip()
            if item:
                current.items.append(item)
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


# ---------- Steam main-image lookup ----------


def _normalise_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _steam_news_items(limit: int = 50) -> list[dict]:
    response = requests.get(
        STEAM_NEWS_API,
        params={"appid": STEAM_APP_ID, "count": limit, "maxlength": 0, "format": "json"},
        timeout=30,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("appnews", {}).get("newsitems", []) or []


def _extract_bbcode_images(contents: str) -> list[str]:
    urls: list[str] = []
    patterns = [
        r"\[img\](https?://[^\[]+)\[/img\]",
        r"\[img src=[\"']?(https?://[^\]\"']+)[\"']?\]",
    ]
    for pattern in patterns:
        urls.extend(re.findall(pattern, contents, flags=re.IGNORECASE))

    seen: set[str] = set()
    result: list[str] = []
    for url in urls:
        url = url.strip()
        if url and url not in seen:
            seen.add(url)
            result.append(url)
    return result


def _extract_steam_og_image(article_url: str) -> str | None:
    try:
        html = fetch_html(article_url)
    except requests.RequestException as exc:
        print(f"Steam announcement page request failed: {exc}")
        return None

    soup = BeautifulSoup(html, "html.parser")
    for attrs in (
        {"property": "og:image"},
        {"name": "og:image"},
    ):
        tag = soup.find("meta", attrs=attrs)
        if tag and isinstance(tag.get("content"), str) and tag["content"].strip():
            return urljoin(article_url, tag["content"].strip())

    return None


def _steam_announcement_url(item: dict) -> str | None:
    url = item.get("url")
    if isinstance(url, str) and url.startswith("http"):
        return url
    gid = item.get("gid")
    if gid:
        return f"https://steamcommunity.com/games/{STEAM_APP_ID}/announcements/detail/{gid}"
    return None


def fetch_steam_main_image(patch_name: str) -> ArticleImage | None:
    """Find the Steam announcement matching the Rust patch and return its main image.

    We first open the matching Steam announcement and read its OpenGraph image,
    which is the header/cover artwork displayed by Steam. The older API feed does
    not expose that cover field directly, so the article page is required.
    """
    try:
        items = _steam_news_items()
    except (requests.RequestException, ValueError):
        print("Steam news feed unavailable; no Steam main image will be used.")
        return None

    wanted = _normalise_text(patch_name)
    best_item: dict | None = None
    best_score = 0.0

    for item in items:
        if not isinstance(item, dict):
            continue
        title = _normalise_text(str(item.get("title", "")))
        if not title:
            continue

        if title == wanted:
            best_item = item
            best_score = 1.0
            break

        if wanted in title or title in wanted:
            score = 0.8
        else:
            wanted_words = set(wanted.split())
            title_words = set(title.split())
            score = len(wanted_words & title_words) / max(len(wanted_words | title_words), 1)

        if score > best_score:
            best_score = score
            best_item = item

    if best_item is None or best_score < 0.50:
        print(f"No Steam announcement matched patch '{patch_name}'.")
        return None

    article_url = _steam_announcement_url(best_item)
    if not article_url:
        print(f"Steam announcement matched but has no usable URL: {best_item.get('title')}")
        return None

    print(f"Matched Steam announcement: {best_item.get('title')} ({best_score:.2f})")

    # Preferred source: the actual Steam announcement cover/header.
    image_url = _extract_steam_og_image(article_url)
    if image_url:
        print(f"Steam main image (OG) found: {image_url}")
        return ArticleImage(
            url=image_url,
            context=f"Steam main update image {patch_name}",
            is_og_image=True,
        )

    # Fallback: use the first explicit image in the announcement body.
    image_urls = _extract_bbcode_images(str(best_item.get("contents", "")))
    if image_urls:
        print(f"Steam main image (body fallback) found: {image_urls[0]}")
        return ArticleImage(
            url=image_urls[0],
            context=f"Steam main update image {patch_name}",
            is_og_image=True,
        )

    print(f"Steam announcement found for '{patch_name}', but no main image was found.")
    return None


# ---------- Legacy Facepunch helpers kept for tests/fallback tooling ----------


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


def _dimension(value: object) -> int | None:
    if value is None:
        return None
    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else None


def _image_context(img: Tag) -> str:
    pieces: list[str] = []
    alt = img.get("alt")
    if isinstance(alt, str) and alt.strip():
        pieces.append(alt.strip())
    heading = img.find_previous(["h1", "h2", "h3", "h4"])
    if heading:
        pieces.append(heading.get_text(" ", strip=True))
    parent = img.parent
    if parent:
        nearby = parent.get_text(" ", strip=True)
        if nearby:
            pieces.append(nearby[:500])
    return " ".join(pieces)


def _add_image(images: list[ArticleImage], seen: set[str], image: ArticleImage) -> None:
    if not image.url or image.url in seen or "facepunch.com" not in image.url:
        return
    seen.add(image.url)
    images.append(image)


def fetch_article_images(patch_name: str) -> list[ArticleImage]:
    article_url = f"https://rust.facepunch.com/news/{_slugify(patch_name)}/"
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

    og = soup.find("meta", attrs={"property": "og:image"})
    og_width_tag = soup.find("meta", attrs={"property": "og:image:width"})
    og_height_tag = soup.find("meta", attrs={"property": "og:image:height"})
    if og and isinstance(og.get("content"), str):
        _add_image(
            images,
            seen,
            ArticleImage(
                url=urljoin(article_url, og["content"]),
                context=f"{patch_name} official Devblog social banner",
                width=_dimension(og_width_tag.get("content") if og_width_tag else None),
                height=_dimension(og_height_tag.get("content") if og_height_tag else None),
                is_og_image=True,
            ),
        )

    for img in soup.find_all("img"):
        url = _image_url(img, article_url)
        if not url:
            continue
        _add_image(
            images,
            seen,
            ArticleImage(
                url=url,
                context=_image_context(img),
                width=_dimension(img.get("width")),
                height=_dimension(img.get("height")),
            ),
        )
    return images


def choose_hero_image(images: list[ArticleImage]) -> ArticleImage | None:
    if not images:
        return None
    return images[0]


def _words(value: str) -> set[str]:
    stopwords = {
        "the", "and", "for", "with", "from", "this", "that", "are",
        "was", "were", "will", "have", "has", "into", "your", "you",
        "can", "not", "all", "new", "fixed", "added", "update",
    }
    return {w for w in re.findall(r"[a-z0-9]{3,}", value.casefold()) if w not in stopwords}


def match_section_images(
    sections: Iterable[PatchSection],
    images: list[ArticleImage],
) -> dict[str, str]:
    """Legacy matcher retained for tests and backwards compatibility."""
    if not images:
        return {}

    remaining = list(images)
    matches: dict[str, str] = {}
    for section in sections:
        section_words = _words(section.title + " " + " ".join(section.items[:12]))
        if not section_words:
            continue
        best_image: ArticleImage | None = None
        best_score = 0
        best_index = -1
        for index, image in enumerate(remaining):
            image_words = _words(image.context)
            score = len(section_words & image_words)
            if score > best_score:
                best_score = score
                best_image = image
                best_index = index
        if best_image is not None and best_score >= 2:
            matches[section.title] = best_image.url
            remaining.pop(best_index)
    return matches
