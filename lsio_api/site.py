"""
The docs page, in the design of www.linuxserver.io ("Raft"). The endpoint reference is read from the
generated OpenAPI spec, so the docs can never disagree with the API; the templates only lay it out.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown_it import MarkdownIt
from markupsafe import Markup

from . import responses
from .config import SiteConfig
from .responses import Model

TEMPLATES = Path(__file__).parent / "templates"
EXAMPLE_IMAGE = "sonarr"
MAX_DEPTH = 6
"""Deep enough for every schema; stops a recursive schema from recursing forever."""

Schema = dict[str, Any]

_md = MarkdownIt("commonmark").enable("table")
_wordmark = json.loads((TEMPLATES / "wordmark.json").read_text())


# ---------------------------------------------------------------------------------------------------
# Reading the spec


def _resolve(spec: Schema, schema: Schema) -> Schema:
    """Follows a local "#/components/…" reference."""
    while "$ref" in schema:
        target: Any = spec
        for key in schema["$ref"].removeprefix("#/").split("/"):
            target = target[key]
        schema = target
    return schema


def _variants(schema: Schema) -> list[Schema]:
    """The alternatives of an anyOf/oneOf, without the null that Pydantic adds for optional fields."""
    options = schema.get("anyOf") or schema.get("oneOf") or [schema]
    return [s for s in options if s.get("type") != "null"]


def type_label(spec: Schema, schema: Schema) -> str:
    variants = _variants(schema)
    if len(variants) > 1:
        return " | ".join(type_label(spec, s) for s in variants)
    schema = variants[0] if variants else {}
    if "$ref" in schema:
        target = _resolve(spec, schema)
        return schema["$ref"].rsplit("/", 1)[-1] if "properties" in target else type_label(spec, target)
    if "const" in schema:
        return json.dumps(schema["const"])
    if "enum" in schema:
        return " | ".join(json.dumps(v) for v in schema["enum"])
    if schema.get("type") == "array":
        return type_label(spec, schema.get("items", {})) + "[]"
    if isinstance(schema.get("additionalProperties"), dict):
        return f"map<string, {type_label(spec, schema['additionalProperties'])}>"
    return f"{schema.get('type', 'any')} ({schema['format']})" if "format" in schema else schema.get("type", "any")


def _expandable(spec: Schema, schema: Schema) -> Schema | None:
    """The object a field expands into, if any: itself, its array items, or its map values."""
    variants = _variants(schema)
    if len(variants) != 1:
        return None
    s = _resolve(spec, variants[0])
    for candidate in (s, s.get("items"), s.get("additionalProperties")):
        if isinstance(candidate, dict) and "properties" in _resolve(spec, candidate):
            return _resolve(spec, candidate)
    return None


@dataclass
class FieldView:
    name: str
    type: str
    required: bool
    description: str
    children: list["FieldView"] = field(default_factory=list)


def _fields(spec: Schema, schema: Schema, depth: int = 0) -> list[FieldView]:
    required = set(schema.get("required", []))
    views = []
    for name, prop in schema.get("properties", {}).items():
        child = _expandable(spec, prop)
        description = prop.get("description") or (child.get("description", "") if child else "")
        views.append(
            FieldView(
                name=name,
                type=type_label(spec, prop),
                required=name in required,
                description=description,
                children=_fields(spec, child, depth + 1) if child and depth < MAX_DEPTH else [],
            )
        )
    return views


@dataclass
class OperationView:
    path: str
    anchor: str
    summary: str
    description: str
    params: list[FieldView]
    media_type: str
    schema_name: str | None
    fields: list[FieldView]
    response_text: str
    name_param: str | None
    default_name: str
    open_href: str

    @property
    def path_parts(self) -> list[tuple[str, bool]]:
        """The path split into (text, is_parameter) for highlighting."""
        return [(part, part.startswith("{")) for part in re.split(r"(\{[^}]+\})", self.path) if part]


def _operation(spec: Schema, path: str, op: Schema, config: SiteConfig, default_name: str) -> OperationView:
    content: dict[str, Schema] = op["responses"]["200"].get("content", {})
    media_type, body = next(iter(content.items()), ("application/json", {}))
    schema: Schema = body.get("schema", {})
    resolved = _expandable(spec, schema)
    params = [
        FieldView(
            name=p["name"],
            type=f"{p['in']} · {type_label(spec, p.get('schema', {}))}",
            required=p.get("required", False),
            description=p.get("description", ""),
        )
        for p in op.get("parameters", [])
    ]
    name_param = next((p["name"] for p in op.get("parameters", []) if p["in"] == "path"), None)
    # The real URL, so Open works before (or without) the script, which keeps it in sync with the input.
    open_path = path.replace(f"{{{name_param}}}", quote(default_name)) if name_param else path
    return OperationView(
        path=path,
        anchor=f"op-{op['operationId']}",
        summary=op["summary"],
        description=op.get("description", ""),
        params=params,
        media_type=media_type,
        schema_name=schema["$ref"].rsplit("/", 1)[-1] if "$ref" in schema else None,
        fields=_fields(spec, resolved) if resolved else [],
        response_text=type_label(spec, schema) if schema else "Text",
        name_param=name_param,
        default_name=default_name,
        open_href=config.base_path + open_path.lstrip("/"),
    )


def operation_groups(spec: Schema, config: SiteConfig, default_name: str) -> list[tuple[Schema, list[OperationView]]]:
    """Operations grouped by tag, in the order the spec lists its tags."""
    ops = [(path, item["get"]) for path, item in spec["paths"].items() if "get" in item]
    return [
        (
            tag,
            [_operation(spec, path, op, config, default_name) for path, op in ops if tag["name"] in op.get("tags", [])],
        )
        for tag in spec.get("tags", [])
    ]


# ---------------------------------------------------------------------------------------------------
# Formatting helpers for the templates


def markdown(text: str | None) -> Markup:
    """Markdown from the spec's own descriptions (trusted content)."""
    return Markup(_md.render(text)) if text else Markup("")


