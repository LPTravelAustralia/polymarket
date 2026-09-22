"""Odds consensus, market matching, and the sports fair-value model."""

import time

import pytest

from polybot.clients.gamma import MarketRef
from polybot.models.matching import match_market, normalize, similarity, token_set
from polybot.models.odds_feed import OddsEvent, StaticOddsProvider, build_consensus
from polybot.models.sports import SportsFairValue

HOUR = 3600.0


def h2h_book(key, name_a, price_a, name_b, price_b):
    return {
        "key": key,
        "markets": [{
            "key": "h2h",
            "outcomes": [
                {"name": name_a, "price": price_a},
                {"name": name_b, "price": price_b},
            ],
        }],
    }


def event(commence=None, home="Los Angeles Lakers", away="Boston Celtics",
          probs=(0.60, 0.40), books=3, spread=0.01, eid="e1"):
    return OddsEvent(
        event_id=eid,
        sport_key="basketball_nba",
        commence_time=commence if commence is not None else time.time() + 6 * HOUR,
        home_team=home,
        away_team=away,
        consensus={home: probs[0], away: probs[1]},
        book_count=books,
        spread=spread,
    )


class TestConsensus:
    def test_devigs_a_single_book(self):
        books = [h2h_book("pinnacle", "A", 1.5, "B", 2.6)]
        consensus, count, _ = build_consensus(books)
        assert count == 1
        assert sum(consensus.values()) == pytest.approx(1.0, abs=1e-6)
        assert consensus["A"] > consensus["B"]

    def test_removes_the_overround(self):
        """Raw implied probabilities sum above 1; fair ones must sum to 1."""
        books = [h2h_book("pinnacle", "A", 1.5, "B", 2.6)]
        raw = 1 / 1.5 + 1 / 2.6
        assert raw > 1.0
        consensus, _, _ = build_consensus(books)
        assert sum(consensus.values()) == pytest.approx(1.0, abs=1e-6)

    def test_sharp_books_weighted_higher(self):
        """Pinnacle at 0.70 and a retail book at 0.50, weighted 3:1, should
        land at 0.65 -- not the naive 0.60 midpoint."""
        books = [
            h2h_book("pinnacle", "A", 1 / 0.7, "B", 1 / 0.3),
            h2h_book("someretailbook", "A", 2.0, "B", 2.0),
        ]
        consensus, count, spread = build_consensus(books)
        assert count == 2
        assert consensus["A"] == pytest.approx(0.65, abs=1e-6)
        assert spread == pytest.approx(0.10, abs=1e-6)

    def test_skips_three_way_markets(self):
        """A draw outcome would corrupt a two-way devig, so the book is
        skipped rather than silently mangled."""
        three_way = {
            "key": "pinnacle",
            "markets": [{"key": "h2h", "outcomes": [
                {"name": "A", "price": 2.5},
                {"name": "Draw", "price": 3.2},
                {"name": "B", "price": 3.0},
            ]}],
        }
        consensus, count, _ = build_consensus([three_way])
        assert count == 0
        assert consensus == {}

    def test_ignores_books_without_h2h(self):
        book = {"key": "x", "markets": [{"key": "spreads", "outcomes": []}]}
        _, count, _ = build_consensus([book])
        assert count == 0

    def test_handles_malformed_prices(self):
        bad = {"key": "x", "markets": [{"key": "h2h", "outcomes": [
            {"name": "A", "price": "abc"}, {"name": "B", "price": 2.0}]}]}
        _, count, _ = build_consensus([bad])
        assert count == 0

    def test_empty_input(self):
        assert build_consensus([]) == ({}, 0, 0.0)


class TestNameMatching:
    def test_normalize_strips_punctuation_and_case(self):
        assert normalize("St. Louis Blues!") == "st louis blues"

    def test_stopwords_removed(self):
        assert "the" not in token_set("The Lakers")

    def test_identical_names(self):
        assert similarity("Lakers", "Lakers") == pytest.approx(1.0)

    def test_subset_names_match_strongly(self):
        """Polymarket says 'Lakers', the book says 'Los Angeles Lakers'.
        Plain Jaccard scores that 0.33 and would reject a perfect match."""
        assert similarity("Lakers", "Los Angeles Lakers") > 0.9

    def test_unrelated_names_do_not_match(self):
        assert similarity("Lakers", "Celtics") == 0.0

    def test_empty_name(self):
        assert similarity("", "Lakers") == 0.0


