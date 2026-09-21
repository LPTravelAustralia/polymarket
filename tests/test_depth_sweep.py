"""Adverse selection vs quote depth.

The point of the sweep is that "adverse selection = Xbp" is not a property
of a market -- it is a property of a market AND a quote placement. These
tests check the sweep reports a curve and judges it against fees, rather
than collapsing to a single verdict.
"""

import pytest

from polybot.simulation.depth_sweep import DepthResult, DepthSweep, render_sweep


def result(depth, fills=100, gross=10.0, adverse=4.0, fill_rate=0.1, pickoff=0.2):
    return DepthResult(depth_bps=depth, fills=fills, fill_rate=fill_rate,
                       gross_edge_bps=gross, adverse_bps=adverse,
                       pickoff_share=pickoff)


class TestDepthResult:
    def test_net_is_gross_minus_adverse(self):
        assert result(10, gross=10.0, adverse=4.0).net_bps == pytest.approx(6.0)

    def test_negative_net_is_not_viable(self):
        assert not result(0, gross=1.0, adverse=4.0).is_viable

    def test_thin_sample_is_not_viable_even_when_positive(self):
        """A handful of fills must not produce a tradeable verdict."""
        assert not result(20, fills=5, gross=20.0, adverse=1.0).is_viable

    def test_positive_and_well_sampled_is_viable(self):
        assert result(20, fills=200, gross=20.0, adverse=1.0).is_viable


class TestSweepVerdict:
    def test_picks_the_best_depth_that_beats_fees(self):
        s = DepthSweep(fee_bps=1.5, results=[
            result(0, gross=0.5, adverse=6.0),
            result(5, gross=5.0, adverse=4.0),
            result(20, gross=20.0, adverse=3.0),
        ])
        best = s.best()
        assert best is not None and best.depth_bps == 20
        assert s.verdict().startswith("VIABLE")

    def test_a_profit_smaller_than_the_fee_is_not_viable(self):
        """Beating adverse selection but not the fee is still a loss."""
        s = DepthSweep(fee_bps=5.0, results=[result(5, gross=5.0, adverse=4.0)])
        assert s.best() is None
        assert s.verdict().startswith("NO VIABLE DEPTH")

    def test_all_negative_reports_the_best_attempt(self):
        s = DepthSweep(fee_bps=1.5, results=[
            result(0, gross=0.5, adverse=6.0),
            result(5, gross=5.0, adverse=9.0),
        ])
        v = s.verdict()
        assert v.startswith("NO VIABLE DEPTH")
        assert "does not clear its costs" in v

    def test_no_fills_anywhere_is_inconclusive_not_negative(self):
        """Absence of data is not evidence of absence of edge."""
        s = DepthSweep(fee_bps=1.5, results=[result(0, fills=0), result(5, fills=2)])
        assert "INCONCLUSIVE" in s.verdict()

    def test_empty_sweep(self):
        assert "INCONCLUSIVE" in DepthSweep(fee_bps=1.5).verdict()


class TestRender:
    def test_renders_the_curve(self):
        s = DepthSweep(fee_bps=1.5, results=[
            result(0, gross=0.5, adverse=6.0), result(20, gross=20.0, adverse=3.0),
        ])
        text = render_sweep(s)
        assert "depth" in text and "adverse" in text
        assert "VIABLE" in text

    def test_marks_thin_rows(self):
        s = DepthSweep(fee_bps=1.5, results=[result(5, fills=4)])
        assert "(thin)" in render_sweep(s)

    def test_zero_fill_rows_render(self):
        assert "0" in render_sweep(DepthSweep(results=[result(5, fills=0)]))
