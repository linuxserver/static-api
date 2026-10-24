"""Builds every response from the image list. Pure, so each endpoint is tested without HTTP."""

import datetime
from collections import Counter, defaultdict
from dataclasses import dataclass

from .models import (
    Category,
    ChangelogEntry,
    Health,
    Image,
    ImageDetail,
    ImagesData,
    ImagesResponse,
    Repository,
    SourceStatus,
    Stats,
    Status,
)
from .snapshot import Snapshot
from .transform import build_images, python_timestamp

CHANGELOG_LIMIT = 100


@dataclass(frozen=True)
class Model:
    images: list[ImageDetail]
    updated_at: str
    """ISO 8601 time of the last successful GitHub refresh."""
    health: Health
    sources: dict[str, SourceStatus]

    @property
    def last_updated(self) -> str:
        """The envelope's timestamp, in the original API's format."""
        return python_timestamp(self.updated_at)

    @property
    def current(self) -> list[ImageDetail]:
        return [i for i in self.images if not i.deprecated]


def to_model(snapshot: Snapshot) -> Model:
    return Model(
        images=build_images(snapshot.github.repos, snapshot.scarf.pulls, snapshot.dockerhub.pulls),
        updated_at=snapshot.github.fetched_at,
        health="Success" if snapshot.source_status("github").ok else "Failed",
        # A source that has never been tried has nothing to report yet.
        sources={name: status for name, status in snapshot.status.items() if status.checked_at},
    )


def to_v1_image(image: ImageDetail, include_config: bool) -> Image:
    """The v1 view of an image: the original fields only, three changelog entries, config on request."""
    fields = Image.model_fields.keys() - {"changelog", "config"}
    return Image(
        **{key: getattr(image, key) for key in fields},
        changelog=image.changelog[:3] if image.changelog is not None else None,
        config=image.config if include_config else None,
    )


def images_response(model: Model, include_config: bool = False, include_deprecated: bool = False) -> ImagesResponse:
    images = model.images if include_deprecated else model.current
    linuxserver = [to_v1_image(i, include_config) for i in images]
    return ImagesResponse(
        status="OK", last_updated=model.last_updated, data=ImagesData(repositories=Repository(linuxserver=linuxserver))
    )


def slugify(name: str) -> str:
    return "-".join("".join(c if c.isalnum() else " " for c in name.lower()).split())


def categories(model: Model) -> list[Category]:
    """Categories of current images, most populated first."""
    by_name: defaultdict[str, list[str]] = defaultdict(list)
    for image in model.current:
        for category in image.categories:
            by_name[category].append(image.name)
    found = [Category(name=n, slug=slugify(n), count=len(i), images=sorted(i)) for n, i in by_name.items()]
    return sorted(found, key=lambda c: (-c.count, c.name.casefold()))


def _parse(timestamp: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(timestamp)
    except ValueError:
        return None


def _on_or_after(timestamp: str, since: datetime.datetime | None) -> bool:
    when = _parse(timestamp)
    return bool(when and since and when >= since)


def stats(model: Model) -> Stats:
    images = model.current
    updated = _parse(model.updated_at)
    week_before = updated - datetime.timedelta(days=7) if updated else None
    first_dates = sorted(i.initial_date for i in images if i.initial_date)
    return Stats(
        images=len(images),
        deprecated=len(model.images) - len(images),
        monthly_pulls=sum(i.monthly_pulls or 0 for i in images),
        docker_hub_pulls=sum(i.docker_hub_pulls or 0 for i in images),
        stars=sum(i.stars for i in images),
        architectures=dict(Counter(arch for i in images for arch in {a.arch for a in i.architectures})),
        readonly_supported=sum(1 for i in images if i.config.readonly_supported),
        nonroot_supported=sum(1 for i in images if i.config.nonroot_supported),
        updated_last_7_days=sum(1 for i in images if _on_or_after(i.version_timestamp, week_before)),
        categories=len({c for i in images for c in i.categories}),
        first_release=first_dates[0] if first_dates else None,
    )


def recent_changelog(model: Model) -> list[ChangelogEntry]:
    """The most recent changelog entries across current images: newest first, then by image name."""
    entries = [
        ChangelogEntry(image=image.name, date=c.date, desc=c.desc)
        for image in model.current
        for c in image.changelog or []
    ]
    entries.sort(key=lambda e: e.image)
    entries.sort(key=lambda e: e.date, reverse=True)
    return entries[:CHANGELOG_LIMIT]


def status(model: Model) -> Status:
    current = len(model.current)
    return Status(health=model.health, images=current, deprecated=len(model.images) - current, sources=model.sources)
