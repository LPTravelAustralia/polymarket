"""Signal lab.

A signal study fails in one direction: it finds things that are not there.
These tests pin the machinery that stops that -- no lookahead, honest sample
sizes, and planted signals found while noise is not.
"""

import math
import random

import pytest

from polybot.research.signals import (
    forward_sum,
    forward_vol,
    ic_test,
    information_coefficient,
    log_returns,
    rank,
    rule_backtest,
    spearman,
    tercile_cuts,
    trailing,
)


def noise(n, seed):
    rng = random.Random(seed)
    return [rng.gauss(0, 0.02) for _ in range(n)]


class TestStats:
    def test_rank_shares_ties(self):
        assert rank([10, 20, 20, 30]) == [1.0, 2.5, 2.5, 4.0]

    def test_spearman_monotone(self):
        x = list(range(50))
        assert spearman(x, [v ** 3 for v in x]) == pytest.approx(1.0)
        assert spearman(x, [-v for v in x]) == pytest.approx(-1.0)


class TestNoLookahead:
    def test_forward_sum_starts_tomorrow(self):
        v = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert forward_sum(v, 2) == [5.0, 7.0, 9.0, None, None]

    def test_trailing_includes_today_only(self):
        assert trailing([1.0, 2.0, 3.0], 2, sum) == [None, 3.0, 5.0]

    def test_rule_uses_yesterdays_signal(self):
        """A signal that equals *today's* return sign carries no information
        about tomorrow on noise. If the backtest let it trade today's return,
        it would print an impossible profit."""
        r = noise(3000, 1)
        sig = [x > 0 for x in r]
        res = rule_backtest(sig, r, lo=0, hi=len(r), cost=0.0)
        assert abs(res.rule_return) < 0.5

    def test_a_peek_at_tomorrow_would_be_obvious(self):
        """Sanity check on the check: the same signal shifted to see
        tomorrow is wildly profitable, so the test above is meaningful."""
        r = noise(3000, 1)
        sig = [x > 0 for x in r[1:]] + [False]
        res = rule_backtest(sig, r, lo=0, hi=len(r), cost=0.0)
        assert res.rule_return > 5.0


class TestIC:
    def test_planted_signal_is_found(self):
        rng = random.Random(4)
        f = [rng.gauss(0, 1) for _ in range(3000)]
        # Tomorrow's return leans on today's feature.
        r = [0.0] + [0.1 * f[i] * 0.02 + rng.gauss(0, 0.02) for i in range(2999)]
        target = forward_sum(r, 1)
        t = ic_test(f, target, 1)
        assert t.ic > 0.05 and t.p < 0.01

    def test_noise_is_not_found(self):
        f = noise(3000, 7)
        target = forward_sum(noise(3000, 8), 7)
        t = ic_test(f, target, 7)
        assert t.p > 0.01

    def test_overlap_does_not_inflate_the_sample(self):
        """3,000 days of 30-day windows are ~100 independent observations."""
        f = noise(3000, 9)
        target = forward_sum(noise(3000, 10), 30)
        _, n = information_coefficient(f, target, 30)
        assert 90 <= n <= 101


class TestVolatility:
    def test_forward_vol_is_annualised(self):
        rng = random.Random(3)
        r = [rng.gauss(0, 0.02) for _ in range(400)]
        v = [x for x in forward_vol(r, 30) if x is not None]
        assert statistics_mean(v) == pytest.approx(0.02 * math.sqrt(365), rel=0.15)


def statistics_mean(xs):
    return sum(xs) / len(xs)


class TestTerciles:
    def test_fitted_on_training_window_only(self):
        vals = [float(i) for i in range(100)] + [1000.0 + i for i in range(100)]
        lo_cut, hi_cut = tercile_cuts(vals, 0, 100)
        assert hi_cut < 100

    def test_log_returns(self):
        assert log_returns([100.0, 110.0])[1] == pytest.approx(math.log(1.1))
