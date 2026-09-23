"""Regime monitor.

The costly failures here are notification failures, in both directions: an
alert that never fires when the market turns, and -- worse, because it is
silent -- an alert that closes itself because a data source went down.
"""

import pytest

from polybot.monitor import alerts
from polybot.monitor.alerts import (
    Action,
    apply,
    decide,
    level_from_title,
    title_for,
)
from polybot.monitor.regime import (
    DEFAULT_HURDLE,
    FUNDING_INTEREST_BASELINE,
    Level,
    Reading,
    Signal,
    Thresholds,
    _env_float,
    annualise,
    flow_adjusted_return,
    render_markdown,
    thresholds_from_env,
)

T = Thresholds(warm=0.10, rich=0.20)


def sig(value, name="S", error=None, is_net=True):
    return Signal(name, T, value=value, error=error, is_net=is_net)


def reading(*values, errors=()):
    sigs = [sig(v, name=f"S{i}") for i, v in enumerate(values)]
    for i in errors:
        sigs[i].value, sigs[i].error = None, "down"
    return Reading(signals=sigs)


class TestClassify:
    @pytest.mark.parametrize("v,lvl", [(0.0, Level.QUIET), (0.0999, Level.QUIET),
                                       (0.10, Level.WARMING), (0.1999, Level.WARMING),
                                       (0.20, Level.RICH), (5.0, Level.RICH)])
    def test_boundaries(self, v, lvl):
        assert T.classify(v) is lvl

    def test_regime_is_the_highest_signal(self):
        assert reading(0.01, 0.25, 0.12).level is Level.RICH

    def test_unavailable_signals_do_not_count(self):
        r = reading(0.25, 0.01, errors=(0,))
        assert r.level is Level.QUIET
        assert not r.complete

    def test_nothing_available(self):
        assert reading(0.1, errors=(0,)).level is None

    def test_funding_threshold_clears_the_fair_value_baseline(self):
        """A perp at fair value pays 10.95% on Hyperliquid. A warm threshold
        at or below that would alert in perfectly ordinary markets -- which
        is what the live reading on 23 Sep 2026 (11.57%) would have done."""
        from polybot.monitor.regime import DEFAULT_THRESHOLDS
        t = DEFAULT_THRESHOLDS["BTC/ETH 30d funding"]
        assert FUNDING_INTEREST_BASELINE == pytest.approx(0.1095, abs=1e-4)
        assert t.warm > FUNDING_INTEREST_BASELINE + 0.03
        assert t.classify(0.1157) is Level.QUIET


class TestSettings:
    @pytest.mark.parametrize("raw,want", [("4.5", 0.045), ("4.5%", 0.045),
                                          ("0.045", 0.045), ("1", 0.01),
                                          ("10", 0.10)])
    def test_rates_parse_either_way(self, raw, want, monkeypatch):
        monkeypatch.setenv("X_RATE", raw)
        assert _env_float("X_RATE") == pytest.approx(want)

    def test_empty_means_default(self, monkeypatch):
        """GitHub passes an unset repository variable as an empty string."""
        monkeypatch.setenv("X_RATE", "")
        assert _env_float("X_RATE") is None

    def test_threshold_override(self, monkeypatch):
        monkeypatch.setenv("REGIME_HLP_RICH", "30")
        t = thresholds_from_env()["HLP 90d return"]
        assert t.rich == pytest.approx(0.30)
        assert t.warm == pytest.approx(0.10)


