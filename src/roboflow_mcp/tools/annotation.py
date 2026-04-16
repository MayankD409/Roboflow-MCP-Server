"""Annotation-upload tool.

Roboflow's ``POST /dataset/{project}/annotate/{image_id}`` accepts a
raw annotation body plus a ``name`` hint that tells it which parser to
use (COCO, YOLO, Pascal VOC, CreateML, or Roboflow's own JSON). We
pass the content through verbatim after a size check — the parsing is
Roboflow's job, not ours, and re-parsing client-side would just add a
brittle double-validation layer.

Callers typically read the annotation file themselves and pass its
contents as the ``annotation`` string. To keep the contract simple
we accept either a plain ``str`` or a dict (serialized to JSON before
sending).
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..audit import AuditLogger
from ..client import RoboflowClient
from ..config import RoboflowSettings
from ..guards import is_tool_enabled, validate_bounds
from ..models.annotation import AnnotationFormat, AnnotationResult
from ._common import dry_run_preview, resolve_workspace

# Per-annotation-file cap — defensive, not contractual. Roboflow will set
# its own limits server-side.
_MAX_ANNOTATION_BYTES = 8 * 1024 * 1024  # 8 MiB

# Map our pydantic-literal format name to Roboflow's `name=` parameter value.
# Roboflow uses lowercase hyphenated names; we use snake_case in the API
# so the LLM picks from a predictable set.
_FORMAT_MAP: dict[AnnotationFormat, str] = {
    "coco": "coco",
    "yolo": "yolov8",  # Roboflow parses YOLO variants under one name
    "pascal_voc": "pascal-voc",
    "createml": "createml",
    "roboflow_json": "roboflow",
}


async def upload_annotation_impl(
    project: str,
    image_id: str,
    annotation: str | dict[str, Any],
    annotation_format: AnnotationFormat,
    *,
    workspace: str | None,
    labelmap: str | None = None,
    dry_run: bool = False,
    client: RoboflowClient,
    settings: RoboflowSettings,
) -> AnnotationResult | dict[str, Any]:
    """Push an annotation onto an existing image."""
    validate_bounds(
        {
            "project": project,
            "image_id": image_id,
            "workspace": workspace,
            "labelmap": labelmap,
        },
        max_string=settings.max_string_length,
        max_list=settings.max_list_length,
    )
    if annotation_format not in _FORMAT_MAP:
        raise ValueError(
            f"Unknown annotation_format {annotation_format!r}; "
            f"expected one of {list(_FORMAT_MAP)}"
        )

    body_text = json.dumps(annotation) if isinstance(annotation, dict) else annotation
    body_bytes = body_text.encode("utf-8")
    if len(body_bytes) > _MAX_ANNOTATION_BYTES:
        raise ValueError(
            f"Annotation body of {len(body_bytes)} bytes exceeds "
            f"{_MAX_ANNOTATION_BYTES} cap."
        )

    resolve_workspace(workspace, settings)  # enforces the allowlist
    path = f"/dataset/{project}/annotate/{image_id}"
    params: dict[str, Any] = {"name": _FORMAT_MAP[annotation_format]}
    if labelmap:
        params["labelmap"] = labelmap

    if dry_run:
        return dry_run_preview(
            "roboflow_upload_annotation",
            method="POST",
            path=path,
            params={**params, "api_key": "***"},
            body={
                "format": annotation_format,
                "body_bytes": len(body_bytes),
            },
        )

    # Raw POST with JSON-or-text body. httpx lets us pass `content=` for
    # already-serialised bytes; add an explicit content-type so Roboflow
    # parses correctly.
    response = await client.request(
        "POST",
        path,
        params=params,
        content=body_bytes,
        headers={
            "Content-Type": (
                "application/json"
                if annotation_format in ("coco", "createml", "roboflow_json")
                else "text/plain"
            )
        },
    )
    return AnnotationResult(
        image_id=image_id,
        project=project,
        format=annotation_format,
        success=bool((response or {}).get("success", True))
        if isinstance(response, dict)
        else True,
        raw=response if isinstance(response, dict) else {"raw": str(response)},
    )


def register(
    mcp: FastMCP,
    client: RoboflowClient,
    settings: RoboflowSettings,
    audit: AuditLogger | None = None,
) -> None:
    from .image import _audited

    if is_tool_enabled("roboflow_upload_annotation", settings):

        @mcp.tool()
        async def roboflow_upload_annotation(
            project: str,
            image_id: str,
            annotation: str | dict[str, Any],
            annotation_format: AnnotationFormat,
            workspace: str | None = None,
            labelmap: str | None = None,
            dry_run: bool = False,
        ) -> AnnotationResult | dict[str, Any]:
            """Attach an annotation to an image.

            Supported formats (``annotation_format`` literal):
            - ``"coco"``
            - ``"yolo"`` (YOLOv5/v8/v11-compatible .txt)
            - ``"pascal_voc"`` (XML)
            - ``"createml"`` (Apple CreateML JSON)
            - ``"roboflow_json"``

            Pass ``annotation`` as a string (raw file contents) or a dict
            (Python object; we serialize to JSON). Optional ``labelmap``
            is a class-id to name map Roboflow uses for YOLO formats.
            """
            args = {
                "project": project,
                "image_id": image_id,
                "annotation_format": annotation_format,
                "workspace": workspace,
                "has_labelmap": labelmap is not None,
                "dry_run": dry_run,
            }
            with _audited(
                audit, "roboflow_upload_annotation", settings, workspace, args
            ) as span:
                result = await upload_annotation_impl(
                    project,
                    image_id,
                    annotation,
                    annotation_format,
                    workspace=workspace,
                    labelmap=labelmap,
                    dry_run=dry_run,
                    client=client,
                    settings=settings,
                )
                span.outcome = "dry_run" if dry_run else "ok"
                return result
