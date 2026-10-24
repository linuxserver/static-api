# LinuxServer API, static

The [LinuxServer.io API](https://github.com/linuxserver/docker-lsio-api) rebuilt as a static site: every
endpoint is a plain file, regenerated daily by GitHub Actions from the same sources, with an OpenAPI spec
and a docs page in the design of [www.linuxserver.io](https://linuxserver.github.io/site/). There is no
server, database or container to run in production.

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
GITHUB_TOKEN=$(gh auth token) python -m lsio_api.refresh   # data/ from GitHub, Scarf (SCARF_TOKEN) and Docker Hub
python -m lsio_api.build                                   # dist/
python -m lsio_api.serve                                   # the same app, live, on http://localhost:8000/
ruff check . && ruff format --check . && mypy lsio_api tests && pytest
```

## Endpoints

The original API's endpoints are served at the same paths with byte-for-byte the same JSON (the parity
tests check this against real responses). Its query parameters become files, because a static host
ignores query strings:

| Original                                                     | Here                                                       |
| ------------------------------------------------------------ | ---------------------------------------------------------- |
| `/health`                                                    | `/health` (also `/health.json`)                            |
| `/api/v1/images`                                             | `/api/v1/images` (also `/api/v1/images.json`)              |
| `/api/v1/images?include_config=true`                         | `/api/v1/images.config.json`                               |
| `/api/v1/images?include_deprecated=true`                     | `/api/v1/images.deprecated.json`                           |
| `/api/v1/images?include_config=true&include_deprecated=true` | `/api/v1/images.config.deprecated.json`                    |
| `/` (Swagger UI), `/openapi.json`                            | `/` (docs with "Try it"), `/openapi.json`, `/openapi.yaml` |

Added:

| Path                                        | What                                                                                                                                                                       |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/api/v1/catalog/{name}.json`               | One image in full: whole changelog, config, setup instructions, deprecation message, Docker Hub pulls, registries, docs link and generated `docker run` / compose snippets |
| `/api/v1/catalog/{name}/docker-compose.yml` | A ready-to-use compose file                                                                                                                                                |
| `/api/v1/catalog.json`                      | Every image in full, in one request                                                                                                                                        |
| `/api/v1/categories.json`                   | Categories with their images                                                                                                                                               |
| `/api/v1/stats.json`                        | Fleet totals: images, pulls, stars, architectures, rootless/read-only support, recent releases                                                                             |
| `/api/v1/changelog.json`, `.xml`            | The 100 latest changelog entries across all images, as JSON and an Atom feed                                                                                               |
| `/api/v1/status.json`                       | When each source last refreshed, and whether it worked                                                                                                                     |

The per-image files live under `catalog/` because `/api/v1/images` has to stay a file for compatibility
and so can't also be a directory.

### Differences from the original

- `/health` can't return a 500 from a static host, so it is always `200`; read the body (`"Success"` or `"Failed"`).
- A `readme-vars.yml` that fails to parse skips that one image (with a warning in the log) instead of
  failing the whole update; changelog entries with impossible dates are skipped the same way.
- Static hosts serve the extensionless compatibility paths as `application/octet-stream`. Clients that
  parse the body as JSON are unaffected; the `.json` twins are served as `application/json`.

## How it works

It is the original API's design: a FastAPI app whose routes return Pydantic models, with the OpenAPI spec
generated from them. Instead of serving it, the build requests every route through FastAPI's test client
and writes each response to a file.

```
GitHub (GraphQL) ─┐                                     ┌─ dist/api/v1/…  (JSON, YAML, Atom)
Scarf ────────────┼─ refresh ─> data/*.json ─ build ─────┼─ dist/openapi.{json,yaml}
Docker Hub ───────┘  (committed daily)    (FastAPI app)  └─ dist/index.html, 404.html
```

| Module | |
| --- | --- |
| `lsio_api/models.py` | Every response shape. The v1 models are the original's, field for field; field descriptions are the spec's documentation. |
| `lsio_api/transform.py` | `updater.py`'s `get_*` functions: readme-vars.yml and GitHub data to an image. The parity tests compare its output with real API responses. |
| `lsio_api/app.py` | The FastAPI app: one route per endpoint. |
| `lsio_api/build.py` | Requests every route (its paths come from the app, so nothing is missed) and writes `dist/`. A response that doesn't fit its model fails the build. |
| `lsio_api/refresh.py`, `sources/` | Fetches each source. One that fails keeps its previous data and the error is recorded in `data/status.json`, as the Python updater did, so the API keeps serving and `/health` reports `Failed`. GitHub's data comes from about seven GraphQL requests rather than several REST calls per repository. |
| `lsio_api/site.py`, `templates/` | The docs page, rendered from the generated spec with Jinja. Styles in `public/assets/` are the site's Raft tokens in plain CSS. |

`data/` holds raw source data rather than finished responses, so changing how a field is derived needs no
refetch, builds are deterministic and work offline, and the daily commit is a readable diff.

### Adding a field

1. Add it to the model in `lsio_api/models.py`, with a description. That also documents it.
2. Derive it in `lsio_api/transform.py` (or `lsio_api/responses.py` for fleet-wide data).
3. Test it. If it comes from `readme-vars.yml`, add a case to `tests/test_transform.py`.

Fields in the v1 list endpoints must stay exactly as the original API has them; add new ones to
`ImageDetail` (the catalog) instead.

## Deploying

`.github/workflows/deploy.yml` refreshes data daily at 04:23 UTC, commits it, builds and deploys to
GitHub Pages. It also deploys on every push to `main` (with the committed data) and on demand.

1. In the repository settings, set Pages to deploy from GitHub Actions.
2. Add a `SCARF_TOKEN` secret for monthly pull counts. Without it everything else still works, and
   `status.json` shows Scarf as failing.
3. The data commit is pushed to `main` by `github-actions[bot]`, so branch protection must allow that.
4. For a custom domain such as `api.linuxserver.io`, set it in the Pages settings. The build takes the
   URL and base path from `actions/configure-pages`, so links and the spec's `servers` entry follow.

To refresh more often, change the cron. GitHub GraphQL and Docker Hub would both cope with hourly runs,
but every run that changes data adds a commit.

The `node` branch has the same API built with TypeScript; it is kept for reference and is not deployed.
