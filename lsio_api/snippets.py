"""
Quick-start snippets generated from an image's config, in the same shape as the READMEs and
docs.linuxserver.io. Ported from the site (src/lib/images.ts) so both produce identical output;
optional parameters are included and marked as such.
"""

import json
import re
from collections.abc import Callable, Sequence
from typing import Protocol

from .models import Config, Port

REGISTRY = "lscr.io/linuxserver"


class _Optional(Protocol):
    optional: bool


def _quote(s: str) -> str:
    """Quote a YAML scalar only when it needs it."""
    # ensure_ascii=False, as JSON.stringify in the site, so "café" isn't written as "caf\u00e9".
    return json.dumps(s, ensure_ascii=False) if s == "" or re.search(r"""[\s:#{}\[\],&*?|<>=!%@`'"]""", s) else s


def _ports(c: Config) -> list[Port]:
    """Port mappings are meaningless with host networking."""
    return [] if c.networking == "host" else (c.ports or [])


def docker_compose(name: str, c: Config) -> str:
    def opt(x: _Optional) -> str:
        return " # optional" if x.optional else ""

    lines = ["---", "services:", f"  {name}:", f"    image: {REGISTRY}/{name}:latest", f"    container_name: {name}"]

    def listing[T: _Optional](key: str, items: Sequence[T] | None, value: Callable[[T], str]) -> None:
        if items:
            lines.append(f"    {key}:")
            lines.extend(f"      - {value(x)}{opt(x)}" for x in items)

    if c.networking:
        lines.append(f"    network_mode: {c.networking}")
    if c.privileged:
        lines.append("    privileged: true")
    if c.hostname:
        lines.append(f"    hostname: {_quote(c.hostname.hostname)}{opt(c.hostname)}")
    if c.mac_address:
        lines.append(f"    mac_address: {_quote(c.mac_address.mac_address)}{opt(c.mac_address)}")
    listing("cap_add", c.caps, lambda x: x.cap_add)
    listing("security_opt", c.security_opt, lambda x: x.compose_var)
    listing("environment", c.env_vars, lambda e: f"{e.name}={e.value}")
    listing("volumes", c.volumes, lambda v: f"{v.host_path}:{v.path}")
    listing("ports", _ports(c), lambda p: f"{p.external}:{p.internal}")
    listing("devices", c.devices, lambda d: f"{d.host_path}:{d.path}")
    for x in c.custom or []:
        if isinstance(x.value, list):
            lines.append(f"    {x.name_compose}:")
            lines.extend(f"      - {v}" for v in x.value)
        else:
            lines.append(f"    {x.name_compose}: {_quote(x.value)}{opt(x)}")
    lines.append("    restart: unless-stopped")
    return "\n".join(lines) + "\n"


def docker_run(name: str, c: Config) -> str:
    def opt(x: _Optional) -> str:
        return " `#optional`" if x.optional else ""

    lines = ["docker run -d", f"  --name={name}"]
    if c.networking:
        lines.append(f"  --net={c.networking}")
    if c.privileged:
        lines.append("  --privileged")
    if c.hostname:
        lines.append(f"  --hostname={c.hostname.hostname}{opt(c.hostname)}")
    if c.mac_address:
        lines.append(f"  --mac-address={c.mac_address.mac_address}{opt(c.mac_address)}")
    lines.extend(f"  --cap-add={x.cap_add}{opt(x)}" for x in c.caps or [])
    lines.extend(f"  --security-opt {x.run_var}{opt(x)}" for x in c.security_opt or [])
    lines.extend(f"  -e {e.name}={e.value}{opt(e)}" for e in c.env_vars or [])
    lines.extend(f"  -p {p.external}:{p.internal}{opt(p)}" for p in _ports(c))
    lines.extend(f"  -v {v.host_path}:{v.path}{opt(v)}" for v in c.volumes or [])
    lines.extend(f"  --device {d.host_path}:{d.path}{opt(d)}" for d in c.devices or [])
    for x in c.custom or []:
        values = x.value if isinstance(x.value, list) else [x.value]
        lines.extend(f"  --{x.name}={v}{opt(x)}" for v in values)
    lines.extend(["  --restart unless-stopped", f"  {REGISTRY}/{name}:latest"])
    return " \\\n".join(lines) + "\n"
