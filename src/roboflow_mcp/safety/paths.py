"""Path-traversal guard for local-file ingestion.

An LLM-controlled upload path argument (e.g. ``/tmp/alice/photo.jpg``) must
not escape the operator-configured upload roots. ``Path.resolve(strict=True)``
canonicalises symlinks, so a symlink from inside an allowed root that
points at ``/etc/passwd`` resolves to ``/etc/passwd`` and fails the
``relative_to`` check below.

We also forbid any upload path that is itself a symlink before resolving,
to catch the "operator places a symlink inside an allowed root" variant
where the resolved destination is also inside the root but still points
at unintended data. Both guards together make the rule simple:
**every path must both (a) be a real file after resolve(), and (b) live
inside one of the allowed roots after resolve().**
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ..errors import PathGuardError


def resolve_local_path(path_arg: str | Path, allowed_roots: Iterable[Path]) -> Path:
    """Return the canonical path if it lives inside one of ``allowed_roots``.

    Raises :class:`PathGuardError` if:

    - the path doesn't exist or isn't a regular file
    - any component on the way to the file is a symlink
    - the canonical path is not inside any allowed root

    ``allowed_roots`` can be any iterable of ``Path``; each is itself
    resolved (strict) once so a root configured as ``~/datasets`` is
    expanded before comparison.
    """
    raw = Path(path_arg)

    # Walk the parts and fail on any symlink component. resolve() would
    # silently follow them; we want to reject them up front so the caller
    # doesn't accidentally ingest a file they didn't mean to.
    for parent in (raw, *raw.parents):
        if parent.is_symlink():
            raise PathGuardError(
                f"{parent} is a symlink; symlinked components are not allowed "
                "in upload paths. Resolve the path manually and pass the real "
                "file location."
            )

    try:
        resolved = raw.resolve(strict=True)
    except FileNotFoundError as exc:
        raise PathGuardError(f"Path does not exist: {raw}") from exc
    except OSError as exc:  # pragma: no cover - rare filesystem errors
        raise PathGuardError(f"Could not resolve {raw}: {exc}") from exc

    if not resolved.is_file():
        raise PathGuardError(f"{resolved} is not a regular file")

    normalised_roots: list[Path] = []
    for root in allowed_roots:
        try:
            normalised_roots.append(Path(root).expanduser().resolve(strict=True))
        except FileNotFoundError as exc:
            raise PathGuardError(
                f"Configured upload root does not exist: {root}. Check "
                "ROBOFLOW_MCP_UPLOAD_ROOTS."
            ) from exc

    if not normalised_roots:
        raise PathGuardError(
            "No upload roots configured. Set ROBOFLOW_MCP_UPLOAD_ROOTS to "
            "a comma-separated list of absolute directories."
        )

    for root in normalised_roots:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue

    raise PathGuardError(
        f"{resolved} is not under any configured upload root "
        f"({', '.join(str(r) for r in normalised_roots)})."
    )
