"""Calibration study.

The ways this goes wrong all produce a confident, fake edge: pooling
correlated outcomes, counting decided contracts as predictions, and
reporting the luckiest of many bands. Each has a test.
"""

import random

import pytest

from polybot.research.calibration import (
    Contract,
    benjamini_hochberg,
    calibrate,
)


def world(n, *, bias=0.0, events=None, seed=1, fee=0.0, price_range=(0.05, 0.95)):
    """Contracts whose true win probability is price + bias."""
    rng = random.Random(seed)
    out = []
    for i in range(n):
        p = rng.uniform(*price_range)
        won = rng.random() < min(max(p + bias, 0.0), 1.0)
        ev = f"e{i % events}" if events else f"e{i}"
        out.append(Contract(f"m{i}", ev, p, won, fee, "x", 7.0))
    return out


class TestHonestMarket:
    def test_no_band_survives_correction(self):
        """A perfectly calibrated market must not produce a discovery."""
        bands, _ = calibrate(world(20_000, seed=3), n_boot=300)
        assert bands
        assert not any(b.significant for b in bands)

    def test_edges_are_small(self):
        bands, _ = calibrate(world(20_000, seed=4), n_boot=200)
        assert all(abs(b.gross_edge) < 0.03 for b in bands)


class TestBiasedMarket:
    def test_detects_underpriced_favourites(self):
        cs = world(20_000, bias=0.04, seed=5, price_range=(0.70, 0.95))
        bands, _ = calibrate(cs, n_boot=300)
        hits = [b for b in bands if b.significant]
        assert hits and all(b.side == "YES" for b in hits)

    def test_detects_overpriced_longshots(self):
        cs = world(20_000, bias=-0.03, seed=6, price_range=(0.05, 0.30))
        bands, _ = calibrate(cs, n_boot=300)
        hits = [b for b in bands if b.significant]
        assert hits and all(b.side == "NO" for b in hits)


class TestClustering:
    def test_correlated_outcomes_widen_the_interval(self):
        """Same contracts, grouped into a few events that resolve together:
        the interval must widen, or a single lucky event reads as an edge."""
        rng = random.Random(9)
        indep, clustered = [], []
        for e in range(40):
            won = rng.random() < 0.5
            for k in range(50):
                clustered.append(Contract(f"c{e}-{k}", f"e{e}", 0.5, won, 0.0, "x", 1.0))
                indep.append(Contract(f"i{e}-{k}", f"i{e}-{k}", 0.5,
                                      rng.random() < 0.5, 0.0, "x", 1.0))
        bi, _ = calibrate(indep, bands=(0.0, 1.0), n_boot=400)
        bc, _ = calibrate(clustered, bands=(0.0, 1.0), n_boot=400)
        width = lambda b: b[0].ci_hi - b[0].ci_lo  # noqa: E731
        assert width(bc) > 3 * width(bi)


class TestDecided:
    def test_decided_contracts_are_held_out(self):
        cs = [Contract(f"m{i}", f"e{i}", 0.995, True, 0.0, "x", 0.5) for i in range(100)]
        bands, held = calibrate(cs, n_boot=50)
        assert bands == []
        assert len(held) == 100


class TestCosts:
    def test_fee_follows_the_p_one_minus_p_curve(self):
        mid = Contract("a", "a", 0.5, True, 0.04, "x", 1.0)
        tail = Contract("b", "b", 0.95, True, 0.04, "x", 1.0)
        assert mid.fee_per_share == pytest.approx(0.01)
        assert tail.fee_per_share == pytest.approx(0.0019)

    def test_net_edge_charges_fee_and_spread(self):
        cs = world(8_000, bias=0.05, seed=11, fee=0.05, price_range=(0.45, 0.55))
        (b,) = calibrate(cs, bands=(0.4, 0.6), n_boot=100, half_spread=0.01)[0]
        assert b.net_edge == pytest.approx(abs(b.gross_edge) - b.mean_fee - 0.01)
        assert b.mean_fee == pytest.approx(0.05 * 0.25, rel=0.02)


class TestBH:
    def test_matches_hand_calculation(self):
        q = benjamini_hochberg([0.01, 0.04, 0.03, 0.20])
        assert q == pytest.approx([0.04, 0.0533333, 0.0533333, 0.20], rel=1e-4)

    def test_monotone_in_p(self):
        ps = [0.001, 0.2, 0.01, 0.5, 0.04]
        q = benjamini_hochberg(ps)
        order = sorted(range(5), key=lambda i: ps[i])
        assert all(q[order[i]] <= q[order[i + 1]] for i in range(4))
