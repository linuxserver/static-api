"""Builds the content of each response from the fleet. Pure, so each endpoint is tested without HTTP."""

import datetime
from collections import Counter, defaultdict

from .dates import parse_iso
from .fleet import Fleet
from .models import (
    CHANGELOG_LIMIT,
    V1_CHANGELOG_ENTRIES,
    Category,
    ChangelogEntry,
    Image,
    ImageDetail,
    ImagesData,
    ImagesResponse,
    Repository,
    Stats,
    Status,
)

_V1_FIELDS = Image.model_fields.keys() - {"changelog", "config"}


def to_v1_image(image: ImageDetail, include_config: bool) -> Image:
    """The v1 view of an image: the original fields only, three changelog entries, config on request."""
    return Image(
        **{key: getattr(image, key) for key in _V1_FIELDS},
        changelog=image.changelog[:V1_CHANGELOG_ENTRIES] if image.changelog is not None else None,
        config=image.config if include_config else None,
    )


def images_response(fleet: Fleet, include_config: bool = False, include_deprecated: bool = False) -> ImagesResponse:
    images = fleet.images if include_deprecated else fleet.current
    linuxserver = [to_v1_image(i, include_config) for i in images]
    return ImagesResponse(
        status="OK", last_updated=fleet.last_updated, data=ImagesData(repositories=Repository(linuxserver=linuxserver))
    )


def slugify(name: str) -> str:
    return "-".join("".join(c if c.isalnum() else " " for c in name.lower()).split())


def categories(fleet: Fleet) -> list[Category]:
    """Categories of current images, most populated first."""
    by_name: defaultdict[str, list[str]] = defaultdict(list)
    for image in fleet.current:
        for category in image.categories:
            by_name[category].append(image.name)
    found = [Category(name=n, slug=slugify(n), count=len(i), images=sorted(i)) for n, i in by_name.items()]
    return sorted(found, key=lambda c: (-c.count, c.name.casefold()))


def stats(fleet: Fleet) -> Stats:
    images = fleet.current
    updated = parse_iso(fleet.updated_at)
    week_before = updated - datetime.timedelta(days=7) if updated else None

    def recent(image: ImageDetail) -> bool:
        released = parse_iso(image.version_timestamp)
        return bool(released and week_before and released >= week_before)

    first_dates = sorted(i.initial_date for i in images if i.initial_date)
    return Stats(
        images=len(images),
        deprecated=len(fleet.images) - len(images),
        monthly_pulls=sum(i.monthly_pulls or 0 for i in images),
        docker_hub_pulls=sum(i.docker_hub_pulls or 0 for i in images),
        stars=sum(i.stars for i in images),
        # dict.fromkeys, not a set: each image counts once, and the key order is stable between builds.
        architectures=dict(Counter(arch for i in images for arch in dict.fromkeys(a.arch for a in i.architectures))),
        readonly_supported=sum(1 for i in images if i.config.readonly_supported),
        nonroot_supported=sum(1 for i in images if i.config.nonroot_supported),
        updated_last_7_days=sum(1 for i in images if recent(i)),
        categories=len({c for i in images for c in i.categories}),
        first_release=first_dates[0] if first_dates else None,
    )


def recent_changelog(fleet: Fleet) -> list[ChangelogEntry]:
    """The most recent changelog entries across current images: newest first, then by image name."""
    entries = [(c.date, image.name, c.desc) for image in fleet.current for c in image.changelog or []]
    entries.sort(key=lambda e: e[1])
    entries.sort(key=lambda e: e[0], reverse=True)
    return [ChangelogEntry(image=name, date=date, desc=desc) for date, name, desc in entries[:CHANGELOG_LIMIT]]


def status(fleet: Fleet) -> Status:
    current = len(fleet.current)
    return Status(health=fleet.health, images=current, deprecated=len(fleet.images) - current, sources=fleet.sources)
