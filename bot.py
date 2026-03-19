import asyncio
import logging
import re

from aiogram import Bot, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    WebAppInfo,
)

from config import Config
from database import Database
from poster_api import PosterAPIClient
from telegram_checker import TelegramChecker

logger = logging.getLogger(__name__)
router = Router(name="bot")


class BroadcastStates(StatesGroup):
    choose_target = State()
    enter_phone = State()
    enter_message = State()
    confirm = State()


def normalize_phone(raw_phone: str) -> str:
    """Нормализация телефона к формату только цифры (380XXXXXXXXX)."""
    digits = re.sub(r"\D", "", raw_phone)
    if digits.startswith("0"):
        digits = "38" + digits
    if digits.startswith("80") and len(digits) == 11:
        digits = "3" + digits
    return digits


ORDER_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(
            text="🍕 Зробити замовлення",
            web_app=WebAppInfo(url="https://royal-food-pervo.ps.me/"),
        )],
    ],
    resize_keyboard=True,
)


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database, poster: PosterAPIClient) -> None:
    # Проверяем, зарегистрирован ли уже по chat_id
    already = await db.find_phone_by_chat_id(message.chat.id)
    if already:
        # Проверяем, есть ли клиент в Poster (мог быть удалён)
        try:
            existing = await poster.find_client_by_phone(already)
            if not existing:
                first_name = message.from_user.first_name or ""
                last_name = message.from_user.last_name or ""
                await poster.create_client(already, first_name, last_name)
                logger.info("Re-created client in Poster: phone=%s", already)
        except Exception:
            logger.exception("Failed to check/re-create client in Poster: phone=%s", already)

        await message.answer(
            "✅ Ви вже зареєстровані!\n\n"
            "Вам доступні:\n"
            "🧾 Чеки після кожного відвідування\n"
            "🔥 Акції та спеціальні пропозиції\n"
            "🎁 Розіграші та подарунки\n"
            "📢 Новини та оновлення меню\n\n"
            "Залишайтесь з нами! 💛",
            reply_markup=ORDER_KEYBOARD,
        )
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(
                text="📱 Поділитися номером телефону",
                request_contact=True,
            )]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer(
        "Привіт! 👋 Ласкаво просимо до Royal Food!\n\n"
        "Тут ви будете отримувати:\n"
        "🧾 Чеки після кожного відвідування\n"
        "🔥 Акції та спеціальні пропозиції\n"
        "🎁 Розіграші та подарунки\n"
        "📢 Новини та оновлення меню\n\n"
        "Щоб почати, натисніть кнопку нижче та поділіться своїм номером телефону.",
        reply_markup=keyboard,
    )


@router.message(lambda msg: msg.contact is not None)
async def handle_contact(message: Message, db: Database, poster: PosterAPIClient) -> None:
    contact = message.contact

    if contact.user_id != message.from_user.id:
        await message.answer("Будь ласка, надішліть свій номер телефону.")
        return

    phone = normalize_phone(contact.phone_number)
    chat_id = message.chat.id
    first_name = message.from_user.first_name or ""
    last_name = message.from_user.last_name or ""

    # Сохраняем в локальную базу
    await db.save_customer(phone, chat_id, first_name)

    # Создаём/находим клиента в Poster
    poster_status = ""
    try:
        existing = await poster.find_client_by_phone(phone)
        if existing:
            poster_status = "\n📋 Ви вже є в нашій базі клієнтів."
            logger.info("Client already exists in Poster: phone=%s", phone)
        else:
            await poster.create_client(phone, first_name, last_name)
            poster_status = "\n📋 Вас додано до нашої бази клієнтів."
            logger.info("Client created in Poster: phone=%s", phone)
    except Exception:
        logger.exception("Failed to sync client with Poster: phone=%s", phone)

    await message.answer(
        f"✅ Ваш номер успішно зареєстровано!\n"
        f"Тепер ви будете отримувати чеки після кожного відвідування."
        f"{poster_status}",
        reply_markup=ORDER_KEYBOARD,
    )
    logger.info("Customer registered: phone=%s, chat_id=%d", phone, chat_id)


