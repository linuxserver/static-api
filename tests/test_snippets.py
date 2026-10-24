import yaml

from lsio_api.fleet import Fleet
from lsio_api.models import Cap, Config, Custom, Device, EnvVar, Hostname, Port, Volume
from lsio_api.snippets import docker_compose, docker_run

CONFIG = Config(
    hostname=Hostname(hostname="my host", desc="", optional=True),
    caps=[Cap(cap_add="NET_ADMIN", desc="", optional=False)],
    env_vars=[
        EnvVar(name="PUID", value="1000", desc="", optional=False),
        EnvVar(name="EXTRA", value="", desc="", optional=True),
    ],
    volumes=[Volume(path="/config", host_path="/path/to/config", desc="", optional=False)],
    ports=[Port(external="51820", internal="51820/udp", desc="", optional=False)],
    custom=[
        Custom(name="shm-size", name_compose="shm_size", value="1gb", desc="", optional=False),
        Custom(name="sysctl", name_compose="sysctls", value=["a=1", "b=2"], desc="", optional=False),
    ],
)


def test_compose_marks_optional_settings() -> None:
    assert docker_compose("wg", CONFIG) == (
        "---\n"
        "services:\n"
        "  wg:\n"
        "    image: lscr.io/linuxserver/wg:latest\n"
        "    container_name: wg\n"
        '    hostname: "my host" # optional\n'
        "    cap_add:\n"
        "      - NET_ADMIN\n"
        "    environment:\n"
        "      - PUID=1000\n"
        "      - EXTRA= # optional\n"
        "    volumes:\n"
        "      - /path/to/config:/config\n"
        "    ports:\n"
        "      - 51820:51820/udp\n"
        "    shm_size: 1gb\n"
        "    sysctls:\n"
        "      - a=1\n"
        "      - b=2\n"
        "    restart: unless-stopped\n"
    )


def test_compose_drops_ports_with_host_networking() -> None:
    compose = docker_compose("x", CONFIG.model_copy(update={"networking": "host"}))
    assert "network_mode: host" in compose
    assert "ports:" not in compose


def test_compose_is_valid_yaml_for_every_fixture_image(fleet: Fleet) -> None:
    for image in fleet.images:
        doc = yaml.safe_load(image.snippets.docker_compose)
        assert doc["services"][image.name]["image"] == f"lscr.io/linuxserver/{image.name}:latest"


def test_docker_run_marks_optional_flags() -> None:
    assert (
        docker_run("wg", CONFIG)
        == " \\\n".join(
            [
                "docker run -d",
                "  --name=wg",
                "  --hostname=my host `#optional`",
                "  --cap-add=NET_ADMIN",
                "  -e PUID=1000",
                "  -e EXTRA= `#optional`",
                "  -p 51820:51820/udp",
                "  -v /path/to/config:/config",
                "  --shm-size=1gb",
                "  --sysctl=a=1",
                "  --sysctl=b=2",
                "  --restart unless-stopped",
                "  lscr.io/linuxserver/wg:latest",
            ]
        )
        + "\n"
    )


def test_docker_run_privileged_networking_devices() -> None:
    run = docker_run(
        "x",
        Config(
            privileged=True,
            networking="host",
            ports=[Port(external="80", internal="80", desc="", optional=False)],
            devices=[Device(path="/dev/dri", host_path="/dev/dri", desc="", optional=True)],
        ),
    )
    assert "--net=host" in run
    assert "--privileged" in run
    assert "--device /dev/dri:/dev/dri `#optional`" in run
    assert " -p " not in run
