from __future__ import annotations

from typing import Iterable

import requests

DISCORD_MAX_EMBEDS = 10
DISCORD_MAX_TOTAL_CHARS = 6000
MAX_ITEMS_PER_SECTION_CARD = 7
MAX_SECTION_CARD_CHARS = 1500
BOT_NAME = "Rust Updates PT-BR"
BR_FLAG = "🇧🇷"
RUST_LOGO_URL = "https://static.cdnlogo.com/logos/r/90/rust_800.png"
RUST_COLOR = 0xCE422B


def _bullet_chunks(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ["Sem conteúdo."]

    chunks: list[str] = []
    current: list[str] = []
    current_chars = 0

    for line in lines:
        line_size = len(line) + 1
        if current and (
            len(current) >= MAX_ITEMS_PER_SECTION_CARD
            or current_chars + line_size > MAX_SECTION_CARD_CHARS
        ):
            chunks.append("\n".join(current))
            current = []
            current_chars = 0

        current.append(line)
        current_chars += line_size

    if current:
        chunks.append("\n".join(current))

    return chunks or ["Sem conteúdo."]


def _embed_size(embed: dict) -> int:
    total = len(embed.get("title", "")) + len(embed.get("description", ""))
    total += len(embed.get("footer", {}).get("text", ""))
    total += len(embed.get("author", {}).get("name", ""))
    return total


def _post(webhook_url: str, embeds: list[dict]) -> None:
    payload = {
        "username": BOT_NAME,
        "embeds": embeds,
        "allowed_mentions": {"parse": []},
    }
    response = requests.post(
        webhook_url,
        params={"wait": "true"},
        json=payload,
        timeout=30,
    )
    print(f"Discord webhook HTTP status: {response.status_code}")
    if not response.ok:
        print(f"Discord response: {response.text[:1000]}")
    response.raise_for_status()
    try:
        message = response.json()
        print(f"Discord message created: {message.get('id', 'unknown')}")
        print(f"Discord channel: {message.get('channel_id', 'unknown')}")
    except ValueError:
        print("Discord accepted the webhook, but returned no JSON payload.")


def _patchbot_card(
    patch_name: str,
    source_url: str,
    section_title: str,
    description: str,
    image_url: str | None,
    chunk_number: int,
    chunk_total: int,
) -> dict:
    heading = section_title.upper()
    if chunk_total > 1:
        heading += f" ({chunk_number}/{chunk_total})"

    embed = {
        "author": {"name": "Rust"},
        "title": patch_name,
        "url": source_url,
        "description": f"**{heading}**\n{description}",
        "color": RUST_COLOR,
        "thumbnail": {"url": RUST_LOGO_URL},
        "footer": {"text": f"{BR_FLAG} Tradução automática PT-BR"},
    }
    if image_url and chunk_number == 1:
        embed["image"] = {"url": image_url}
    return embed


def _send_batches(webhook_url: str, embeds: list[dict]) -> None:
    batches: list[list[dict]] = []
    current: list[dict] = []
    current_chars = 0

    for embed in embeds:
        size = _embed_size(embed)
        if current and (
            len(current) >= DISCORD_MAX_EMBEDS
            or current_chars + size > DISCORD_MAX_TOTAL_CHARS
        ):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(embed)
        current_chars += size

    if current:
        batches.append(current)

    for index, batch in enumerate(batches, start=1):
        print(f"Sending Discord batch {index}/{len(batches)} with {len(batch)} embeds...")
        _post(webhook_url, batch)


def send_patch(
    webhook_url: str,
    patch_name: str,
    patch_date: str,
    source_url: str,
    sections: Iterable[tuple[str, str, str | None]],
    hero_image_url: str | None = None,
) -> None:
    """Publish Rust updates using a PatchBot-style embed layout in PT-BR."""
    del patch_date, hero_image_url
    embeds: list[dict] = []

    for section_title, description, image_url in sections:
        chunks = _bullet_chunks(description)
        total = len(chunks)
        for index, chunk in enumerate(chunks, start=1):
            embeds.append(
                _patchbot_card(
                    patch_name,
                    source_url,
                    section_title,
                    chunk,
                    image_url,
                    index,
                    total,
                )
            )

    if not embeds:
        embeds.append(
            _patchbot_card(
                patch_name,
                source_url,
                "Atualização",
                "Sem conteúdo disponível.",
                None,
                1,
                1,
            )
        )

    _send_batches(webhook_url, embeds)
