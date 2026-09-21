"""Replay engine and model scoring."""

import pytest

from polybot.backtest.engine import ReplayEngine
from polybot.backtest.scoring import (
    Observation,
    brier,
    calibration_curve,
    log_loss,
    render_score,
    score_model,
)
from polybot.config import MakerParams
from polybot.marketdata.store import PublicTrade, Snapshot
from polybot.strategy.fair_value import MicropriceModel


def snap(ts, bid=0.48, ask=0.52, size=500.0, token="t1"):
    return Snapshot(ts=ts, token_id=token, bids=[(bid, size)],
                    asks=[(ask, size)], tick_size=0.01, min_order_size=5.0)


class TestReplayEngine:
    def test_places_quotes_on_a_stable_book(self):
        engine = ReplayEngine(MicropriceModel())
        result = engine.run([snap(i) for i in range(10)], [])
        assert result.snapshots_processed == 10
        assert result.quotes_placed > 0

    def test_keeps_queue_position_on_an_unchanged_book(self):
        """An unchanged fair value must not cause a cancel/replace storm --
        that surrenders the queue priority the strategy depends on."""
        engine = ReplayEngine(MicropriceModel())
        result = engine.run([snap(i) for i in range(50)], [])
        assert result.quotes_placed <= 3

    def test_fills_when_the_market_trades_through(self):
        snaps = [snap(float(i)) for i in range(10)]
        trades = [PublicTrade(ts=5.5, token_id="t1", price=0.47, size=100)]
        result = ReplayEngine(MicropriceModel()).run(snaps, trades)

        assert result.trades_processed == 1
        assert len(result.fills) == 1
        assert result.fills[0].side == "BUY"

    def test_declines_to_quote_without_a_fair_value(self):
        """A one-sided book has no microprice, so the engine should skip it
        rather than invent one."""
        one_sided = [
            Snapshot(ts=float(i), token_id="t1", bids=[(0.48, 100.0)], asks=[])
            for i in range(5)
        ]
        result = ReplayEngine(MicropriceModel()).run(one_sided, [])
        assert result.quotes_placed == 0
        assert result.skip_reasons.get("no fair value") == 5

    def test_empty_input(self):
        result = ReplayEngine(MicropriceModel()).run([], [])
        assert result.snapshots_processed == 0
        assert result.net_pnl == 0.0

    def test_inventory_is_marked_at_the_final_mid(self):
        """Realised PnL alone hides losses sitting in an open position."""
        snaps = [snap(float(i)) for i in range(5)]
        snaps += [snap(float(i), bid=0.40, ask=0.44) for i in range(5, 10)]
        trades = [PublicTrade(ts=1.5, token_id="t1", price=0.47, size=200)]

        result = ReplayEngine(MicropriceModel()).run(snaps, trades)
        assert result.fills
        # Bought at 0.47, market ended at a 0.42 mid: inventory is under water.
        assert result.inventory_pnl < 0
        assert result.net_pnl < result.realised_pnl + 1e-9

    def test_pickoff_share_is_reported(self):
        """A collapsing market should fill the bot via price-through, and the
        report must say so -- that is the adverse selection."""
        snaps = [snap(0.0), snap(1.0)]
        snaps.append(snap(2.0, bid=0.30, ask=0.34))
        result = ReplayEngine(MicropriceModel()).run(snaps, [])
        if result.fills:
            assert result.price_through_share > 0

    def test_summary_renders(self):
        result = ReplayEngine(MicropriceModel()).run([snap(i) for i in range(5)], [])
        text = result.summary()
        assert "net PnL" in text
        assert "quotes placed" in text

    def test_respects_custom_params(self):
        """An impossible edge requirement should stop it quoting entirely."""
        strict = MakerParams(min_edge_per_share=0.99)
        result = ReplayEngine(MicropriceModel(), params=strict).run(
            [snap(i) for i in range(5)], []
        )
        assert result.quotes_placed == 0


class TestScoringMetrics:
    def test_brier_perfect(self):
        assert brier([1.0, 0.0], [1, 0]) == pytest.approx(0.0)

    def test_brier_coin_flip(self):
        assert brier([0.5, 0.5], [1, 0]) == pytest.approx(0.25)

    def test_log_loss_punishes_confident_errors(self):
        confident_wrong = log_loss([0.99], [0])
        mildly_wrong = log_loss([0.6], [0])
        assert confident_wrong > mildly_wrong * 4

    def test_log_loss_handles_certainty_without_exploding(self):
        assert log_loss([1.0], [0]) < float("inf")

    def test_empty_input(self):
        assert brier([], []) != brier([], [])   # nan


class TestCalibrationCurve:
    def test_bins_and_measures_error(self):
        preds = [0.05] * 100 + [0.95] * 100
        outcomes = [0] * 100 + [1] * 100
        bins = calibration_curve(preds, outcomes, bins=10)
        assert all(abs(b.error) < 0.06 for b in bins)

    def test_detects_overconfidence(self):
        """Predicting 0.9 on events that happen half the time must show up."""
        preds = [0.9] * 100
        outcomes = [1] * 50 + [0] * 50
        bins = calibration_curve(preds, outcomes, bins=10)
        assert len(bins) == 1
        assert bins[0].error == pytest.approx(0.4, abs=0.01)


class TestModelScore:
    @staticmethod
    def _observations(n, model_edge=True):
        obs = []
        for i in range(n):
            outcome = i % 2
            if model_edge:
                model_p = 0.9 if outcome else 0.1
            else:
                model_p = 0.5
            market_p = 0.7 if outcome else 0.3
            obs.append(Observation(model_p, market_p, outcome))
        return obs

    def test_detects_a_real_edge(self):
        score = score_model(self._observations(400))
        assert score.beats_market
        assert score.skill_score > 0
        assert score.is_meaningful
        assert "EDGE" in score.verdict()

    def test_detects_no_edge(self):
        score = score_model(self._observations(400, model_edge=False))
        assert not score.beats_market
        assert "NO EDGE" in score.verdict()
        assert "do not trade" in score.verdict().lower()

    def test_small_sample_is_inconclusive(self):
        """A 20-market sample producing a great-looking skill score must be
        reported as inconclusive, not as an edge."""
        score = score_model(self._observations(20))
        assert score.skill_score > 0
        assert not score.is_meaningful
        assert "INCONCLUSIVE" in score.verdict()

    def test_render(self):
        text = render_score(score_model(self._observations(400)))
        assert "skill score" in text
        assert "calibration" in text
