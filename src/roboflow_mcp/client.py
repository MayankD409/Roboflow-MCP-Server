"""Thin async HTTP client around the Roboflow REST API.

The client does five things and nothing else:

1. Injects ``api_key`` into every request so callers don't have to.
2. Maps Roboflow status codes onto typed exceptions from :mod:`roboflow_mcp.errors`.
3. Retries transient failures (429 / network blips) with exponential backoff.
4. Enforces a client-side quota (token bucket, per-minute and per-hour).
5. Trips a circuit breaker after repeated server errors so the LLM can't
   chew through a workspace's quota on a broken endpoint.

Tools call this client; they do not talk to ``httpx`` directly. That keeps
retry and error-mapping logic in one place.
"""

from __future__ import annotations

import time
from collections import deque
from types import TracebackType
from typing import Any

import anyio
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
    CircuitOpenError,
    ConfigurationError,
    NotFoundError,
    QuotaExceededError,
    RateLimitError,
    RoboflowAPIError,
)

_DEFAULT_TIMEOUT = 30.0
_MAX_ATTEMPTS = 3


class _TokenBucket:
    """Two-window sliding counter. Rejects with :class:`QuotaExceededError`."""

    def __init__(self, per_minute: int, per_hour: int) -> None:
        self._per_minute = per_minute
        self._per_hour = per_hour
        self._minute: deque[float] = deque()
        self._hour: deque[float] = deque()
        self._lock = anyio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self._drain(now)
            if len(self._minute) >= self._per_minute:
                retry_after = 60.0 - (now - self._minute[0])
                raise QuotaExceededError(
                    f"Client-side rate limit reached: "
                    f"{self._per_minute} requests/minute.",
                    retry_after=max(retry_after, 0.0),
                )
            if len(self._hour) >= self._per_hour:
                retry_after = 3600.0 - (now - self._hour[0])
                raise QuotaExceededError(
                    f"Client-side rate limit reached: {self._per_hour} requests/hour.",
                    retry_after=max(retry_after, 0.0),
                )
            self._minute.append(now)
            self._hour.append(now)

    def _drain(self, now: float) -> None:
        while self._minute and now - self._minute[0] >= 60.0:
            self._minute.popleft()
        while self._hour and now - self._hour[0] >= 3600.0:
            self._hour.popleft()


class _CircuitBreaker:
    """Simple consecutive-failure circuit breaker.

    Trips open after ``threshold`` consecutive 5xx responses. Stays open for
    ``cooldown_s`` seconds, then allows exactly one probe through
    (half-open). A successful probe closes the circuit; a failing probe
    reopens it.
    """

    def __init__(self, threshold: int, cooldown_s: float) -> None:
        self._threshold = threshold
        self._cooldown_s = cooldown_s
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._lock = anyio.Lock()

    async def before_request(self) -> None:
        async with self._lock:
            if self._opened_at is None:
                return
            elapsed = time.monotonic() - self._opened_at
            if elapsed < self._cooldown_s:
                raise CircuitOpenError(
                    "Circuit breaker is open after repeated server errors.",
                    retry_after=self._cooldown_s - elapsed,
                )
            # Cooldown elapsed: allow this request through as a probe.
            # We leave `_opened_at` set until `record_outcome` resets it on
            # success, so an overlapping probe during the cooldown still
            # counts as a single attempt.
            self._opened_at = None
            self._consecutive_failures = 0

    async def record_outcome(self, *, success: bool) -> None:
        async with self._lock:
            if success:
                self._consecutive_failures = 0
                self._opened_at = None
                return
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._threshold:
                self._opened_at = time.monotonic()


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
        self._check_tls(settings)
        self._client = httpx.AsyncClient(
            base_url=settings.api_url,
            timeout=timeout,
            transport=transport,
            verify=True,
        )
        self._bucket = _TokenBucket(
            per_minute=settings.rate_limit_per_minute,
            per_hour=settings.rate_limit_per_hour,
        )
        self._breaker = _CircuitBreaker(
            threshold=settings.circuit_breaker_threshold,
            cooldown_s=settings.circuit_breaker_cooldown_s,
        )

    @staticmethod
    def _check_tls(settings: RoboflowSettings) -> None:
        url = settings.api_url.lower()
        if url.startswith("https://"):
            return
        if settings.allow_insecure:
            # Operator opted in to HTTP for local dev against a proxy or
            # self-hosted endpoint. We don't fail, but we also don't try to
            # paper over the risk — the audit log will still record the
            # cleartext URL, and anyone reading the code knows it happened.
            return
        raise ConfigurationError(
            f"ROBOFLOW_API_URL={settings.api_url!r} must use https:// . "
            "Set ROBOFLOW_MCP_ALLOW_INSECURE=1 to override for local "
            "development against a trusted proxy."
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
        """Send a request, auto-authenticated, quota-gated, auto-retried."""
        params = dict(kwargs.pop("params", None) or {})
        params.setdefault("api_key", self._settings.api_key.get_secret_value())
        kwargs["params"] = params

        await self._bucket.acquire()
        await self._breaker.before_request()

        retrying = AsyncRetrying(
            stop=stop_after_attempt(_MAX_ATTEMPTS),
            wait=wait_exponential(multiplier=0.5, min=0, max=5),
            retry=retry_if_exception_type((RateLimitError, httpx.TransportError)),
            reraise=True,
        )
        try:
            async for attempt in retrying:
                with attempt:
                    response = await self._client.request(method, path, **kwargs)
                    self._raise_for_status(response)
                    await self._breaker.record_outcome(success=True)
                    return _parse_response(response)
        except (RoboflowAPIError, httpx.TransportError):
            # Any 5xx or transport failure that survives retry counts against
            # the circuit breaker. 4xx responses (auth, not-found, etc.) are
            # caller errors, not server errors — don't trip the breaker.
            await self._breaker.record_outcome(success=False)
            raise
        except Exception:
            raise

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
