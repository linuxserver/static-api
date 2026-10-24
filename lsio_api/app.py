"""
The API as a FastAPI app, like the original: every endpoint is a route with a Pydantic response model,
and the OpenAPI spec is generated from them. The static build requests every route and writes the
responses to files; the same app also runs as a live server for development (python -m lsio_api.serve).
"""

from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Path
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import responses
from .config import PUBLIC_DIR, SiteConfig
from .feed import changelog_feed
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
from .responses import Model
from .site import render_index

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


def create_app(model: Model, config: SiteConfig) -> FastAPI:
    app = FastAPI(
        title="LinuxServer API",
        version="1.1",
        summary="Metadata for every LinuxServer.io container image.",
        description=DESCRIPTION,
        servers=[{"url": config.api_root}],
        openapi_tags=TAGS,
        contact={"name": "LinuxServer.io", "url": "https://www.linuxserver.io/support/"},
        license_info={"name": "GPL-3.0", "url": "https://www.gnu.org/licenses/gpl-3.0.html"},
        docs_url=None,
        redoc_url=None,
    )
    images = {image.name: image for image in model.images}

    def find(name: str) -> ImageDetail:
        if name not in images:
            raise HTTPException(status_code=404, detail="Not found")
        return images[name]

    # ------------------------------------------------------------------------------------- Images

    @app.get(
        "/api/v1/catalog/{name}.json",
        tags=["Images"],
        operation_id="getImage",
        summary="Get one image",
        responses=NOT_FOUND,
        response_model_exclude_none=True,
    )
    def get_image(name: ImageName) -> ImageResponse:
        """
        Everything about one image, deprecated images included: the full changelog, container
        configuration, setup instructions, Docker Hub pulls and generated `docker run` and compose snippets.
        """
        return ImageResponse(last_updated=model.last_updated, data=ImageData(image=find(name)))

    @app.get(
        "/api/v1/catalog/{name}/docker-compose.yml",
        tags=["Images"],
        operation_id="getImageCompose",
        summary="Get a compose file for one image",
        response_class=YamlResponse,
        responses={200: {"content": {"application/yaml": {"schema": {"type": "string"}}}}, **NOT_FOUND},
    )
    def get_image_compose(name: ImageName) -> str:
        """
        A Docker Compose file with the image's recommended settings, optional ones marked `# optional`.
        The same text is in `snippets.docker_compose` of the image.
        """
        return find(name).snippets.docker_compose

    @app.get(
        "/api/v1/catalog.json",
        tags=["Images"],
        operation_id="getCatalog",
        summary="Get every image in full",
        response_model_exclude_none=True,
    )
    def get_catalog() -> CatalogResponse:
        """
        Every image, deprecated ones included, with the same detail as `/api/v1/catalog/{name}.json`.
        One request for everything; use the smaller list endpoints when you only need a summary.
        """
        return CatalogResponse(last_updated=model.last_updated, data=CatalogData(images=model.images))

    # ------------------------------------------------------------------------------------- Fleet

    @app.get(
        "/api/v1/categories.json",
        tags=["Fleet"],
        operation_id="getCategories",
        summary="Get image categories",
        response_model_exclude_none=True,
    )
    def get_categories() -> CategoriesResponse:
        """Categories of the current (not deprecated) images, most populated first."""
        return CategoriesResponse(
            last_updated=model.last_updated, data=CategoriesData(categories=responses.categories(model))
        )

    @app.get(
        "/api/v1/stats.json",
        tags=["Fleet"],
        operation_id="getStats",
        summary="Get fleet statistics",
        response_model_exclude_none=True,
    )
    def get_stats() -> StatsResponse:
        """Headline numbers across the current (not deprecated) images."""
        return StatsResponse(last_updated=model.last_updated, data=StatsData(stats=responses.stats(model)))

    @app.get(
        "/api/v1/changelog.json",
        tags=["Fleet"],
        operation_id="getChangelog",
        summary="Get recent changelog entries",
        response_model_exclude_none=True,
    )
    def get_changelog() -> ChangelogResponse:
        """
        The 100 most recent changelog entries across the current images, newest first. These are the
        notable changes to an image (new base, new variables, breaking changes), not every rebuild.
        """
        return ChangelogResponse(
            last_updated=model.last_updated, data=ChangelogData(changelog=responses.recent_changelog(model))
        )

    @app.get(
        "/api/v1/changelog.xml",
        tags=["Fleet"],
        operation_id="getChangelogFeed",
        summary="Subscribe to changelog entries",
        response_class=AtomResponse,
        responses={200: {"content": {"application/atom+xml": {"schema": {"type": "string"}}}}},
    )
    def get_changelog_feed() -> str:
        """The same entries as `/api/v1/changelog.json`, as an Atom feed."""
        return changelog_feed(
            responses.recent_changelog(model),
            model.images,
            self_url=f"{config.api_root}/api/v1/changelog.xml",
            site_url=config.site_root,
            updated=model.updated_at,
        )

    # ------------------------------------------------------------------------------------- Service

    @app.get(
        "/api/v1/status.json",
        tags=["Service"],
        operation_id="getStatus",
        summary="Get data freshness",
        response_model_exclude_none=True,
    )
    def get_status() -> StatusResponse:
        """
        The outcome of the last refresh of each data source. When a source fails, the previous data keeps
        being served, so check `fetched_at` to see how old it is.
        """
        return StatusResponse(last_updated=model.last_updated, data=StatusData(status=responses.status(model)))

    # ------------------------------------------------------------------------------------- Compatibility

    health_description = (
        '`"Success"` when the last GitHub refresh worked, `"Failed"` when it did not (the previous data is '
        "still served). A static host cannot change the status code, so this is always `200`; read the body."
    )

    @app.get(
        "/health",
        tags=["Compatibility"],
        operation_id="health_health_get",
        summary="Get the health status",
        description=health_description,
    )
    def health() -> Health:
        return model.health

    @app.get(
        "/health.json", tags=["Compatibility"], operation_id="getHealthJson", summary="Get the health status (JSON)"
    )
    def health_json() -> Health:
        """The same as `/health`, served as `application/json`."""
        return model.health

    @app.get(
        "/api/v1/images",
        tags=["Compatibility"],
        operation_id="images_api_v1_images_get",
        summary="Get a list of images",
        response_model_exclude_none=True,
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
        return responses.images_response(model)

    @app.get(
        "/api/v1/images.json",
        tags=["Compatibility"],
        operation_id="listImages",
        summary="List current images",
        response_model_exclude_none=True,
    )
    def images_json() -> ImagesResponse:
        """Current images without their configuration. The same as `/api/v1/images`."""
        return responses.images_response(model)

    @app.get(
        "/api/v1/images.config.json",
        tags=["Compatibility"],
        operation_id="listImagesWithConfig",
        summary="List current images with configuration",
        response_model_exclude_none=True,
    )
    def images_config() -> ImagesResponse:
        """The original `/api/v1/images?include_config=true`."""
        return responses.images_response(model, include_config=True)

    @app.get(
        "/api/v1/images.deprecated.json",
        tags=["Compatibility"],
        operation_id="listImagesWithDeprecated",
        summary="List all images, deprecated included",
        response_model_exclude_none=True,
    )
    def images_deprecated() -> ImagesResponse:
        """The original `/api/v1/images?include_deprecated=true`."""
        return responses.images_response(model, include_deprecated=True)

    @app.get(
        "/api/v1/images.config.deprecated.json",
        tags=["Compatibility"],
        operation_id="listImagesWithConfigAndDeprecated",
        summary="List all images with configuration",
        response_model_exclude_none=True,
    )
    def images_config_deprecated() -> ImagesResponse:
        """The original `/api/v1/images?include_config=true&include_deprecated=true`."""
        return responses.images_response(model, include_config=True, include_deprecated=True)

    # ------------------------------------------------------------------------------------- Docs

    @app.get("/", include_in_schema=False, response_class=HTMLResponse)
    def docs() -> str:
        return render_index(model, app.openapi(), config)

    app.mount("/", StaticFiles(directory=PUBLIC_DIR), name="public")
    return app
