"""
The API as a FastAPI app, like the original: every endpoint is a route with a Pydantic response model,
and the OpenAPI spec is generated from them. The static build requests every route and writes the
responses to files; the same app also runs as a live server for development (python -m lsio_api.serve).
"""

import json
from functools import partial
from typing import Annotated, Any

import yaml
from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import responses
from .config import PUBLIC_DIR, SiteConfig
from .feed import changelog_feed
from .fleet import Fleet
from .models import (
    CatalogData,
    CatalogResponse,
    CategoriesData,
    CategoriesResponse,
    ChangelogData,
    ChangelogResponse,
    Health,
    ImageData,
    ImageDetail,
    ImageResponse,
    ImagesResponse,
    StatsData,
    StatsResponse,
    StatusData,
    StatusResponse,
)
from .site import render_index, render_not_found

DESCRIPTION = """
Everything we know about the LinuxServer.io images: versions, tags, architectures, changelogs,
container parameters, pull counts and ready-to-use compose snippets.

The API is a set of static files, rebuilt daily from each image's `readme-vars.yml`, GitHub releases,
Scarf and Docker Hub. Every endpoint is a plain `GET` with no authentication and no rate limit beyond the
host's. Fields that have no value are omitted rather than `null`.

**Query parameters are not supported.** The original API's `include_config` and `include_deprecated`
switches are separate files instead; see the Compatibility endpoints.
"""

TAGS = [
    {"name": "Images", "description": "Every image, or one image in full."},
    {"name": "Fleet", "description": "Numbers, categories and changes across all images."},
    {"name": "Service", "description": "Whether the data is fresh."},
    {
        "name": "Compatibility",
        "description": "The original api.linuxserver.io endpoints, same paths and same response shapes. The "
        "extensionless paths are served as `application/octet-stream` by some static hosts; the `.json` "
        "equivalents are identical and served as `application/json`.",
    },
]


class YamlResponse(PlainTextResponse):
    media_type = "application/yaml"


class AtomResponse(PlainTextResponse):
    media_type = "application/atom+xml"


ImageName = Annotated[
    str,
    Path(description="The image name, as in `lscr.io/linuxserver/<name>`.", examples=["sonarr"]),
]

NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"description": "There is no image with that name."}}


