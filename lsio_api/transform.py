"""
Turns one repository's snapshot into an API image. A port of updater.py (get_image and its get_*
helpers) in linuxserver/docker-lsio-api, kept deliberately close so the output matches. The differences:
bad data skips the one field or image instead of failing the whole update, values are coerced to the
types the models expect, and this also produces the extra fields ImageDetail adds.
"""

import datetime
import logging
from collections.abc import Callable, Iterable
from typing import Any

from .models import (
    Architecture,
    Cap,
    Changelog,
    Config,
    Custom,
    Device,
    EnvVar,
    Hostname,
    ImageDetail,
    MacAddress,
    Port,
    Registries,
    SecurityOpt,
    Snippets,
    Tag,
    Volume,
)
from .readme_vars import ReadmeVars, api_substitutions, parse_readme_vars, readme_substitutions
from .snapshot import RepoSnapshot, is_image_repo
from .snippets import REGISTRY, docker_compose, docker_run

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------------
# Reading loosely typed YAML values the way Pydantic's lax mode would.


def _str(value: Any) -> str:
    return "" if value is None else str(value)


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.lower() in ("true", "yes", "on", "1", "y", "t")
    return bool(value)


def _items(readme_vars: ReadmeVars, key: str) -> list[dict[str, Any]]:
    """The list under `key`, keeping only mapping entries."""
    value = readme_vars.get(key)
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def _paired[T](
    readme_vars: ReadmeVars, key: str, opt_key: str, make: Callable[[dict[str, Any], bool], T]
) -> list[T] | None:
    """Required entries from `key`, then optional ones from `opt_key`; None when there are none."""
    result = [make(x, False) for x in _items(readme_vars, key)] + [make(x, True) for x in _items(readme_vars, opt_key)]
    return result or None


# ---------------------------------------------------------------------------------------------------
# Dates


def python_timestamp(iso: str | None) -> str:
    """ "2026-10-24T11:25:58.123Z" -> "2026-10-24 11:25:58+00:00", as the original API formats times."""
    if not iso:
        return ""
    try:
        parsed = datetime.datetime.fromisoformat(iso)
    except ValueError:
        return ""
    return str(parsed.astimezone(datetime.UTC).replace(microsecond=0))


def changelog_date(raw: Any) -> str | None:
    """ "24.10.26:" -> "2026-10-24", or None if it isn't a real date."""
    try:
        return str(datetime.datetime.strptime(_str(raw).strip().removesuffix(":"), "%d.%m.%y").date())
    except ValueError:
        return None


# ---------------------------------------------------------------------------------------------------
# The get_* helpers from updater.py


def get_tags(readme_vars: ReadmeVars) -> tuple[list[Tag], bool]:
    if "development_versions_items" not in readme_vars:
        return [Tag(tag="latest", desc="Stable releases")], True
    tags = [
        Tag(tag=_str(x.get("tag")), desc=_str(x.get("desc"))) for x in _items(readme_vars, "development_versions_items")
    ]
    return tags, any(t.tag == "latest" for t in tags)


def get_architectures(readme_vars: ReadmeVars) -> list[Architecture]:
    if "available_architectures" not in readme_vars:
        return [Architecture(arch="x86_64", tag="amd64-latest")]
    return [
        Architecture(arch=_str(x.get("arch")), tag=_str(x.get("tag")))
        for x in _items(readme_vars, "available_architectures")
    ]


def get_changelog(readme_vars: ReadmeVars) -> tuple[list[Changelog] | None, str | None]:
    """Every entry with a valid date (newest first), and the date of the oldest one."""
    if "changelogs" not in readme_vars:
        return None, None
    changelog = []
    for x in _items(readme_vars, "changelogs"):
        if date := changelog_date(x.get("date")):
            changelog.append(Changelog(date=date, desc=_str(x.get("desc"))))
    return changelog, changelog[-1].date if changelog else None


def get_description(readme_vars: ReadmeVars) -> str:
    return _str(readme_vars.get("project_blurb", "No description")).replace("\n", " ").strip(" \t\n\r")


def get_env_vars(readme_vars: ReadmeVars) -> list[EnvVar] | None:
    env_vars = []
    if readme_vars.get("common_param_env_vars_enabled", False):
        env_vars = [
            EnvVar(name="PUID", value="1000", desc="User ID", optional=False),
            EnvVar(name="PGID", value="1000", desc="Group ID", optional=False),
            EnvVar(name="TZ", value="Etc/UTC", desc="Timezone", optional=False),
        ]
    own = _paired(
        readme_vars,
        "param_env_vars",
        "opt_param_env_vars",
        lambda x, optional: EnvVar(
            name=_str(x.get("env_var")), value=_str(x.get("env_value")), desc=_str(x.get("desc")), optional=optional
        ),
    )
    return (env_vars + (own or [])) or None


