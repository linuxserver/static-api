import pytest

from lsio_api.readme_vars import parse_api_vars
from lsio_api.snapshot import is_image_repo
from lsio_api.transform import (
    build_image,
    build_images,
    changelog_date,
    get_architectures,
    get_changelog,
    get_custom,
    get_description,
    get_env_vars,
    get_hostname,
    get_ports,
    get_setup_instructions,
    get_tags,
    split_categories,
)

from .conftest import repo


def readme(yaml: str) -> dict[str, object]:
    parsed = parse_api_vars(yaml, "example")
    assert parsed is not None
    return parsed


def build(**overrides: object) -> dict[str, object]:
    image = build_image(repo(**overrides), {}, {})
    assert image is not None
    return image.model_dump(exclude_none=True)


def test_is_image_repo() -> None:
    assert is_image_repo("docker-sonarr")
    assert is_image_repo("docker-mods")
    assert not is_image_repo("docker-baseimage-alpine")
    assert not is_image_repo("site")


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "docs"},
        {"name": "docker-baseimage-ubuntu"},
        {"readme_vars": None},
        {"readme_vars": 'project_categories: "Internal,Tools"\n'},
    ],
)
def test_skips_repositories_that_are_not_listed(overrides: dict[str, object]) -> None:
    assert build_image(repo(**overrides), {}, {}) is None


def test_uses_the_latest_release_for_the_version() -> None:
    image = build()
    assert image["version"] == "1.0.0-ls1"
    assert image["version_timestamp"] == "2026-10-20 08:30:00+00:00"
    assert image["release_url"] == "https://github.com/linuxserver/docker-example/releases/tag/1.0.0-ls1"


def test_falls_back_to_latest_and_the_last_push() -> None:
    image = build(latest_release=None)
    assert image["version"] == "latest"
    assert image["version_timestamp"] == "2026-10-01 10:00:00+00:00"
    assert "release_url" not in image


def test_adds_pull_counts_when_the_sources_have_them() -> None:
    image = build_image(repo(), {"example": 12}, {"example": 3400})
    assert image is not None
    assert (image.monthly_pulls, image.docker_hub_pulls) == (12, 3400)
    assert "monthly_pulls" not in build()


def test_adds_the_detail_fields() -> None:
    image = build(archived=True)
    assert image["archived"] is True
    assert image["docs_url"] == "https://docs.linuxserver.io/images/docker-example/"
    assert image["registries"] == {
        "lscr": "lscr.io/linuxserver/example",
        "ghcr": "ghcr.io/linuxserver/example",
        "docker_hub": "docker.io/linuxserver/example",
    }
    assert image["categories"] == ["Tools"]
    assert "image: lscr.io/linuxserver/example:latest" in image["snippets"]["docker_compose"]  # type: ignore[index]


def test_deprecation_message_only_for_deprecated_images() -> None:
    deprecated = 'project_deprecation_status: true\nproject_deprecation_message: "Upstream is gone."\n'
    assert build(readme_vars=deprecated)["deprecation_message"] == "Upstream is gone."
    assert "deprecation_message" not in build(readme_vars='project_deprecation_message: "Left over."\n')


def test_one_broken_file_does_not_stop_the_rest() -> None:
    repos = [repo(name="docker-broken", readme_vars="a: [unclosed"), repo()]
    assert [i.name for i in build_images(repos, {}, {})] == ["example"]


def test_sorted_by_repository_name() -> None:
    images = build_images([repo(name="docker-zeta"), repo(name="docker-alpha")], {}, {})
    assert [i.name for i in images] == ["alpha", "zeta"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("24.10.26:", "2026-10-24"),
        ("01.01.50:", "2050-01-01"),
        ("29.06.15:", "2015-06-29"),
        ("01.01.69:", "1969-01-01"),
        ("1.2.24", "2024-02-01"),
        ("31.02.24:", None),
        ("2024-01-01", None),
        (None, None),
    ],
)
def test_changelog_date(raw: object, expected: str | None) -> None:
    assert changelog_date(raw) == expected


def test_default_tags_and_architectures() -> None:
    tags, stable = get_tags(readme("a: 1"))
    assert [t.model_dump() for t in tags] == [{"tag": "latest", "desc": "Stable releases"}]
    assert stable
    assert [a.model_dump() for a in get_architectures(readme("a: 1"))] == [{"arch": "x86_64", "tag": "amd64-latest"}]