def compact(n: int) -> str:
    """12345678 -> "12.3M", like Intl's compact notation."""
    for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= size:
            return f"{n / size:.1f}".removesuffix(".0") + suffix
    return str(n)


def grouped(n: int) -> str:
    return f"{n:,}"


def format_timestamp(iso: str) -> str:
    """ "2026-10-24T13:11:46.000Z" -> "24 Oct 2026, 13:11 UTC" """
    try:
        d = datetime.fromisoformat(iso)
    except ValueError:
        return "never"
    return f"{d.day} {d:%b %Y, %H:%M} UTC"


def logo(class_name: str, id_prefix: str) -> Markup:
    """The LinuxServer.io logo. `id_prefix` makes its gradient ids unique on the page."""
    body = _wordmark["body"].replace("__ID__", id_prefix)
    return Markup(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{_wordmark["viewBox"]}" class="{class_name}" '
        f'aria-hidden="true" focusable="false">{body}</svg>'
    )


_env = Environment(
    loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(), trim_blocks=True, lstrip_blocks=True
)
_env.filters.update(markdown=markdown, compact=compact, grouped=grouped, timestamp=format_timestamp)
_env.globals.update(logo=logo)


def _context(model: Model, config: SiteConfig) -> dict[str, Any]:
    return {"model": model, "config": config, "base": config.base_path, "stats": responses.stats(model)}


def render_index(model: Model, spec: Schema, config: SiteConfig) -> str:
    example = next((i for i in model.images if i.name == EXAMPLE_IMAGE), model.images[0] if model.images else None)
    example_name = example.name if example else EXAMPLE_IMAGE
    return _env.get_template("index.html").render(
        **_context(model, config),
        spec=spec,
        groups=operation_groups(spec, config, example_name),
        example_name=example_name,
        example_version=example.version if example else "latest",
        image_names=[i.name for i in model.images],
    )


def render_not_found(model: Model, config: SiteConfig) -> str:
    return _env.get_template("404.html").render(**_context(model, config))
