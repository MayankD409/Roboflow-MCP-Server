"""Tests for roboflow_mcp.safety.imageguard."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from roboflow_mcp.errors import ImageGuardError
from roboflow_mcp.safety.imageguard import validate_image_bytes


def _png_bytes(width: int = 10, height: int = 10, color: str = "red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes(width: int = 10, height: int = 10) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "blue").save(buf, format="JPEG", quality=70)
    return buf.getvalue()


# ---------- happy path ----------


def test_valid_png_accepted() -> None:
    info = validate_image_bytes(_png_bytes())
    assert info.format == "PNG"
    assert info.mime == "image/png"
    assert info.width == 10 and info.height == 10


def test_valid_jpeg_accepted() -> None:
    info = validate_image_bytes(_jpeg_bytes())
    assert info.format == "JPEG"
    assert info.mime == "image/jpeg"


# ---------- size bounds ----------


def test_empty_rejected() -> None:
    with pytest.raises(ImageGuardError, match="empty"):
        validate_image_bytes(b"")


def test_oversize_rejected() -> None:
    data = _png_bytes(100, 100)
    with pytest.raises(ImageGuardError, match="exceeds"):
        validate_image_bytes(data, max_bytes=50)


# ---------- format bounds ----------


def test_unknown_format_rejected() -> None:
    with pytest.raises(ImageGuardError, match="not a recognised image"):
        validate_image_bytes(b"this is not an image" * 20)


def test_corrupt_png_rejected() -> None:
    # Valid PNG header + garbage — verify() catches it
    data = b"\x89PNG\r\n\x1a\n" + b"garbage data" * 100
    with pytest.raises(ImageGuardError):
        validate_image_bytes(data)


# ---------- dimension bounds ----------


def test_dimension_bound_honoured() -> None:
    data = _png_bytes(50, 50)
    with pytest.raises(ImageGuardError, match="exceed"):
        validate_image_bytes(data, max_dim=10)


# ---------- decompression bomb ----------


def test_bomb_cap_is_reasserted_on_each_call() -> None:
    """If another library sets ``Image.MAX_IMAGE_PIXELS = None`` (a
    documented opt-out in PIL), the next call to validate_image_bytes
    must re-apply the cap rather than silently inherit a disabled
    bomb guard. Hostile libraries (or a CVE) could otherwise bypass
    imageguard entirely."""
    from PIL import Image as _Image

    original = _Image.MAX_IMAGE_PIXELS
    _Image.MAX_IMAGE_PIXELS = None  # "opt out" — the scary state
    try:
        data = _png_bytes(10, 10)
        # validate_image_bytes re-asserts the cap internally, so this
        # call should succeed (the image is well under the cap) and
        # the cap should be put back in place.
        validate_image_bytes(data)
        assert _Image.MAX_IMAGE_PIXELS == 100_000_000
    finally:
        _Image.MAX_IMAGE_PIXELS = original


# ---------- extra formats ----------


def test_gif_accepted() -> None:
    buf = io.BytesIO()
    Image.new("RGB", (5, 5)).save(buf, format="GIF")
    info = validate_image_bytes(buf.getvalue())
    assert info.format == "GIF"


def test_bmp_accepted() -> None:
    buf = io.BytesIO()
    Image.new("RGB", (5, 5)).save(buf, format="BMP")
    info = validate_image_bytes(buf.getvalue())
    assert info.format == "BMP"


def test_tiff_accepted() -> None:
    buf = io.BytesIO()
    Image.new("RGB", (5, 5)).save(buf, format="TIFF")
    info = validate_image_bytes(buf.getvalue())
    assert info.format == "TIFF"


def test_webp_accepted() -> None:
    buf = io.BytesIO()
    Image.new("RGB", (5, 5)).save(buf, format="WEBP")
    info = validate_image_bytes(buf.getvalue())
    assert info.format == "WEBP"
