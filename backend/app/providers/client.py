from typing import Any

import httpx


class ProviderHttpClient:
    def __init__(self, timeout: float = 20.0) -> None:
        self._timeout = timeout

    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, dict):
            msg = f"Provider returned {type(payload).__name__}, expected JSON object"
            raise ValueError(msg)

        return payload
