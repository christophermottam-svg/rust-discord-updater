from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from discord import send_patch
from scraper import extract_latest_patch, fetch_html, fetch_steam_main_image
from topic_extractor import MainTopic, fetch_main_topics
from translator import translate_text

STATE_FILE = Path(os.getenv("STATE_FILE", "last_patch.json"))
RUST_CHANGES_URL = "https://rust.facepunch.com/changes/1"


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid state file: {STATE_FILE}") from exc


def save_state(patch_id: str, patch_name: str, patch_date: str) -> None:
    data = {
        "patch_id": patch_id,
        "patch_name": patch_name,
        "patch_date": patch_date,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }
    STATE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _translate_topic(topic: MainTopic) -> tuple[str, str]:
    """Translate one user-facing Rust topic to Brazilian Portuguese."""
    translated_title = translate_text(topic.title).strip() or topic.title
    translated_description = translate_text(topic.description).strip() or topic.description
    return translated_title, translated_description


def _raw_sections_to_topics(patch) -> list[MainTopic]:
    """Fallback: turn the official changelist sections into readable topics."""
    topics: list[MainTopic] = []
    for section in patch.sections:
        if not section.items:
            continue
        description = "\n".join(f"• {item}" for item in section.items[:8])
        topics.append(MainTopic(title=section.title, description=description))
    return topics


def main() -> None:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        raise RuntimeError("DISCORD_WEBHOOK_URL secret is not configured.")

    test_mode = os.environ.get("TEST_MODE", "false").lower() == "true"
    if test_mode:
        print(
            "TEST MODE enabled: this run will publish the current patch again "
            "and will NOT change last_patch.json."
        )

    print("Downloading official Rust changes page...")
    patch = extract_latest_patch(fetch_html(RUST_CHANGES_URL))
    state = load_state()

    if not test_mode and state.get("patch_id") == patch.patch_id:
        print(f"Patch already published: {patch.name}")
        return

    if test_mode:
        print(f"Test patch: {patch.name}")
    else:
        print(f"New patch detected: {patch.name}")

    print("Finding user-facing main topics from the Rust Devblog...")
    topics = fetch_main_topics(patch.name, max_topics=6)
    if not topics:
        print("No curated main topics found; using official changelist sections as fallback.")
        topics = _raw_sections_to_topics(patch)

    print("Finding Steam Community main update image...")
    steam_image = fetch_steam_main_image(patch.name)
    if steam_image:
        print(f"Steam main image: {steam_image.url}")
    else:
        print("Steam main image: none")

    published_sections: list[tuple[str, str, str | None]] = []
    for index, topic in enumerate(topics):
        print(f"Translating main topic: {topic.title}")
        translated_title, translated_description = _translate_topic(topic)
        image_url = steam_image.url if steam_image and index == 0 else None
        published_sections.append(
            (
                translated_title,
                translated_description,
                image_url,
            )
        )

    send_patch(
        webhook_url=webhook,
        patch_name=patch.name,
        patch_date=patch.date,
        source_url=patch.source_url,
        sections=published_sections,
    )

    if test_mode:
        print("TEST MODE: publication sent; last_patch.json was NOT changed.")
    else:
        save_state(patch.patch_id, patch.name, patch.date)
        print("Patch published successfully.")


if __name__ == "__main__":
    main()
