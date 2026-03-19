from datetime import datetime
from typing import Any


def format_receipt(
    transaction: dict[str, Any],
    product_names: dict[str, str],
    client_name: str | None = None,
) -> str:
    lines: list[str] = []
    lines.append("<b>🧾 Чек</b>")
    lines.append("")

    date_close_raw = transaction.get("date_close_date") or ""
    if date_close_raw:
        lines.append(f"📅 Дата: {date_close_raw}")
    else:
        ts = int(transaction.get("date_close", "0"))
        if ts > 0:
            dt = datetime.fromtimestamp(ts / 1000)
            lines.append(f"📅 Дата: {dt.strftime('%d.%m.%Y %H:%M')}")

    order_id = transaction.get("transaction_id", "?")
    lines.append(f"№ Замовлення: {order_id}")

    if client_name:
        lines.append(f"👤 Клієнт: {client_name}")

    lines.append("")
    lines.append("<b>Товари:</b>")
    lines.append("\u2500" * 28)

    products = transaction.get("products", [])
    for p in products:
        pid = str(p.get("product_id", ""))
        name = product_names.get(pid, f"Товар #{pid}")
        qty = p.get("num", "1")
        price_cents = int(p.get("product_price", 0))
        paid_cents = int(p.get("payed_sum", 0))

        if int(qty) > 1:
            lines.append(f"  {name} x{qty}")
            lines.append(f"    {price_cents / 100:.2f} грн \u00d7 {qty} = {paid_cents / 100:.2f} грн")
        else:
            lines.append(f"  {name} \u2014 {paid_cents / 100:.2f} грн")

    lines.append("\u2500" * 28)

    total_cents = int(transaction.get("sum", 0))
    paid_cents = int(transaction.get("payed_sum", 0))
    discount = transaction.get("discount", "0")

    if discount and int(discount) > 0:
        lines.append(f"Підсумок: {total_cents / 100:.2f} грн")
        lines.append(f"Знижка: {discount}%")

    lines.append(f"<b>💰 Разом: {paid_cents / 100:.2f} грн</b>")

    payed_cash = int(transaction.get("payed_cash", 0))
    payed_card = int(transaction.get("payed_card", 0))
    payment_parts = []
    if payed_cash > 0:
        payment_parts.append(f"Готівка: {payed_cash / 100:.2f}")
    if payed_card > 0:
        payment_parts.append(f"Картка: {payed_card / 100:.2f}")
    if payment_parts:
        lines.append(f"Оплата: {', '.join(payment_parts)}")

    lines.append("")
    lines.append("<i>Дякуємо за відвідування! ❤️</i>")

    return "\n".join(lines)
