"""Turn regime readings into notifications without crying wolf.

Alerts are GitHub issues, because a repository owner is notified of new
issues and comments by default and it needs no secrets beyond the workflow's
own token. The open issue *is* the state: its title carries the regime it
last reported, so the monitor needs nothing else to remember.

The rules, in order of how much they matter:

1. **Missing data never produces an all-clear.** If any source fails, an
   open alert can be escalated but not downgraded or closed. A DefiLlama
   outage must not read as "the market went quiet".
2. **Notify on change, not on every run.** A reading at the same level
   silently refreshes the issue body. A different level comments, which
   notifies; returning to QUIET comments and closes.
3. **QUIET never opens anything.** Most runs, for most of the year, should
   produce no notification at all.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum

from .regime import Level, Reading, render_markdown

log = logging.getLogger(__name__)

TITLE_PREFIX = "[regime]"
LABEL = "regime-alert"


class Action(Enum):
    NONE = "none"
    OPEN = "open"
    REFRESH = "refresh"        # same level: update body, no notification
    ESCALATE = "escalate"
    DEESCALATE = "deescalate"
    CLOSE = "close"


def decide(open_level: Level | None, reading: Reading) -> Action:
    """What to do given the open alert's level (None if none is open)."""
    new = reading.held_level(open_level)
    if new is None:
        return Action.NONE
    if open_level is None:
        return Action.OPEN if new >= Level.WARMING else Action.NONE
    if new == open_level:
        return Action.REFRESH
    if new > open_level:
        return Action.ESCALATE
    if not reading.complete:
        return Action.REFRESH
    return Action.CLOSE if new == Level.QUIET else Action.DEESCALATE


def title_for(reading: Reading, level: Level | None = None) -> str:
    lvl = level if level is not None else reading.level
    name = lvl.name if lvl is not None else "UNKNOWN"
    tops = []
    if lvl is not None and lvl > Level.QUIET:
        live = [s for s in reading.drivers if s.available]
        tops = [s for s in live if s.level is not None and s.level >= lvl]
        if not tops and live:
            # Held by hysteresis: name the signal doing the holding.
            tops = [max(live, key=lambda s: (s.level, s.value))]
    names = [f"{s.name} {s.value:.1%}" for s in tops]
    return f"{TITLE_PREFIX} {name}" + (f" — {', '.join(names)}" if names else "")


def level_from_title(title: str) -> Level | None:
    if not title.startswith(TITLE_PREFIX):
        return None
    word = title[len(TITLE_PREFIX):].strip().split(" ")[0]
    try:
        return Level[word]
    except KeyError:
        return None


# ------------------------------------------------------------------ GitHub

@dataclass
class GitHubIssues:
    repo: str
    token: str
    api: str = "https://api.github.com"

    @classmethod
    def from_env(cls) -> "GitHubIssues":
        return cls(repo=os.environ["GITHUB_REPOSITORY"],
                   token=os.environ["GITHUB_TOKEN"],
                   api=os.environ.get("GITHUB_API_URL", "https://api.github.com"))

    def _call(self, method: str, path: str, body: dict | None = None):
        req = urllib.request.Request(
            f"{self.api}/repos/{self.repo}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "polybot-regime-monitor",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else None

    def find_open(self) -> dict | None:
        issues = self._call("GET", "/issues?state=open&per_page=100") or []
        for i in issues:
            # The issues endpoint also returns pull requests.
            if "pull_request" not in i and i["title"].startswith(TITLE_PREFIX):
                return i
        return None

    def open(self, title: str, body: str) -> dict:
        try:
            return self._call("POST", "/issues",
                              {"title": title, "body": body, "labels": [LABEL]})
        except urllib.error.HTTPError as exc:
            # The label is cosmetic -- issues are found by title -- so a
            # rejected label must not cost the alert.
            if exc.code != 422:
                raise
            return self._call("POST", "/issues", {"title": title, "body": body})

    def update(self, number: int, **fields) -> None:
        self._call("PATCH", f"/issues/{number}", fields)

    def comment(self, number: int, body: str) -> None:
        self._call("POST", f"/issues/{number}/comments", {"body": body})


def post_webhook(url: str, text: str) -> None:
    """Optional Slack/Discord push. Both accept this shape: Slack reads
    `text`, Discord reads `content`, each ignores the other."""
    req = urllib.request.Request(
        url, data=json.dumps({"text": text, "content": text[:1900]}).encode(),
        headers={"Content-Type": "application/json",
                 "User-Agent": "polybot-regime-monitor"}, method="POST")
    with urllib.request.urlopen(req, timeout=20):
        pass


def apply(reading: Reading, gh: GitHubIssues,
          *, webhook: str | None = None) -> Action:
    """Reconcile the open alert issue with a fresh reading."""
    current = gh.find_open()
    open_level = level_from_title(current["title"]) if current else None
    action = decide(open_level, reading)
    # A refresh never changes the level, including when partial data is
    # holding it up -- so the body must show what the title shows.
    target = (open_level if action is Action.REFRESH
              else reading.held_level(open_level))
    body = render_markdown(reading, shown=target)
    owner = gh.repo.split("/")[0]

    if action is Action.OPEN:
        gh.open(title_for(reading, target),
                body + f"\n\ncc @{owner} — this issue closes itself when the "
                       "regime returns to QUIET.")
    elif action is Action.REFRESH:
        gh.update(current["number"], body=body)
    elif action in (Action.ESCALATE, Action.DEESCALATE):
        verb = "up" if action is Action.ESCALATE else "down"
        gh.update(current["number"], title=title_for(reading, target),
                  body=body)
        gh.comment(current["number"],
                   f"Regime moved {verb}: **{open_level.name} → "
                   f"{target.name}**.\n\n" + body)
    elif action is Action.CLOSE:
        gh.comment(current["number"],
                   f"Regime back to **QUIET** from {open_level.name}. "
                   "Closing.\n\n" + body)
        gh.update(current["number"], state="closed", state_reason="completed")

    if webhook and action in (Action.OPEN, Action.ESCALATE,
                              Action.DEESCALATE, Action.CLOSE):
        lvl = target.name if target is not None else "UNKNOWN"
        try:
            post_webhook(webhook, f"Regime monitor: {action.value} -> {lvl}. "
                                  f"{title_for(reading, target)}")
        except Exception as exc:                      # noqa: BLE001
            # The issue is the record; a failed push should not fail the run.
            log.warning("webhook failed: %s", exc)
    return action
