import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient

from lsio_api.app import create_app
from lsio_api.build import render
from lsio_api.config import SiteConfig
from lsio_api.fleet import Fleet, load_fleet
from lsio_api.models import SourceStatus
from lsio_api.snapshot import GithubSnapshot, PullsSnapshot, Release, RepoSnapshot, Snapshot

FIXTURES = Path(__file__).parent / "fixtures"
FETCHED_AT = "2026-10-24T13:11:46.000Z"


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def repo(**overrides: Any) -> RepoSnapshot:
    """A repository with a minimal valid readme-vars.yml; override anything."""
    fields: dict[str, Any] = {
        "name": "docker-example",
        "url": "https://github.com/linuxserver/docker-example",
        "stars": 5,
        "pushed_at": "2026-10-01T10:00:00Z",
        "archived": False,
        "latest_release": Release(
            tag="1.0.0-ls1",
            published_at="2026-10-20T08:30:00Z",
            url="https://github.com/linuxserver/docker-example/releases/tag/1.0.0-ls1",
        ),
        "readme_vars": 'project_name: example\nproject_blurb: An example.\nproject_categories: "Tools"\n',
    }
    return RepoSnapshot(**(fields | overrides))


def fixture_snapshot() -> Snapshot:
    fixture = load_fixture("repos.json")
    ok = SourceStatus(ok=True, checked_at=FETCHED_AT, fetched_at=FETCHED_AT)
    return Snapshot(
        github=GithubSnapshot(fetched_at=FETCHED_AT, repos=fixture["repos"]),
        scarf=PullsSnapshot(fetched_at=FETCHED_AT, pulls=fixture["scarf"]),
        dockerhub=PullsSnapshot(fetched_at=FETCHED_AT, pulls={"sonarr": 1_000_000, "wireguard": 500_000}),
        status={"github": ok, "scarf": ok, "dockerhub": ok},
    )


@pytest.fixture
def fleet() -> Fleet:
    return load_fleet(fixture_snapshot())


@pytest.fixture
def config() -> SiteConfig:
    return SiteConfig(site_url="https://example.github.io", base_path="/static-api/")


@pytest.fixture
def files(fleet: Fleet, config: SiteConfig) -> dict[str, bytes]:
    """Every file of the built site."""
    return render(fleet, config)


@pytest.fixture
def spec(files: dict[str, bytes]) -> dict[str, Any]:
    """The published OpenAPI spec."""
    parsed: dict[str, Any] = json.loads(files["openapi.json"])
    return parsed


@pytest.fixture
def client(fleet: Fleet, config: SiteConfig) -> Iterator[TestClient]:
    with TestClient(create_app(fleet, config)) as c:
        yield c


# ---------------------------------------------------------------------------------------------------
# Fake HTTP for the sources


def graphql_node(**overrides: Any) -> dict[str, Any]:
    """A repository as the GitHub GraphQL query returns it."""
    return {
        "name": "docker-example",
        "url": "https://github.com/linuxserver/docker-example",
        "stargazerCount": 3,
        "pushedAt": "2026-10-01T00:00:00Z",
        "isArchived": False,
        "latestRelease": {"tagName": "v1", "publishedAt": "2026-10-02T00:00:00Z", "url": "https://example/v1"},
        **overrides,
    }


def graphql_page(nodes: list[dict[str, Any]], next_cursor: str | None = None) -> dict[str, Any]:
    page_info = {"hasNextPage": next_cursor is not None, "endCursor": next_cursor}
    return {"data": {"organization": {"repositories": {"pageInfo": page_info, "nodes": nodes}}}}


Handler = Callable[[httpx2.Request], httpx2.Response]


def fake_http(handler: Handler) -> tuple[httpx2.Client, list[httpx2.Request]]:
    """An HTTP client answered by `handler`, and the list of requests it received."""
    requests: list[httpx2.Request] = []

    def record(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return handler(request)

    return httpx2.Client(transport=httpx2.MockTransport(record)), requests


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retries back off with time.sleep; tests shouldn't wait."""
    monkeypatch.setattr("lsio_api.sources.http.time.sleep", lambda _: None)