class TestFlowAdjustedReturn:
    DAY = 86_400_000

    def test_deposits_are_not_performance(self):
        """A vault that doubles in size from deposits and earns nothing has
        returned nothing."""
        av = [(0, 1e6), (self.DAY, 2e6), (2 * self.DAY, 2e6)]
        pn = [(0, 0.0), (self.DAY, 0.0), (2 * self.DAY, 0.0)]
        total, days = flow_adjusted_return(av, pn)
        assert total == pytest.approx(0.0)
        assert days == pytest.approx(2.0)

    def test_pnl_is_measured_on_the_starting_base(self):
        av = [(0, 1e6), (self.DAY, 1.01e6), (2 * self.DAY, 2.02e6)]
        pn = [(0, 0.0), (self.DAY, 1e4), (2 * self.DAY, 2.01e4)]
        total, _ = flow_adjusted_return(av, pn)
        assert total == pytest.approx(1.01 * 1.01 - 1, rel=1e-3)

    def test_window(self):
        av = [(i * self.DAY, 1e6) for i in range(5)]
        pn = [(i * self.DAY, i * 1e4) for i in range(5)]
        total, days = flow_adjusted_return(av, pn, since_ms=3 * self.DAY)
        assert days == pytest.approx(1.0)
        assert total == pytest.approx(0.01)

    def test_seed_period_is_skipped(self):
        av = [(0, 0.0), (self.DAY, 1e6), (2 * self.DAY, 1e6)]
        pn = [(0, 0.0), (self.DAY, 0.0), (2 * self.DAY, 1e4)]
        total, _ = flow_adjusted_return(av, pn)
        assert total == pytest.approx(0.01)

    def test_mismatched_series(self):
        assert flow_adjusted_return([(0, 1.0)], [(0, 0.0), (1, 0.0)]) is None

    def test_annualise(self):
        assert annualise(0.01, 365.0) == pytest.approx(0.01)
        assert annualise(0.0, 30.0) == pytest.approx(0.0)


class TestDecide:
    @pytest.mark.parametrize("open_lvl,new,complete,want", [
        (None, Level.QUIET, True, Action.NONE),
        (None, Level.WARMING, True, Action.OPEN),
        (None, Level.RICH, False, Action.OPEN),
        (Level.WARMING, Level.WARMING, True, Action.REFRESH),
        (Level.WARMING, Level.RICH, True, Action.ESCALATE),
        (Level.WARMING, Level.RICH, False, Action.ESCALATE),
        (Level.RICH, Level.WARMING, True, Action.DEESCALATE),
        (Level.RICH, Level.QUIET, True, Action.CLOSE),
    ])
    def test_transitions(self, open_lvl, new, complete, want):
        value = {Level.QUIET: 0.0, Level.WARMING: 0.15, Level.RICH: 0.25}[new]
        r = reading(value, 0.0, errors=() if complete else (1,))
        assert decide(open_lvl, r) is want

    @pytest.mark.parametrize("open_lvl", [Level.WARMING, Level.RICH])
    def test_partial_data_never_downgrades(self, open_lvl):
        """The failure that matters most: a source goes down, the remaining
        signals read QUIET, and the alert silently closes."""
        r = reading(0.25, 0.0, errors=(0,))
        assert r.level is Level.QUIET
        assert decide(open_lvl, r) is Action.REFRESH

    def test_no_data_does_nothing(self):
        assert decide(Level.RICH, reading(0.3, errors=(0,))) is Action.NONE


class TestTitles:
    def test_round_trip(self):
        r = reading(0.25, 0.12)
        t = title_for(r)
        assert t.startswith("[regime] RICH")
        assert level_from_title(t) is Level.RICH

    def test_foreign_titles(self):
        assert level_from_title("Fix the bot") is None
        assert level_from_title("[regime] NONSENSE") is None


class FakeGitHub:
    repo = "owner/repo"

    def __init__(self, open_issue=None):
        self.issue = open_issue
        self.calls = []

    def find_open(self):
        return self.issue

    def open(self, title, body):
        self.calls.append(("open", title, body))

    def update(self, number, **fields):
        self.calls.append(("update", number, fields))

    def comment(self, number, body):
        self.calls.append(("comment", number, body))


class TestApply:
    def test_opens_and_mentions_the_owner(self):
        gh = FakeGitHub()
        assert apply(reading(0.25), gh) is Action.OPEN
        kind, title, body = gh.calls[0]
        assert kind == "open" and title.startswith("[regime] RICH")
        assert "@owner" in body

    def test_refresh_does_not_comment(self):
        """Comments notify; a refresh at the same level must not."""
        gh = FakeGitHub({"number": 7, "title": "[regime] WARMING — S0 15.0%"})
        apply(reading(0.15), gh)
        assert [c[0] for c in gh.calls] == ["update"]

    def test_escalation_comments(self):
        gh = FakeGitHub({"number": 7, "title": "[regime] WARMING"})
        assert apply(reading(0.3), gh) is Action.ESCALATE
        kinds = [c[0] for c in gh.calls]
        assert kinds == ["update", "comment"]
        assert "WARMING → RICH" in gh.calls[1][2]

    def test_quiet_closes(self):
        gh = FakeGitHub({"number": 7, "title": "[regime] RICH"})
        assert apply(reading(0.0), gh) is Action.CLOSE
        assert gh.calls[-1] == ("update", 7,
                                {"state": "closed", "state_reason": "completed"})

    def test_webhook_failure_does_not_fail_the_run(self, monkeypatch):
        def boom(url, text):
            raise OSError("unreachable")
        monkeypatch.setattr(alerts, "post_webhook", boom)
        assert apply(reading(0.25), FakeGitHub(), webhook="http://x") is Action.OPEN


