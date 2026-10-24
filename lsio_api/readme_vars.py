"""
readme-vars.yml is the source of truth for every image's README, docs page and API entry. It is a Jinja
template in places, so it is rendered before parsing (rendering after would not work: an unquoted
"[{{ project_name }}]" is a YAML list).
"""

from typing import Any

import jinja2
import yaml

ReadmeVars = dict[str, Any]

# The C parser when PyYAML has it (12x faster, same results), as the original's SafeLoader otherwise.
_Loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

# Unknown variables stay as written, rather than becoming empty or raising.
_jinja = jinja2.Environment(undefined=jinja2.DebugUndefined, keep_trailing_newline=True)


def _parse(text: str) -> ReadmeVars | None:
    parsed = yaml.load(text, Loader=_Loader)
    return parsed if isinstance(parsed, dict) else None


def parse_api_vars(text: str | None, project_name: str) -> ReadmeVars | None:
    """
    readme-vars.yml with exactly the substitutions lsio_github.py makes, so the v1 fields match the
    original API: the project name without links, and no project URL. None when the file is missing, empty
    or not a mapping; raises on invalid YAML.
    """
    if not text:
        return None
    substitutions = [  # in order: the bracketed forms must go before the bare ones
        ("[{{ project_name|capitalize }}]", project_name),
        ("{{ project_name|capitalize }}", project_name),
        ("[{{ project_name }}]", project_name),
        ("{{ project_name }}", project_name),
        ("({{ project_url }})", ""),
        ("{{ project_url }}", ""),
        ("{{ arch_x86_64 }}", "x86_64"),
        ("{{ arch_arm64 }}", "arm64"),
    ]
    for expression, value in substitutions:
        text = text.replace(expression, value)
    return _parse(text)


def parse_readme_vars(text: str, project_name: str, project_url: str) -> ReadmeVars | None:
    """
    readme-vars.yml rendered by Jinja the way the README is, links included, for the fields this API adds.
    Raises on a template or YAML error.
    """
    rendered = _jinja.from_string(text).render(
        project_name=project_name, project_url=project_url, arch_x86_64="x86_64", arch_arm64="arm64"
    )
    return _parse(rendered)
