"""
Builds dist/ from data/ by requesting every route of the FastAPI app through its test client and writing
each response to a file: the API, the generated OpenAPI spec and the docs pages. Pydantic validates every
response on the way, so data that doesn't fit the models is never published.

Usage: [SITE_URL=https://api.linuxserver.io] [BASE_PATH=/] python -m lsio_api.build
"""

import itertools
import logging
import shutil
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from .app import create_app
from .config import DATA_DIR, DIST_DIR, PUBLIC_DIR, SiteConfig
from .fleet import Fleet, load_fleet
from .snapshot import load_snapshot

log = logging.getLogger(__name__)

Files = dict[str, bytes]


def route_paths(app: FastAPI, fleet: Fleet) -> list[str]:
    """Every route's path, with each path parameter expanded to all its values."""
    values = {"name": [image.name for image in fleet.images]}
    paths = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        params = list(route.param_convertors)
        if unknown := set(params) - values.keys():
            raise ValueError(f"{route.path}: no values to build {', '.join(sorted(unknown))} with")
        for combination in itertools.product(*(values[p] for p in params)):
            paths.append(route.path_format.format(**dict(zip(params, combination, strict=True))))
    return paths


def render(fleet: Fleet, config: SiteConfig) -> Files:
    """Every generated file of the site, by path relative to the site root. Raises if any route fails."""
    app = create_app(fleet, config)
    files: Files = {}
    with TestClient(app) as client:
        for path in route_paths(app, fleet):
            res = client.get(path)
            res.raise_for_status()
            files[path.lstrip("/") or "index.html"] = res.content
        missing = client.get("/404.html")  # any path that doesn't exist gets the 404 page
        assert missing.status_code == 404, missing.status_code
        files["404.html"] = missing.content
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
    fleet = load_fleet(load_snapshot(DATA_DIR))
    if not fleet.images:
        log.error("No images in data/. Run `python -m lsio_api.refresh` first.")
        return 1
    files = render(fleet, config)
    write_site(DIST_DIR, files)
    log.info("Built %d files for %d images into dist/ (%s)", len(files), len(fleet.images), config.site_root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
