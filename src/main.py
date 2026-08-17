from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from discord import send_patch
from scraper import extract_latest_patch, fetch_html, fetch_steam_main_image
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


def _translate_items(items: list[str]) -> str:
    if not items:
        return ""

    english = "\n".join(items)
    portuguese = translate_text(english)
    translated_lines = [
        line.strip().lstrip("•-* ").strip()
        for line in portuguese.splitlines()
        if line.strip()
    ]
    return "\n".join(f"• {line}" for line in translated_lines)


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
    print(f"Sections: {len(patch.sections)}")

    print("Finding Steam Community main update image...")
    steam_image = fetch_steam_main_image(patch.name)
    if steam_image:
        print(f"Steam main image: {steam_image.url}")
    else:
        print("Steam main image: none")

    published_sections: list[tuple[str, str, str | None]] = []
    for index, section in enumerate(patch.sections):
        print(f"Translating section: {section.title}")
        portuguese = _translate_items(section.items)

        image_url = steam_image.url if steam_image and index == 0 else None
        published_sections.append(
            (
                section.title,
                portuguese,
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
