from lsio_api import responses
from lsio_api.config import SiteConfig
from lsio_api.feed import changelog_feed
from lsio_api.fleet import Fleet
from lsio_api.models import CHANGELOG_LIMIT, SourceStatus
from lsio_api.responses import images_response, to_v1_image
from lsio_api.transform import build_images

from .conftest import repo


def small_fleet() -> Fleet:
    """Three images with known dates, categories and architectures; one deprecated."""

    def readme(category: str, changelog: list[str], extra: str = "") -> str:
        entries = "".join(f'  - {{date: "{c}:", desc: "Change on {c}"}}\n' for c in changelog)
        return (
            f'project_categories: "{category}"\n'
            "available_architectures:\n"
            '  - {arch: "x86_64", tag: "amd64-latest"}\n'
            '  - {arch: "arm64", tag: "arm64v8-latest"}\n'
            f"changelogs:\n{entries}{extra}"
        )

    repos = [
        repo(name="docker-alpha", readme_vars=readme("Media,Tools", ["10.10.26", "01.01.20"])),
        repo(name="docker-beta", readme_vars=readme("Tools", ["10.10.26", "02.02.21"]), latest_release=None),
        repo(name="docker-gone", readme_vars=readme("Media", ["20.10.26"], "project_deprecation_status: true\n")),
    ]
    images = build_images(repos, {"alpha": 10, "beta": 5, "gone": 100}, {"alpha": 1000})
    return Fleet(images=images, updated_at="2026-10-24T12:00:00.000Z", health="Success", sources={})


def test_images_wrapped_like_the_original(fleet: Fleet) -> None:
    res = images_response(fleet)
    assert res.status == "OK"
    assert res.last_updated == "2026-10-24 13:11:46+00:00"


def test_images_default_leaves_out_deprecated_and_config(fleet: Fleet) -> None:
    images = images_response(fleet).data.repositories.linuxserver
    assert all(not i.deprecated and i.config is None for i in images)
    names = [i.name for i in images]
    assert "sonarr" in names and "readarr" not in names


def test_images_honour_both_switches(fleet: Fleet) -> None:
    images = images_response(fleet, include_config=True, include_deprecated=True).data.repositories.linuxserver
    assert len(images) == len(fleet.images)
    assert all(i.config is not None for i in images)


def test_v1_image_has_only_original_fields_and_three_changelog_entries(fleet: Fleet) -> None:
    detail = next(i for i in fleet.images if i.name == "sonarr")
    v1 = to_v1_image(detail, include_config=False).model_dump(exclude_none=True)
    assert len(detail.changelog or []) > 3
    assert len(v1["changelog"]) == 3
    for extra in ("categories", "snippets", "registries", "docs_url", "archived", "config"):
        assert extra not in v1


def test_categories_most_populated_first() -> None:
    assert [c.model_dump() for c in responses.categories(small_fleet())] == [
        {"name": "Tools", "slug": "tools", "count": 2, "images": ["alpha", "beta"]},
        {"name": "Media", "slug": "media", "count": 1, "images": ["alpha"]},
    ]


def test_slugify() -> None:
    assert responses.slugify("3D Printing") == "3d-printing"
    assert responses.slugify(" Home Automation ") == "home-automation"


def test_stats_sum_current_images_only() -> None:
    assert responses.stats(small_fleet()).model_dump() == {
        "images": 2,
        "deprecated": 1,
        "monthly_pulls": 15,
        "docker_hub_pulls": 1000,
        "stars": 10,
        "architectures": {"x86_64": 2, "arm64": 2},
        "readonly_supported": 0,
        "nonroot_supported": 0,
        # alpha's release (20 Oct) is in the week before updated_at; beta has none and last pushed 1 Oct.
        "updated_last_7_days": 1,
        "categories": 2,
        "first_release": "2020-01-01",
    }


def test_changelog_newest_first_ties_by_name() -> None:
    assert [e.model_dump() for e in responses.recent_changelog(small_fleet())] == [
        {"image": "alpha", "date": "2026-10-10", "desc": "Change on 10.10.26"},
        {"image": "beta", "date": "2026-10-10", "desc": "Change on 10.10.26"},
        {"image": "beta", "date": "2021-02-02", "desc": "Change on 02.02.21"},
        {"image": "alpha", "date": "2020-01-01", "desc": "Change on 01.01.20"},
    ]


def test_changelog_limited(fleet: Fleet) -> None:
    assert len(responses.recent_changelog(fleet)) <= CHANGELOG_LIMIT


def test_feed_escapes_text_and_has_stable_ids() -> None:
    readme = 'changelogs:\n  - {date: "10.10.26:", desc: "Use <new> \'flag\' & more"}\n'
    fleet = Fleet(build_images([repo(readme_vars=readme)], {}, {}), "2026-10-24T12:00:00.000Z", "Success", {})
    feed = changelog_feed(fleet, SiteConfig(site_url="https://x"))
    assert "<title>example: Use &lt;new&gt; &#39;flag&#39; &amp; more</title>" in feed
    assert "<updated>2026-10-10T00:00:00Z</updated>" in feed
    assert '<link rel="self" href="https://x/api/v1/changelog.xml"/>' in feed
    assert feed == changelog_feed(fleet, SiteConfig(site_url="https://x"))


def test_status_reports_health_and_sources() -> None:
    sources = {"github": SourceStatus(ok=False, checked_at="x")}
    status = responses.status(Fleet(small_fleet().images, "2026-10-24T12:00:00Z", "Failed", sources))
    assert status.model_dump(exclude_none=True) == {
        "health": "Failed",
        "images": 2,
        "deprecated": 1,
        "sources": {"github": {"ok": False, "checked_at": "x"}},
    }
