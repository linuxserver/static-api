"""
Refreshes data/ from GitHub, Scarf and Docker Hub. Like the Python updater, a source that fails keeps its
previous data and the failure is recorded, so the API keeps serving and /health reports it.

Usage: GITHUB_TOKEN=… [SCARF_TOKEN=…] python -m lsio_api.refresh [--skip-dockerhub]
"""

import datetime
import logging
import os
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import httpx2

from .config import DATA_DIR
from .models import SourceStatus
from .snapshot import GithubSnapshot, PullsSnapshot, Snapshot, SourceName, load_snapshot, save_snapshot
from .sources.github import fetch_repos
from .sources.http import client
from .sources.pulls import fetch_docker_hub_pulls, fetch_scarf_pulls
from .transform import listed_image_names

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def refresh(
    previous: Snapshot,
    *,
    github_token: str | None,
    scarf_token: str | None,
    skip_dockerhub: bool = False,
    http: httpx2.Client | None = None,
    now: Callable[[], str] = _now,
) -> Snapshot:
    """A new snapshot; `previous` is not modified."""
    snapshot = previous.model_copy(deep=True)
    http = http or client()

    def attempt(source: SourceName, run: Callable[[], str | None]) -> None:
        """Runs one source; on failure the previous data stays and the error is recorded."""
        checked_at = now()
        try:
            ok, message = True, run()
        except Exception as e:
            ok, message = False, str(e)
        fetched_at = getattr(snapshot, source).fetched_at or None
        snapshot.status[source] = SourceStatus(ok=ok, checked_at=checked_at, fetched_at=fetched_at, error=message)
        if ok:
            log.info("  ✓ %s%s", source, f" ({message})" if message else "")
        else:
            log.info("  ✗ %s: %s (keeping data from %s)", source, message, fetched_at or "never")

    def github() -> None:
        if not github_token:
            raise RuntimeError("GITHUB_TOKEN is not set")
        repos = fetch_repos(http, github_token)
        if not repos:
            raise RuntimeError("no image repositories returned")
        snapshot.github = GithubSnapshot(fetched_at=now(), repos=repos)

    def dockerhub() -> str | None:
        names = listed_image_names(snapshot.github.repos)
        pulls, failed = fetch_docker_hub_pulls(http, names, snapshot.dockerhub.pulls)
        if names and len(failed) == len(names):
            raise RuntimeError("every request failed")
        snapshot.dockerhub = PullsSnapshot(fetched_at=now(), pulls=pulls)
        return f"{len(failed)} kept previous counts: {', '.join(failed)}" if failed else None

    def scarf() -> None:
        if not scarf_token:
            raise RuntimeError("SCARF_TOKEN is not set")
        pulls = fetch_scarf_pulls(http, scarf_token)
        if not pulls:
            raise RuntimeError("no pull counts returned")
        snapshot.scarf = PullsSnapshot(fetched_at=now(), pulls=pulls)

    def github_then_dockerhub() -> None:
        attempt("github", github)
        if not skip_dockerhub:
            attempt("dockerhub", dockerhub)

    # Docker Hub needs the image names from GitHub; Scarf needs nothing, so it runs alongside.
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in [pool.submit(github_then_dockerhub), pool.submit(attempt, "scarf", scarf)]:
            future.result()
    return snapshot


def _annotation(source: str, message: str) -> str:
    """A GitHub Actions warning; % CR and LF must be escaped or the message is cut short."""
    escaped = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return f"::warning title={source} refresh failed::{escaped}"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    snapshot = refresh(
        load_snapshot(DATA_DIR),
        github_token=os.environ.get("GITHUB_TOKEN"),
        scarf_token=os.environ.get("SCARF_TOKEN"),
        skip_dockerhub="--skip-dockerhub" in sys.argv,
    )
    save_snapshot(DATA_DIR, snapshot)
    if os.environ.get("GITHUB_ACTIONS"):
        for source, status in snapshot.status.items():
            if not status.ok:
                print(_annotation(source, status.error or "unknown error"))
    # Only fail when there is nothing to build from at all; otherwise stale data is still worth serving.
    if not snapshot.github.repos:
        log.error("No GitHub data, so there is nothing to build.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
