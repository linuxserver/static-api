import json

import httpx2
import pytest

from lsio_api.sources.github import fetch_repos, to_repo_snapshot
from lsio_api.sources.http import request_json
from lsio_api.sources.pulls import fetch_docker_hub_pulls, fetch_scarf_pulls

from .conftest import fake_http, graphql_node, graphql_page


def test_retries_429_and_5xx_then_succeeds() -> None:
    statuses = iter([429, 503, 200])
    http, requests = fake_http(lambda _: httpx2.Response(next(statuses), json={"ok": 1}))
    assert request_json(http, "GET", "https://x") == {"ok": 1}
    assert len(requests) == 3


def test_retries_network_errors() -> None:
    def flaky(request: httpx2.Request) -> httpx2.Response:
        if not getattr(flaky, "failed", False):
            flaky.failed = True  # type: ignore[attr-defined]
            raise httpx2.ConnectError("reset", request=request)
        return httpx2.Response(200, json={"ok": 1})

    http, requests = fake_http(flaky)
    assert request_json(http, "GET", "https://x") == {"ok": 1}
    assert len(requests) == 2


def test_does_not_retry_other_errors() -> None:
    http, requests = fake_http(lambda _: httpx2.Response(404))
    with pytest.raises(httpx2.HTTPStatusError):
        request_json(http, "GET", "https://x")
    assert len(requests) == 1


def test_gives_up_after_the_retries() -> None:
    http, requests = fake_http(lambda _: httpx2.Response(500))
    with pytest.raises(httpx2.HTTPStatusError):
        request_json(http, "GET", "https://x", retries=2)
    assert len(requests) == 3


def test_readme_vars_from_the_first_branch_that_has_one() -> None:
    node = graphql_node(master=None, main={"text": "from: main"}, develop={"text": "from: develop"})
    assert to_repo_snapshot(node).readme_vars == "from: main"
    assert to_repo_snapshot(graphql_node()).readme_vars is None


def test_latest_release() -> None:
    release = to_repo_snapshot(graphql_node()).latest_release
    assert release is not None
    assert release.model_dump() == {"tag": "v1", "published_at": "2026-10-02T00:00:00Z", "url": "https://example/v1"}
    assert to_repo_snapshot(graphql_node(latestRelease=None)).latest_release is None


def test_pages_through_the_org_keeping_image_repos() -> None:
    pages = iter(
        [
            graphql_page([graphql_node(name="docker-a"), graphql_node(name="site")], "c1"),
            graphql_page([graphql_node(name="docker-baseimage-alpine"), graphql_node(name="docker-b")]),
        ]
    )
    http, requests = fake_http(lambda _: httpx2.Response(200, json=next(pages)))
    assert [r.name for r in fetch_repos(http, "t")] == ["docker-a", "docker-b"]
    assert json.loads(requests[1].content)["variables"]["cursor"] == "c1"
    assert requests[0].headers["Authorization"] == "Bearer t"


def test_surfaces_graphql_errors() -> None:
    http, _ = fake_http(lambda _: httpx2.Response(200, json={"errors": [{"message": "Bad credentials"}]}))
    with pytest.raises(RuntimeError, match="Bad credentials"):
        fetch_repos(http, "t")


def test_scarf_monthly_installs() -> None:
    results = [
        {"package": {"name": "linuxserver/sonarr"}, "total_installs": 100},
        {"package": {"name": "linuxserver/radarr"}},
    ]
    http, requests = fake_http(lambda _: httpx2.Response(200, json={"results": results}))
    assert fetch_scarf_pulls(http, "s") == {"sonarr": 100}
    assert requests[0].headers["Authorization"] == "Bearer s"


def test_docker_hub_keeps_previous_counts_for_failures() -> None:
    def hub(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"pull_count": 42}) if "/sonarr/" in request.url.path else httpx2.Response(404)

    http, _ = fake_http(hub)
    pulls, failed = fetch_docker_hub_pulls(http, ["sonarr", "radarr", "new"], {"radarr": 7})
    assert pulls == {"sonarr": 42, "radarr": 7}
    assert failed == ["new", "radarr"]
