from __future__ import annotations

from typing import Iterable

import requests

DISCORD_MAX_DESCRIPTION = 4096
DISCORD_MAX_EMBEDS = 10
DISCORD_MAX_TOTAL_CHARS = 6000
BOT_NAME = "Rust Updates PT-BR"
BR_FLAG = "🇧🇷"

CATEGORY_STYLE = {
    "Features": {"icon": "🛠️", "color": 0x57F287},
    "Improvements": {"icon": "⚙️", "color": 0x3498DB},
    "Fixed": {"icon": "🐛", "color": 0xF1C40F},
    "Removed": {"icon": "🗑️", "color": 0xED4245},
    "Known Issues": {"icon": "⚠️", "color": 0xE67E22},
    "Changes": {"icon": "🔄", "color": 0x9B59B6},
}


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
    return chunks or ["Sem conteúdo."]


def _category_style(title: str) -> tuple[str, int]:
    style = CATEGORY_STYLE.get(title, {"icon": "🔹", "color": 0x5865F2})
    return style["icon"], style["color"]


def _embed_size(embed: dict) -> int:
    total = len(embed.get("title", "")) + len(embed.get("description", ""))
    total += len(embed.get("footer", {}).get("text", ""))
    total += len(embed.get("author", {}).get("name", ""))
    return total


def _post(webhook_url: str, embeds: list[dict], components: list[dict] | None = None) -> None:
    payload = {
        "username": BOT_NAME,
        "embeds": embeds,
        "allowed_mentions": {"parse": []},
    }
    if components:
        payload["components"] = components

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


def _header_embed(
    patch_name: str,
    patch_date: str,
    source_url: str,
    hero_image_url: str | None,
) -> dict:
    """Build a compact header with the artwork as a small thumbnail."""
    embed = {
        "title": f"{BR_FLAG} RUST UPDATE • {patch_name}",
        "description": (
            "🟢 **NOVO UPDATE**\n"
            f"📅 **{patch_date or 'Data oficial'}**\n"
            f"{BR_FLAG} **Português (Brasil)**  •  🤖 Tradução automática"
        ),
        "url": source_url,
        "color": 0x57F287,
        "footer": {"text": f"{BR_FLAG} Rust Updates PT-BR • {patch_name}"},
    }
    if hero_image_url:
        embed["thumbnail"] = {"url": hero_image_url}
    return embed


def _section_embeds(
    patch_name: str,
    source_url: str,
    title: str,
    description: str,
    image_url: str | None,
) -> list[dict]:
    icon, color = _category_style(title)
    chunks = _chunks(description)
    embeds: list[dict] = []

    for index, chunk in enumerate(chunks, start=1):
        suffix = f" • {index}/{len(chunks)}" if len(chunks) > 1 else ""
        embed = {
            "title": f"{icon} {title.upper()}{suffix}",
            "description": chunk,
            "url": source_url,
            "color": color,
        }
        if image_url and index == 1:
            embed["image"] = {"url": image_url}
        embeds.append(embed)
    return embeds


def _official_button(source_url: str) -> list[dict]:
    return [{
        "type": 1,
        "components": [{
            "type": 2,
            "style": 5,
            "label": "Ver Patch Notes Oficiais",
            "emoji": {"name": "🔗"},
            "url": source_url,
        }],
    }]


def _send_batches(webhook_url: str, embeds: list[dict], source_url: str) -> None:
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

    for index, batch in enumerate(batches):
        components = _official_button(source_url) if index == len(batches) - 1 else None
        print(f"Sending Discord batch {index + 1}/{len(batches)} with {len(batch)} embeds...")
        _post(webhook_url, batch, components=components)


def send_patch(
    webhook_url: str,
    patch_name: str,
    patch_date: str,
    source_url: str,
    sections: Iterable[tuple[str, str, str | None]],
    hero_image_url: str | None = None,
) -> None:
    """Publish a compact, modern PT-BR Rust update as grouped Discord embeds."""
    embeds = [_header_embed(patch_name, patch_date, source_url, hero_image_url)]

    for title, description, image_url in sections:
        embeds.extend(_section_embeds(patch_name, source_url, title, description, image_url))

    _send_batches(webhook_url, embeds, source_url)
