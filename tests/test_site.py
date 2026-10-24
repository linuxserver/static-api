import re
from dataclasses import replace
from typing import Any

from lsio_api.config import SiteConfig
from lsio_api.fleet import Fleet
from lsio_api.site import FieldView, operation_groups, render_not_found, type_label
from lsio_api.templating import compact, format_timestamp

PAGE_FILES = ("index.html", "404.html")


def field(fields: list[FieldView], *names: str) -> FieldView:
    """The field at a path of names, e.g. field(fields, "data", "status")."""
    found = next(f for f in fields if f.name == names[0])
    return field(found.children, *names[1:]) if len(names) > 1 else found


def test_documents_every_operation(spec: dict[str, Any], files: dict[str, bytes]) -> None:
    page = files["index.html"].decode()
    for path, item in spec["paths"].items():
        assert f'id="op-{item["get"]["operationId"]}"' in page
        assert f'data-path="{path}"' in page


def test_local_links_use_the_base_path(files: dict[str, bytes]) -> None:
    for name in PAGE_FILES:
        local = re.findall(r'(?:href|src)="(/[^"]*)"', files[name].decode())
        assert local
        assert all(url.startswith("/static-api/") for url in local), name


def test_open_links_point_at_real_urls(files: dict[str, bytes]) -> None:
    assert 'href="/static-api/api/v1/catalog/sonarr.json"' in files["index.html"].decode()


def test_shows_real_data_in_the_examples(fleet: Fleet, files: dict[str, bytes]) -> None:
    page = files["index.html"].decode()
    sonarr = next(i for i in fleet.images if i.name == "sonarr")
    assert "https://example.github.io/static-api/api/v1/catalog/sonarr.json" in page
    assert f'<span class="out">{sonarr.version}</span>' in page
    assert '<option value="wireguard">' in page


def test_says_when_the_last_refresh_failed(fleet: Fleet, config: SiteConfig) -> None:
    page = render_not_found(replace(fleet, health="Failed"), config)
    assert "Last refresh failed" in page and "pulse-bad" in page


def test_one_h1_and_labelled_landmarks(files: dict[str, bytes]) -> None:
    for name in PAGE_FILES:
        page = files[name].decode()
        assert len(re.findall(r"<h1[\s>]", page)) == 1
        assert '<main id="main"' in page and '<nav aria-label="Main"' in page and '<html lang="en-GB"' in page


def test_documents_map_values(spec: dict[str, Any]) -> None:
    status = next(
        op
        for tag, ops in operation_groups(spec, SiteConfig(), "sonarr")
        for op in ops
        if op.path == "/api/v1/status.json"
    )
    sources = field(status.fields, "data", "status", "sources")
    assert [f.name for f in sources.children] == ["ok", "checked_at", "fetched_at", "error"]


def test_type_labels(spec: dict[str, Any]) -> None:
    assert type_label(spec, {"$ref": "#/components/schemas/Config"}) == "Config"
    assert type_label(spec, {"anyOf": [{"$ref": "#/components/schemas/Config"}, {"type": "null"}]}) == "Config"
    assert type_label(spec, {"type": "array", "items": {"$ref": "#/components/schemas/Tag"}}) == "Tag[]"
    assert type_label(spec, {"anyOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}]}) == (
        "string | string[]"
    )
    assert type_label(spec, {"enum": ["Success", "Failed"]}) == '"Success" | "Failed"'
    assert type_label(spec, {"type": "object", "additionalProperties": {"type": "integer"}}) == "map<string, integer>"


def test_formatting() -> None:
    assert compact(17_321_271_697) == "17.3B"
    assert compact(186_886) == "186.9K"
    assert compact(42) == "42"
    assert compact(999) == "999"
    assert compact(999_999) == "1M"
    assert format_timestamp("2026-10-24T13:11:46.000Z") == "24 Oct 2026, 13:11 UTC"
    assert format_timestamp("2026-10-31T23:30:00-01:00") == "1 Nov 2026, 00:30 UTC"
    assert format_timestamp("") == "never"
