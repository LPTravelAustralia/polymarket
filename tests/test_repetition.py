"""Repeated betting.

The property under test is the one that trips up every "lots of small
trades" plan: bankrolls compound, so what accumulates is the mean of the
log, and the mean of the log can be negative while the mean is positive.
"""

import math

import pytest

from polybot.research.repetition import (
    CALL_MEAN_RETURN,
    CALL_MEDIAN_RETURN,
    COST_LOW,
    LogNormalReturns,
    optimal_fraction,
    sanity_check,
    simulate_repetition,
    truncate,
)


@pytest.fixture
def calls():
    return LogNormalReturns.from_mean_and_median(CALL_MEAN_RETURN,
                                                 CALL_MEDIAN_RETURN)


class TestFit:
    def test_reproduces_the_published_pair(self, calls):
        assert calls.arithmetic_mean == pytest.approx(CALL_MEAN_RETURN, rel=1e-6)
        assert calls.median == pytest.approx(CALL_MEDIAN_RETURN, rel=1e-6)

    def test_geometric_mean_is_the_median_not_the_mean(self, calls):
        """The whole problem in one assertion."""
        assert calls.geometric_mean == pytest.approx(calls.median)
        assert calls.geometric_mean < 0 < calls.arithmetic_mean

    def test_rejects_a_mean_below_the_median(self):
        with pytest.raises(ValueError):
            LogNormalReturns.from_mean_and_median(0.1, 0.5)

    def test_rejects_total_loss(self):
        with pytest.raises(ValueError):
            LogNormalReturns.from_mean_and_median(1.0, -1.0)


class TestCompounding:
    def test_full_stake_ruins_despite_a_positive_mean(self, calls):
        r = simulate_repetition(calls, trades=100, fraction=1.0,
                                cost=COST_LOW, paths=4_000)
        assert r.median_terminal < 0.01
        assert r.p_below_start > 0.5
        assert r.mean_terminal > 1.0, "the mean is positive; that is the trap"

    def test_costs_make_it_strictly_worse(self, calls):
        free = simulate_repetition(calls, trades=50, fraction=1.0, cost=0.0,
                                   paths=3_000)
        paid = simulate_repetition(calls, trades=50, fraction=1.0,
                                   cost=COST_LOW, paths=3_000)
        assert paid.median_terminal < free.median_terminal

    def test_a_genuinely_positive_edge_does_compound(self):
        """The model must not simply always say no -- with an edge, repeating
        is exactly the right thing to do."""
        good = LogNormalReturns.from_mean_and_median(0.30, 0.05)
        r = simulate_repetition(good, trades=100, fraction=1.0, cost=0.0,
                                paths=3_000)
        assert r.median_terminal > 1.0
        assert r.log_growth_per_trade > 0

    def test_no_stake_saves_a_negative_arithmetic_mean(self):
        """Sizing down rescues a negative *geometric* mean. It cannot rescue
        a negative arithmetic one, and claiming otherwise would be the most
        dangerous bug this module could carry."""
        bad = LogNormalReturns(mu=math.log(0.90), sigma=0.20)
        assert bad.arithmetic_mean < 0
        f, g = optimal_fraction(bad, cost=0.0, samples=20_000)
        assert g <= 0
        assert f == 0.0


class TestSanityCheck:
    def test_flags_a_fit_that_contradicts_observed_outcomes(self, calls):
        """67% modelled against 94% observed is not a near miss."""
        out = sanity_check(calls, observed_loss_rate=0.94, trades=100)
        assert "FAILS" in out
        assert "not a population parameter" in out

    def test_passes_when_the_model_matches(self, calls):
        modelled = simulate_repetition(calls, trades=100, fraction=1.0,
                                       cost=COST_LOW, paths=20_000)
        out = sanity_check(calls, observed_loss_rate=modelled.p_below_start,
                           trades=100)
        assert "CONSISTENT" in out


class TestTruncation:
    def test_take_profit_removes_almost_all_of_the_mean(self, calls):
        """The point of the whole exercise: the mean is in the tail, and a
        take-profit is a rule for discarding the tail."""
        capped = truncate(calls, take_profit=0.20, stop_loss=0.10,
                          cost=COST_LOW, samples=100_000)
        assert capped.mean < 0.05
        assert capped.tail_mean_lost < -5.0

    def test_wider_targets_keep_more_of_the_mean(self, calls):
        near = truncate(calls, take_profit=0.20, stop_loss=0.10,
                        cost=COST_LOW, samples=100_000)
        far = truncate(calls, take_profit=2.00, stop_loss=0.50,
                       cost=COST_LOW, samples=100_000)
        assert far.mean > near.mean

    def test_exit_rules_do_not_move_the_median(self, calls):
        """Caps bite in the tails; the typical trade is untouched. So a
        strategy of small fast scalps inherits the median as its experience
        and gives up the mean as its compensation."""
        capped = truncate(calls, take_profit=0.20, stop_loss=0.10,
                          cost=COST_LOW, samples=100_000)
        uncapped = truncate(calls, cost=COST_LOW, samples=100_000)
        assert capped.median == pytest.approx(uncapped.median, abs=1e-6)
        assert capped.median < 0

    def test_no_rule_means_no_tail_given_up(self, calls):
        plain = truncate(calls, cost=COST_LOW, samples=50_000)
        assert plain.tail_mean_lost == pytest.approx(0.0, abs=1e-9)
