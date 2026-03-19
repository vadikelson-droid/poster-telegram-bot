import asyncio
import logging

from aiohttp import web
from aiogram import Bot, Dispatcher

from bot import router as bot_router
from config import load_config
from database import Database
from poster_api import PosterAPIClient
from telegram_checker import TelegramChecker
from webhook_server import create_webhook_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    config = load_config()

    # Инициализация
    db = Database(config.db_path)
    await db.connect()

    poster = PosterAPIClient(config.poster_access_token)
    await poster.start()

    checker = TelegramChecker(
        config.telegram_api_id,
        config.telegram_api_hash,
        session_path="/opt/poster-telegram-bot/checker_session",
    )
    await checker.start()

    bot = Bot(token=config.telegram_bot_token)

    dp = Dispatcher()
    dp.include_router(bot_router)

    # Запуск HTTP сервера для вебхуков Poster
    webhook_app = create_webhook_app(config, db, poster, bot)
    runner = web.AppRunner(webhook_app)
    await runner.setup()
    site = web.TCPSite(runner, config.webhook_host, config.webhook_port)
    await site.start()
    logger.info(
        "Webhook server started on %s:%d",
        config.webhook_host,
        config.webhook_port,
    )

    # Запуск Telegram бота (polling)
    try:
        logger.info("Starting Telegram bot polling...")
        await dp.start_polling(bot, db=db, poster=poster, config=config, checker=checker)
    finally:
        logger.info("Shutting down...")
        await runner.cleanup()
        await checker.close()
        await poster.close()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
