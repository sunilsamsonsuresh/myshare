"""Split math: every split type, remainder handling, and the sum-equals-total invariant."""

import random
from decimal import Decimal

import pytest

from myshare_api.services.splits import Participant, SplitError, compute_split


def P(uid: int, v=None) -> Participant:
    return Participant(uid, None if v is None else Decimal(str(v)))


def test_equal_even():
    assert compute_split(900, "equal", [P(1), P(2), P(3)]) == {1: 300, 2: 300, 3: 300}


def test_equal_remainder_goes_to_first_participants():
    # 1000 / 3 = 333 r 1 -> first person absorbs the extra paisa
    assert compute_split(1000, "equal", [P(1), P(2), P(3)]) == {1: 334, 2: 333, 3: 333}
    # 1001 / 3 = 333 r 2 -> first two absorb one each
    assert compute_split(1001, "equal", [P(7), P(8), P(9)]) == {7: 334, 8: 334, 9: 333}


def test_equal_order_is_respected():
    assert compute_split(1000, "equal", [P(3), P(1), P(2)]) == {3: 334, 1: 333, 2: 333}


def test_exact_ok_and_mismatch_message():
    assert compute_split(1000, "exact", [P(1, 600), P(2, 400)]) == {1: 600, 2: 400}
    with pytest.raises(SplitError, match="short by 100"):
        compute_split(1000, "exact", [P(1, 500), P(2, 400)])
    with pytest.raises(SplitError, match="over by 1"):
        compute_split(1000, "exact", [P(1, 601), P(2, 400)])


def test_exact_rejects_fractional_minor_units():
    with pytest.raises(SplitError, match="whole minor units"):
        compute_split(1000, "exact", [P(1, "500.5"), P(2, "499.5")])


def test_percent():
    assert compute_split(10000, "percent", [P(1, 50), P(2, 25), P(3, 25)]) == {
        1: 5000,
        2: 2500,
        3: 2500,
    }
    # 33.33/33.33/33.34 of 100 -> 33/33/33 floors + 1 leftover to first
    assert compute_split(100, "percent", [P(1, "33.33"), P(2, "33.33"), P(3, "33.34")]) == {
        1: 34,
        2: 33,
        3: 33,
    }


def test_percent_must_total_100():
    with pytest.raises(SplitError, match="add up to 90"):
        compute_split(1000, "percent", [P(1, 50), P(2, 40)])


def test_shares():
    assert compute_split(4000, "shares", [P(1, 2), P(2, 1), P(3, 1)]) == {1: 2000, 2: 1000, 3: 1000}
    assert compute_split(1000, "shares", [P(1, 2), P(2, 1), P(3, 1)]) == {1: 500, 2: 250, 3: 250}
    # 100 split 1:1:1 -> 34/33/33
    assert compute_split(100, "shares", [P(1, 1), P(2, 1), P(3, 1)]) == {1: 34, 2: 33, 3: 33}


def test_zero_weight_never_absorbs_leftover():
    # First participant has 0 shares/0%: leftover units must skip them.
    assert compute_split(101, "shares", [P(1, 0), P(2, 1), P(3, 1)]) == {1: 0, 2: 51, 3: 50}
    assert compute_split(101, "percent", [P(1, 0), P(2, 50), P(3, 50)]) == {1: 0, 2: 51, 3: 50}


@pytest.mark.parametrize(
    ("total", "kind", "parts", "msg"),
    [
        (0, "equal", [P(1)], "greater than zero"),
        (100, "equal", [], "at least one"),
        (100, "equal", [P(1), P(1)], "only once"),
        (100, "shares", [P(1, 0), P(2, 0)], "greater than zero"),
        (100, "shares", [P(1, 1), P(2)], "missing"),
        (100, "percent", [P(1, -10), P(2, 110)], "negative"),
    ],
)
def test_invalid_inputs(total, kind, parts, msg):
    with pytest.raises(SplitError, match=msg):
        compute_split(total, kind, parts)


def test_property_splits_always_sum_to_total():
    rng = random.Random(42)
    for _ in range(2000):
        total = rng.randint(1, 10_000_000)
        n = rng.randint(1, 9)
        kind = rng.choice(["equal", "percent", "shares", "exact"])
        if kind == "equal":
            parts = [P(i) for i in range(n)]
        elif kind == "shares":
            parts = [P(i, rng.randint(1, 5)) for i in range(n)]
        elif kind == "percent":
            cuts = sorted(rng.randint(0, 10000) for _ in range(n - 1))
            bps = [b - a for a, b in zip([0, *cuts], [*cuts, 10000], strict=True)]
            parts = [P(i, Decimal(b) / 100) for i, b in enumerate(bps)]
        else:
            cuts = sorted(rng.randint(0, total) for _ in range(n - 1))
            parts = [
                P(i, b - a) for i, (a, b) in enumerate(zip([0, *cuts], [*cuts, total], strict=True))
            ]
        result = compute_split(total, kind, parts)
        assert sum(result.values()) == total
        assert all(v >= 0 for v in result.values())
