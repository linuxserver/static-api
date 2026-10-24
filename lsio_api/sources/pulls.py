"""Pull counts: monthly from Scarf (what the original API reports) and lifetime from Docker Hub."""

from concurrent.futures import ThreadPoolExecutor

import httpx2

from .http import request_json


def fetch_scarf_pulls(http: httpx2.Client, token: str) -> dict[str, int]:
    """Monthly installs per image, as updater.py's get_monthly_pulls reads them."""
    res = request_json(
        http,
        "GET",
        "https://api.scarf.sh/v2/packages/linuxserver-ci/overview?per_page=1000",
        headers={"Authorization": f"Bearer {token}"},
    )
    return {
        r["package"]["name"].replace("linuxserver/", ""): r["total_installs"]
        for r in res["results"]
        if "total_installs" in r
    }


def fetch_docker_hub_pulls(
    http: httpx2.Client, names: list[str], previous: dict[str, int]
) -> tuple[dict[str, int], list[str]]:
    """
    Lifetime pull counts, one request per image (anonymous listing only pages 100 deep), four at a time.
    Images that fail keep their previous count and are returned, sorted, as the second value.
    """

    def pull_count(name: str) -> int | None:
        try:
            count: int = request_json(http, "GET", f"https://hub.docker.com/v2/repositories/linuxserver/{name}/")[
                "pull_count"
            ]
            return count
        except Exception:  # anything (an odd body as much as a failed request) costs only this image
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        counts = dict(zip(names, pool.map(pull_count, names), strict=True))
    failed = sorted(name for name, count in counts.items() if count is None)
    pulls = {name: count if count is not None else previous.get(name) for name, count in counts.items()}
    return {name: count for name, count in pulls.items() if count is not None}, failed
