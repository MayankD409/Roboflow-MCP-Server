"""Curate-a-dataset example.

Uses the v0.1 tag tools to find all images with a stale tag, re-tag them
under a new name, and verify with a follow-up search.

Run with:
    ROBOFLOW_API_KEY=... ROBOFLOW_WORKSPACE=contoro \
    ROBOFLOW_MCP_MODE=curate \
    python examples/curate_dataset.py
"""

from __future__ import annotations

import asyncio
import os
import sys

from roboflow_mcp.client import RoboflowClient
from roboflow_mcp.config import RoboflowSettings
from roboflow_mcp.tools.image import (
    add_image_tags_impl,
    remove_image_tags_impl,
    search_images_impl,
)


async def main() -> int:
    settings = RoboflowSettings()  # reads env
    project = os.environ.get("ROBOFLOW_PROJECT", "boxes")

    async with RoboflowClient(settings) as client:
        found = await search_images_impl(
            project=project,
            workspace=None,
            tag="stale",
            limit=50,
            client=client,
            settings=settings,
        )
        if isinstance(found, dict):  # dry-run path; not in use here
            return 1
        print(f"Found {found.total} images tagged 'stale'")

        for img in found.results:
            await remove_image_tags_impl(
                project=project,
                image_id=img.id,
                tags=["stale"],
                workspace=None,
                confirm="yes",
                client=client,
                settings=settings,
            )
            await add_image_tags_impl(
                project=project,
                image_id=img.id,
                tags=["archived", "2026-04"],
                workspace=None,
                client=client,
                settings=settings,
            )
        print(f"Re-tagged {len(found.results)} images")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