@router.message(Command("clients"))
async def cmd_clients(
    message: Message, db: Database, poster: PosterAPIClient,
    config: Config, checker: TelegramChecker,
) -> None:
    if message.chat.id not in config.admin_chat_ids:
        return

    status_msg = await message.answer("Загружаю данные клиентов...")

    try:
        data = await poster._get("clients.getClients")
        poster_clients = data.get("response", [])
    except Exception:
        await status_msg.edit_text("Ошибка при загрузке клиентов из Poster.")
        return

    if not poster_clients:
        await status_msg.edit_text("В Poster нет клиентов.")
        return

    # Collect all phones for batch check
    clients_with_phone = []
    no_phone = []

    for client in poster_clients:
        phone = client.get("phone_number", "")
        name = f"{client.get('firstname', '')} {client.get('lastname', '')}".strip()
        if not name:
            name = client.get("client_name", "Без имени")

        if not phone:
            no_phone.append(f"  {name} — нет телефона")
        else:
            clients_with_phone.append((name, phone))

    all_phones = [phone for _, phone in clients_with_phone]

    # Progress callback
    async def on_progress(checked: int, total: int, wait_sec: int = 0) -> None:
        try:
            if wait_sec > 0:
                await status_msg.edit_text(
                    f"Проверяю Telegram... {checked}/{total}\n"
                    f"⏳ Пауза {wait_sec} сек (лимит Telegram)"
                )
            else:
                await status_msg.edit_text(
                    f"Проверяю Telegram... {checked}/{total} номеров"
                )
        except Exception:
            pass

    await status_msg.edit_text(
        f"Проверяю {len(all_phones)} номеров в Telegram..."
    )
    tg_phones = await checker.check_phones_batch(all_phones, progress_callback=on_progress)

    has_tg_and_bot = []
    has_tg_no_bot = []
    no_telegram = []

    for name, phone in clients_with_phone:
        has_tg = phone in tg_phones
        chat_id = await db.find_chat_id_by_phone(phone)

        if has_tg and chat_id:
            has_tg_and_bot.append(f"  ✅ {name} — +{phone}")
        elif has_tg and not chat_id:
            has_tg_no_bot.append(f"  📱 {name} — +{phone}")
        else:
            no_telegram.append(f"  ❌ {name} — +{phone}")

    total = len(poster_clients)
    lines = [
        f"<b>Клиенты Poster:</b> {total}",
        f"<b>✅ Telegram + бот:</b> {len(has_tg_and_bot)}",
        f"<b>📱 Есть Telegram, нет бота:</b> {len(has_tg_no_bot)}",
        f"<b>❌ Нет Telegram:</b> {len(no_telegram)}",
        f"<b>📵 Нет телефона:</b> {len(no_phone)}",
        "",
    ]

    if has_tg_and_bot:
        lines.append("<b>✅ Получают чеки:</b>")
        lines.extend(has_tg_and_bot)
        lines.append("")

    if has_tg_no_bot:
        lines.append("<b>📱 Есть Telegram, но не писали боту:</b>")
        lines.extend(has_tg_no_bot)
        lines.append("")

    if no_telegram:
        lines.append("<b>❌ Нет Telegram на этом номере:</b>")
        lines.extend(no_telegram)
        lines.append("")

    if no_phone:
        lines.append("<b>📵 Без телефона:</b>")
        lines.extend(no_phone)

    # Split into messages if too long (Telegram limit 4096 chars)
    text = "\n".join(lines)
    while text:
        chunk = text[:4000]
        if len(text) > 4000:
            last_nl = chunk.rfind("\n")
            if last_nl > 0:
                chunk = text[:last_nl]
            text = text[len(chunk):]
        else:
            text = ""
        await message.answer(chunk, parse_mode="HTML")

    await status_msg.delete()


# ── Broadcast / Send ──────────────────────────────────────────────

TARGET_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📢 Всім"), KeyboardButton(text="👤 Одному")],
        [KeyboardButton(text="❌ Скасувати")],
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)

CONFIRM_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ Так"), KeyboardButton(text="❌ Ні")],
    ],
    resize_keyboard=True,
    one_time_keyboard=True,
)

CANCEL_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Скасувати")]],
    resize_keyboard=True,
    one_time_keyboard=True,
)


@router.message(Command("send"))
async def cmd_send(message: Message, state: FSMContext, config: Config) -> None:
    if message.chat.id not in config.admin_chat_ids:
        return

    await state.clear()
    await message.answer("Кому відправити?", reply_markup=TARGET_KEYBOARD)
    await state.set_state(BroadcastStates.choose_target)


@router.message(BroadcastStates.choose_target)
async def on_choose_target(message: Message, state: FSMContext, db: Database) -> None:
    text = message.text or ""

    if text == "❌ Скасувати":
        await state.clear()
        await message.answer("Скасовано.", reply_markup=ReplyKeyboardRemove())
        return

    if text == "📢 Всім":
        customers = await db.get_all_chat_ids()
        if not customers:
            await state.clear()
            await message.answer("Немає зареєстрованих клієнтів.", reply_markup=ReplyKeyboardRemove())
            return
        await state.update_data(target="all", count=len(customers))
        await message.answer(
            f"Клієнтів у базі: {len(customers)}\n"
            "Надішліть повідомлення (текст, фото або фото з підписом):",
            reply_markup=CANCEL_KEYBOARD,
        )
        await state.set_state(BroadcastStates.enter_message)

    elif text == "👤 Одному":
        await state.update_data(target="one")
        await message.answer(
            "Введіть номер телефону (380XXXXXXXXX):",
            reply_markup=CANCEL_KEYBOARD,
        )
        await state.set_state(BroadcastStates.enter_phone)
    else:
        await message.answer("Оберіть кнопку нижче:", reply_markup=TARGET_KEYBOARD)


