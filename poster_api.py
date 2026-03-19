import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

POSTER_API_BASE = "https://joinposter.com/api"


class PosterAPIClient:
    def __init__(self, access_token: str):
        self._token = access_token
        self._session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        self._session = aiohttp.ClientSession()

    async def close(self) -> None:
        if self._session:
            await self._session.close()

    async def _get(self, method: str, **params: str) -> dict[str, Any]:
        params["token"] = self._token
        url = f"{POSTER_API_BASE}/{method}"
        async with self._session.get(url, params=params) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def get_transaction(self, transaction_id: str | int) -> dict[str, Any] | None:
        data = await self._get(
            "dash.getTransaction",
            transaction_id=str(transaction_id),
            include_products="true",
        )
        response = data.get("response", [])
        return response[0] if response else None

    async def get_client(self, client_id: str | int) -> dict[str, Any] | None:
        data = await self._get(
            "clients.getClient",
            client_id=str(client_id),
        )
        response = data.get("response", [])
        return response[0] if response else None

    async def get_product(self, product_id: str | int) -> dict[str, Any] | None:
        data = await self._get(
            "menu.getProduct",
            product_id=str(product_id),
        )
        return data.get("response")

    async def _post(self, method: str, **params: str) -> dict[str, Any]:
        url = f"{POSTER_API_BASE}/{method}?token={self._token}"
        form = aiohttp.FormData(charset="utf-8")
        for k, v in params.items():
            form.add_field(k, v)
        async with self._session.post(url, data=form) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def create_client(
        self,
        phone: str,
        first_name: str = "",
        last_name: str = "",
    ) -> dict[str, Any] | None:
        """Создать клиента в Poster. Возвращает данные созданного клиента."""
        if not phone.startswith("+"):
            phone = "+" + phone
        data = await self._post(
            "clients.createClient",
            client_name=f"{first_name} {last_name}".strip() or "Telegram",
            client_groups_id_client="1",
            phone=phone,
        )
        return data.get("response")

    async def find_client_by_phone(self, phone: str) -> dict[str, Any] | None:
        """Поиск клиента по номеру телефона."""
        data = await self._get("clients.getClients")
        clients = data.get("response", [])
        for client in clients:
            client_phone = client.get("phone_number", "")
            if client_phone == phone:
                return client
        return None
