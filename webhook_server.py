import hashlib
import logging

from aiohttp import web
from aiogram import Bot

from bot import normalize_phone
from config import Config
from database import Database
from poster_api import PosterAPIClient
from receipt_formatter import format_receipt

logger = logging.getLogger(__name__)


def verify_poster_webhook(
    account: str,
    object_type: str,
    object_id: str,
    action: str,
    data: str,
    time: str,
    secret: str,
    received_verify: str,
) -> bool:
    parts = [account, object_type, object_id, action]
    if data:
        parts.append(data)
    parts.extend([time, secret])
    payload = ";".join(parts)
    computed = hashlib.md5(payload.encode()).hexdigest()
    return computed == received_verify


async def handle_poster_webhook(request: web.Request) -> web.Response:
    config: Config = request.app["config"]
    db: Database = request.app["db"]
    poster: PosterAPIClient = request.app["poster"]
    bot: Bot = request.app["bot"]

    post_data = await request.post()

    account = post_data.get("account", "")
    object_type = post_data.get("object", "")
    object_id = post_data.get("object_id", "")
    action = post_data.get("action", "")
    time_str = post_data.get("time", "")
    verify = post_data.get("verify", "")
    data = post_data.get("data", "")

    logger.info(
        "Webhook: object=%s, object_id=%s, action=%s",
        object_type, object_id, action,
    )

    # Проверка подписи
    if not verify_poster_webhook(
        account, object_type, object_id, action,
        data, time_str, config.poster_app_secret, verify,
    ):
        logger.warning("Webhook signature verification failed!")
        return web.json_response(
            {"status": "error", "reason": "invalid signature"}, status=403
        )

    # Обрабатываем только транзакции
    if object_type != "transaction":
        return web.json_response({"status": "ok"})

    if action not in ("changed", "added"):
        return web.json_response({"status": "ok"})

    # Получаем данные транзакции
    try:
        transaction = await poster.get_transaction(object_id)
    except Exception:
        logger.exception("Failed to fetch transaction %s", object_id)
        return web.json_response({"status": "ok"})

    if not transaction:
        logger.warning("Transaction %s not found", object_id)
        return web.json_response({"status": "ok"})

    # Проверяем что заказ закрыт (status=2)
    if str(transaction.get("status")) != "2":
        logger.debug("Transaction %s not closed, skipping", object_id)
        return web.json_response({"status": "ok"})

    # Получаем телефон клиента
    client_id = transaction.get("client_id", "0")
    phone = None
    client_name = None

    if client_id and str(client_id) != "0":
        try:
            client = await poster.get_client(client_id)
            if client:
                phone = client.get("phone_number")
                firstname = client.get("firstname", "")
                lastname = client.get("lastname", "")
                client_name = f"{firstname} {lastname}".strip() or None
        except Exception:
            logger.exception("Failed to fetch client %s", client_id)

    if not phone:
        logger.info("Transaction %s: no client phone, skipping", object_id)
        return web.json_response({"status": "ok"})

    # Ищем chat_id по телефону
    normalized_phone = normalize_phone(phone)
    chat_id = await db.find_chat_id_by_phone(normalized_phone)

    if not chat_id:
        logger.info("Phone %s not registered in bot", normalized_phone)
        return web.json_response({"status": "ok"})

    # Получаем названия товаров
    product_names: dict[str, str] = {}
    for product in transaction.get("products", []):
        pid = str(product.get("product_id", ""))
        if pid and pid not in product_names:
            try:
                prod_info = await poster.get_product(pid)
                if prod_info:
                    product_names[pid] = prod_info.get(
                        "product_name", f"Товар #{pid}"
                    )
            except Exception:
                product_names[pid] = f"Товар #{pid}"

    # Форматируем и отправляем чек
    receipt_text = format_receipt(transaction, product_names, client_name)

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=receipt_text,
            parse_mode="HTML",
        )
        logger.info("Receipt sent: transaction %s -> chat %d", object_id, chat_id)
    except Exception:
        logger.exception("Failed to send receipt to chat %d", chat_id)

    return web.json_response({"status": "ok"})


def create_webhook_app(
    config: Config,
    db: Database,
    poster: PosterAPIClient,
    bot: Bot,
) -> web.Application:
    app = web.Application()
    app["config"] = config
    app["db"] = db
    app["poster"] = poster
    app["bot"] = bot

    app.router.add_post("/poster-webhook", handle_poster_webhook)

    async def health_check(request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    app.router.add_get("/health", health_check)

    return app