@router.message(BroadcastStates.enter_phone)
async def on_enter_phone(message: Message, state: FSMContext, db: Database) -> None:
    text = message.text or ""

    if text == "❌ Скасувати":
        await state.clear()
        await message.answer("Скасовано.", reply_markup=ReplyKeyboardRemove())
        return

    phone = normalize_phone(text)
    if len(phone) < 10:
        await message.answer("Невірний формат. Введіть номер (380XXXXXXXXX):", reply_markup=CANCEL_KEYBOARD)
        return

    customer = await db.find_customer_by_phone(phone)
    if not customer:
        await message.answer(
            f"Клієнт з номером +{phone} не знайдений у боті.\nСпробуйте інший номер:",
            reply_markup=CANCEL_KEYBOARD,
        )
        return

    chat_id, name = customer
    await state.update_data(target="one", recipient_chat_id=chat_id, recipient_name=name, recipient_phone=phone)
    await message.answer(
        f"Клієнт: {name or 'Без імені'} (+{phone})\n"
        "Надішліть повідомлення (текст, фото або фото з підписом):",
        reply_markup=CANCEL_KEYBOARD,
    )
    await state.set_state(BroadcastStates.enter_message)


@router.message(BroadcastStates.enter_message)
async def on_enter_message(message: Message, state: FSMContext) -> None:
    if message.text == "❌ Скасувати":
        await state.clear()
        await message.answer("Скасовано.", reply_markup=ReplyKeyboardRemove())
        return

    # Save message data
    msg_data = {}
    if message.photo:
        msg_data["type"] = "photo"
        msg_data["photo_id"] = message.photo[-1].file_id
        msg_data["caption"] = message.caption or ""
    elif message.text:
        msg_data["type"] = "text"
        msg_data["text"] = message.text
    else:
        await message.answer("Підтримується тільки текст або фото. Спробуйте ще раз:", reply_markup=CANCEL_KEYBOARD)
        return

    data = await state.get_data()
    await state.update_data(msg=msg_data)

    if data.get("target") == "all":
        preview = msg_data.get("text") or msg_data.get("caption") or "(фото без підпису)"
        if len(preview) > 100:
            preview = preview[:100] + "..."
        await message.answer(
            f"Надіслати {data['count']} клієнтам?\n\n"
            f"Превʼю: {preview}",
            reply_markup=CONFIRM_KEYBOARD,
        )
        await state.set_state(BroadcastStates.confirm)
    else:
        # Send to one person immediately
        await _do_send_one(message, state)


@router.message(BroadcastStates.confirm)
async def on_confirm(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    text = message.text or ""

    if text == "❌ Ні" or text == "❌ Скасувати":
        await state.clear()
        await message.answer("Скасовано.", reply_markup=ReplyKeyboardRemove())
        return

    if text != "✅ Так":
        await message.answer("Натисніть кнопку:", reply_markup=CONFIRM_KEYBOARD)
        return

    data = await state.get_data()
    msg_data = data["msg"]
    await state.clear()

    customers = await db.get_all_chat_ids()
    total = len(customers)
    sent = 0
    errors = 0

    status_msg = await message.answer(
        f"Відправляю... 0/{total}",
        reply_markup=ReplyKeyboardRemove(),
    )

    for chat_id, name in customers:
        try:
            if msg_data["type"] == "text":
                await bot.send_message(chat_id=chat_id, text=msg_data["text"])
            elif msg_data["type"] == "photo":
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=msg_data["photo_id"],
                    caption=msg_data.get("caption"),
                )
            sent += 1
        except Exception:
            errors += 1
            logger.warning("Failed to send broadcast to chat_id=%d", chat_id)

        if (sent + errors) % 10 == 0:
            try:
                await status_msg.edit_text(f"Відправляю... {sent + errors}/{total}")
            except Exception:
                pass

        await asyncio.sleep(0.05)

    await status_msg.edit_text(
        f"✅ Розсилка завершена!\n"
        f"Надіслано: {sent} | Помилки: {errors}"
    )
    logger.info("Broadcast done: sent=%d, errors=%d, total=%d", sent, errors, total)


async def _do_send_one(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    msg_data = data["msg"]
    chat_id = data["recipient_chat_id"]
    name = data.get("recipient_name", "")
    phone = data.get("recipient_phone", "")
    await state.clear()

    bot: Bot = message.bot
    try:
        if msg_data["type"] == "text":
            await bot.send_message(chat_id=chat_id, text=msg_data["text"])
        elif msg_data["type"] == "photo":
            await bot.send_photo(
                chat_id=chat_id,
                photo=msg_data["photo_id"],
                caption=msg_data.get("caption"),
            )
        await message.answer(
            f"✅ Надіслано клієнту {name} (+{phone})!",
            reply_markup=ReplyKeyboardRemove(),
        )
    except Exception:
        logger.exception("Failed to send to chat_id=%d", chat_id)
        await message.answer(
            f"❌ Не вдалося надіслати клієнту {name} (+{phone}). "
            "Можливо, він заблокував бота.",
            reply_markup=ReplyKeyboardRemove(),
        )
