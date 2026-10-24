import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DIST_DIR = ROOT / "dist"
PUBLIC_DIR = ROOT / "public"


@dataclass(frozen=True)
class SiteConfig:
    site_url: str = "http://localhost:8000"
    """Origin the site is served from, e.g. https://api.linuxserver.io"""
    base_path: str = "/"
    """Path prefix, with leading and trailing slash: "/" or "/static-api/"."""

    @classmethod
    def from_env(cls) -> "SiteConfig":
        """SITE_URL and BASE_PATH come from actions/configure-pages in CI."""
        site_url = (os.environ.get("SITE_URL") or cls.site_url).rstrip("/")
        base = os.environ.get("BASE_PATH", "").strip("/")
        return cls(site_url=site_url, base_path=f"/{base}/" if base else "/")

    @property
    def site_root(self) -> str:
        """The site's public URL, with a trailing slash: "https://api.linuxserver.io/"."""
        return f"{self.site_url}{self.base_path}"

    @property
    def api_root(self) -> str:
        """The API's base URL for `servers` and examples, without a trailing slash."""
        return self.site_root.rstrip("/")