class TestReport:
    def test_gross_signals_are_not_compared_to_cash(self):
        r = Reading(signals=[sig(0.12, name="F", is_net=False)])
        assert "gross, n/a" in render_markdown(r)

    def test_unavailable_and_incomplete_are_stated(self):
        md = render_markdown(reading(0.25, 0.0, errors=(1,)))
        assert "unavailable" in md
        assert "incomplete" in md

    def test_hurdle_is_shown(self):
        assert f"{DEFAULT_HURDLE:.2%}" in render_markdown(reading(0.0))


class TestContextSignals:
    """HLP's trailing return predicts its next at +0.03. It must be visible
    and must never move the alert."""

    def _r(self, driver, context, *, context_down=False):
        ctx = Signal("HLP", T, value=None if context_down else context,
                     error="down" if context_down else None,
                     drives_regime=False)
        return Reading(signals=[sig(driver, name="carry"), ctx])

    def test_context_cannot_raise_the_regime(self):
        assert self._r(0.0, 0.90).level is Level.QUIET

    def test_context_outage_does_not_make_the_reading_incomplete(self):
        r = self._r(0.0, None, context_down=True)
        assert r.complete
        assert decide(Level.RICH, r) is Action.CLOSE

    def test_context_is_labelled_and_has_no_thresholds(self):
        md = render_markdown(self._r(0.0, 0.5))
        assert "context only" in md
        assert "| context only | — |" in md

    def test_context_never_appears_in_the_alert_title(self):
        r = Reading(signals=[sig(0.25, name="carry"),
                             Signal("HLP", T, value=0.5, drives_regime=False)])
        assert "HLP" not in title_for(r)
        assert "carry" in title_for(r)


class TestHysteresis:
    """A 7-day funding window flipped level 15-36 times a year near a
    threshold; the fix is a 30-day window plus a one-point buffer on the way
    down. Rises must stay immediate."""

    @pytest.mark.parametrize("value,want", [
        (0.195, Action.REFRESH),     # within 1pt of RICH: held
        (0.185, Action.DEESCALATE),  # clearly below: moves down
    ])
    def test_rich_is_held_near_its_threshold(self, value, want):
        assert decide(Level.RICH, reading(value)) is want

    @pytest.mark.parametrize("value,want", [
        (0.095, Action.REFRESH),
        (0.085, Action.CLOSE),
    ])
    def test_warming_is_held_near_its_threshold(self, value, want):
        assert decide(Level.WARMING, reading(value)) is want

    def test_rises_are_not_delayed(self):
        assert decide(Level.WARMING, reading(0.20)) is Action.ESCALATE
        assert decide(None, reading(0.10)) is Action.OPEN

    def test_hysteresis_cannot_open_an_alert(self):
        """Slack applies to open alerts only; 9.5% with nothing open is
        QUIET."""
        assert decide(None, reading(0.095)) is Action.NONE

    def test_held_alert_keeps_its_title_and_says_why(self):
        gh = FakeGitHub({"number": 3, "title": "[regime] RICH — S0 25.0%"})
        assert apply(reading(0.195), gh) is Action.REFRESH
        (kind, _, fields), = gh.calls
        assert kind == "update" and "title" not in fields
        assert "Regime: **RICH**" in fields["body"]
        assert "raw reading WARMING" in fields["body"]

    def test_deescalation_is_to_the_held_level(self):
        gh = FakeGitHub({"number": 3, "title": "[regime] RICH"})
        apply(reading(0.185), gh)
        assert "RICH → WARMING" in gh.calls[-1][2]

    def test_partial_data_refresh_shows_the_open_level(self):
        gh = FakeGitHub({"number": 3, "title": "[regime] RICH"})
        assert apply(reading(0.0, 0.30, errors=(1,)), gh) is Action.REFRESH
        assert "Regime: **RICH**" in gh.calls[0][2]["body"]


