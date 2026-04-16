"""Defensive primitives shared by tools and client.

Each module here enforces one narrow invariant so it can be unit-tested in
isolation and reused across the rest of the package.
"""

from .sanitize import sanitize_untrusted, wrap_untrusted_dict

__all__ = ["sanitize_untrusted", "wrap_untrusted_dict"]