class TestMarketMatching:
    def test_matches_short_names_to_full_names(self):
        result = match_market(["Lakers", "Celtics"], [event()])
        assert result is not None
        assert result.confidence > 0.9
        assert result.outcome_to_team["Lakers"] == "Los Angeles Lakers"
        assert result.probability_for("Lakers") == pytest.approx(0.60)

    def test_handles_reversed_order(self):
        result = match_market(["Celtics", "Lakers"], [event()])
        assert result is not None
        assert result.outcome_to_team["Celtics"] == "Boston Celtics"

    def test_refuses_ambiguous_duplicate_fixtures(self):
        """Two identical fixtures (a doubleheader) must be refused, not
        resolved by coin flip -- guessing here prices one game with the
        other's probability."""
        result = match_market(["Lakers", "Celtics"], [event(eid="a"), event(eid="b")])
        assert result is None

    def test_refuses_unrelated_teams(self):
        assert match_market(["Yankees", "Red Sox"], [event()]) is None

    def test_refuses_non_two_way_markets(self):
        assert match_market(["A", "B", "C"], [event()]) is None

    def test_refuses_events_far_from_market_end(self):
        now = time.time()
        far = event(commence=now + 30 * 24 * HOUR)
        assert match_market(["Lakers", "Celtics"], [far],
                            market_end_ts=now, max_time_delta_hours=48) is None

    def test_accepts_events_near_market_end(self):
        now = time.time()
        near = event(commence=now + 3 * HOUR)
        assert match_market(["Lakers", "Celtics"], [near], market_end_ts=now) is not None

    def test_ignores_unusable_events(self):
        thin = event(books=1)
        assert match_market(["Lakers", "Celtics"], [thin]) is None

    def test_empty_event_list(self):
        assert match_market(["Lakers", "Celtics"], []) is None


def market(token_ids=("tok_a", "tok_b"), outcomes=("Lakers", "Celtics"),
           end_offset=6 * HOUR):
    from datetime import datetime, timezone
    end = datetime.fromtimestamp(time.time() + end_offset, tz=timezone.utc)
    return MarketRef(
        condition_id="c1",
        question="Lakers vs Celtics",
        slug="lakers-celtics",
        category="sports",
        token_ids=list(token_ids),
        outcomes=list(outcomes),
        end_date=end.isoformat().replace("+00:00", "Z"),
    )


class TestSportsFairValue:
    def test_binds_and_prices(self):
        svc = SportsFairValue(StaticOddsProvider([event()]),
                              sport_keys=["basketball_nba"])
        assert svc.register([market()]) == 1

        result = svc.probability_fn("tok_a")
        assert result is not None
        prob, uncertainty = result
        assert prob == pytest.approx(0.60)
        assert uncertainty > 0

    def test_prices_both_sides_consistently(self):
        svc = SportsFairValue(StaticOddsProvider([event()]),
                              sport_keys=["basketball_nba"])
        svc.register([market()])
        a = svc.probability_fn("tok_a")[0]
        b = svc.probability_fn("tok_b")[0]
        assert a + b == pytest.approx(1.0, abs=1e-6)

    def test_declines_unknown_token(self):
        svc = SportsFairValue(StaticOddsProvider([event()]))
        svc.register([market()])
        assert svc.probability_fn("nonexistent") is None

    def test_declines_once_the_game_is_about_to_start(self):
        """Pre-game odds are worthless in-play. Without a live feed the only
        safe answer is to stop quoting."""
        soon = event(commence=time.time() + 60)
        svc = SportsFairValue(StaticOddsProvider([soon]),
                              sport_keys=["basketball_nba"],
                              stop_quoting_before_start_seconds=900)
        svc.register([market(end_offset=60)])
        assert svc.probability_fn("tok_a") is None

    def test_unmatched_markets_are_reported_not_guessed(self):
        svc = SportsFairValue(StaticOddsProvider([event()]),
                              sport_keys=["basketball_nba"])
        bound = svc.register([market(outcomes=("Yankees", "Red Sox"))])
        assert bound == 0
        assert svc.unmatched
        assert "Bound 0 markets" in svc.coverage_report()

    def test_no_odds_available(self):
        svc = SportsFairValue(StaticOddsProvider([]), sport_keys=["basketball_nba"])
        assert svc.register([market()]) == 0
        assert svc.probability_fn("tok_a") is None
