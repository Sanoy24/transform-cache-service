import pytest
from pydantic import ValidationError

from transform_cache.schemas import PayloadCreate


def test_accepts_equal_length_lists() -> None:
    body = PayloadCreate(list_1=["a", "b"], list_2=["c", "d"])

    assert body.list_1 == ["a", "b"]
    assert body.list_2 == ["c", "d"]


def test_accepts_empty_lists() -> None:
    body = PayloadCreate(list_1=[], list_2=[])

    assert body.list_1 == body.list_2 == []


def test_rejects_unequal_lengths() -> None:
    with pytest.raises(ValidationError, match="same length"):
        PayloadCreate(list_1=["a"], list_2=["b", "c"])


@pytest.mark.parametrize(
    "data",
    [
        {"list_1": ["a"]},
        {"list_1": ["a"], "list_2": [1]},
        {"list_1": ["a"], "list_2": [None]},
        {"list_1": "a", "list_2": "b"},
        {"list_1": ["a"], "list_2": ["b"], "list_3": ["c"]},
    ],
    ids=["missing-list", "non-string-item", "null-item", "not-a-list", "extra-field"],
)
def test_rejects_malformed_input(data: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PayloadCreate.model_validate(data)
