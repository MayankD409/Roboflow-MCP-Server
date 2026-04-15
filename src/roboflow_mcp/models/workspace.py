"""Pydantic models for the Roboflow workspace endpoint.

The shape comes from ``GET /{workspace}?api_key=...`` which returns a
``workspace`` object containing the workspace metadata and its projects. We
model both because callers care about fields beyond the obvious ones (class
distribution, split counts, unannotated image count).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProjectSplits(BaseModel):
    """Train/test/valid image counts for a project."""

    model_config = ConfigDict(extra="ignore")

    train: int = 0
    test: int = 0
    valid: int = 0


class Project(BaseModel):
    """A Roboflow project as returned inside a workspace payload."""

    model_config = ConfigDict(extra="ignore")

    id: str
    type: str
    name: str
    created: float
    updated: float
    images: int = 0
    unannotated: int = 0
    annotation: str | None = None
    versions: int = 0
    public: bool = False
    splits: ProjectSplits | None = None
    classes: dict[str, int] = Field(default_factory=dict)


class Workspace(BaseModel):
    """A Roboflow workspace with its projects inlined."""

    model_config = ConfigDict(extra="ignore")

    name: str
    url: str
    members: int = 0
    projects: list[Project] = Field(default_factory=list)
