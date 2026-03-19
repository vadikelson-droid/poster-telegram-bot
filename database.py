import logging

import aiosqlite

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL UNIQUE,
                chat_id INTEGER NOT NULL,
                first_name TEXT,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone)"
        )
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    async def save_customer(
        self, phone: str, chat_id: int, first_name: str | None = None
    ) -> None:
        await self._db.execute(
            """INSERT INTO customers (phone, chat_id, first_name)
               VALUES (?, ?, ?)
               ON CONFLICT(phone) DO UPDATE SET
                   chat_id = excluded.chat_id,
                   first_name = excluded.first_name
            """,
            (phone, chat_id, first_name),
        )
        await self._db.commit()
        logger.info("Saved customer: phone=%s, chat_id=%d", phone, chat_id)

    async def find_chat_id_by_phone(self, phone: str) -> int | None:
        cursor = await self._db.execute(
            "SELECT chat_id FROM customers WHERE phone = ?",
            (phone,),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def find_phone_by_chat_id(self, chat_id: int) -> str | None:
        cursor = await self._db.execute(
            "SELECT phone FROM customers WHERE chat_id = ?",
            (chat_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def get_all_chat_ids(self) -> list[tuple[int, str]]:
        cursor = await self._db.execute(
            "SELECT chat_id, first_name FROM customers"
        )
        return await cursor.fetchall()

    async def find_customer_by_phone(self, phone: str) -> tuple[int, str] | None:
        cursor = await self._db.execute(
            "SELECT chat_id, first_name FROM customers WHERE phone = ?",
            (phone,),
        )
        row = await cursor.fetchone()
        return (row[0], row[1] or "") if row else None
