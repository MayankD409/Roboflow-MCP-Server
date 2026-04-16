"""End-to-end example: generate a dataset version, poll until ready,
export to YOLOv8, and download the zip.

Requires:
- ROBOFLOW_MCP_MODE=full (version creation and export download are gated)
- ROBOFLOW_MCP_ENABLE_DOWNLOADS=true (default)
- ROBOFLOW_MCP_EXPORT_CACHE_DIR (default ~/.cache/roboflow-mcp)
"""

from __future__ import annotations

import asyncio
import os
import sys

from roboflow_mcp.client import RoboflowClient
from roboflow_mcp.config import RoboflowSettings
from roboflow_mcp.models.version import (
    DownloadResult,
    ExportResult,
    VersionGenerationStatus,
)
from roboflow_mcp.tools.download import download_export_impl
from roboflow_mcp.tools.version import (
    create_version_impl,
    export_version_impl,
    get_version_generation_status_impl,
)

POLL_INTERVAL_S = 30
POLL_TIMEOUT_S = 30 * 60  # 30 minutes


async def main() -> int:
    settings = RoboflowSettings()
    project = os.environ.get("ROBOFLOW_PROJECT", "boxes")

    async with RoboflowClient(settings) as client:
        # 1. Kick off async generation.
        create_response = await create_version_impl(
            project=project,
            workspace=None,
            preprocessing={"resize": 640},
            augmentation={"rotate": 15, "flip": "horizontal"},
            confirm="yes",
            client=client,
            settings=settings,
        )
        new_version = str(create_response.get("raw", {}).get("version", ""))
        if not new_version:
            print("Roboflow did not return a version id", file=sys.stderr)
            return 1
        print(f"Version {new_version} kicked off")

        # 2. Poll until ready.
        elapsed = 0
        while elapsed < POLL_TIMEOUT_S:
            status = await get_version_generation_status_impl(
                project=project,
                version=new_version,
                workspace=None,
                client=client,
                settings=settings,
            )
            if isinstance(status, VersionGenerationStatus):
                print(f"  state={status.status} progress={status.progress}")
                if status.status == "ready":
                    break
                if status.status == "failed":
                    print(f"  generation failed: {status.message}")
                    return 2
            await asyncio.sleep(POLL_INTERVAL_S)
            elapsed += POLL_INTERVAL_S
        else:
            print("Timed out waiting for version generation.", file=sys.stderr)
            return 3

        # 3. Export to YOLOv8 format.
        export = await export_version_impl(
            project=project,
            version=new_version,
            export_format="yolov8",
            workspace=None,
            client=client,
            settings=settings,
        )
        if not isinstance(export, ExportResult) or not export.download_url:
            print("Export did not yield a download URL", file=sys.stderr)
            return 4

        # 4. Stream the zip + extract.
        download = await download_export_impl(
            project=project,
            version=new_version,
            export_format="yolov8",
            workspace=None,
            download_url=export.download_url,
            extract=True,
            confirm="yes",
            client=client,
            settings=settings,
        )
        if isinstance(download, DownloadResult):
            print(
                f"Downloaded {download.bytes} bytes to {download.path}; "
                f"extracted={download.extracted}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
