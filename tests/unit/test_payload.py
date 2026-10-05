import pytest

from transform_cache.payload import build_output, interleave, payload_key


def test_interleave_alternates_between_lists() -> None:
    assert interleave(["a1", "a2"], ["b1", "b2"]) == ["a1", "b1", "a2", "b2"]


def test_interleave_empty_lists() -> None:
    assert interleave([], []) == []


def test_interleave_rejects_unequal_lengths() -> None:
    with pytest.raises(ValueError):
        interleave(["a"], ["b", "c"])


def test_build_output_matches_spec_example() -> None:
    output = build_output(
        ["FIRST STRING", "SECOND STRING", "THIRD STRING"],
        ["OTHER STRING", "ANOTHER STRING", "LAST STRING"],
    )

    assert output == (
        "FIRST STRING, OTHER STRING, SECOND STRING, "
        "ANOTHER STRING, THIRD STRING, LAST STRING"
    )


def test_build_output_empty_lists() -> None:
    assert build_output([], []) == ""


def test_payload_key_is_deterministic() -> None:
    assert payload_key(["a", "b"], ["c", "d"]) == payload_key(["a", "b"], ["c", "d"])


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ((["a", "b"], ["c", "d"]), (["c", "d"], ["a", "b"])),  # lists swapped
        ((["a", "b"], ["c", "d"]), (["b", "a"], ["c", "d"])),  # order within list
        ((["a,b"], ["c"]), (["a"], ["b,c"])),  # same text after a naive join
        ((["a"], ["b"]), (["a "], ["b"])),  # whitespace is significant
    ],
    ids=["swapped", "reordered", "join-collision", "whitespace"],
)
def test_payload_key_distinguishes_different_inputs(
    first: tuple[list[str], list[str]], second: tuple[list[str], list[str]]
) -> None:
    assert payload_key(*first) != payload_key(*second)
