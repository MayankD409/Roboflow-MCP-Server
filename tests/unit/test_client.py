"""Tests for roboflow_mcp.client."""

from __future__ import annotations

import httpx
import pytest
import respx
from pydantic import SecretStr

from roboflow_mcp.client import RoboflowClient
from roboflow_mcp.config import RoboflowSettings
from roboflow_mcp.errors import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    RoboflowAPIError,
)


def _make_settings(
    api_key: str = "k_test", url: str = "https://api.roboflow.com"
) -> RoboflowSettings:
    return RoboflowSettings.model_construct(
        api_key=SecretStr(api_key),
        workspace=None,
        api_url=url,
        log_level="INFO",
    )


@respx.mock
async def test_api_key_is_appended_to_params() -> None:
    route = respx.get("https://api.roboflow.com/foo").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    async with RoboflowClient(_make_settings("secret_key")) as client:
        result = await client.request("GET", "/foo")

    assert result == {"ok": True}
    assert route.called
    sent_params = dict(route.calls.last.request.url.params)
    assert sent_params["api_key"] == "secret_key"


@respx.mock
async def test_401_raises_authentication_error() -> None:
    respx.get("https://api.roboflow.com/foo").mock(
        return_value=httpx.Response(401, json={"message": "bad key"})
    )
    async with RoboflowClient(_make_settings()) as client:
        with pytest.raises(AuthenticationError, match="bad key"):
            await client.request("GET", "/foo")


@respx.mock
async def test_403_raises_authentication_error() -> None:
    respx.get("https://api.roboflow.com/foo").mock(
        return_value=httpx.Response(403, json={"message": "forbidden"})
    )
    async with RoboflowClient(_make_settings()) as client:
        with pytest.raises(AuthenticationError):
            await client.request("GET", "/foo")


@respx.mock
async def test_404_raises_not_found() -> None:
    respx.get("https://api.roboflow.com/missing").mock(
        return_value=httpx.Response(404, json={"message": "gone"})
    )
    async with RoboflowClient(_make_settings()) as client:
        with pytest.raises(NotFoundError):
            await client.request("GET", "/missing")


@respx.mock
async def test_429_retries_then_raises_rate_limit() -> None:
    respx.get("https://api.roboflow.com/busy").mock(
        return_value=httpx.Response(
            429, json={"message": "slow down"}, headers={"retry-after": "2"}
        )
    )
    async with RoboflowClient(_make_settings()) as client:
        with pytest.raises(RateLimitError) as ei:
            await client.request("GET", "/busy")

    assert ei.value.retry_after == 2.0


@respx.mock
async def test_500_raises_api_error_with_payload() -> None:
    respx.get("https://api.roboflow.com/boom").mock(
        return_value=httpx.Response(500, json={"message": "kaboom", "trace": "..."})
    )
    async with RoboflowClient(_make_settings()) as client:
        with pytest.raises(RoboflowAPIError) as ei:
            await client.request("GET", "/boom")

    assert ei.value.status == 500
    assert ei.value.payload["trace"] == "..."


@respx.mock
async def test_non_json_response_returns_bytes() -> None:
    respx.get("https://api.roboflow.com/blob").mock(
        return_value=httpx.Response(
            200, content=b"\x89PNG\r\n", headers={"content-type": "image/png"}
        )
    )
    async with RoboflowClient(_make_settings()) as client:
        result = await client.request("GET", "/blob")

    assert isinstance(result, bytes)
    assert result.startswith(b"\x89PNG")


@respx.mock
async def test_retry_succeeds_after_transient_rate_limit() -> None:
    route = respx.get("https://api.roboflow.com/flaky").mock(
        side_effect=[
            httpx.Response(429, json={"message": "wait"}, headers={"retry-after": "0"}),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    async with RoboflowClient(_make_settings()) as client:
        result = await client.request("GET", "/flaky")

    assert result == {"ok": True}
    assert route.call_count == 2


@respx.mock
async def test_custom_api_url_is_honoured() -> None:
    respx.get("https://proxy.example/api/foo").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    async with RoboflowClient(
        _make_settings(url="https://proxy.example/api")
    ) as client:
        result = await client.request("GET", "/foo")

    assert result == {"ok": True}
