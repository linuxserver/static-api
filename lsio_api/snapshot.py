"""
The raw source data the build reads, committed to data/ by CI. Keeping raw data (rather than finished
responses) means a change to how images are built from readme-vars.yml needs no refetch, and the
build is deterministic and works offline.
"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .models import SourceStatus

SourceName = Literal["github", "scarf", "dockerhub"]


def is_image_repo(repo_name: str) -> bool:
    """Image repositories are docker-<name>, except the base images."""
    return repo_name.startswith("docker-") and not repo_name.startswith("docker-baseimage-")


class Release(BaseModel):
    tag: str
    published_at: str
    url: str


class RepoSnapshot(BaseModel):
    name: str
    url: str
    stars: int
    pushed_at: str | None
    archived: bool
    latest_release: Release | None
    """The latest non-prerelease release, as GitHub reports it."""
    readme_vars: str | None
    """readme-vars.yml from the first of master, main, develop, nightly that has one."""


class GithubSnapshot(BaseModel):
    fetched_at: str | None = None
    repos: list[RepoSnapshot] = []


class PullsSnapshot(BaseModel):
    """Monthly (Scarf) or lifetime (Docker Hub) pull counts keyed by image name."""

    fetched_at: str | None = None
    pulls: dict[str, int] = {}


class Snapshot(BaseModel):
    github: GithubSnapshot = GithubSnapshot()
    scarf: PullsSnapshot = PullsSnapshot()
    dockerhub: PullsSnapshot = PullsSnapshot()
    status: dict[SourceName, SourceStatus] = {}
    """Outcome of the most recent refresh of each source; a source never tried has no entry."""


def _read(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def load_snapshot(directory: Path) -> Snapshot:
    """Reads data/. Missing files are treated as empty so a fresh checkout can refresh straight away."""
    return Snapshot.model_validate({key: _read(directory / f"{key}.json") for key in Snapshot.model_fields})


def save_snapshot(directory: Path, snapshot: Snapshot) -> None:
    """One JSON file per source, indented, so the daily data commit is a readable diff."""
    directory.mkdir(parents=True, exist_ok=True)
    # Repositories keep their nulls (the fields are required); statuses leave unset fields out.
    for key, value in snapshot.model_dump().items():
        if key == "status":
            value = {name: s.model_dump(exclude_none=True) for name, s in snapshot.status.items()}
        (directory / f"{key}.json").write_text(json.dumps(value, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
