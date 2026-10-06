import pytest

from payload_cache.domain.payloads import (
    interleave,
    payload_fingerprint,
    render_output,
    transformation_key,
)


def test_interleave_alternates_items() -> None:
    assert interleave(["a", "b", "c"], ["1", "2", "3"]) == ["a", "1", "b", "2", "c", "3"]


def test_interleave_empty_lists() -> None:
    assert interleave([], []) == []


def test_interleave_rejects_length_mismatch() -> None:
    with pytest.raises(ValueError, match="equal length"):
        interleave(["a"], ["1", "2"])


def test_render_output_matches_spec_sample() -> None:
    first = ["FIRST STRING", "SECOND STRING", "THIRD STRING"]
    second = ["OTHER STRING", "ANOTHER STRING", "LAST STRING"]

    assert render_output(first, second) == (
        "FIRST STRING, OTHER STRING, SECOND STRING, ANOTHER STRING, THIRD STRING, LAST STRING"
    )


def test_fingerprint_is_deterministic() -> None:
    assert payload_fingerprint(["a"], ["b"]) == payload_fingerprint(["a"], ["b"])


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ((["a"], ["b"]), (["b"], ["a"])),  # list order matters
        ((["a, b"], ["c"]), (["a"], ["b, c"])),  # separator inside a value
        ((["a", "b"], ["c", "d"]), (["a", "c"], ["b", "d"])),  # same interleaving, other split
    ],
)
def test_fingerprint_distinguishes_different_inputs(
    left: tuple[list[str], list[str]], right: tuple[list[str], list[str]]
) -> None:
    assert payload_fingerprint(*left) != payload_fingerprint(*right)


def test_transformation_key_is_exact_match() -> None:
    assert transformation_key("a") == transformation_key("a")
    assert transformation_key("a") != transformation_key("A")
    assert transformation_key("a") != transformation_key("a ")


def test_transformation_key_is_fixed_width_for_long_input() -> None:
    assert len(transformation_key("x" * 100_000)) == 64
