import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.fakes import CountingTransformer
from transform_cache.config import Settings
from transform_cache.main import create_app


@pytest.fixture
def transformer() -> CountingTransformer:
    return CountingTransformer()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(database_url=f"sqlite+aiosqlite:///{tmp_path / 'api.db'}")


@pytest.fixture
def client(
    settings: Settings, transformer: CountingTransformer
) -> Iterator[TestClient]:
    # The context manager runs the app's lifespan: tables, engine, service.
    with TestClient(create_app(settings, transformer)) as client:
        yield client


SPEC_INPUT = {
    "list_1": ["first string", "second string", "third string"],
    "list_2": ["other string", "another string", "last string"],
}


def test_create_then_read_spec_example(client: TestClient) -> None:
    created = client.post("/payload", json=SPEC_INPUT)

    assert created.status_code == 201
    payload_id = created.json()["id"]
    assert created.json()["message"] == "Payload created"
    assert created.headers["Location"] == f"/payload/{payload_id}"

    read = client.get(f"/payload/{payload_id}")

    assert read.status_code == 200
    assert read.json() == {
        "output": "FIRST STRING, OTHER STRING, SECOND STRING, "
        "ANOTHER STRING, THIRD STRING, LAST STRING"
    }


def test_repeated_post_returns_existing_id(
    client: TestClient, transformer: CountingTransformer
) -> None:
    first = client.post("/payload", json=SPEC_INPUT)
    transformer.calls.clear()

    second = client.post("/payload", json=SPEC_INPUT)

    assert second.status_code == 200
    assert second.json() == {
        "id": first.json()["id"],
        "message": "Payload already exists",
    }
    assert transformer.calls == []


def test_new_payload_reuses_cached_strings(
    client: TestClient, transformer: CountingTransformer
) -> None:
    client.post("/payload", json={"list_1": ["a", "b"], "list_2": ["c", "d"]})
    transformer.calls.clear()

    response = client.post(
        "/payload", json={"list_1": ["a", "x"], "list_2": ["c", "d"]}
    )

    assert response.status_code == 201
    assert transformer.calls == ["x"]


def test_duplicate_strings_are_transformed_once(
    client: TestClient, transformer: CountingTransformer
) -> None:
    created = client.post("/payload", json={"list_1": ["a", "a"], "list_2": ["a", "b"]})

    read = client.get(f"/payload/{created.json()['id']}")

    assert read.json() == {"output": "A, A, A, B"}
    assert sorted(transformer.calls) == ["a", "b"]


def test_payload_and_cache_survive_restart(settings: Settings) -> None:
    # Fresh app and service on the same database: anything reused here must
    # have come from persisted state, not from memory.
    with TestClient(create_app(settings, CountingTransformer())) as client:
        first = client.post("/payload", json=SPEC_INPUT)

    restarted_transformer = CountingTransformer()
    with TestClient(create_app(settings, restarted_transformer)) as client:
        repeated = client.post("/payload", json=SPEC_INPUT)
        overlapping = client.post(
            "/payload",
            json={"list_1": ["first string"], "list_2": ["new string"]},
        )
        read = client.get(f"/payload/{first.json()['id']}")

    assert repeated.status_code == 200
    assert repeated.json()["id"] == first.json()["id"]
    assert overlapping.status_code == 201
    assert restarted_transformer.calls == ["new string"]
    assert read.status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"list_1": ["a"], "list_2": ["b", "c"]},
        {"list_1": ["a"]},
        {"list_1": ["a"], "list_2": [1]},
        {"list_1": ["a"], "list_2": ["b"], "extra": []},
    ],
    ids=["unequal-lengths", "missing-list", "non-string", "unknown-field"],
)
def test_invalid_body_is_rejected(client: TestClient, body: dict[str, object]) -> None:
    assert client.post("/payload", json=body).status_code == 422


def test_unknown_payload_returns_404(client: TestClient) -> None:
    response = client.get(f"/payload/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Payload not found"}


def test_malformed_payload_id_is_rejected(client: TestClient) -> None:
    assert client.get("/payload/not-a-uuid").status_code == 422
