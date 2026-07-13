"""Annotation-job tools.

Roboflow's Annotate tab organises labeling work into *jobs*. The public
REST API exposes job state (``GET /{ws}/{project}/jobs``) but has no
endpoint for the "Add to Dataset" action that moves fully-reviewed
images out of the review queue — the web app performs it through an
internal endpoint on ``app.roboflow.com`` authenticated by the
operator's browser session::

    POST /datasets/addImagesFromJobToDataset
    {"projectId", "jobId", "splitMethod", "trainCount", "validCount",
     "testCount", "statusesToInclude"}

The contract was recovered from the web app's webpack bundles. If
Roboflow changes it, the strict response check below aborts loudly.
Re-discovery recipe: fetch ``runtime.*.js`` from
``cdnassets.roboflow.com/_app/``, resolve the chunk map it contains,
and grep the chunks for ``addImagesFromJobToDataset``.

``roboflow_add_reviewed_to_dataset`` therefore requires
``ROBOFLOW_SESSION_COOKIE`` (see :meth:`RoboflowClient.request_app_session`);
the read-only ``roboflow_list_annotation_jobs`` uses the ordinary API key.
"""

from __future__ import annotations

import logging
import random
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..audit import AuditLogger
from ..client import RoboflowClient
from ..config import RoboflowSettings
from ..guards import destructive, is_tool_enabled, validate_bounds
from ..models.jobs import AddReviewedResult, AnnotationJob, JobAddResult, JobsList
from ._common import dry_run_preview, resolve_workspace

logger = logging.getLogger(__name__)

_ADD_TO_DATASET_PATH = "/datasets/addImagesFromJobToDataset"
_SPLITS = ("train", "valid", "test")
_RATIO_TOLERANCE = 1e-6
_CONTRACT_MISMATCH = (
    "Response did not match the expected add-to-dataset contract; the "
    "internal endpoint may have changed. Remaining jobs were skipped."
)


