"""
Every shape the API serves. The v1 models are those of linuxserver/docker-lsio-api (root/app/models.py),
field for field and in the same order, because names and key order are part of what clients see.
The OpenAPI spec is generated from these, so descriptions here are the API's documentation.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

V1_CHANGELOG_ENTRIES = 3
"""How many changelog entries the v1 list endpoints include, as the original does."""
CHANGELOG_LIMIT = 100
"""How many entries /api/v1/changelog.json lists."""

IsoDate = Annotated[str, Field(description="YYYY-MM-DD")]
LastUpdated = Annotated[
    str, Field(description="When the data was last refreshed, UTC, as `YYYY-MM-DD HH:MM:SS+00:00`.")
]

# ---------------------------------------------------------------------------------------------------
# v1, as the original API serves them


class Tag(BaseModel):
    tag: str = Field(examples=["latest"])
    desc: str


class Architecture(BaseModel):
    arch: str = Field(examples=["x86_64", "arm64"])
    tag: str = Field(description="The architecture-specific tag.", examples=["amd64-latest"])


class Changelog(BaseModel):
    date: IsoDate
    desc: str


class Volume(BaseModel):
    path: str = Field(description="Path inside the container.")
    host_path: str = Field(description="Example path on the host.")
    desc: str
    optional: bool


class Port(BaseModel):
    external: str
    internal: str = Field(description="Container port, with `/udp` when it is UDP.")
    desc: str
    optional: bool


class EnvVar(BaseModel):
    name: str
    value: str = Field(description="Example or default value.")
    desc: str
    optional: bool


class Custom(BaseModel):
    """Any other `docker run` flag, with its compose equivalent."""

    name: str = Field(description="The `docker run` flag without the leading `--`.", examples=["shm-size"])
    name_compose: str = Field(description="The compose key.", examples=["shm_size"])
    value: str | list[str]
    desc: str
    optional: bool


class SecurityOpt(BaseModel):
    run_var: str = Field(examples=["seccomp=unconfined"])
    compose_var: str = Field(examples=["seccomp:unconfined"])
    desc: str
    optional: bool


class Device(BaseModel):
    path: str
    host_path: str
    desc: str
    optional: bool


class Cap(BaseModel):
    cap_add: str = Field(examples=["NET_ADMIN"])
    desc: str
    optional: bool


class Hostname(BaseModel):
    hostname: str
    desc: str
    optional: bool


class MacAddress(BaseModel):
    mac_address: str
    desc: str
    optional: bool


class Config(BaseModel):
    """How to run the container. Each list holds required entries first, then optional ones."""

    application_setup: str | None = Field(None, description="Link to the Application Setup section of the README.")
    readonly_supported: bool | None = Field(None, description="Runs with a read-only root filesystem.")
    nonroot_supported: bool | None = Field(None, description="Runs as a non-root user.")
    privileged: bool | None = None
    networking: str | None = Field(None, description="Network mode, e.g. `host`.")
    hostname: Hostname | None = None
    mac_address: MacAddress | None = None
    env_vars: list[EnvVar] | None = None
    volumes: list[Volume] | None = None
    ports: list[Port] | None = None
    custom: list[Custom] | None = None
    security_opt: list[SecurityOpt] | None = None
    devices: list[Device] | None = None
    caps: list[Cap] | None = None


class Image(BaseModel):
    name: str = Field(examples=["sonarr"])
    initial_date: str | None = Field(None, description="Date of the image's first changelog entry.")
    github_url: str
    project_url: str | None = Field(None, description="The upstream project's website.")
    project_logo: str | None = Field(None, description="URL of the logo. Empty for a few images that have none.")
    description: str = Field(description="Markdown; may contain links.")
    version: str = Field(description="The latest stable release tag, or `latest` when there is none.")
    version_timestamp: str = Field(description="UTC, as `YYYY-MM-DD HH:MM:SS+00:00`.")
    category: str = Field(
        description="Comma-separated categories, verbatim from the image (may contain stray spaces).",
        examples=["Network,DNS"],
    )
    stable: bool = Field(description="Whether the image publishes a `latest` tag.")
    deprecated: bool
    stars: int = Field(description="GitHub stars of the image repository.")
    monthly_pulls: int | None = Field(None, description="Pulls in the last 30 days, from Scarf.")
    tags: list[Tag]
    architectures: list[Architecture]
    changelog: list[Changelog] | None = Field(
        None,
        description=f"The most recent entries; {V1_CHANGELOG_ENTRIES} in list responses, all in `ImageDetail`.",
    )
    config: Config | None = None


class Repository(BaseModel):
    linuxserver: list[Image]


class ImagesData(BaseModel):
    repositories: Repository


class ImagesResponse(BaseModel):
    status: str
    last_updated: LastUpdated
    data: ImagesData


Health = Literal["Success", "Failed"]

# ---------------------------------------------------------------------------------------------------
# Added by this API


class Registries(BaseModel):
    """Where the image is published."""

    lscr: str = Field(examples=["lscr.io/linuxserver/sonarr"])
    ghcr: str = Field(examples=["ghcr.io/linuxserver/sonarr"])
    docker_hub: str = Field(examples=["docker.io/linuxserver/sonarr"])


class Snippets(BaseModel):
    """Ready-to-use commands with every parameter, optional ones marked."""

    docker_compose: str
    docker_run: str


class ImageDetail(Image):
    """An image with everything this API knows about it."""

    config: Config  # always present
    categories: list[str] = Field(description="`category`, split and trimmed.")
    deprecation_message: str | None = Field(None, description="Why the image is deprecated, when it is.")
    setup_instructions: str | None = Field(None, description="The README's Application Setup section, as Markdown.")
    archived: bool = Field(description="Whether the GitHub repository is archived.")
    release_url: str | None = Field(None, description="The GitHub release for `version`.")
    docker_hub_pulls: int | None = Field(
        None, description="Lifetime pulls from Docker Hub (other registries are not counted)."
    )
    docs_url: str
    registries: Registries
    snippets: Snippets


class Category(BaseModel):
    name: str = Field(examples=["Media Servers"])
    slug: str = Field(examples=["media-servers"])
    count: int
    images: list[str] = Field(description="Image names, alphabetical.")


class Stats(BaseModel):
    images: int = Field(description="Current images.")
    deprecated: int = Field(description="Deprecated images (not counted anywhere else).")
    monthly_pulls: int = Field(description="Sum of `monthly_pulls`.")
    docker_hub_pulls: int = Field(
        description="Sum of `docker_hub_pulls`. A lower bound; other registries are not counted."
    )
    stars: int
    architectures: dict[str, int] = Field(description="Images available for each architecture.")
    readonly_supported: int
    nonroot_supported: int
    updated_last_7_days: int = Field(description="Images with a release in the 7 days before `last_updated`.")
    categories: int
    first_release: str | None = Field(None, description="The oldest `initial_date`.")


class ChangelogEntry(BaseModel):
    image: str
    date: IsoDate
    desc: str


class SourceStatus(BaseModel):
    ok: bool
    checked_at: str = Field(description="When the last refresh tried this source (ISO 8601).")
    fetched_at: str | None = Field(None, description="When this source last returned data (ISO 8601).")
    error: str | None = Field(None, description="Why the last attempt failed, or what it could not fetch.")


class Status(BaseModel):
    health: Health
    images: int
    deprecated: int
    sources: dict[str, SourceStatus] = Field(
        description="`github` (images, versions, stars), `scarf` (monthly pulls), `dockerhub` (lifetime pulls)."
    )


# Every new response has the same envelope as ImagesResponse.


class Envelope(BaseModel):
    status: Literal["OK"] = "OK"
    last_updated: LastUpdated


class ImageData(BaseModel):
    image: ImageDetail


class ImageResponse(Envelope):
    data: ImageData


class CatalogData(BaseModel):
    images: list[ImageDetail]


class CatalogResponse(Envelope):
    data: CatalogData


class CategoriesData(BaseModel):
    categories: list[Category]


class CategoriesResponse(Envelope):
    data: CategoriesData


class StatsData(BaseModel):
    stats: Stats


class StatsResponse(Envelope):
    data: StatsData


class ChangelogData(BaseModel):
    changelog: list[ChangelogEntry] = Field(max_length=CHANGELOG_LIMIT)


class ChangelogResponse(Envelope):
    data: ChangelogData


class StatusData(BaseModel):
    status: Status


class StatusResponse(Envelope):
    data: StatusData
