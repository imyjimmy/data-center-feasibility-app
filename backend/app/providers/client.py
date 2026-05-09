from typing import Any

import httpx


class ProviderHttpClient:
    def __init__(self, timeout: float = 20.0) -> None:
        self._timeout = timeout

    async def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            payload = response.json()

        if not isinstance(payload, (dict, list)):
            msg = f"Provider returned {type(payload).__name__}, expected JSON object or array"
            raise ValueError(msg)

        return payload