class TestLockedRate:
    """The Deribit locked rate: a regime driver on its 30-day mean only."""

    @staticmethod
    def _futures(premium_ann, start, days=60):
        import datetime as dt
        from polybot.venues.deribit import last_friday, quarterly_name
        exp = last_friday(start.year + (start.month > 9), ((start.month + 2) // 3 * 3) % 12 + 3)
        exp_ms = int(dt.datetime(exp.year, exp.month, exp.day, 8,
                                 tzinfo=dt.timezone.utc).timestamp() * 1000)
        ticks, close, spot = [], [], {}
        for i in range(days):
            d = start + dt.timedelta(days=i)
            t = int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)
            left = (exp_ms - (t + 86_400_000)) / 86_400_000
            ticks.append(t)
            close.append(100.0 * (1 + premium_ann * left / 365))
            spot[d.isoformat()] = 100.0
        return {quarterly_name("BTC", exp): {"expiry_ms": exp_ms, "ticks": ticks,
                                             "close": close}}, spot

    def test_thirty_day_mean_recovers_the_rate(self):
        import datetime as dt
        from polybot.monitor.regime import basis_30d_mean
        fut, spot = self._futures(0.09, dt.date(2025, 1, 2))
        mean, n = basis_30d_mean(fut, spot)
        assert mean == pytest.approx(0.09, rel=1e-6)
        assert n == 30

    def test_too_little_history_is_unavailable(self):
        import datetime as dt
        from polybot.monitor.regime import basis_30d_mean
        fut, spot = self._futures(0.09, dt.date(2025, 1, 2), days=5)
        assert basis_30d_mean(fut, spot) is None

    def test_locked_rate_thresholds_match_the_calibration(self):
        from polybot.monitor.regime import DEFAULT_THRESHOLDS
        t = DEFAULT_THRESHOLDS["BTC/ETH 3m locked rate"]
        # sUSDe-regime means from 2024-26: QUIET 4.5%, WARMING 7.4%, RICH 13.2%.
        assert t.classify(0.045) is Level.QUIET
        assert t.classify(0.132) is Level.RICH

    def test_env_override_key(self, monkeypatch):
        monkeypatch.setenv("REGIME_BASIS_RICH", "15")
        assert thresholds_from_env()["BTC/ETH 3m locked rate"].rich == pytest.approx(0.15)


class TestGap:
    def test_gap_is_context_only(self):
        from polybot.monitor.regime import gap_signal
        f = Signal("f", T, value=0.40)
        b = Signal("b", T, value=0.05)
        g = gap_signal(f, b)
        assert g.value == pytest.approx(0.35)
        assert not g.drives_regime
        r = Reading(signals=[Signal("carry", T, value=0.0), g])
        assert r.level is Level.QUIET

    def test_gap_needs_both_legs(self):
        from polybot.monitor.regime import gap_signal
        g = gap_signal(Signal("f", T, value=0.1), Signal("b", T, error="down"))
        assert not g.available


class TestRiskGauges:
    def test_trend_gap(self):
        from polybot.monitor.regime import trend_gap
        closes = [100.0] * 199 + [120.0]
        assert trend_gap(closes) == pytest.approx(120.0 / 100.1 - 1)
        assert trend_gap([1.0] * 50) is None

    def test_percentile_rank(self):
        from polybot.monitor.regime import percentile_rank
        assert percentile_rank([1, 2, 3, 4], 2) == pytest.approx(0.5)

    def test_gauges_never_move_the_alert_and_are_not_compared_with_cash(self):
        from polybot.monitor.regime import _NEVER
        g = Signal("Trend", _NEVER, value=0.25, is_net=False,
                   drives_regime=False, is_yield=False)
        r = Reading(signals=[Signal("carry", T, value=0.0), g])
        assert r.level is Level.QUIET
        md = render_markdown(r)
        assert "| **+25.00%** | — | context only | — |" in md

    def test_unavailable_gauge_does_not_print_infinite_thresholds(self):
        from polybot.monitor.regime import _NEVER
        g = Signal("Trend", _NEVER, error="down", drives_regime=False, is_yield=False)
        md = render_markdown(Reading(signals=[Signal("carry", T, value=0.0), g]))
        assert "inf" not in md
