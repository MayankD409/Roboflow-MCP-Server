"""Tests for roboflow_mcp.tools.jobs."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx
from pydantic import SecretStr

from roboflow_mcp.client import RoboflowClient
from roboflow_mcp.config import ServerMode
from roboflow_mcp.errors import AuthenticationError, ConfigurationError
from roboflow_mcp.models.jobs import AddReviewedResult, JobsList
from roboflow_mcp.tools import jobs as jobs_tools
from tests.conftest import SettingsFactory

_JOBS_URL = "https://api.roboflow.com/contoro/boxes/jobs"
_ADD_URL = "https://app.roboflow.com/datasets/addImagesFromJobToDataset"
_COOKIE = "__session=s3cr3t-session"


def _job(
    job_id: str,
    *,
    status: str = "review",
    num_images: int = 10,
    approved: int | None = None,
) -> dict[str, Any]:
    return {
        "id": job_id,
        "name": f"batch-{job_id}",
        "status": status,
        "project": "internal-project-id",
        "numImages": num_images,
        "unannotated": 0,
        "annotated": num_images - (num_images if approved is None else approved),
        "approved": num_images if approved is None else approved,
        "rejected": 0,
    }


def _mock_jobs(payload: list[dict[str, Any]]) -> None:
    respx.get(_JOBS_URL).mock(return_value=httpx.Response(200, json={"jobs": payload}))


def _echoing_add_route() -> respx.Route:
    """Mock the app endpoint: report numImagesAdded = sum of the counts."""

    def _respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        added = body["trainCount"] + body["validCount"] + body["testCount"]
        return httpx.Response(200, json={"success": True, "numImagesAdded": added})

    return respx.post(_ADD_URL).mock(side_effect=_respond)


@respx.mock
async def test_list_jobs_reports_ready_to_add(
    settings_factory: SettingsFactory,
) -> None:
    _mock_jobs(
        [
            _job("full", num_images=10),
            _job("partial", num_images=5, approved=0),
            _job("empty", num_images=0, approved=0),
            _job("done", status="complete", num_images=3),
        ]
    )
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        result = await jobs_tools.list_annotation_jobs_impl(
            "boxes", workspace=None, client=client, settings=settings
        )
    assert isinstance(result, JobsList)
    assert result.total == 4
    assert result.ready_to_add_jobs == 1
    assert result.ready_to_add_images == 10
    ready_flags = {job.id: job.ready_to_add for job in result.jobs}
    assert ready_flags == {
        "full": True,
        "partial": False,
        "empty": False,
        "done": False,
    }


async def test_list_jobs_dry_run(settings_factory: SettingsFactory) -> None:
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        preview = await jobs_tools.list_annotation_jobs_impl(
            "boxes", workspace=None, dry_run=True, client=client, settings=settings
        )
    assert isinstance(preview, dict)
    assert preview["dry_run"] is True
    assert preview["path"] == "/contoro/boxes/jobs"


@respx.mock
async def test_add_reviewed_happy_path(settings_factory: SettingsFactory) -> None:
    _mock_jobs(
        [
            _job("a", num_images=10),
            _job("b", num_images=9),
            _job("partial", num_images=5, approved=0),
        ]
    )
    add_route = _echoing_add_route()
    settings = settings_factory(workspace="contoro", session_cookie=SecretStr(_COOKIE))
    async with RoboflowClient(settings) as client:
        result = await jobs_tools.add_reviewed_to_dataset_impl(
            "boxes",
            workspace=None,
            confirm="yes",
            client=client,
            settings=settings,
        )

    assert isinstance(result, AddReviewedResult)
    assert result.all_ok is True
    assert result.jobs_added == 2
    assert result.images_added == 19
    # 19 images at 70/20/10 with largest-remainder rounding.
    assert result.split_counts == {"train": 13, "valid": 4, "test": 2}
    for job_result in result.results:
        assert job_result.ok
        assert (
            job_result.train + job_result.valid + job_result.test
            == job_result.images_expected
        )

    assert add_route.call_count == 2
    request = add_route.calls[0].request
    assert "api_key" not in str(request.url)
    assert request.headers["cookie"] == _COOKIE
    body = json.loads(request.content)
    assert body["projectId"] == "internal-project-id"
    assert body["splitMethod"] == "random"
    assert body["statusesToInclude"] == ["approved"]


@respx.mock
async def test_add_reviewed_dry_run_plans_without_posting(
    settings_factory: SettingsFactory,
) -> None:
    _mock_jobs([_job("a", num_images=10)])
    add_route = _echoing_add_route()
    settings = settings_factory(workspace="contoro", session_cookie=SecretStr(_COOKIE))
    async with RoboflowClient(settings) as client:
        preview = await jobs_tools.add_reviewed_to_dataset_impl(
            "boxes",
            workspace=None,
            confirm="yes",
            dry_run=True,
            client=client,
            settings=settings,
        )
    assert isinstance(preview, dict)
    assert preview["dry_run"] is True
    assert len(preview["body"]) == 1
    assert preview["body"][0]["jobId"] == "a"
    assert add_route.call_count == 0


@respx.mock
async def test_add_reviewed_requires_session_cookie(
    settings_factory: SettingsFactory,
) -> None:
    _mock_jobs([_job("a", num_images=10)])
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        with pytest.raises(ConfigurationError, match="ROBOFLOW_SESSION_COOKIE"):
            await jobs_tools.add_reviewed_to_dataset_impl(
                "boxes",
                workspace=None,
                confirm="yes",
                client=client,
                settings=settings,
            )


async def test_add_reviewed_requires_confirm(
    settings_factory: SettingsFactory,
) -> None:
    settings = settings_factory(workspace="contoro")
    async with RoboflowClient(settings) as client:
        with pytest.raises(ConfigurationError, match="confirm"):
            await jobs_tools.add_reviewed_to_dataset_impl(
                "boxes", workspace=None, client=client, settings=settings
            )


async def test_add_reviewed_blocked_in_readonly_mode(
    settings_factory: SettingsFactory,
) -> None:
    settings = settings_factory(workspace="contoro", mode=ServerMode.READONLY)
    async with RoboflowClient(settings) as client:
        with pytest.raises(ConfigurationError, match="readonly"):
            await jobs_tools.add_reviewed_to_dataset_impl(
                "boxes",
                workspace=None,
                confirm="yes",
                client=client,
                settings=settings,
            )


@respx.mock
async def test_add_reviewed_aborts_on_contract_mismatch(
    settings_factory: SettingsFactory,
) -> None:
    _mock_jobs([_job("a", num_images=10), _job("b", num_images=9)])
    add_route = respx.post(_ADD_URL).mock(
        return_value=httpx.Response(200, json={"success": True, "numImagesAdded": 0})
    )
    settings = settings_factory(workspace="contoro", session_cookie=SecretStr(_COOKIE))
    async with RoboflowClient(settings) as client:
        result = await jobs_tools.add_reviewed_to_dataset_impl(
            "boxes",
            workspace=None,
            confirm="yes",
            client=client,
            settings=settings,
        )
    assert isinstance(result, AddReviewedResult)
    assert result.all_ok is False
    assert result.aborted_on == "a"
    assert result.jobs_added == 0
    assert len(result.results) == 1
    assert add_route.call_count == 1  # job "b" was never attempted


@respx.mock
async def test_add_reviewed_expired_session_gets_refresh_hint(
    settings_factory: SettingsFactory,
) -> None:
    _mock_jobs([_job("a", num_images=10)])
    respx.post(_ADD_URL).mock(
        return_value=httpx.Response(403, text="Unauthorized (no cookie)")
    )
    settings = settings_factory(workspace="contoro", session_cookie=SecretStr(_COOKIE))
    async with RoboflowClient(settings) as client:
        with pytest.raises(AuthenticationError, match="ROBOFLOW_SESSION_COOKIE"):
            await jobs_tools.add_reviewed_to_dataset_impl(
                "boxes",
                workspace=None,
                confirm="yes",
                client=client,
                settings=settings,
            )


@respx.mock
async def test_add_reviewed_rejects_ineligible_job_ids(
    settings_factory: SettingsFactory,
) -> None:
    _mock_jobs([_job("a", num_images=10), _job("partial", num_images=5, approved=0)])
    settings = settings_factory(workspace="contoro", session_cookie=SecretStr(_COOKIE))
    async with RoboflowClient(settings) as client:
        with pytest.raises(ValueError, match="partial"):
            await jobs_tools.add_reviewed_to_dataset_impl(
                "boxes",
                workspace=None,
                job_ids=["a", "partial"],
                confirm="yes",
                client=client,
                settings=settings,
            )


async def test_add_reviewed_rejects_bad_ratios(
    settings_factory: SettingsFactory,
) -> None:
    settings = settings_factory(workspace="contoro", session_cookie=SecretStr(_COOKIE))
    async with RoboflowClient(settings) as client:
        with pytest.raises(ValueError, match=r"sum to 1\.0"):
            await jobs_tools.add_reviewed_to_dataset_impl(
                "boxes",
                workspace=None,
                train_ratio=0.9,
                valid_ratio=0.2,
                test_ratio=0.1,
                confirm="yes",
                client=client,
                settings=settings,
            )