def create_app(fleet: Fleet, config: SiteConfig) -> FastAPI:
    app = FastAPI(
        title="LinuxServer API",
        version="1.1",
        summary="Metadata for every LinuxServer.io container image.",
        description=DESCRIPTION,
        servers=[{"url": config.api_root}],
        openapi_tags=TAGS,
        contact={"name": "LinuxServer.io", "url": "https://www.linuxserver.io/support/"},
        license_info={"name": "GPL-3.0", "url": "https://www.gnu.org/licenses/gpl-3.0.html"},
        openapi_url=None,  # served below, as the build writes it
        docs_url=None,
        redoc_url=None,
    )
    # Fields without a value are omitted, as in the original, on every route.
    get = partial(app.get, response_model_exclude_none=True)
    images = {image.name: image for image in fleet.images}

    def find(name: str) -> ImageDetail:
        if name not in images:
            raise HTTPException(status_code=404)
        return images[name]

    # ------------------------------------------------------------------------------------- Images

    @get(
        "/api/v1/catalog/{name}.json",
        tags=["Images"],
        operation_id="getImage",
        summary="Get one image",
        responses=NOT_FOUND,
    )
    def get_image(name: ImageName) -> ImageResponse:
        """
        Everything about one image, deprecated images included: the full changelog, container
        configuration, setup instructions, Docker Hub pulls and generated `docker run` and compose snippets.
        """
        return ImageResponse(last_updated=fleet.last_updated, data=ImageData(image=find(name)))

    @get(
        "/api/v1/catalog/{name}/docker-compose.yml",
        tags=["Images"],
        operation_id="getImageCompose",
        summary="Get a compose file for one image",
        response_class=YamlResponse,
        responses=NOT_FOUND,
    )
    def get_image_compose(name: ImageName) -> str:
        """
        A Docker Compose file with the image's recommended settings, optional ones marked `# optional`.
        The same text is in `snippets.docker_compose` of the image.
        """
        return find(name).snippets.docker_compose

    @get("/api/v1/catalog.json", tags=["Images"], operation_id="getCatalog", summary="Get every image in full")
    def get_catalog() -> CatalogResponse:
        """
        Every image, deprecated ones included, with the same detail as `/api/v1/catalog/{name}.json`.
        One request for everything; use the smaller list endpoints when you only need a summary.
        """
        return CatalogResponse(last_updated=fleet.last_updated, data=CatalogData(images=fleet.images))

    # ------------------------------------------------------------------------------------- Fleet

    @get("/api/v1/categories.json", tags=["Fleet"], operation_id="getCategories", summary="Get image categories")
    def get_categories() -> CategoriesResponse:
        """Categories of the current (not deprecated) images, most populated first."""
        categories = responses.categories(fleet)
        return CategoriesResponse(last_updated=fleet.last_updated, data=CategoriesData(categories=categories))

    @get("/api/v1/stats.json", tags=["Fleet"], operation_id="getStats", summary="Get fleet statistics")
    def get_stats() -> StatsResponse:
        """Headline numbers across the current (not deprecated) images."""
        return StatsResponse(last_updated=fleet.last_updated, data=StatsData(stats=responses.stats(fleet)))

    @get("/api/v1/changelog.json", tags=["Fleet"], operation_id="getChangelog", summary="Get recent changelog entries")
    def get_changelog() -> ChangelogResponse:
        """
        The 100 most recent changelog entries across the current images, newest first. These are the
        notable changes to an image (new base, new variables, breaking changes), not every rebuild.
        """
        changelog = responses.recent_changelog(fleet)
        return ChangelogResponse(last_updated=fleet.last_updated, data=ChangelogData(changelog=changelog))

    @get(
        "/api/v1/changelog.xml",
        tags=["Fleet"],
        operation_id="getChangelogFeed",
        summary="Subscribe to changelog entries",
        response_class=AtomResponse,
    )
    def get_changelog_feed() -> str:
        """The same entries as `/api/v1/changelog.json`, as an Atom feed."""
        return changelog_feed(fleet, config)

    # ------------------------------------------------------------------------------------- Service

    @get("/api/v1/status.json", tags=["Service"], operation_id="getStatus", summary="Get data freshness")
    def get_status() -> StatusResponse:
        """
        The outcome of the last refresh of each data source. When a source fails, the previous data keeps
        being served, so check `fetched_at` to see how old it is.
        """
        return StatusResponse(last_updated=fleet.last_updated, data=StatusData(status=responses.status(fleet)))

    # ------------------------------------------------------------------------------------- Compatibility

    @get(
        "/health.json",
        tags=["Compatibility"],
        operation_id="getHealthJson",
        summary="Get the health status (JSON)",
        description="The same as `/health`, served as `application/json`.",
    )
    @get("/health", tags=["Compatibility"], operation_id="health_health_get", summary="Get the health status")
    def health() -> Health:
        """
        `"Success"` when the last GitHub refresh worked, `"Failed"` when it did not (the previous data is
        still served). A static host cannot change the status code, so this is always `200`; read the body.
        """
        return fleet.health

    @get(
        "/api/v1/images.json",
        tags=["Compatibility"],
        operation_id="listImages",
        summary="List current images",
        description="Current images without their configuration. The same as `/api/v1/images`.",
    )
    @get(
        "/api/v1/images",
        tags=["Compatibility"],
        operation_id="images_api_v1_images_get",
        summary="Get a list of images",
    )
    def images_list() -> ImagesResponse:
        """
        Current images without their configuration: the original endpoint with its default parameters.
        Query parameters are ignored by static hosts; use the files below for the other combinations.

        | Original | File |
        | --- | --- |
        | `/api/v1/images` | `/api/v1/images.json` |
        | `?include_config=true` | `/api/v1/images.config.json` |
        | `?include_deprecated=true` | `/api/v1/images.deprecated.json` |
        | `?include_config=true&include_deprecated=true` | `/api/v1/images.config.deprecated.json` |
        """
        return responses.images_response(fleet)

    @get(
        "/api/v1/images.config.json",
        tags=["Compatibility"],
        operation_id="listImagesWithConfig",
        summary="List current images with configuration",
    )
    def images_config() -> ImagesResponse:
        """The original `/api/v1/images?include_config=true`."""
        return responses.images_response(fleet, include_config=True)

    @get(
        "/api/v1/images.deprecated.json",
        tags=["Compatibility"],
        operation_id="listImagesWithDeprecated",
        summary="List all images, deprecated included",
    )
    def images_deprecated() -> ImagesResponse:
        """The original `/api/v1/images?include_deprecated=true`."""
        return responses.images_response(fleet, include_deprecated=True)

    @get(
        "/api/v1/images.config.deprecated.json",
        tags=["Compatibility"],
        operation_id="listImagesWithConfigAndDeprecated",
        summary="List all images with configuration",
    )
    def images_config_deprecated() -> ImagesResponse:
        """The original `/api/v1/images?include_config=true&include_deprecated=true`."""
        return responses.images_response(fleet, include_config=True, include_deprecated=True)

    # ------------------------------------------------------------------------------------- Spec and docs

    @app.get("/openapi.json", include_in_schema=False)
    def openapi_json() -> Response:
        return Response(json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n", media_type="application/json")

    @app.get("/openapi.yaml", include_in_schema=False, response_class=YamlResponse)
    def openapi_yaml() -> str:
        return yaml.dump(
            app.openapi(),
            Dumper=getattr(yaml, "CSafeDumper", yaml.SafeDumper),
            sort_keys=False,
            allow_unicode=True,
            width=1000,
        )

    @app.get("/", include_in_schema=False, response_class=HTMLResponse)
    def docs() -> str:
        return render_index(fleet, app.openapi(), config)

    @app.exception_handler(StarletteHTTPException)
    def not_found(request: Request, exc: StarletteHTTPException) -> Response:
        # Static hosts answer every missing file with 404.html, so the app does too.
        return HTMLResponse(render_not_found(fleet, config), status_code=exc.status_code)

    app.mount("/", StaticFiles(directory=PUBLIC_DIR), name="public")
    return app
