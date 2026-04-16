"""Models for the annotation-upload tool."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AnnotationFormat = Literal[
    "coco",
    "yolo",
    "pascal_voc",
    "createml",
    "roboflow_json",
]


class AnnotationResult(BaseModel):
    """Response from ``roboflow_upload_annotation``."""

    model_config = ConfigDict(extra="ignore")

    image_id: str
    project: str
    format: AnnotationFormat
    success: bool = True
    raw: dict[str, Any] = Field(default_factory=dict)
