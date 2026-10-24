"""The compatibility endpoints against real responses from api.linuxserver.io (see fixtures/README.md)."""

import json

from fastapi.testclient import TestClient

from .conftest import load_fixture

LIVE = load_fixture("live-v1.json")


def test_lists_the_same_images(client: TestClient) -> None:
    images = client.get("/api/v1/images.config.deprecated.json").json()["data"]["repositories"]["linuxserver"]
    assert [i["name"] for i in images] == sorted(i["name"] for i in LIVE)


def test_every_image_is_byte_identical(client: TestClient) -> None:
    images = client.get("/api/v1/images.config.deprecated.json").json()["data"]["repositories"]["linuxserver"]
    by_name = {i["name"]: i for i in images}
    for expected in LIVE:
        # The live API serves compact JSON, so equal objects with equal key order are equal bytes.
        assert json.dumps(by_name[expected["name"]]) == json.dumps(expected), expected["name"]


def test_serialises_like_the_original(client: TestClient) -> None:
    body = client.get("/api/v1/images").text
    assert body == json.dumps(json.loads(body), separators=(",", ":"), ensure_ascii=False)
    assert client.get("/health").text == '"Success"'
