"""
Every image repository in the linuxserver org, with its stars, latest release and readme-vars.yml.

The Python updater makes one REST call per repository for releases and up to four for readme-vars;
GraphQL gets the same data for the whole org in a handful of requests. `latestRelease` is GitHub's
"most recent non-prerelease, non-draft release", which is what iterating the release list and skipping
prereleases finds.
"""

from typing import Any

import httpx2

from ..snapshot import Release, RepoSnapshot, is_image_repo
from .http import request_json

ORG = "linuxserver"

README_VARS_BRANCHES = ("master", "main", "develop", "nightly")
"""Where readme-vars.yml is looked for, in order."""

_BLOBS = "\n".join(
    f'{branch}: object(expression: "{branch}:readme-vars.yml") {{ ... on Blob {{ text }} }}'
    for branch in README_VARS_BRANCHES
)

QUERY = f"""
query ($org: String!, $cursor: String) {{
  organization(login: $org) {{
    repositories(first: 50, after: $cursor, orderBy: {{ field: NAME, direction: ASC }}) {{
      pageInfo {{ hasNextPage endCursor }}
      nodes {{
        name url stargazerCount pushedAt isArchived
        latestRelease {{ tagName publishedAt url }}
        {_BLOBS}
      }}
    }}
  }}
}}"""


def to_repo_snapshot(node: dict[str, Any]) -> RepoSnapshot:
    release = node.get("latestRelease")
    texts = ((node.get(branch) or {}).get("text") for branch in README_VARS_BRANCHES)
    return RepoSnapshot(
        name=node["name"],
        url=node["url"],
        stars=node["stargazerCount"],
        pushed_at=node.get("pushedAt"),
        archived=node["isArchived"],
        latest_release=(
            Release(tag=release["tagName"], published_at=release["publishedAt"], url=release["url"])
            if release and release.get("publishedAt")
            else None
        ),
        readme_vars=next((text for text in texts if text), None),
    )


def fetch_repos(http: httpx2.Client, token: str) -> list[RepoSnapshot]:
    repos: list[RepoSnapshot] = []
    cursor = None
    while True:
        res = request_json(
            http,
            "POST",
            "https://api.github.com/graphql",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": QUERY, "variables": {"org": ORG, "cursor": cursor}},
        )
        if res.get("errors"):
            raise RuntimeError("GitHub GraphQL: " + "; ".join(e["message"] for e in res["errors"]))
        page = ((res.get("data") or {}).get("organization") or {}).get("repositories")
        if not page:
            raise RuntimeError(f"GitHub GraphQL: organization {ORG} not found")
        repos += [to_repo_snapshot(node) for node in page["nodes"] if is_image_repo(node["name"])]
        if not page["pageInfo"]["hasNextPage"]:
            return repos
        cursor = page["pageInfo"]["endCursor"]
