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
SOURCES: tuple[SourceName, ...] = ("github", "scarf", "dockerhub")


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
    fetched_at: str = ""
    repos: list[RepoSnapshot] = []


class PullsSnapshot(BaseModel):
    """Monthly (Scarf) or lifetime (Docker Hub) pull counts keyed by image name."""

    fetched_at: str = ""
    pulls: dict[str, int] = {}


def never_tried() -> SourceStatus:
    return SourceStatus(ok=False, checked_at="")


class Snapshot(BaseModel):
    github: GithubSnapshot = GithubSnapshot()
    scarf: PullsSnapshot = PullsSnapshot()
    dockerhub: PullsSnapshot = PullsSnapshot()
    status: dict[SourceName, SourceStatus] = {}
    """Outcome of the most recent refresh of each source."""

    def source_status(self, source: SourceName) -> SourceStatus:
        return self.status.get(source) or never_tried()


def _read(path: Path) -> object:
    return json.loads(path.read_text()) if path.exists() else {}


def load_snapshot(directory: Path) -> Snapshot:
    """Reads data/. Missing files are treated as empty so a fresh checkout can refresh straight away."""
    parts = {key: _read(directory / f"{key}.json") for key in ("github", "scarf", "dockerhub", "status")}
    return Snapshot.model_validate(parts)


def save_snapshot(directory: Path, snapshot: Snapshot) -> None:
    """One JSON file per source, indented, so the daily data commit is a readable diff."""
    directory.mkdir(parents=True, exist_ok=True)
    parts = {
        "github": snapshot.github.model_dump(),
        "scarf": snapshot.scarf.model_dump(),
        "dockerhub": snapshot.dockerhub.model_dump(),
        "status": {name: s.model_dump(exclude_none=True) for name, s in snapshot.status.items()},
    }
    for key, value in parts.items():
        (directory / f"{key}.json").write_text(json.dumps(value, indent=1, ensure_ascii=False) + "\n")
