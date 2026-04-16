"""Input shapes for tools that ingest binary data (images, annotations).

Every image-accepting tool uses the :class:`ImageSource` discriminated
union so the caller can pick exactly one of three modes — URL, local
path, or inline base64 — without us needing three different tool
signatures per domain. The accompanying :func:`resolve_source` turns the
source into validated bytes by running every appropriate guard:

- ``url`` → :func:`roboflow_mcp.safety.urlguard.fetch_bytes_safely`
- ``path`` → :func:`roboflow_mcp.safety.paths.resolve_local_path`
- ``base64`` → size check
- all three → :func:`roboflow_mcp.safety.imageguard.validate_image_bytes`

Tools never read bytes directly; they go through ``resolve_source``.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..config import RoboflowSettings
from ..errors import ImageGuardError
from ..safety.imageguard import ImageInfo, validate_image_bytes
from ..safety.paths import resolve_local_path
from ..safety.urlguard import fetch_bytes_safely


class ImageSourceUrl(BaseModel):
    """Fetch an image from a publicly reachable URL."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["url"] = "url"
    url: str = Field(..., min_length=1, max_length=2048)


class ImageSourcePath(BaseModel):
    """Read an image from a local file (must be under an upload root)."""

    model_config = ConfigDict(extra="forbid")
    kind: Literal["path"] = "path"
    path: str = Field(..., min_length=1, max_length=4096)


class ImageSourceBase64(BaseModel):
    """Pass an image inline as base64 data.

    ``filename`` is required so the Roboflow API has something sensible to
    display in the UI; bare base64 blobs get labelled as ``image.bin``.
    """

    model_config = ConfigDict(extra="forbid")
    kind: Literal["base64"] = "base64"
    data: str = Field(..., min_length=1)
    filename: str = Field(..., min_length=1, max_length=512)


ImageSource = Annotated[
    ImageSourceUrl | ImageSourcePath | ImageSourceBase64,
    Field(discriminator="kind"),
]
"""Tagged union — exactly one of URL, local path, or inline base64."""


@dataclass(frozen=True)
class ResolvedImage:
    """Result of :func:`resolve_source` — validated bytes plus metadata."""

    content: bytes
    filename: str
    info: ImageInfo


_SAFE_FILENAME_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
)


def _filename_from_url(url: str) -> str:
    """Derive a sanitised filename from a URL path.

    The URL's path is percent-decoded, the last component extracted, then
    filtered to ``[A-Za-z0-9._-]`` and capped at 200 chars. This defeats
    a crafted URL that tries to smuggle path traversal or shell
    metacharacters into the filename stored in Roboflow.
    """
    from urllib.parse import unquote, urlparse

    parsed = urlparse(url)
    raw = Path(unquote(parsed.path)).name or "download"
    cleaned = "".join(c if c in _SAFE_FILENAME_CHARS else "_" for c in raw)
    # Prevent pathological names like "." or "..".
    cleaned = cleaned.strip(".") or "download"
    return cleaned[:200]


async def resolve_source(
    source: ImageSource | dict[str, Any],
    settings: RoboflowSettings,
) -> ResolvedImage:
    """Turn an :class:`ImageSource` into validated bytes.

    Accepts either an already-parsed pydantic model or a raw dict so the
    tool layer doesn't need to do a separate validation pass.
    """
    # Pydantic union-validation path. When callers pass a dict (which is
    # what FastMCP hands us for complex tool args), let the adapter do the
    # discriminator dispatch.
    if isinstance(source, dict):
        from pydantic import TypeAdapter

        adapter: TypeAdapter[ImageSource] = TypeAdapter(ImageSource)
        source = adapter.validate_python(source)

    content: bytes
    filename: str

    if isinstance(source, ImageSourceUrl):
        fetched = await fetch_bytes_safely(
            source.url,
            allow_insecure=settings.allow_insecure,
            max_bytes=settings.max_upload_bytes,
        )
        content = fetched.content
        filename = _filename_from_url(source.url)
    elif isinstance(source, ImageSourcePath):
        if not settings.upload_roots:
            raise ImageGuardError(
                "Local-path uploads are disabled. Set "
                "ROBOFLOW_MCP_UPLOAD_ROOTS to a comma-separated list of "
                "absolute directories to enable them."
            )
        resolved_path = resolve_local_path(source.path, settings.upload_roots)
        content = resolved_path.read_bytes()
        filename = resolved_path.name
    elif isinstance(source, ImageSourceBase64):
        try:
            content = base64.b64decode(source.data, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ImageGuardError(f"Invalid base64 payload: {exc}") from exc
        filename = source.filename
    else:  # pragma: no cover - pydantic's discriminator makes this unreachable
        raise ImageGuardError(f"Unknown source kind: {type(source).__name__}")

    if len(content) > settings.max_upload_bytes:
        raise ImageGuardError(
            f"Image size {len(content)} exceeds "
            f"ROBOFLOW_MCP_MAX_UPLOAD_BYTES={settings.max_upload_bytes}."
        )

    info = validate_image_bytes(
        content,
        max_bytes=settings.max_upload_bytes,
    )
    return ResolvedImage(content=content, filename=filename, info=info)
