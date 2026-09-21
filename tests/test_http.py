"""Regression tests for the pagination bugs found when the profiler was first
run against the live Data API.

Both were discovered the same way -- by running it -- and both failed in the
direction that silently corrupts research output rather than crashing loudly.
"""

import httpx
import pytest

from polybot.clients.http import OFFSET_CEILING, ClientRequestError, JsonClient


def client_with(handler, **kwargs) -> JsonClient:
    c = JsonClient("https://example.test", rate_per_sec=1000, max_retries=3, **kwargs)
    c._client = httpx.Client(transport=httpx.MockTransport(handler))
    return c


class TestRetryPolicy:
    def test_does_not_retry_client_errors(self):
        """A 400 means the request is wrong. Retrying it five times just
        delays the same failure and burns rate limit."""
        calls = []

        def handler(request):
            calls.append(request.url)
            return httpx.Response(400, json={"error": "bad offset"})

        with pytest.raises(ClientRequestError) as exc:
            client_with(handler).get("/trades")
        assert exc.value.status_code == 400
        assert len(calls) == 1, "should fail fast, not retry"

    def test_does_retry_server_errors(self):
        calls = []

        def handler(request):
            calls.append(request.url)
            if len(calls) < 3:
                return httpx.Response(503)
            return httpx.Response(200, json={"ok": True})

        assert client_with(handler).get("/x") == {"ok": True}
        assert len(calls) == 3

    def test_retries_rate_limits(self):
        calls = []

        def handler(request):
            calls.append(1)
            return httpx.Response(429 if len(calls) == 1 else 200, json=[])

        client_with(handler).get("/x")
        assert len(calls) == 2


class TestPagination:
    def test_offset_cap_returns_partial_results_instead_of_crashing(self):
        """The original bug: the API 400s past its offset ceiling, the client
        retried, then raised -- discarding 10,000 already-fetched trades."""
        def handler(request):
            offset = int(request.url.params.get("offset", 0))
            if offset >= 1_000:
                return httpx.Response(400, json={"error": "offset too large"})
            return httpx.Response(200, json=[{"i": offset + n} for n in range(500)])

        rows = list(client_with(handler).paginate_offset("/trades", limit=500))
        assert len(rows) == 1_000, "must keep what was already fetched"

    def test_stops_at_offset_ceiling(self):
        """Never page past the documented wall, even if the server would
        answer -- it cannot return real data up there."""
        def handler(request):
            return httpx.Response(200, json=[{"n": 1}] * 500)

        rows = list(
            client_with(handler).paginate_offset("/trades", limit=500, max_items=None)
        )
        assert len(rows) <= OFFSET_CEILING

    def test_short_page_ends_pagination(self):
        def handler(request):
            offset = int(request.url.params.get("offset", 0))
            return httpx.Response(200, json=[{"n": 1}] * (500 if offset == 0 else 3))

        rows = list(client_with(handler).paginate_offset("/x", limit=500))
        assert len(rows) == 503

    def test_empty_first_page(self):
        rows = list(
            client_with(lambda r: httpx.Response(200, json=[])).paginate_offset("/x")
        )
        assert rows == []

    def test_max_items_respected(self):
        def handler(request):
            return httpx.Response(200, json=[{"n": 1}] * 500)

        rows = list(client_with(handler).paginate_offset("/x", limit=500, max_items=120))
        assert len(rows) == 120

    def test_unwraps_data_envelope(self):
        def handler(request):
            offset = int(request.url.params.get("offset", 0))
            body = [{"n": 1}] * (2 if offset == 0 else 0)
            return httpx.Response(200, json={"data": body})

        rows = list(client_with(handler).paginate_offset("/x", limit=500))
        assert len(rows) == 2


class TestLeaderboardNormalisation:
    def test_accepts_v2_field_names(self):
        """/v2/leaderboard uses user_id/user_name. The original normaliser
        only looked for proxyWallet/name and silently returned nothing."""
        from polybot.clients.data_api import DataAPI

        rows = DataAPI._normalise_leaderboard({
            "data": [{
                "rank": 1,
                "user_id": "0xabc",
                "user_name": "HomeRunHazard",
                "pnl": 1202263.0,
                "volume": 1458351.7,
            }]
        })
        assert len(rows) == 1
        assert rows[0]["wallet"] == "0xabc"
        assert rows[0]["name"] == "HomeRunHazard"
        assert rows[0]["pnl"] == pytest.approx(1202263.0)

    def test_accepts_legacy_field_names(self):
        from polybot.clients.data_api import DataAPI

        rows = DataAPI._normalise_leaderboard(
            [{"proxyWallet": "0xdef", "name": "legacy", "pnl": 5.0}]
        )
        assert rows[0]["wallet"] == "0xdef"

    def test_skips_rows_without_a_wallet(self):
        from polybot.clients.data_api import DataAPI

        assert DataAPI._normalise_leaderboard([{"pnl": 1.0}]) == []

    def test_handles_unexpected_shape(self):
        from polybot.clients.data_api import DataAPI

        assert DataAPI._normalise_leaderboard("nonsense") == []
