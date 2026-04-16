"""Pydantic models for project + version tools."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ExportFormat = Literal[
    "coco",
    "yolov5",
    "yolov8",
    "yolov11",
    "pascal-voc",
    "createml",
    "tfrecord",
    "multiclass",
]


class ProjectDetail(BaseModel):
    """Full project metadata from ``roboflow_get_project``."""

    model_config = ConfigDict(extra="ignore")

    id: str
    type: str
    name: str
    images: int = 0
    unannotated: int = 0
    annotation: str | None = None
    versions: int = 0
    public: bool = False
    classes: dict[str, int] = Field(default_factory=dict)
    created: int | str | None = None
    updated: int | str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class VersionSummary(BaseModel):
    """One row in ``roboflow_list_versions``."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str | None = None
    created: int | str | None = None
    images: int = 0
    trained: bool = False


class VersionDetail(BaseModel):
    """Full shape from ``roboflow_get_version``."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str | None = None
    created: int | str | None = None
    images: int = 0
    splits: dict[str, int] = Field(default_factory=dict)
    preprocessing: dict[str, Any] = Field(default_factory=dict)
    augmentation: dict[str, Any] = Field(default_factory=dict)
    classes: dict[str, int] = Field(default_factory=dict)
    generating: bool = False
    trained: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)


class VersionGenerationStatus(BaseModel):
    """Response from ``roboflow_get_version_generation_status``."""

    model_config = ConfigDict(extra="ignore")

    version: str
    status: Literal["queued", "generating", "ready", "failed", "unknown"] = "unknown"
    progress: float | None = None
    message: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class ExportResult(BaseModel):
    """Response from ``roboflow_export_version``."""

    model_config = ConfigDict(extra="ignore")

    version: str
    project: str
    format: ExportFormat
    download_url: str | None = None
    ready: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)


class DownloadResult(BaseModel):
    """Response from ``roboflow_download_export``."""

    model_config = ConfigDict(extra="ignore")

    version: str
    project: str
    format: ExportFormat
    path: str
    bytes: int
    extracted: bool = False
