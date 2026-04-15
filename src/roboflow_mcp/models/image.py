"""Pydantic models for Roboflow image endpoints.

The server talks to two image APIs: search (``POST /{ws}/{project}/search``)
and tag operations (``POST /{ws}/{project}/images/{id}/tags``). Only the
search response has enough shape to warrant a typed model; tag operations
return an opaque status payload that we pass through as a dict.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ImageAnnotationInfo(BaseModel):
    """Summary of annotations on an image."""

    model_config = ConfigDict(extra="ignore")

    count: int = 0
    classes: dict[str, int] = Field(default_factory=dict)


class ImageSummary(BaseModel):
    """A single image record as returned by the search endpoint.

    Most fields are optional because the ``fields`` parameter on the search
    request controls which ones come back. Callers that opt in to extra fields
    can rely on the names below.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str | None = None
    owner: str | None = None
    annotations: ImageAnnotationInfo | None = None
    labels: list[Any] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    # Roboflow's docs claim `created` is a string, but the live search endpoint
    # returns it as a Unix-millisecond int (e.g. 1715286185986). Accept either
    # so parsing works against the real API and any future string variant.
    created: int | str | None = None
    split: str | None = None


class ImageSearchResult(BaseModel):
    """Response shape of ``POST /{workspace}/{project}/search``."""

    model_config = ConfigDict(extra="ignore")

    offset: int = 0
    total: int = 0
    results: list[ImageSummary] = Field(default_factory=list)
