"""Shared HTTP plumbing: retries, backoff, and a token-bucket rate limiter.

Polymarket's public read APIs are unauthenticated but they will rate-limit a
profiling run that walks 200k trades. Pace yourself.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)

RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}

# The Data API refuses offsets past ~10,000 with a 400. That is a hard wall,
# not an error to retry: deep history simply is not reachable by paging.
OFFSET_CEILING = 10_000


class ClientRequestError(RuntimeError):
    """A 4xx that will not succeed on retry."""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


class RateLimiter:
    """Simple thread-safe token bucket."""

    def __init__(self, rate_per_sec: float, burst: int | None = None):
        self.rate = max(rate_per_sec, 0.01)
        self.capacity = burst if burst is not None else max(1, int(rate_per_sec))
        self._tokens = float(self.capacity)
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(
                    self.capacity, self._tokens + (now - self._last) * self.rate
                )
                self._last = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait = (1.0 - self._tokens) / self.rate
            time.sleep(wait)


class JsonClient:
    """Thin JSON-over-HTTP client with retry and rate limiting."""

    def __init__(
        self,
        base_url: str,
        *,
        rate_per_sec: float = 8.0,
        timeout: float = 30.0,
        max_retries: int = 5,
        headers: dict[str, str] | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.limiter = RateLimiter(rate_per_sec)
        self.max_retries = max_retries
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": "polybot/0.1", **(headers or {})},
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "JsonClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        clean = {k: v for k, v in (params or {}).items() if v is not None}

        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            self.limiter.acquire()
            try:
                resp = self._client.get(url, params=clean)
                if resp.status_code in RETRY_STATUS:
                    raise httpx.HTTPStatusError(
                        f"retryable status {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                # A non-retryable 4xx means the request itself is wrong.
                # Retrying it five times just delays the same failure and
                # burns rate limit, so fail fast and let the caller decide.
                if 400 <= resp.status_code < 500:
                    raise ClientRequestError(
                        f"{resp.status_code} from {url}", resp.status_code
                    )
                resp.raise_for_status()
                return resp.json()
            except ClientRequestError:
                raise
            except (httpx.HTTPError, ValueError) as exc:
                last_exc = exc
                if attempt == self.max_retries - 1:
                    break
                # Honour Retry-After when the server sends one.
                delay = 2.0**attempt + random.uniform(0, 0.4)
                resp_obj = getattr(exc, "response", None)
                if resp_obj is not None:
                    retry_after = resp_obj.headers.get("Retry-After")
                    if retry_after:
                        try:
                            delay = max(delay, float(retry_after))
                        except ValueError:
                            pass
                log.warning(
                    "GET %s failed (%s), retrying in %.1fs [%d/%d]",
                    url, exc, delay, attempt + 1, self.max_retries,
                )
                time.sleep(delay)

        raise RuntimeError(f"GET {url} failed after {self.max_retries} attempts") from last_exc

    def paginate_offset(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        limit: int = 500,
        max_items: int | None = None,
        page_key: str | None = None,
    ):
        """Walk an offset/limit paginated endpoint, yielding items.

        Stops on a short page, which is how the Data API signals the end.
        """
        offset = 0
        yielded = 0
        while True:
            if offset >= OFFSET_CEILING:
                log.warning(
                    "%s: stopping at offset %d (API ceiling). Deeper history is "
                    "not reachable by paging -- results cover the most recent "
                    "%d records only.",
                    path, offset, yielded,
                )
                return

            try:
                page = self.get(path, {**(params or {}), "limit": limit, "offset": offset})
            except ClientRequestError as exc:
                # Walking off the end of a paginated endpoint is a normal stop
                # condition, not a failure. Returning what we have beats
                # discarding thousands of already-fetched rows.
                log.warning(
                    "%s: pagination stopped at offset %d (%s). Returning %d records.",
                    path, offset, exc, yielded,
                )
                return

            rows = page.get(page_key, []) if isinstance(page, dict) and page_key else page
            if isinstance(rows, dict):
                rows = rows.get("data", [])
            if not rows:
                return

            for row in rows:
                yield row
                yielded += 1
                if max_items is not None and yielded >= max_items:
                    return

            if len(rows) < limit:
                return
            offset += len(rows)
