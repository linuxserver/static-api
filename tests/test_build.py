"""The built site: every documented path is built, the spec is valid, and the files land where they should."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from openapi_spec_validator import validate

from lsio_api.app import create_app
from lsio_api.build import render, route_paths, write_site
from lsio_api.config import SiteConfig
from lsio_api.fleet import Fleet, load_fleet
from lsio_api.models import SourceStatus
from lsio_api.snapshot import Snapshot, load_snapshot, save_snapshot

from .conftest import fixture_snapshot


def test_builds_every_documented_path(fleet: Fleet, spec: dict[str, Any], files: dict[str, bytes]) -> None:
    for path in spec["paths"]:
        if "{name}" not in path:
            assert path.lstrip("/") in files, path
    for image in fleet.images:
        assert f"api/v1/catalog/{image.name}.json" in files
        assert f"api/v1/catalog/{image.name}/docker-compose.yml" in files
    assert {"index.html", "404.html", "openapi.json", "openapi.yaml"} <= files.keys()


def test_route_paths_need_values_for_every_parameter(fleet: Fleet, config: SiteConfig) -> None:
    app = create_app(fleet, config)

    @app.get("/api/v1/categories/{category}.json")
    def category(category: str) -> str:
        return category

    with pytest.raises(ValueError, match="no values to build category"):
        route_paths(app, fleet)


def test_spec_is_valid_openapi(spec: dict[str, Any], files: dict[str, bytes]) -> None:
    validate(spec)
    assert spec["servers"] == [{"url": "https://example.github.io/static-api"}]
    assert yaml.safe_load(files["openapi.yaml"]) == spec


def test_operation_ids_are_unique_and_tagged(spec: dict[str, Any]) -> None:
    ops = [item["get"] for item in spec["paths"].values()]
    ids = [op["operationId"] for op in ops]
    assert len(set(ids)) == len(ids)
    tags = {t["name"] for t in spec["tags"]}
    assert all(set(op["tags"]) <= tags for op in ops)


def test_extensionless_compat_files_match_their_json_twins(files: dict[str, bytes]) -> None:
    assert files["health"] == files["health.json"] == b'"Success"'
    assert files["api/v1/images"] == files["api/v1/images.json"]


def test_compose_and_feed(files: dict[str, bytes]) -> None:
    compose = yaml.safe_load(files["api/v1/catalog/sonarr/docker-compose.yml"])
    assert compose["services"]["sonarr"]["restart"] == "unless-stopped"
    feed = files["api/v1/changelog.xml"].decode()
    assert feed.startswith('<?xml version="1.0" encoding="utf-8"?>') and feed.endswith("</feed>\n")


def test_unknown_paths_get_the_404_page(client: TestClient, files: dict[str, bytes]) -> None:
    for path in ("/api/v1/catalog/nope.json", "/nope"):
        res = client.get(path)
        assert res.status_code == 404
        assert res.content == files["404.html"]


def test_writes_files_and_public_assets(tmp_path: Path, files: dict[str, bytes]) -> None:
    write_site(tmp_path, files)
    assert (tmp_path / "api/v1/images").read_bytes() == (tmp_path / "api/v1/images.json").read_bytes()
    assert sorted(p.name for p in (tmp_path / "assets/fonts").glob("*.woff2")) == ["geist-mono.woff2", "geist.woff2"]
    for asset in ("assets/site.css", "assets/site.js", "favicon.svg", "index.html", "404.html"):
        assert (tmp_path / asset).stat().st_size > 0


def test_never_tried_sources_are_left_out_of_status() -> None:
    snapshot = fixture_snapshot()
    snapshot.status = {"github": snapshot.status["github"]}
    fleet = load_fleet(snapshot)
    assert set(fleet.sources) == {"github"}
    render(fleet, SiteConfig())  # and the build still validates


def test_failed_github_refresh_reports_failed() -> None:
    snapshot = fixture_snapshot()
    snapshot.status["github"] = SourceStatus(ok=False, checked_at="2026-10-25T04:00:00Z", error="down")
    assert render(load_fleet(snapshot), SiteConfig())["health"] == b'"Failed"'


def test_snapshot_round_trips_byte_for_byte(tmp_path: Path) -> None:
    save_snapshot(tmp_path, fixture_snapshot())
    first = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    save_snapshot(tmp_path, load_snapshot(tmp_path))
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == first


def test_missing_data_loads_as_empty(tmp_path: Path) -> None:
    assert load_snapshot(tmp_path) == Snapshot()
