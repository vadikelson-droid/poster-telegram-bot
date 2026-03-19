import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    telegram_bot_token: str
    poster_access_token: str
    poster_app_secret: str
    poster_account_name: str
    webhook_host: str
    webhook_port: int
    db_path: str
    admin_chat_ids: frozenset[int]
    telegram_api_id: int
    telegram_api_hash: str


def load_config() -> Config:
    return Config(
        telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        poster_access_token=os.environ["POSTER_ACCESS_TOKEN"],
        poster_app_secret=os.environ["POSTER_APP_SECRET"],
        poster_account_name=os.environ.get("POSTER_ACCOUNT_NAME", ""),
        webhook_host=os.environ.get("WEBHOOK_HOST", "0.0.0.0"),
        webhook_port=int(os.environ.get("PORT", os.environ.get("WEBHOOK_PORT", "8080"))),
        db_path=os.environ.get("DB_PATH", "customers.db"),
        admin_chat_ids=frozenset(
            int(x.strip()) for x in os.environ.get("ADMIN_CHAT_IDS", "").split(",") if x.strip()
        ),
        telegram_api_id=int(os.environ.get("TELEGRAM_API_ID", "0")),
        telegram_api_hash=os.environ.get("TELEGRAM_API_HASH", ""),
    )
