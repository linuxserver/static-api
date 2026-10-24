"""
readme-vars.yml is the source of truth for every image's README, docs page and API entry. It is a Jinja
template in places, so the expressions that appear in values are substituted in the text before parsing
(substituting after parsing would not work: an unquoted "[{{ project_name }}]" is a YAML list).
"""

import re
from typing import Any

import yaml

ReadmeVars = dict[str, Any]
Substitution = tuple[str | re.Pattern[str], str]


def api_substitutions(project_name: str) -> list[Substitution]:
    """
    Exactly what lsio_github.py substitutes, so the v1 fields match the original API. Applied in order;
    the bracketed forms must go before the bare ones. Links to the project are dropped.
    """
    return [
        ("[{{ project_name|capitalize }}]", project_name),
        ("{{ project_name|capitalize }}", project_name),
        ("[{{ project_name }}]", project_name),
        ("{{ project_name }}", project_name),
        ("({{ project_url }})", ""),
        ("{{ project_url }}", ""),
        ("{{ arch_x86_64 }}", "x86_64"),
        ("{{ arch_arm64 }}", "arm64"),
    ]


def readme_substitutions(project_name: str, project_url: str) -> list[Substitution]:
    """What Jinja renders for the README, for fields this API adds: links kept, raw markers removed."""
    return [
        (re.compile(r"\{\{\s*project_name\s*\|\s*capitalize\s*\}\}"), project_name.capitalize()),
        (re.compile(r"\{\{\s*project_name\s*\}\}"), project_name),
        (re.compile(r"\{\{\s*project_url\s*\}\}"), project_url),
        (re.compile(r"\{\{\s*arch_x86_64\s*\}\}"), "x86_64"),
        (re.compile(r"\{\{\s*arch_arm64\s*\}\}"), "arm64"),
        (re.compile(r"\{%-?\s*(?:end)?raw\s*-?%\}"), ""),
    ]


def parse_readme_vars(text: str | None, substitutions: list[Substitution]) -> ReadmeVars | None:
    """None when the file is missing, empty or not a YAML mapping. Raises on invalid YAML."""
    if not text:
        return None
    for expression, value in substitutions:
        if isinstance(expression, str):
            text = text.replace(expression, value)
        else:
            text = expression.sub(value.replace("\\", "\\\\"), text)  # escaped, so "\1" in a URL stays literal
    parsed = yaml.load(text, Loader=yaml.SafeLoader)
    return parsed if isinstance(parsed, dict) else None
