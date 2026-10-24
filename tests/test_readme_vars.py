import pytest
import yaml

from lsio_api.readme_vars import api_substitutions, parse_readme_vars, readme_substitutions


def test_substitutes_what_lsio_github_does() -> None:
    text = (
        'project_blurb: "[{{ project_name|capitalize }}]({{ project_url }}) is {{ project_name }}."\n'
        "available_architectures:\n"
        '  - {arch: "{{ arch_x86_64 }}", tag: "amd64-latest"}\n'
        '  - {arch: "{{ arch_arm64 }}", tag: "arm64v8-latest"}\n'
    )
    assert parse_readme_vars(text, api_substitutions("sonarr")) == {
        "project_blurb": "sonarr is sonarr.",
        "available_architectures": [
            {"arch": "x86_64", "tag": "amd64-latest"},
            {"arch": "arm64", "tag": "arm64v8-latest"},
        ],
    }


def test_renders_like_the_readme_for_added_fields() -> None:
    text = (
        "block: |\n"
        "  {% raw -%}\n"
        "  [{{ project_name|capitalize }}]({{ project_url }})"
        " and [{{project_name}}]({{project_url}}) on {{ arch_arm64 }}\n"
        "  {%- endraw %}\n"
    )
    parsed = parse_readme_vars(text, readme_substitutions("sonarr", "https://sonarr.tv/"))
    assert parsed == {"block": "\n[Sonarr](https://sonarr.tv/) and [sonarr](https://sonarr.tv/) on arm64\n"}


def test_inserts_values_literally() -> None:
    parsed = parse_readme_vars("a: '{{ project_url }}'", readme_substitutions("x", r"https://e.com/\1$&"))
    assert parsed == {"a": r"https://e.com/\1$&"}


def test_yaml_like_pyyaml() -> None:
    assert parse_readme_vars("a: yes\nb: off\n", api_substitutions("x")) == {"a": True, "b": False}
    assert parse_readme_vars("a: 1\na: 2\n", api_substitutions("x")) == {"a": 2}


@pytest.mark.parametrize("text", [None, "", "- a\n- b\n"])
def test_none_for_missing_empty_or_non_mapping(text: str | None) -> None:
    assert parse_readme_vars(text, api_substitutions("x")) is None


def test_raises_on_invalid_yaml() -> None:
    with pytest.raises(yaml.YAMLError):
        parse_readme_vars("a: [unclosed", api_substitutions("x"))
