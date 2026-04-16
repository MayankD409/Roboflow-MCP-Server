"""Defensive primitives shared by tools and client.

Each module here enforces one narrow invariant so it can be unit-tested in
isolation and reused across the rest of the package.
"""

from .imageguard import ImageInfo, validate_image_bytes
from .paths import resolve_local_path
from .sanitize import sanitize_untrusted, wrap_untrusted_dict
from .urlguard import FetchResult, fetch_bytes_safely, validate_url

__all__ = [
    "FetchResult",
    "ImageInfo",
    "fetch_bytes_safely",
    "resolve_local_path",
    "sanitize_untrusted",
    "validate_image_bytes",
    "validate_url",
    "wrap_untrusted_dict",
]
