import asyncio
import logging
import time

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.functions.contacts import ImportContactsRequest, DeleteContactsRequest
from telethon.tl.types import InputPhoneContact

logger = logging.getLogger(__name__)

BATCH_SIZE = 5
BATCH_DELAY = 3
CACHE_TTL = 3600  # 1 hour


class TelegramChecker:
    def __init__(self, api_id: int, api_hash: str, session_path: str = "checker_session"):
        self._api_id = api_id
        self._api_hash = api_hash
        self._session_path = session_path
        self._client: TelegramClient | None = None
        self._cache: dict[str, bool] = {}
        self._cache_time: float = 0

    async def start(self) -> None:
        self._client = TelegramClient(self._session_path, self._api_id, self._api_hash)
        await self._client.start()
        logger.info("TelegramChecker started")

    async def close(self) -> None:
        if self._client:
            await self._client.disconnect()

    def _normalize(self, phone: str) -> str:
        """Normalize to 380XXXXXXXXX format."""
        p = phone.lstrip("+").strip()
        if p.startswith("0") and len(p) == 10:
            p = "38" + p
        return p

    async def _check_batch(self, phones: list[str]) -> set[str]:
        """Check a batch of phones. Returns set of normalized phones that have Telegram."""
        contacts = []
        for i, phone in enumerate(phones):
            contacts.append(InputPhoneContact(
                client_id=i,
                phone=f"+{phone}",
                first_name=f"c{i}",
                last_name="",
            ))

        try:
            result = await self._client(ImportContactsRequest(contacts))
        except FloodWaitError as e:
            logger.warning("FloodWait %d sec on Import, waiting...", e.seconds)
            await asyncio.sleep(e.seconds + 1)
            try:
                result = await self._client(ImportContactsRequest(contacts))
            except FloodWaitError as e2:
                logger.error("FloodWait again %d sec, skipping batch", e2.seconds)
                return set()
        except Exception:
            logger.exception("ImportContacts failed")
            return set()

        found = set()
        for user in result.users:
            if user.phone:
                tg_phone = self._normalize(user.phone)
                for orig in phones:
                    if self._normalize(orig) == tg_phone:
                        found.add(orig)
                        break

        # Clean up imported contacts, ignore FloodWait on delete
        if result.users:
            try:
                await self._client(DeleteContactsRequest(id=result.users))
            except FloodWaitError as e:
                logger.debug("FloodWait %d sec on Delete, skipping cleanup", e.seconds)
            except Exception:
                pass

        return found

    async def check_phones_batch(self, phones: list[str], progress_callback=None) -> set[str]:
        """Check all phones in batches. Returns set of phones that have Telegram.

        progress_callback(checked, total, wait_sec) is called after each batch.
        wait_sec > 0 means FloodWait is happening.
        """
        if not phones:
            return set()

        # Check cache
        if self._cache and (time.time() - self._cache_time) < CACHE_TTL:
            logger.info("Using cached results (%d entries)", len(self._cache))
            return {p for p in phones if self._cache.get(self._normalize(p), False)}

        # Normalize all phones
        norm_phones = [self._normalize(p) for p in phones]
        # Deduplicate but keep mapping
        unique_phones = list(set(norm_phones))

        all_found_norm = set()
        total = len(unique_phones)

        for i in range(0, total, BATCH_SIZE):
            batch = unique_phones[i:i + BATCH_SIZE]

            # Import contacts
            contacts = []
            for j, phone in enumerate(batch):
                contacts.append(InputPhoneContact(
                    client_id=j,
                    phone=f"+{phone}",
                    first_name=f"c{j}",
                    last_name="",
                ))

            try:
                result = await self._client(ImportContactsRequest(contacts))
            except FloodWaitError as e:
                logger.warning("FloodWait %d sec, waiting...", e.seconds)
                if progress_callback:
                    await progress_callback(min(i, total), total, e.seconds)
                await asyncio.sleep(e.seconds + 1)
                try:
                    result = await self._client(ImportContactsRequest(contacts))
                except FloodWaitError as e2:
                    logger.error("FloodWait again, skipping batch")
                    continue
            except Exception:
                logger.exception("ImportContacts failed")
                continue

            for user in result.users:
                if user.phone:
                    tg_phone = self._normalize(user.phone)
                    for orig in batch:
                        if self._normalize(orig) == tg_phone:
                            all_found_norm.add(orig)
                            break

            # Clean up, don't wait on FloodWait for delete
            if result.users:
                try:
                    await self._client(DeleteContactsRequest(id=result.users))
                except FloodWaitError:
                    pass
                except Exception:
                    pass

            checked = min(i + BATCH_SIZE, total)
            logger.info("Batch %d-%d: %d found (total: %d/%d)",
                        i, checked, len(result.users), len(all_found_norm), total)

            if progress_callback:
                await progress_callback(checked, total, 0)

            if i + BATCH_SIZE < total:
                await asyncio.sleep(BATCH_DELAY)

        # Update cache
        self._cache = {p: (p in all_found_norm) for p in unique_phones}
        self._cache_time = time.time()

        logger.info("Total: %d/%d have Telegram", len(all_found_norm), total)

        # Map back to original phones
        return {p for p in phones if self._normalize(p) in all_found_norm}

    def clear_cache(self) -> None:
        self._cache.clear()
        self._cache_time = 0