def get_volumes(readme_vars: ReadmeVars) -> list[Volume] | None:
    return _paired(
        readme_vars,
        "param_volumes",
        "opt_param_volumes",
        lambda x, optional: Volume(
            path=_str(x.get("vol_path")),
            host_path=_str(x.get("vol_host_path")),
            desc=_str(x.get("desc")),
            optional=optional,
        ),
    )


def get_ports(readme_vars: ReadmeVars) -> list[Port] | None:
    return _paired(
        readme_vars,
        "param_ports",
        "opt_param_ports",
        lambda x, optional: Port(
            external=_str(x.get("external_port")),
            internal=_str(x.get("internal_port")),
            desc=_str(x.get("port_desc")),
            optional=optional,
        ),
    )


def get_custom(readme_vars: ReadmeVars) -> list[Custom] | None:
    def make(x: dict[str, Any], optional: bool) -> Custom:
        value = x.get("value")
        return Custom(
            name=_str(x.get("name")),
            name_compose=_str(x.get("name_compose")),
            value=[_str(v) for v in value] if isinstance(value, list) else _str(value),
            desc=_str(x.get("desc")),
            optional=optional,
        )

    return _paired(readme_vars, "custom_params", "opt_custom_params", make)


def get_security_opt(readme_vars: ReadmeVars) -> list[SecurityOpt] | None:
    return _paired(
        readme_vars,
        "security_opt_param_vars",
        "opt_security_opt_param_vars",
        lambda x, optional: SecurityOpt(
            run_var=_str(x.get("run_var")),
            compose_var=_str(x.get("compose_var")),
            desc=_str(x.get("desc")),
            optional=optional,
        ),
    )


def get_devices(readme_vars: ReadmeVars) -> list[Device] | None:
    return _paired(
        readme_vars,
        "param_devices",
        "opt_param_devices",
        lambda x, optional: Device(
            path=_str(x.get("device_path")),
            host_path=_str(x.get("device_host_path")),
            desc=_str(x.get("desc")),
            optional=optional,
        ),
    )


def get_caps(readme_vars: ReadmeVars) -> list[Cap] | None:
    return _paired(
        readme_vars,
        "cap_add_param_vars",
        "opt_cap_add_param_vars",
        lambda x, optional: Cap(cap_add=_str(x.get("cap_add_var")), desc=_str(x.get("desc")), optional=optional),
    )


def get_hostname(readme_vars: ReadmeVars) -> Hostname | None:
    """`param_usage_include_hostname` is true (required) or "optional"."""
    include = readme_vars.get("param_usage_include_hostname", False)
    if not include:
        return None
    return Hostname(
        hostname=_str(readme_vars.get("param_hostname")),
        desc=_str(readme_vars.get("param_hostname_desc")),
        optional=include == "optional",
    )


def get_mac_address(readme_vars: ReadmeVars) -> MacAddress | None:
    include = readme_vars.get("param_usage_include_mac_address", False)
    if not include:
        return None
    return MacAddress(
        mac_address=_str(readme_vars.get("param_mac_address")),
        desc=_str(readme_vars.get("param_mac_address_desc")),
        optional=include == "optional",
    )


def get_setup_instructions(text: str, name: str, readme_vars: ReadmeVars) -> str | None:
    """
    The Application Setup section as Markdown, rendered the way the README renders it (with links to the
    project) rather than with the v1 substitutions, which drop them. A block only this rendering can't
    parse costs just this field, not the image.
    """
    if not readme_vars.get("app_setup_block_enabled", False):
        return None
    try:
        readme = parse_readme_vars(text, readme_substitutions(name, _str(readme_vars.get("project_url"))))
    except Exception as e:
        log.warning("  ! %s: setup instructions skipped: %s", name, e)
        return None
    return _str((readme or {}).get("app_setup_block")).strip() or None


