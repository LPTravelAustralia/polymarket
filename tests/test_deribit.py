"""Deribit locked-rate reconstruction."""

import datetime as dt

import pytest

from polybot.venues.deribit import (
    BasisPoint,
    LockVsFloat,
    annualised_basis,
    constant_maturity,
    last_friday,
    lock_vs_float,
    non_overlapping,
    quarterly_name,
)

DAY = 86_400_000


def ms(d):
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp() * 1000)


class TestNames:
    def test_last_friday_of_quarter(self):
        assert last_friday(2024, 12) == dt.date(2024, 12, 27)
        assert last_friday(2025, 3) == dt.date(2025, 3, 28)

    def test_no_zero_padding(self):
        assert quarterly_name("ETH", dt.date(2026, 3, 6)) == "ETH-6MAR26"


class TestBasis:
    def test_annualisation(self):
        assert annualised_basis(101.0, 100.0, 91.25) == pytest.approx(0.04)

    def test_rejects_bad_inputs(self):
        with pytest.raises(ValueError):
            annualised_basis(101.0, 0.0, 30.0)


def contract(expiry: dt.date, start: dt.date, premium_ann: float, spot=100.0):
    """A synthetic future quoting a constant annualised premium."""
    exp_ms = ms(expiry) + 8 * 3_600_000
    ticks, close = [], []
    d = start
    while d < expiry:
        t = ms(d)
        days = (exp_ms - (t + DAY)) / DAY
        ticks.append(t)
        close.append(spot * (1 + premium_ann * days / 365.0))
        d += dt.timedelta(days=1)
    return {"expiry_ms": exp_ms, "ticks": ticks, "close": close}


class TestConstantMaturity:
    def test_recovers_the_quoted_rate(self):
        f = {"A": contract(dt.date(2025, 6, 27), dt.date(2025, 1, 1), 0.08)}
        spot = {(dt.date(2025, 1, 1) + dt.timedelta(days=i)).isoformat(): 100.0
                for i in range(200)}
        pts = constant_maturity(f, spot)
        assert pts
        assert all(p.basis == pytest.approx(0.08, rel=1e-6) for p in pts)
        assert all(45 <= p.days <= 150 for p in pts)

    def test_picks_the_contract_nearest_ninety_days(self):
        spot = {(dt.date(2025, 1, 1) + dt.timedelta(days=i)).isoformat(): 100.0
                for i in range(300)}
        f = {"NEAR": contract(dt.date(2025, 3, 28), dt.date(2025, 1, 1), 0.05),
             "FAR": contract(dt.date(2025, 6, 27), dt.date(2025, 1, 1), 0.10)}
        by_day = {p.date: p for p in constant_maturity(f, spot)}
        # On 1 Jan, NEAR has ~86 days left and FAR ~176 (out of range).
        assert by_day["2025-01-01"].contract == "NEAR"
        # By mid-February NEAR is inside 45 days' reach and FAR is nearer 90.
        assert by_day["2025-03-01"].contract == "FAR"

    def test_short_dated_contracts_are_never_used(self):
        """Annualising a 10-day premium magnifies noise ~9x; skip it."""
        spot = {(dt.date(2025, 3, 1) + dt.timedelta(days=i)).isoformat(): 100.0
                for i in range(40)}
        f = {"SHORT": contract(dt.date(2025, 3, 28), dt.date(2025, 3, 1), 0.05)}
        assert constant_maturity(f, spot) == []


class TestLockVsFloat:
    def test_spread_is_floating_minus_locked(self):
        exp = dt.date(2025, 6, 27)
        b = [BasisPoint("2025-03-28", "X", 91.0, 0.06, ms(exp) + 8 * 3_600_000)]
        start = ms(dt.date(2025, 3, 29))
        hourly = [(start + h * 3_600_000, 0.10 / 8760) for h in range(24 * 92)]
        (row,) = lock_vs_float(b, hourly)
        assert row.floating == pytest.approx(0.10, rel=1e-6)
        assert row.spread == pytest.approx(0.04, rel=1e-6)

    def test_incomplete_funding_is_skipped(self):
        exp = dt.date(2025, 6, 27)
        b = [BasisPoint("2025-03-28", "X", 91.0, 0.06, ms(exp))]
        hourly = [(ms(dt.date(2025, 3, 29)) + h * 3_600_000, 0.0001) for h in range(24 * 10)]
        assert lock_vs_float(b, hourly) == []

    def test_non_overlapping_keeps_one_entry_per_contract(self):
        rows = [LockVsFloat("d1", "A", 90, 0.05, 0.06),
                LockVsFloat("d2", "A", 83, 0.05, 0.06),
                LockVsFloat("d3", "B", 90, 0.05, 0.06)]
        assert [r.start for r in non_overlapping(rows)] == ["d1", "d3"]
