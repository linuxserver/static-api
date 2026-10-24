"""
Runs the API as a live server on http://localhost:8000/ for development. It is the same app the build
writes out, so what you see here is what gets published (at the root path, whatever BASE_PATH is).

Usage: python -m lsio_api.serve
"""

import uvicorn

from .app import create_app
from .config import DATA_DIR, SiteConfig
from .responses import to_model
from .snapshot import load_snapshot

if __name__ == "__main__":
    uvicorn.run(create_app(to_model(load_snapshot(DATA_DIR)), SiteConfig()), port=8000)