def get_config(readme_vars: ReadmeVars, github_url: str) -> Config:
    application_setup = None
    if readme_vars.get("app_setup_block_enabled", False):
        application_setup = f"{github_url}?tab=readme-ov-file#application-setup"
    return Config(
        application_setup=application_setup,
        readonly_supported=_optional_bool(readme_vars.get("readonly_supported")),
        nonroot_supported=_optional_bool(readme_vars.get("nonroot_supported")),
        privileged=_optional_bool(readme_vars.get("privileged")),
        networking=_optional_str(readme_vars.get("param_net")),
        hostname=get_hostname(readme_vars),
        mac_address=get_mac_address(readme_vars),
        env_vars=get_env_vars(readme_vars),
        volumes=get_volumes(readme_vars),
        ports=get_ports(readme_vars),
        custom=get_custom(readme_vars),
        security_opt=get_security_opt(readme_vars),
        devices=get_devices(readme_vars),
        caps=get_caps(readme_vars),
    )


def split_categories(category: str) -> list[str]:
    """ "Network,DNS" -> ["Network", "DNS"]"""
    return [c.strip() for c in category.split(",") if c.strip()]


# ---------------------------------------------------------------------------------------------------
# Images


def listed_image(repo: RepoSnapshot) -> tuple[str, str, ReadmeVars] | None:
    """
    The image name, readme-vars text and parsed readme-vars for a repository, or None when it isn't one
    we list: not an image repo, no readme-vars.yml, or categorised Internal. Raises on invalid YAML.
    """
    if not is_image_repo(repo.name) or not repo.readme_vars:
        return None
    name = repo.name.replace("docker-", "")
    readme_vars = parse_readme_vars(repo.readme_vars, api_substitutions(name))
    if not readme_vars or "Internal" in _str(readme_vars.get("project_categories", "")):
        return None
    return name, repo.readme_vars, readme_vars


def build_image(repo: RepoSnapshot, monthly_pulls: dict[str, int], hub_pulls: dict[str, int]) -> ImageDetail | None:
    listed = listed_image(repo)
    if not listed:
        return None
    name, text, readme_vars = listed
    category = _str(readme_vars.get("project_categories", ""))
    tags, stable = get_tags(readme_vars)
    changelog, initial_date = get_changelog(readme_vars)
    release = repo.latest_release
    config = get_config(readme_vars, repo.url)
    deprecated = _optional_bool(readme_vars.get("project_deprecation_status")) or False
    return ImageDetail(
        name=name,
        initial_date=initial_date,
        github_url=repo.url,
        project_url=_optional_str(readme_vars.get("project_url")),
        project_logo=_optional_str(readme_vars.get("project_logo")),
        description=get_description(readme_vars),
        version=release.tag if release else "latest",
        version_timestamp=python_timestamp(release.published_at if release else repo.pushed_at),
        category=category,
        stable=stable,
        deprecated=deprecated,
        stars=repo.stars,
        monthly_pulls=monthly_pulls.get(name),
        tags=tags,
        architectures=get_architectures(readme_vars),
        changelog=changelog,
        config=config,
        categories=split_categories(category),
        deprecation_message=_optional_str(readme_vars.get("project_deprecation_message")) if deprecated else None,
        setup_instructions=get_setup_instructions(text, name, readme_vars),
        archived=repo.archived,
        release_url=release.url if release else None,
        docker_hub_pulls=hub_pulls.get(name),
        docs_url=f"https://docs.linuxserver.io/images/{repo.name}/",
        registries=Registries(
            lscr=f"{REGISTRY}/{name}", ghcr=f"ghcr.io/linuxserver/{name}", docker_hub=f"docker.io/linuxserver/{name}"
        ),
        snippets=Snippets(docker_compose=docker_compose(name, config), docker_run=docker_run(name, config)),
    )


def _skipping_broken[T](repos: Iterable[RepoSnapshot], fn: Callable[[RepoSnapshot], T | None]) -> list[T]:
    """Runs `fn` for each repository. A broken readme-vars.yml skips that image rather than failing them all."""
    results = []
    for repo in repos:
        try:
            result = fn(repo)
        except Exception as e:
            log.warning("  ! skipped %s: %s", repo.name, e)
            continue
        if result is not None:
            results.append(result)
    return results


def build_images(
    repos: list[RepoSnapshot], monthly_pulls: dict[str, int], hub_pulls: dict[str, int]
) -> list[ImageDetail]:
    """Every listed image, sorted by repository name like the Python updater."""
    ordered = sorted(repos, key=lambda repo: repo.name)
    return _skipping_broken(ordered, lambda repo: build_image(repo, monthly_pulls, hub_pulls))


def listed_image_names(repos: list[RepoSnapshot]) -> list[str]:
    """The names build_images would list, without building the images."""
    return _skipping_broken(repos, lambda repo: listed[0] if (listed := listed_image(repo)) else None)
