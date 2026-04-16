"""Upload a local image and attach a YOLO annotation.

Run with:
    ROBOFLOW_API_KEY=... ROBOFLOW_WORKSPACE=contoro \
    ROBOFLOW_MCP_MODE=curate \
    ROBOFLOW_MCP_UPLOAD_ROOTS=/path/to/images \
    python examples/upload_and_annotate.py

The image path must live under one of ``ROBOFLOW_MCP_UPLOAD_ROOTS``.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from roboflow_mcp.client import RoboflowClient
from roboflow_mcp.config import RoboflowSettings
from roboflow_mcp.models.upload import UploadResult
from roboflow_mcp.tools.annotation import upload_annotation_impl
from roboflow_mcp.tools.upload import upload_image_impl


async def main() -> int:
    settings = RoboflowSettings()
    project = os.environ.get("ROBOFLOW_PROJECT", "boxes")
    image_path = os.environ.get(
        "EXAMPLE_IMAGE", str(Path.home() / "Pictures" / "sample.jpg")
    )

    # YOLO one-liner: class_id x_center y_center width height (normalised)
    yolo_annotation = "0 0.5 0.5 0.3 0.3\n"

    async with RoboflowClient(settings) as client:
        upload = await upload_image_impl(
            project=project,
            source={"kind": "path", "path": image_path},
            workspace=None,
            split="train",
            client=client,
            settings=settings,
        )
        if not isinstance(upload, UploadResult):
            print("Unexpected response shape", file=sys.stderr)
            return 1
        if not upload.id:
            print("Upload did not return an image id", file=sys.stderr)
            return 1
        print(f"Uploaded {upload.filename} as id={upload.id}")

        ann = await upload_annotation_impl(
            project=project,
            image_id=upload.id,
            annotation=yolo_annotation,
            annotation_format="yolo",
            workspace=None,
            client=client,
            settings=settings,
        )
        print(f"Annotation attached: {ann}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
