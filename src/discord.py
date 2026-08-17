from __future__ import annotations

from typing import Iterable

import requests

DISCORD_MAX_DESCRIPTION = 4096
BR_FLAG = "🇧🇷"
BOT_NAME = f"{BR_FLAG} Rust Updates PT-BR"

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
    return CATEGORY_STYLE.get(
        title,
        {"icon": "🔹", "color": 0xCE422B},
    )["icon"], CATEGORY_STYLE.get(
        title,
        {"icon": "🔹", "color": 0xCE422B},
    )["color"]


def _post(webhook_url: str, embeds: list[dict]) -> None:
    response = requests.post(
        webhook_url,
        params={"wait": "true"},
        json={
            "username": BOT_NAME,
            "embeds": embeds,
            "allowed_mentions": {"parse": []},
        },
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


def _send_header(
    webhook_url: str,
    patch_name: str,
    patch_date: str,
    source_url: str,
    hero_image_url: str | None,
) -> None:
    description = (
        "🟢 **NOVO UPDATE**\n\n"
        f"📅 **{patch_date or 'Data oficial'}**\n\n"
        f"{BR_FLAG} **Tradução automática para Português (Brasil)**  •  🤖 Traduzido por IA"
    )

    embed = {
        "title": f"{BR_FLAG} RUST UPDATE • {patch_name}",
        "description": description,
        "url": source_url,
        "color": 0x57F287,
        "footer": {
            "text": f"{BR_FLAG} Rust Updates PT-BR • Tradução automática"
        },
    }

    if hero_image_url:
        embed["image"] = {"url": hero_image_url}

    _post(webhook_url, [embed])


def _send_section(
    webhook_url: str,
    patch_name: str,
    source_url: str,
    title: str,
    description: str,
    image_url: str | None,
) -> None:
    icon, color = _category_style(title)
    chunks = _chunks(description)

    for index, chunk in enumerate(chunks, start=1):
        suffix = f" • {index}/{len(chunks)}" if len(chunks) > 1 else ""
        embed = {
            "title": f"{icon} {title.upper()}{suffix}",
            "description": chunk,
            "url": source_url,
            "color": color,
            "footer": {
                "text": f"{BR_FLAG} Rust Updates PT-BR • {patch_name}"
            },
        }
        if image_url and index == 1:
            embed["image"] = {"url": image_url}
        _post(webhook_url, [embed])


def _send_official_link(webhook_url: str, source_url: str) -> None:
    embed = {
        "description": f"🔗 **[VER PATCH NOTES OFICIAIS]({source_url})**",
        "url": source_url,
        "color": 0x5865F2,
        "footer": {"text": f"{BR_FLAG} Rust Updates PT-BR"},
    }
    _post(webhook_url, [embed])


def send_patch(
    webhook_url: str,
    patch_name: str,
    patch_date: str,
    source_url: str,
    sections: Iterable[tuple[str, str, str | None]],
    hero_image_url: str | None = None,
) -> None:
    """Publish a modern, readable PT-BR Rust update as separate Discord embeds."""
    _send_header(
        webhook_url=webhook_url,
        patch_name=patch_name,
        patch_date=patch_date,
        source_url=source_url,
        hero_image_url=hero_image_url,
    )

    for title, description, image_url in sections:
        _send_section(
            webhook_url=webhook_url,
            patch_name=patch_name,
            source_url=source_url,
            title=title,
            description=description,
            image_url=image_url,
        )

    _send_official_link(webhook_url, source_url)
