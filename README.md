# Poster Telegram Bot

> Telegram bot that sends restaurant order receipts to customers. Integrates with Poster POS system via webhooks.

## Features

| Feature | Details |
|---------|---------|
| **POS Integration** | Receives order events from Poster POS via webhook |
| **Receipt Formatting** | Generates formatted receipts with items, prices, totals |
| **Customer Matching** | Links Poster customers to Telegram accounts via phone number |
| **Multi-admin** | Multiple admin accounts with different notification levels |
| **Auto-discovery** | Finds customer Telegram accounts by phone number (Telethon) |
| **Persistent Storage** | SQLite database for customer-Telegram ID mapping |

## Architecture

```
Poster POS → Webhook (aiohttp) → Process Order → Format Receipt → Send via Telegram
                                       ↓
                                  SQLite Database
                                  (customer mapping)
```

Single process runs both:
- **aiogram** polling (Telegram bot commands)
- **aiohttp** webhook server (Poster POS events)

## Tech Stack

- **aiogram 3.x** — async Telegram Bot framework
- **aiohttp** — webhook server for POS events
- **aiosqlite** — async SQLite for customer data
- **Telethon** — Telegram client API for phone→account lookup
- **Poster API** — POS system integration

## Project Structure

```
poster-telegram-bot/
├── main.py               # Entry point — runs bot + webhook server
├── bot.py                # Telegram bot handlers and commands
├── webhook_server.py     # aiohttp server for Poster webhooks
├── poster_api.py         # Poster POS API client
├── receipt_formatter.py  # Order → formatted text receipt
├── database.py           # SQLite operations (customer mapping)
├── telegram_checker.py   # Phone number → Telegram ID lookup
├── config.py             # Environment-based configuration
└── requirements.txt      # Python dependencies
```

## Setup

```bash
# Clone and install
git clone https://github.com/vadikelson-droid/poster-telegram-bot.git
cd poster-telegram-bot
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your Telegram bot token and Poster API credentials

# Run
python main.py
```

## Technologies

`Python` `aiogram` `aiohttp` `aiosqlite` `Telethon` `SQLite` `REST API` `asyncio`

## Author

**Vadim Elson** — [Portfolio](https://vadikelson-droid.github.io/vadim-portfolio/) | [Telegram](https://t.me/lord_elson_05)
