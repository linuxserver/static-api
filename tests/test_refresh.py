import httpx2

from lsio_api.refresh import _annotation, refresh
from lsio_api.snapshot import Snapshot

from .conftest import fake_http, fixture_snapshot, graphql_node, graphql_page

NOW = "2026-10-25T04:00:00.000Z"


def sources(*failing: str) -> httpx2.Client:
    """Answers GitHub, Scarf and Docker Hub, or 404s the hosts containing any of `failing`."""

    def handle(request: httpx2.Request) -> httpx2.Response:
        host = request.url.host
        if any(f in host for f in failing):
            return httpx2.Response(404)
        if host == "api.github.com":
            node = graphql_node(
                name="docker-fresh", latestRelease=None, master={"text": 'project_categories: "Tools"\n'}
            )
            return httpx2.Response(200, json=graphql_page([node]))
        if host == "api.scarf.sh":
            return httpx2.Response(
                200, json={"results": [{"package": {"name": "linuxserver/fresh"}, "total_installs": 9}]}
            )
        return httpx2.Response(200, json={"pull_count": 123})

    return fake_http(handle)[0]


def run(previous: Snapshot, http: httpx2.Client, **options: object) -> Snapshot:
    kwargs: dict[str, object] = {"github_token": "g", "scarf_token": "s"} | options
    return refresh(previous, http=http, now=lambda: NOW, **kwargs)  # type: ignore[arg-type]


def test_replaces_every_source_when_all_succeed() -> None:
    snapshot = run(fixture_snapshot(), sources())
    assert [r.name for r in snapshot.github.repos] == ["docker-fresh"]
    assert snapshot.scarf.pulls == {"fresh": 9}
    assert snapshot.dockerhub.pulls == {"fresh": 123}
    for status in snapshot.status.values():
        assert status.model_dump(exclude_none=True) == {"ok": True, "checked_at": NOW, "fetched_at": NOW}


def test_keeps_previous_data_when_a_source_fails() -> None:
    previous = fixture_snapshot()
    snapshot = run(previous, sources("github"))
    assert snapshot.github == previous.github
    github = snapshot.status["github"]
    assert not github.ok and "404" in (github.error or "")
    assert github.fetched_at == previous.github.fetched_at
    assert snapshot.status["scarf"].ok


def test_missing_token_fails_that_source_without_calling_it() -> None:
    http, requests = fake_http(lambda request: sources().send(request))
    snapshot = run(fixture_snapshot(), http, scarf_token=None)
    assert snapshot.status["scarf"].model_dump(exclude_none=True)["error"] == "SCARF_TOKEN is not set"
    assert all(r.url.host != "api.scarf.sh" for r in requests)


def test_docker_hub_fails_when_every_request_fails() -> None:
    snapshot = run(fixture_snapshot(), sources("docker"))
    assert not snapshot.status["dockerhub"].ok
    assert snapshot.status["dockerhub"].error == "every request failed"


def test_can_skip_docker_hub() -> None:
    previous = fixture_snapshot()
    snapshot = run(previous, sources(), skip_dockerhub=True)
    assert snapshot.dockerhub == previous.dockerhub
    assert snapshot.status["dockerhub"] == previous.status["dockerhub"]


def test_does_not_modify_the_previous_snapshot() -> None:
    previous = fixture_snapshot()
    copy = previous.model_copy(deep=True)
    run(previous, sources())
    assert previous == copy


def test_actions_annotation_escapes_newlines() -> None:
    assert _annotation("github", "a\nb 100%") == "::warning title=github refresh failed::a%0Ab 100%25"
