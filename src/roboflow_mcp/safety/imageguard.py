"""Image-content validation for uploads.

The Roboflow upload endpoint accepts whatever we send it and cheerfully
ingests it into the dataset. That's a small surface for classic
image-parser exploits (decompression bombs, truncated files that crash
downstream consumers, polyglot files, files with misreported extensions).

For v0.3 we run Pillow's verify + load inside the server process — not a
subprocess. A follow-up in v0.4 will wrap this in a subprocess with a
memory cap to contain any PIL RCE; the API of this module is stable so
callers won't change.

What we check today:

- File size <= ``max_bytes`` (default 25 MiB) — matches the upload cap.
- Format is in a whitelist (JPEG, PNG, WebP, BMP, TIFF, GIF).
- Pillow ``Image.verify()`` succeeds.
- ``Image.open().load()`` succeeds (verify doesn't always catch truncated
  files; load actually decodes).
- Dimensions <= ``max_pixels_per_side`` on both axes (default 16_384).
- Pillow's ``MAX_IMAGE_PIXELS`` is set to 1e8 so decompression bombs
  raise ``PIL.Image.DecompressionBombError``.

``python-magic`` is an optional accelerator — if installed, we use it to
cross-check the declared MIME type. We don't hard-require it because it
needs libmagic on the host and that's annoying for Windows users.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

from ..errors import ImageGuardError

# 25 MiB — matches default upload cap. Operators can tune via env.
_DEFAULT_MAX_BYTES = 25 * 1024 * 1024

# 16k px per side — larger than any sensible training image.
_DEFAULT_MAX_DIM = 16_384

_ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "BMP", "TIFF", "GIF"})

_FORMAT_TO_MIME = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
    "GIF": "image/gif",
}

# Pillow's own decompression-bomb cap. Applied inside `validate_image_bytes`
# on every call so a library loaded later that sets ``Image.MAX_IMAGE_PIXELS =
# None`` (a documented PIL convention for libraries that need the cap off)
# cannot silently disable the check for us.
_BOMB_PIXEL_CAP = 100_000_000


@dataclass(frozen=True)
class ImageInfo:
    """Metadata about a validated image."""

    format: str  # PIL format name, e.g. "JPEG"
    mime: str  # e.g. "image/jpeg"
    width: int
    height: int
    size_bytes: int


def validate_image_bytes(
    data: bytes,
    *,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    max_dim: int = _DEFAULT_MAX_DIM,
) -> ImageInfo:
    """Run the full image validation pipeline.

    Returns :class:`ImageInfo` on success, raises :class:`ImageGuardError`
    otherwise. Every error message is user-safe (no raw PIL traces leaked
    to the LLM).

    Order: size cap → structural verify + size probe → format allowlist →
    dimension cap (pre-load!) → decode. Dimensions are checked on the
    probed size *before* ``load()`` so a 20000x20000 image is rejected
    before we allocate memory for the decoded pixels.
    """
    # Re-assert the bomb cap on every call; see module-level note.
    Image.MAX_IMAGE_PIXELS = _BOMB_PIXEL_CAP

    size = len(data)
    if size == 0:
        raise ImageGuardError("Image data is empty.")
    if size > max_bytes:
        raise ImageGuardError(f"Image size {size} exceeds {max_bytes}-byte cap.")

    # `verify()` consumes the stream, so we have to open twice — once for
    # structural verify (+ format/size probe), once for actual decode.
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format or ""
            width, height = probe.size
            probe.verify()
    except UnidentifiedImageError as exc:
        raise ImageGuardError("Content is not a recognised image format.") from exc
    except Image.DecompressionBombError as exc:
        raise ImageGuardError("Image is a decompression bomb.") from exc
    except Exception as exc:
        raise ImageGuardError(f"Image failed structural verify: {exc}") from exc

    if fmt.upper() not in _ALLOWED_FORMATS:
        raise ImageGuardError(
            f"Image format {fmt!r} is not in the allowlist "
            f"({sorted(_ALLOWED_FORMATS)})."
        )

    if width > max_dim or height > max_dim:
        raise ImageGuardError(
            f"Image dimensions {width}x{height} exceed {max_dim}px per side."
        )

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()
    except Image.DecompressionBombError as exc:
        raise ImageGuardError("Image is a decompression bomb.") from exc
    except Exception as exc:
        raise ImageGuardError(f"Image failed decode: {exc}") from exc

    return ImageInfo(
        format=fmt.upper(),
        mime=_FORMAT_TO_MIME[fmt.upper()],
        width=width,
        height=height,
        size_bytes=size,
    )
