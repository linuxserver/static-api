"""The fleet: every image built from a snapshot, with when it was refreshed and how that went."""

from dataclasses import dataclass

from .dates import python_timestamp
from .models import Health, ImageDetail, SourceStatus
from .snapshot import Snapshot
from .transform import build_images


@dataclass(frozen=True)
class Fleet:
    images: list[ImageDetail]
    updated_at: str | None
    """ISO 8601 time of the last successful GitHub refresh."""
    health: Health
    sources: dict[str, SourceStatus]

    @property
    def last_updated(self) -> str:
        """`updated_at` in the original API's format, for every response's envelope."""
        return python_timestamp(self.updated_at)

    @property
    def current(self) -> list[ImageDetail]:
        """The images that aren't deprecated."""
        return [i for i in self.images if not i.deprecated]


def load_fleet(snapshot: Snapshot) -> Fleet:
    github = snapshot.status.get("github")
    return Fleet(
        images=build_images(snapshot.github.repos, snapshot.scarf.pulls, snapshot.dockerhub.pulls),
        updated_at=snapshot.github.fetched_at,
        health="Success" if github and github.ok else "Failed",
        sources={str(name): status for name, status in snapshot.status.items()},
    )
