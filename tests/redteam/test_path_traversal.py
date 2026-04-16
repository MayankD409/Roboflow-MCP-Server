"""Red-team: path-traversal attacks must not escape ROBOFLOW_MCP_UPLOAD_ROOTS."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from roboflow_mcp.errors import PathGuardError
from roboflow_mcp.safety.paths import resolve_local_path

pytestmark = pytest.mark.redteam


def _mkfile(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


# ---------- .. traversal ----------


def test_parent_traversal_blocked(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    _mkfile(tmp_path / "secret")
    with pytest.raises(PathGuardError, match="not under"):
        resolve_local_path(root / ".." / "secret", [root])


def test_double_parent_blocked(tmp_path: Path) -> None:
    root = tmp_path / "a" / "b"
    root.mkdir(parents=True)
    _mkfile(tmp_path / "secret")
    with pytest.raises(PathGuardError, match="not under"):
        resolve_local_path(root / ".." / ".." / "secret", [root])


def test_url_encoded_traversal_has_no_special_meaning(tmp_path: Path) -> None:
    """`%2E%2E` is just the literal chars in a local path — not a traversal
    operator. resolve_local_path never URL-decodes."""
    root = tmp_path / "uploads"
    root.mkdir()
    literal_name = root / "%2E%2E" / "secret"
    literal_name.parent.mkdir()
    _mkfile(literal_name)
    # This is a normal nested file; it's allowed.
    assert resolve_local_path(literal_name, [root]) == literal_name.resolve(strict=True)


# ---------- absolute paths ----------


def test_absolute_path_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    target = _mkfile(tmp_path / "outside")
    with pytest.raises(PathGuardError, match="not under"):
        resolve_local_path(str(target.absolute()), [root])


@pytest.mark.skipif(sys.platform == "win32", reason="unix semantics")
def test_etc_passwd_blocked(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    with pytest.raises(PathGuardError):
        resolve_local_path("/etc/passwd", [root])


# ---------- symlink escapes ----------


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need admin on Windows")
def test_symlink_pointing_outside(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    _mkfile(tmp_path / "secret")
    link = root / "innocent.jpg"
    os.symlink(tmp_path / "secret", link)
    with pytest.raises(PathGuardError, match="symlink"):
        resolve_local_path(link, [root])


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need admin on Windows")
def test_symlink_chain_inside_root(tmp_path: Path) -> None:
    """Even if a symlink points to another file inside the same root, reject
    it — the point of forbidding symlinks is to avoid ambiguity."""
    root = tmp_path / "uploads"
    root.mkdir()
    real = _mkfile(root / "real.jpg")
    link = root / "link.jpg"
    os.symlink(real, link)
    with pytest.raises(PathGuardError, match="symlink"):
        resolve_local_path(link, [root])


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need admin on Windows")
def test_symlink_ancestor_directory_blocked(tmp_path: Path) -> None:
    """A symlinked directory on the way to the file is also rejected."""
    root = tmp_path / "uploads"
    root.mkdir()
    real_sub = _mkfile(tmp_path / "real" / "img.jpg")
    linked_sub = root / "sub"
    os.symlink(real_sub.parent, linked_sub)
    with pytest.raises(PathGuardError, match="symlink"):
        resolve_local_path(linked_sub / "img.jpg", [root])


# ---------- exotic inputs ----------


def test_empty_string_rejected(tmp_path: Path) -> None:
    with pytest.raises(PathGuardError):
        resolve_local_path("", [tmp_path])


def test_null_byte_in_path(tmp_path: Path) -> None:
    root = tmp_path / "uploads"
    root.mkdir()
    # pathlib raises ValueError on null bytes on every platform; the
    # guard should surface some error either way.
    with pytest.raises((PathGuardError, ValueError)):
        resolve_local_path("x\x00y.jpg", [root])
