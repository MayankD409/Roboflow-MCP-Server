"""Red-team: malformed images must not crash the imageguard."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from roboflow_mcp.errors import ImageGuardError
from roboflow_mcp.safety.imageguard import validate_image_bytes

pytestmark = pytest.mark.redteam


def test_truncated_png() -> None:
    """A valid PNG header + truncated body must reject cleanly."""
    buf = io.BytesIO()
    Image.new("RGB", (100, 100)).save(buf, format="PNG")
    truncated = buf.getvalue()[:100]  # chop mid-stream
    with pytest.raises(ImageGuardError):
        validate_image_bytes(truncated)


def test_random_bytes_rejected() -> None:
    with pytest.raises(ImageGuardError):
        validate_image_bytes(b"\x00" * 4096)


def test_text_file_rejected() -> None:
    with pytest.raises(ImageGuardError):
        validate_image_bytes(b"not an image, but maybe malware\n" * 100)


def test_png_magic_but_garbage_body() -> None:
    with pytest.raises(ImageGuardError):
        validate_image_bytes(b"\x89PNG\r\n\x1a\n" + b"\xff" * 200)


def test_svg_rejected() -> None:
    """SVG can embed scripts — not in our whitelist."""
    svg = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" />'
    with pytest.raises(ImageGuardError):
        validate_image_bytes(svg)


def test_pdf_rejected() -> None:
    with pytest.raises(ImageGuardError):
        validate_image_bytes(b"%PDF-1.4\n%...")


def test_archive_rejected() -> None:
    # ZIP magic bytes
    with pytest.raises(ImageGuardError):
        validate_image_bytes(b"PK\x03\x04" + b"\x00" * 200)


def test_icc_profile_bomb_has_dimension_cap() -> None:
    """Dimensions beyond the cap are rejected even if PIL opens the file."""
    # Actually construct a valid small image then crank the cap down.
    buf = io.BytesIO()
    Image.new("RGB", (100, 100)).save(buf, format="PNG")
    with pytest.raises(ImageGuardError, match="exceed"):
        validate_image_bytes(buf.getvalue(), max_dim=50)
