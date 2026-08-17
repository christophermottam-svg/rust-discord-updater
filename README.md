# 🦀 Rust Discord Updater

Automatically reads the latest official Rust patch notes, translates them to Brazilian Portuguese, finds official Facepunch Devblog images, and publishes structured Discord embeds.

## Features

- Official Rust changes page as the source of truth.
- Patch identity based on name, date, and changelist.
- Section-aware parsing instead of scraping the entire page as one block.
- Local Argos Translate English → Portuguese (Brazil) (`pb`) model.
- Official Facepunch images with safe fallback behavior.
- Discord embeds split safely under Discord's description limits.
- Persistent `last_patch.json` state to prevent duplicate posts.
- GitHub Actions every 30 minutes plus manual dispatch.

## Setup

1. Create a Discord webhook.
2. Add it to the repository as the Actions secret `DISCORD_WEBHOOK_URL`.
3. Run **Actions → Rust Update → Run workflow** once for a manual smoke test.
4. The scheduled job will then check every 30 minutes.

## Local run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DISCORD_WEBHOOK_URL="..."
python src/main.py
```

## Architecture

- `src/scraper.py` — Rust patch parsing and official image discovery/matching.
- `src/translator.py` — Argos Translate model installation and translation.
- `src/discord.py` — Discord webhook/embed delivery.
- `src/main.py` — orchestration and persistent state.
- `.github/workflows/rust-update.yml` — scheduled automation.

The Discord webhook is never stored in source control.
