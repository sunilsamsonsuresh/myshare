import random

import pytest

from myshare_api.services.simplify import simplify_debts


def apply(nets: dict[int, int], transfers) -> dict[int, int]:
    out = dict(nets)
    for t in transfers:
        out[t.from_user_id] += t.amount
        out[t.to_user_id] -= t.amount
    return out


def test_simple_chain_collapses():
    # A owes B 100, B owes C 100  =>  nets A=-100, B=0, C=+100  =>  A pays C directly.
    ts = simplify_debts({1: -100, 2: 0, 3: 100})
    assert [(t.from_user_id, t.to_user_id, t.amount) for t in ts] == [(1, 3, 100)]


def test_everyone_settled_means_no_transfers():
    assert simplify_debts({1: 0, 2: 0}) == []
    assert simplify_debts({}) == []


def test_greedy_matches_largest_first_and_is_deterministic():
    nets = {1: 500, 2: 300, 3: -400, 4: -400}
    ts = simplify_debts(nets)
    # Largest creditor (1, 500) meets largest debtor (3 wins the 400 tie by lower id).
    assert (ts[0].from_user_id, ts[0].to_user_id, ts[0].amount) == (3, 1, 400)
    assert ts == simplify_debts(dict(reversed(list(nets.items()))))


def test_rejects_unbalanced_input():
    with pytest.raises(ValueError, match="sum to zero"):
        simplify_debts({1: 10, 2: -5})


def test_property_settles_everyone_with_at_most_n_minus_1_transfers():
    rng = random.Random(7)
    for _ in range(1000):
        n = rng.randint(2, 10)
        vals = [rng.randint(-100_000, 100_000) for _ in range(n - 1)]
        vals.append(-sum(vals))
        nets = dict(enumerate(vals))
        ts = simplify_debts(nets)
        assert all(v == 0 for v in apply(nets, ts).values())
        nonzero = sum(1 for v in vals if v)
        assert len(ts) <= max(nonzero - 1, 0)
        assert all(t.amount > 0 for t in ts)
