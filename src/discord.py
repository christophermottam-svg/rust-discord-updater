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
    embeds: list[dict] = [
        {
            "title": f"🦀 RUST — {patch_name}",
            "description": f"**{patch_date}**\n\n🚀 **Nova atualização do Rust!**",
            "url": source_url,
            "color": 0xCE422B,
            "footer": {"text": "Rust • Patch Notes oficiais • Tradução automática PT-BR"},
        }
    ]

    for title, description, image_url in sections:
        chunks = _chunks(description)
        for index, chunk in enumerate(chunks, start=1):
            suffix = f" ({index})" if len(chunks) > 1 else ""
            embed = {
                "title": f"🔹 {title}{suffix}",
                "description": chunk,
                "url": source_url,
                "color": 0xCE422B,
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
    # wait=true makes Discord return the created message, allowing CI to
    # confirm that the webhook actually accepted the post.
    response = requests.post(
        webhook_url,
        params={"wait": "true"},
        json={
            "username": "🦀 Rust Updates PT-BR",
            "embeds": embeds,
            "allowed_mentions": {"parse": []},
        },
        timeout=30,
    )

    print(f"Discord webhook HTTP status: {response.status_code}")

    if not response.ok:
        print(f"Discord response: {response.text[:500]}")

    response.raise_for_status()

    try:
        message = response.json()
        print(f"Discord message created: {message.get('id', 'unknown')}")
        print(f"Discord channel: {message.get('channel_id', 'unknown')}")
    except ValueError:
        print("Discord accepted the webhook, but returned no JSON payload.")
