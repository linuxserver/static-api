"""
Builds dist/ from data/: every route of the FastAPI app requested through its test client and written
to a file, the generated OpenAPI spec, and the docs pages. Pydantic validates every response on the way,
so data that doesn't fit the models is never published.

Usage: [SITE_URL=https://api.linuxserver.io] [BASE_PATH=/] python -m lsio_api.build
"""

import json
import logging
import shutil
import sys
from pathlib import Path

import yaml
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from .app import create_app
from .config import DATA_DIR, DIST_DIR, PUBLIC_DIR, SiteConfig
from .responses import Model, to_model
from .site import render_not_found
from .snapshot import load_snapshot

log = logging.getLogger(__name__)

Files = dict[str, bytes]


def endpoint_paths(app: FastAPI, model: Model) -> list[str]:
    """Every path the spec documents, with {name} expanded to each image."""
    paths = []
    for route in app.routes:
        if not (isinstance(route, APIRoute) and route.include_in_schema):
            continue
        if "{name}" in route.path:
            paths += [route.path.replace("{name}", image.name) for image in model.images]
        else:
            paths.append(route.path)
    return paths


def render(model: Model, config: SiteConfig) -> Files:
    """Every generated file of the site, by path relative to the site root. Raises if any route fails."""
    app = create_app(model, config)
    files: Files = {}
    with TestClient(app, raise_server_exceptions=True) as client:
        for path in [*endpoint_paths(app, model), "/"]:
            res = client.get(path)
            res.raise_for_status()
            files[path.lstrip("/") or "index.html"] = res.content
    spec = app.openapi()
    files["openapi.json"] = (json.dumps(spec, indent=2, ensure_ascii=False) + "\n").encode()
    files["openapi.yaml"] = yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=1000).encode()
    files["404.html"] = render_not_found(model, config).encode()
    return files


def write_site(out_dir: Path, files: Files) -> None:
    shutil.rmtree(out_dir, ignore_errors=True)
    shutil.copytree(PUBLIC_DIR, out_dir)
    for path, content in files.items():
        target = out_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx2").setLevel(logging.WARNING)  # one line per built file is noise
    config = SiteConfig.from_env()
    model = to_model(load_snapshot(DATA_DIR))
    if not model.images:
        log.error("No images in data/. Run `python -m lsio_api.refresh` first.")
        return 1
    files = render(model, config)
    write_site(DIST_DIR, files)
    log.info("Built %d files for %d images into dist/ (%s)", len(files), len(model.images), config.site_root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
