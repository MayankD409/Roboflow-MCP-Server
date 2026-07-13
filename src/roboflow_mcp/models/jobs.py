"""Pydantic models for annotation-job tools."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, computed_field


class AnnotationJob(BaseModel):
    """One annotation job from ``GET /{workspace}/{project}/jobs``."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    name: str | None = None
    status: str | None = None
    # Internal project id (not the slug) — the add-to-dataset endpoint
    # addresses projects by this id.
    project: str | None = None
    num_images: int = Field(default=0, alias="numImages")
    unannotated: int = 0
    annotated: int = 0
    approved: int = 0
    rejected: int = 0
    labeler: str | None = None
    reviewer: str | None = None
    source_batch: str | None = Field(default=None, alias="sourceBatch")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ready_to_add(self) -> bool:
        """True when the job sits in review with every image approved.

        Excludes empty leftover jobs (``numImages == 0``), which Roboflow
        keeps in ``review`` status but which have nothing to add.
        """
        return (
            self.status == "review"
            and self.num_images > 0
            and self.approved == self.num_images
        )


class JobsList(BaseModel):
    """Response shape for ``roboflow_list_annotation_jobs``."""

    project: str
    total: int
    ready_to_add_jobs: int
    ready_to_add_images: int
    jobs: list[AnnotationJob]


class JobAddResult(BaseModel):
    """Outcome of one add-to-dataset call."""

    job_id: str
    name: str | None = None
    images_expected: int
    images_added: int
    train: int
    valid: int
    test: int
    ok: bool
    error: str | None = None


class AddReviewedResult(BaseModel):
    """Response shape for ``roboflow_add_reviewed_to_dataset``."""

    project: str
    jobs_added: int
    images_added: int
    split_counts: dict[str, int]
    all_ok: bool
    aborted_on: str | None = None
    results: list[JobAddResult]
