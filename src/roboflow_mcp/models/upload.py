"""Response models for image-ingestion tools."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UploadResult(BaseModel):
    """Response from a single image upload."""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    image_id: str | None = None  # some API responses use this alias
    success: bool = True
    duplicate: bool = False
    split: str | None = None
    filename: str
    project: str
    raw: dict[str, Any] = Field(default_factory=dict)


class BatchUploadResult(BaseModel):
    """Aggregate response from ``roboflow_upload_images_batch``."""

    model_config = ConfigDict(extra="ignore")

    total: int
    succeeded: int
    failed: int
    results: list[UploadResult] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class DeleteResult(BaseModel):
    """Response from deleting an image or version."""

    model_config = ConfigDict(extra="ignore")

    success: bool = True
    image_id: str | None = None
    version: str | None = None
    project: str
    raw: dict[str, Any] = Field(default_factory=dict)


class ImageDetail(BaseModel):
    """Response from ``roboflow_get_image``."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str | None = None
    tags: list[str] = Field(default_factory=list)
    split: str | None = None
    batch: str | None = None
    annotations: dict[str, Any] = Field(default_factory=dict)
    created: int | str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class BatchSummary(BaseModel):
    """Single row of ``roboflow_list_image_batches``."""

    model_config = ConfigDict(extra="ignore")

    name: str
    image_count: int = 0
    uploaded_images: int = 0
    created: int | str | None = None
