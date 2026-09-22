"""Does the model actually beat the market?

This is the question that decides whether any of the rest is worth running.
A market-making strategy with no informational edge earns the spread and
loses it again to adverse selection; what turns that into a business is a
fair value that is genuinely better than the book's.

So before risking money, score your model against the market price on
resolved markets. If the skill score is not positive, the honest conclusion
is that you do not have an edge yet -- and finding that out here costs
nothing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

EPS = 1e-15


@dataclass
class Observation:
    """One resolved market: what the model said, what the book said, what
    happened."""

    model_prob: float
    market_prob: float
    outcome: int          # 1 if the YES side resolved true, else 0
    token_id: str = ""
    weight: float = 1.0


def brier(predictions: list[float], outcomes: list[int]) -> float:
    """Mean squared error. 0 is perfect, 0.25 is a coin flip."""
    if not predictions:
        return float("nan")
    return sum((p - y) ** 2 for p, y in zip(predictions, outcomes)) / len(predictions)


def log_loss(predictions: list[float], outcomes: list[int]) -> float:
    """Punishes confident errors far harder than Brier does.

    Worth checking alongside Brier: a model can win on Brier while being
    occasionally, catastrophically overconfident, and on a prediction market
    that is exactly the failure that empties an account.
    """
    if not predictions:
        return float("nan")
    total = 0.0
    for p, y in zip(predictions, outcomes):
        p = min(max(p, EPS), 1 - EPS)
        total += -(y * math.log(p) + (1 - y) * math.log(1 - p))
    return total / len(predictions)


@dataclass
class CalibrationBin:
    lower: float
    upper: float
    n: int
    mean_predicted: float
    observed_rate: float

    @property
    def error(self) -> float:
        return self.mean_predicted - self.observed_rate


def calibration_curve(
    predictions: list[float], outcomes: list[int], bins: int = 10
) -> list[CalibrationBin]:
    """Are things the model calls 70% actually happening 70% of the time?

    A model can be well-calibrated and useless (always predicting the base
    rate), or badly calibrated and profitable. But systematic miscalibration
    in one direction is a bug worth finding before it costs money.
    """
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for p, y in zip(predictions, outcomes):
        idx = min(int(p * bins), bins - 1)
        buckets[idx].append((p, y))

    out = []
    for i, bucket in enumerate(buckets):
        if not bucket:
            continue
        preds = [p for p, _ in bucket]
        obs = [y for _, y in bucket]
        out.append(
            CalibrationBin(
                lower=i / bins,
                upper=(i + 1) / bins,
                n=len(bucket),
                mean_predicted=sum(preds) / len(preds),
                observed_rate=sum(obs) / len(obs),
            )
        )
    return out


@dataclass
class ModelScore:
    n: int
    model_brier: float
    market_brier: float
    model_log_loss: float
    market_log_loss: float
    calibration: list[CalibrationBin] = field(default_factory=list)

    @property
    def skill_score(self) -> float:
        """Brier skill relative to the market. Positive means the model beats
        the book; zero means it adds nothing."""
        if self.market_brier <= 0:
            return float("nan")
        return 1.0 - (self.model_brier / self.market_brier)

    @property
    def beats_market(self) -> bool:
        return self.skill_score > 0

    @property
    def is_meaningful(self) -> bool:
        """Small samples produce impressive-looking skill scores by luck.

        200 resolved markets is a floor, not a guarantee -- prediction market
        outcomes are correlated (one news event resolves many markets at
        once), so effective sample size is smaller than it looks.
        """
        return self.n >= 200

    def verdict(self) -> str:
        if not self.is_meaningful:
            return (
                f"INCONCLUSIVE: only {self.n} observations. Collect at least 200 "
                "resolved markets, and bear in mind correlated outcomes make the "
                "effective sample smaller than the count suggests."
            )
        if not self.beats_market:
            return (
                f"NO EDGE: skill score {self.skill_score:+.4f}. The model does not "
                "beat the market price. Do not trade this -- quoting around a "
                "fair value no better than the book earns the spread and loses it "
                "to adverse selection."
            )
        if self.skill_score < 0.01:
            return (
                f"MARGINAL: skill score {self.skill_score:+.4f}. Real but thin. "
                "Check it clears your measured adverse selection before trading."
            )
        return (
            f"EDGE: skill score {self.skill_score:+.4f}, model Brier "
            f"{self.model_brier:.4f} vs market {self.market_brier:.4f}."
        )


def score_model(observations: list[Observation], bins: int = 10) -> ModelScore:
    model_p = [o.model_prob for o in observations]
    market_p = [o.market_prob for o in observations]
    y = [o.outcome for o in observations]

    return ModelScore(
        n=len(observations),
        model_brier=brier(model_p, y),
        market_brier=brier(market_p, y),
        model_log_loss=log_loss(model_p, y),
        market_log_loss=log_loss(market_p, y),
        calibration=calibration_curve(model_p, y, bins),
    )


def render_score(score: ModelScore) -> str:
    lines = [
        "Model vs market",
        "=" * 60,
        f"  observations      {score.n:,}",
        f"  Brier   model     {score.model_brier:.5f}",
        f"          market    {score.market_brier:.5f}",
        f"  LogLoss model     {score.model_log_loss:.5f}",
        f"          market    {score.market_log_loss:.5f}",
        f"  skill score       {score.skill_score:+.5f}",
        "",
        score.verdict(),
    ]
    if score.calibration:
        lines += ["", "  calibration:", f"    {'range':>12} {'n':>7} {'pred':>8} {'actual':>8} {'err':>8}"]
        for b in score.calibration:
            lines.append(
                f"    {b.lower:.1f}-{b.upper:.1f}".rjust(16)
                + f" {b.n:>7,} {b.mean_predicted:>8.3f} "
                f"{b.observed_rate:>8.3f} {b.error:>+8.3f}"
            )
    return "\n".join(lines)