def test_stable_only_with_a_latest_tag() -> None:
    tags, stable = get_tags(readme('development_versions_items:\n  - {tag: "develop", desc: "Dev"}\n'))
    assert [t.tag for t in tags] == ["develop"]
    assert not stable


def test_changelog_keeps_valid_entries_and_dates_the_image() -> None:
    changelog, initial = get_changelog(
        readme(
            "changelogs:\n"
            '  - {date: "03.01.25:", desc: "Third"}\n'
            '  - {date: "99.99.99:", desc: "Broken"}\n'
            '  - {date: "02.01.25:", desc: "Second"}\n'
            '  - {date: "01.01.25:", desc: "First"}\n'
        )
    )
    assert [c.desc for c in changelog or []] == ["Third", "Second", "First"]
    assert initial == "2025-01-01"
    assert get_changelog(readme("a: 1")) == (None, None)


def test_description() -> None:
    assert get_description(readme("project_blurb: |\n  Line one\n  line two\n")) == "Line one line two"
    assert get_description(readme("a: 1")) == "No description"


def test_env_vars_common_then_required_then_optional() -> None:
    env = get_env_vars(
        readme(
            "common_param_env_vars_enabled: true\n"
            'param_env_vars:\n  - {env_var: "A", env_value: "1", desc: "a"}\n'
            'opt_param_env_vars:\n  - {env_var: "B", env_value: 2, desc: "b"}\n'
        )
    )
    assert [(e.name, e.value, e.optional) for e in env or []] == [
        ("PUID", "1000", False),
        ("PGID", "1000", False),
        ("TZ", "Etc/UTC", False),
        ("A", "1", False),
        ("B", "2", True),
    ]
    assert get_env_vars(readme("a: 1")) is None


def test_ports_and_custom_list_values() -> None:
    vars_ = readme(
        'param_ports:\n  - {external_port: "51820", internal_port: "51820/udp", port_desc: "wg"}\n'
        'custom_params:\n  - {name: "sysctl", name_compose: "sysctls", value: ["a=1", "b=2"], desc: "d"}\n'
    )
    assert [p.model_dump() for p in get_ports(vars_) or []] == [
        {"external": "51820", "internal": "51820/udp", "desc": "wg", "optional": False}
    ]
    assert (get_custom(vars_) or [])[0].value == ["a=1", "b=2"]


def test_hostname_optional_only_when_asked() -> None:
    required = 'param_usage_include_hostname: true\nparam_hostname: "h"\nparam_hostname_desc: "d"\n'
    hostname = get_hostname(readme(required))
    assert hostname is not None and hostname.model_dump() == {"hostname": "h", "desc": "d", "optional": False}
    optional = get_hostname(readme(required.replace("true", '"optional"')))
    assert optional is not None and optional.optional
    assert get_hostname(readme('param_hostname: "h"')) is None


def test_setup_instructions_as_the_readme_renders_them() -> None:
    yaml = (
        'project_url: "https://example.org"\n'
        "app_setup_block_enabled: true\n"
        "app_setup_block: |\n"
        "  See [{{ project_name|capitalize }}]({{ project_url }}) or [docs]({{project_url}}).\n"
        "  {% raw %}Compose uses {{ VAR }} syntax.{% endraw %}\n"
    )
    assert get_setup_instructions(yaml, "example", readme(yaml)) == (
        "See [Example](https://example.org) or [docs](https://example.org).\nCompose uses {{ VAR }} syntax."
    )
    disabled = 'app_setup_block: "x"'
    assert get_setup_instructions(disabled, "example", readme(disabled)) is None


def test_unparseable_setup_instructions_cost_only_that_field() -> None:
    # Valid with the v1 substitutions (the brackets are removed), invalid once the README's link is kept.
    yaml = (
        "project_url: https://e.com\n"
        "app_setup_block_enabled: true\n"
        "app_setup_block: [{{ project_name }}]({{ project_url }}) x\n"
    )
    image = build(readme_vars=yaml)
    assert image["name"] == "example"
    assert "setup_instructions" not in image


def test_split_categories() -> None:
    assert split_categories("Network, DNS,, ") == ["Network", "DNS"]
    assert split_categories("") == []