async def list_annotation_jobs_impl(
    project: str,
    *,
    workspace: str | None,
    status: str | None = None,
    dry_run: bool = False,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> JobsList | dict[str, Any]:
    """List a project's annotation jobs with review-queue state."""
    validate_bounds(
        {"project": project, "workspace": workspace, "status": status},
        max_string=settings.max_string_length,
        max_list=settings.max_list_length,
    )
    slug = resolve_workspace(workspace, settings)
    path = f"/{slug}/{project}/jobs"
    if dry_run:
        return dry_run_preview("roboflow_list_annotation_jobs", method="GET", path=path)
    jobs = await _fetch_jobs(path, client)
    if status:
        jobs = [job for job in jobs if job.status == status]
    ready = [job for job in jobs if job.ready_to_add]
    return JobsList(
        project=f"{slug}/{project}",
        total=len(jobs),
        ready_to_add_jobs=len(ready),
        ready_to_add_images=sum(job.num_images for job in ready),
        jobs=jobs,
    )


@destructive
async def add_reviewed_to_dataset_impl(
    project: str,
    *,
    workspace: str | None,
    job_ids: list[str] | None = None,
    train_ratio: float = 0.7,
    valid_ratio: float = 0.2,
    test_ratio: float = 0.1,
    confirm: str = "",
    dry_run: bool = False,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> AddReviewedResult | dict[str, Any]:
    """Move fully-reviewed annotation-job images into the dataset.

    Selects jobs in ``review`` status whose images are all approved
    (optionally restricted to ``job_ids``), assigns each job
    train/valid/test counts so the batch as a whole lands on the
    requested ratios, then replays the web app's "Add to Dataset" call
    per job and verifies each response. Aborts on the first response
    that misses the expected contract; already-added jobs leave the
    review queue server-side, so re-running after a partial failure
    picks up exactly the remainder.

    ``dry_run`` still performs the read-only jobs lookup so the preview
    can list the exact planned requests.
    """
    validate_bounds(
        {"project": project, "workspace": workspace, "job_ids": job_ids},
        max_string=settings.max_string_length,
        max_list=settings.max_list_length,
    )
    _validate_ratios(train_ratio, valid_ratio, test_ratio)
    slug = resolve_workspace(workspace, settings)
    jobs = await _fetch_jobs(f"/{slug}/{project}/jobs", client)
    eligible = _select_jobs(jobs, job_ids)
    plan = _allocate_splits(eligible, (train_ratio, valid_ratio, test_ratio))

    if dry_run:
        return dry_run_preview(
            "roboflow_add_reviewed_to_dataset",
            method="POST",
            path=_ADD_TO_DATASET_PATH,
            body=[_request_body(job, counts) for job, counts in plan],
        )

    results: list[JobAddResult] = []
    aborted_on: str | None = None
    for job, counts in plan:
        response = await client.request_app_session(
            "POST", _ADD_TO_DATASET_PATH, json=_request_body(job, counts)
        )
        added = _extract_added(response)
        ok = added == job.num_images
        results.append(
            JobAddResult(
                job_id=job.id,
                name=job.name,
                images_expected=job.num_images,
                images_added=max(added, 0),
                train=counts["train"],
                valid=counts["valid"],
                test=counts["test"],
                ok=ok,
                error=None if ok else _CONTRACT_MISMATCH,
            )
        )
        if not ok:
            aborted_on = job.id
            logger.error("Add-to-dataset response contract mismatch; aborting.")
            break

    done = [result for result in results if result.ok]
    return AddReviewedResult(
        project=f"{slug}/{project}",
        jobs_added=len(done),
        images_added=sum(result.images_added for result in done),
        split_counts={
            "train": sum(result.train for result in done),
            "valid": sum(result.valid for result in done),
            "test": sum(result.test for result in done),
        },
        all_ok=aborted_on is None,
        aborted_on=aborted_on,
        results=results,
    )


async def _fetch_jobs(path: str, client: RoboflowClient) -> list[AnnotationJob]:
    response = await client.request("GET", path)
    payload = response if isinstance(response, dict) else {}
    raw_jobs = payload.get("jobs")
    if not isinstance(raw_jobs, list):
        raw_jobs = []
    return [AnnotationJob.model_validate(item) for item in raw_jobs]


def _select_jobs(
    jobs: list[AnnotationJob], job_ids: list[str] | None
) -> list[AnnotationJob]:
    ready = {job.id: job for job in jobs if job.ready_to_add}
    if job_ids is None:
        selected = list(ready.values())
    else:
        missing = [job_id for job_id in job_ids if job_id not in ready]
        if missing:
            raise ValueError(
                "job_ids not eligible (jobs must be in review with every "
                f"image approved): {missing}"
            )
        selected = [ready[job_id] for job_id in job_ids]
    without_project = [job.id for job in selected if not job.project]
    if without_project:
        raise ValueError(
            f"Jobs response is missing the internal project id: {without_project}"
        )
    return selected


def _validate_ratios(train: float, valid: float, test: float) -> None:
    ratios = (train, valid, test)
    if any(ratio < 0 for ratio in ratios):
        raise ValueError("Split ratios must be non-negative.")
    if abs(sum(ratios) - 1.0) > _RATIO_TOLERANCE:
        raise ValueError(f"Split ratios must sum to 1.0 (got {sum(ratios):.4f}).")


def _allocate_splits(
    jobs: list[AnnotationJob],
    ratios: tuple[float, float, float],
) -> list[tuple[AnnotationJob, dict[str, int]]]:
    """Assign per-job split counts that hit the global ratios exactly.

    Largest-remainder apportionment fixes the batch-wide train/valid/test
    totals; a shuffled label sequence chunked by job size then spreads
    those totals across jobs, so small jobs don't systematically land in
    a single split. Which images inside a job get which split is decided
    server-side (``splitMethod: random``).
    """
    total = sum(job.num_images for job in jobs)
    targets = _largest_remainder(total, ratios)
    labels = [
        split
        for split, count in zip(_SPLITS, targets, strict=True)
        for _ in range(count)
    ]
    random.shuffle(labels)
    plan: list[tuple[AnnotationJob, dict[str, int]]] = []
    cursor = 0
    for job in jobs:
        chunk = labels[cursor : cursor + job.num_images]
        cursor += job.num_images
        plan.append((job, {split: chunk.count(split) for split in _SPLITS}))
    return plan


def _largest_remainder(total: int, ratios: tuple[float, float, float]) -> list[int]:
    exact = [total * ratio for ratio in ratios]
    counts = [int(value) for value in exact]
    by_remainder = sorted(
        range(len(exact)), key=lambda i: exact[i] - counts[i], reverse=True
    )
    for index in by_remainder[: total - sum(counts)]:
        counts[index] += 1
    return counts


def _request_body(job: AnnotationJob, counts: dict[str, int]) -> dict[str, Any]:
    return {
        "projectId": job.project,
        "jobId": job.id,
        "splitMethod": "random",
        "trainCount": counts["train"],
        "validCount": counts["valid"],
        "testCount": counts["test"],
        "statusesToInclude": ["approved"],
    }


def _extract_added(response: Any) -> int:
    """Return ``numImagesAdded`` from a contract-conforming response, else -1."""
    if not isinstance(response, dict) or response.get("success") is not True:
        return -1
    added = response.get("numImagesAdded")
    return added if isinstance(added, int) else -1


def register(
    mcp: FastMCP,
    client: RoboflowClient,
    settings: RoboflowSettings,
    audit: AuditLogger | None = None,
) -> None:
    """Attach the annotation-job tools to ``mcp``."""
    from .image import _audited

    if is_tool_enabled("roboflow_list_annotation_jobs", settings):

        @mcp.tool()
        async def roboflow_list_annotation_jobs(
            project: str,
            workspace: str | None = None,
            status: str | None = None,
            dry_run: bool = False,
        ) -> JobsList | dict[str, Any]:
            """List a project's annotation jobs (Annotate-tab batches).

            Each job reports labeling / review progress; ``ready_to_add``
            marks jobs sitting in review with every image approved, i.e.
            eligible for ``roboflow_add_reviewed_to_dataset``. Optionally
            filter by ``status`` (e.g. "assigned", "review", "complete").
            """
            args = {
                "project": project,
                "workspace": workspace,
                "status": status,
                "dry_run": dry_run,
            }
            with _audited(
                audit, "roboflow_list_annotation_jobs", settings, workspace, args
            ) as span:
                result = await list_annotation_jobs_impl(
                    project,
                    workspace=workspace,
                    status=status,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
                span.outcome = "dry_run" if dry_run else "ok"
                return result

    if is_tool_enabled("roboflow_add_reviewed_to_dataset", settings):

        @mcp.tool()
        async def roboflow_add_reviewed_to_dataset(
            project: str,
            workspace: str | None = None,
            job_ids: list[str] | None = None,
            train_ratio: float = 0.7,
            valid_ratio: float = 0.2,
            test_ratio: float = 0.1,
            confirm: str = "",
            dry_run: bool = False,
        ) -> AddReviewedResult | dict[str, Any]:
            """Add every fully-reviewed annotation job to the dataset.

            Moves images from jobs in review with all images approved into
            the dataset, split randomly at the given global ratios
            (default 70/20/10). Restrict to specific jobs via ``job_ids``.

            Destructive: requires ``confirm='yes'`` and a server mode of
            ``curate`` or ``full``. Also requires ROBOFLOW_SESSION_COOKIE
            (an app.roboflow.com browser-session cookie) because Roboflow
            has no public API for this action.
            """
            args = {
                "project": project,
                "workspace": workspace,
                "job_ids": job_ids,
                "train_ratio": train_ratio,
                "valid_ratio": valid_ratio,
                "test_ratio": test_ratio,
                "confirm": confirm,
                "dry_run": dry_run,
            }
            with _audited(
                audit, "roboflow_add_reviewed_to_dataset", settings, workspace, args
            ) as span:
                result = await add_reviewed_to_dataset_impl(
                    project,
                    workspace=workspace,
                    job_ids=job_ids,
                    train_ratio=train_ratio,
                    valid_ratio=valid_ratio,
                    test_ratio=test_ratio,
                    confirm=confirm,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
                span.outcome = "dry_run" if dry_run else "ok"
                return result
