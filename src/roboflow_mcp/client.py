"""Thin async HTTP client around the Roboflow REST API.

The client does three things and nothing else:

1. Injects ``api_key`` into every request so callers don't have to.
2. Maps Roboflow status codes onto typed exceptions from :mod:`roboflow_mcp.errors`.
3. Retries on transient failures (429 and network blips) with exponential backoff.

Tools call this client; they do not talk to ``httpx`` directly. That keeps
retry and error-mapping logic in one place.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import RoboflowSettings
from .errors import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    RoboflowAPIError,
)

_DEFAULT_TIMEOUT = 30.0
_MAX_ATTEMPTS = 3


class RoboflowClient:
    """Async HTTP client for the Roboflow REST API."""

    def __init__(
        self,
        settings: RoboflowSettings,
        *,
        timeout: float = _DEFAULT_TIMEOUT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.api_url,
            timeout=timeout,
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> RoboflowClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        """Send a request, auto-authenticated and auto-retried."""
        params = dict(kwargs.pop("params", None) or {})
        params.setdefault("api_key", self._settings.api_key.get_secret_value())
        kwargs["params"] = params

        retrying = AsyncRetrying(
            stop=stop_after_attempt(_MAX_ATTEMPTS),
            wait=wait_exponential(multiplier=0.5, min=0, max=5),
            retry=retry_if_exception_type((RateLimitError, httpx.TransportError)),
            reraise=True,
        )
        async for attempt in retrying:
            with attempt:
                response = await self._client.request(method, path, **kwargs)
                self._raise_for_status(response)
                return _parse_response(response)

        # Unreachable: AsyncRetrying with reraise=True either returns or raises.
        raise RuntimeError("retry loop exited without a result")  # pragma: no cover

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.is_success:
            return

        status = response.status_code
        payload = _safe_json(response)
        message = _extract_message(payload, response)

        if status in (401, 403):
            raise AuthenticationError(message)
        if status == 404:
            raise NotFoundError(message)
        if status == 429:
            retry_after = _parse_retry_after(response)
            raise RateLimitError(message, retry_after=retry_after)
        raise RoboflowAPIError(status, message, payload=payload)


def _parse_response(response: httpx.Response) -> Any:
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        return response.json()
    return response.content


def _safe_json(response: httpx.Response) -> dict[str, object]:
    if not response.content:
        return {}
    try:
        data = response.json()
    except ValueError:
        return {"raw": response.text}
    return data if isinstance(data, dict) else {"body": data}


def _extract_message(payload: dict[str, object], response: httpx.Response) -> str:
    for key in ("message", "error"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return response.reason_phrase or f"HTTP {response.status_code}"


def _parse_retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None
