from __future__ import annotations

from typing import Iterable

import requests

DISCORD_MAX_DESCRIPTION = 4096
DISCORD_MAX_EMBEDS = 10


def _chunks(text: str, limit: int = DISCORD_MAX_DESCRIPTION) -> list[str]:
    text = text.strip()
    chunks: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < 500:
            cut = text.rfind(" ", 0, limit)
        if cut < 500:
            cut = limit
        chunks.append(text[:cut].strip())
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks


def send_patch(
    webhook_url: str,
    patch_name: str,
    patch_date: str,
    source_url: str,
    sections: Iterable[tuple[str, str, str | None]],
) -> None:
    embeds: list[dict] = []
    for title, description, image_url in sections:
        for index, chunk in enumerate(_chunks(description), start=1):
            embed = {
                "title": f"🦀 RUST — {patch_name}" + (f" • {title}" if index == 1 else f" • {title} ({index})"),
                "description": chunk,
                "url": source_url,
                "footer": {"text": "Rust • Patch Notes oficiais • Tradução automática PT-BR"},
            }
            if image_url:
                embed["image"] = {"url": image_url}
            embeds.append(embed)

            if len(embeds) == DISCORD_MAX_EMBEDS:
                _post(webhook_url, embeds)
                embeds = []

    if embeds:
        _post(webhook_url, embeds)


def _post(webhook_url: str, embeds: list[dict]) -> None:
    response = requests.post(
        webhook_url,
        json={"username": "🦀 Rust Updates PT-BR", "embeds": embeds},
        timeout=30,
    )
    response.raise_for_status()
