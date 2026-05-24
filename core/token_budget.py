"""
Token Budget System for Asirive Copartner
==========================================
Tracks token spending per model per day. Enforces soft + hard limits to
prevent API cost overruns. Critical when running on limited API credits.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional

logger = logging.getLogger("Copartner.TokenBudget")

# Default limits (adjust in settings.yaml)
DEFAULT_DAILY_LIMIT = 500_000   # tokens per day
DEFAULT_SOFT_PCT    = 0.80      # warn at 80%
COST_PER_1K = {
    "pro":       0.00700,   # Gemini 2.5 Pro  input ~$7/1M
    "flash":     0.00030,   # Gemini 2.5 Flash input ~$0.30/1M
    "vision":    0.00030,   # same as flash for vision
    "embedding": 0.00001,   # embeddings are nearly free
}


@dataclass
class DayStats:
    date: str
    tokens_by_model: dict = field(default_factory=dict)
    cost_by_model:   dict = field(default_factory=dict)
    calls_by_model:  dict = field(default_factory=dict)
    tasks:           list = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return sum(self.tokens_by_model.values())

    @property
    def total_cost(self) -> float:
        return sum(self.cost_by_model.values())


class TokenBudget:
    """
    Tracks and enforces token spending for Copartner.

    Usage:
        budget = TokenBudget()
        if budget.can_afford(estimated_tokens=2000):
            model = budget.suggest_model()
            ...
            budget.record_usage(tokens=2000, model="pro", task="scaffold landing page")
    """

    def __init__(
        self,
        daily_limit: int = DEFAULT_DAILY_LIMIT,
        soft_pct: float = DEFAULT_SOFT_PCT,
        persist_path: str | Path = "data/token_usage.json",
    ):
        self.daily_limit = daily_limit
        self.soft_limit  = int(daily_limit * soft_pct)
        self.persist_path = Path(persist_path)
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)

        self._history: dict[str, DayStats] = {}
        self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self):
        if self.persist_path.exists():
            try:
                raw = json.loads(self.persist_path.read_text())
                for date, data in raw.items():
                    self._history[date] = DayStats(**data)
                logger.info(f"TokenBudget: loaded {len(self._history)} days of history")
            except Exception as e:
                logger.warning(f"TokenBudget: could not load history: {e}")

    def _save(self):
        try:
            raw = {date: asdict(stats) for date, stats in self._history.items()}
            self.persist_path.write_text(json.dumps(raw, indent=2))
        except Exception as e:
            logger.warning(f"TokenBudget: could not save history: {e}")

    # ── Today's stats ─────────────────────────────────────────────────────────

    def _today_key(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _today(self) -> DayStats:
        key = self._today_key()
        if key not in self._history:
            self._history[key] = DayStats(date=key)
        return self._history[key]

    @property
    def tokens_today(self) -> int:
        return self._today().total_tokens

    @property
    def cost_today(self) -> float:
        return self._today().total_cost

    # ── Core API ──────────────────────────────────────────────────────────────

    def record_usage(self, tokens: int, model: str, task: str = ""):
        """Record token usage after a Gemini API call."""
        today = self._today()
        today.tokens_by_model[model] = today.tokens_by_model.get(model, 0) + tokens
        today.calls_by_model[model]  = today.calls_by_model.get(model, 0) + 1

        cost = (tokens / 1000) * COST_PER_1K.get(model, 0.001)
        today.cost_by_model[model] = today.cost_by_model.get(model, 0.0) + cost

        if task:
            today.tasks.append({
                "time": datetime.now().isoformat(timespec="seconds"),
                "model": model,
                "tokens": tokens,
                "task": task[:120],
            })

        self._save()

        used_pct = self.tokens_today / self.daily_limit
        if used_pct >= 1.0:
            logger.error(f"💸 Daily token limit REACHED ({self.tokens_today:,} / {self.daily_limit:,})")
        elif used_pct >= 0.80:
            logger.warning(f"⚠️  Token budget at {used_pct:.0%}. Auto-routing to Flash.")

    def can_afford(self, estimated_tokens: int) -> bool:
        """Return True if we have budget remaining for this call."""
        return (self.tokens_today + estimated_tokens) <= self.daily_limit

    def suggest_model(self) -> str:
        """
        Suggest the best model given current budget state.
        Returns 'pro' when budget is healthy, 'flash' when budget is tight.
        """
        used_pct = self.tokens_today / self.daily_limit
        if used_pct >= self.soft_limit / self.daily_limit:
            return "flash"
        return "pro"

    def status(self) -> dict:
        """Return a human-readable status dict."""
        today = self._today()
        pct   = self.tokens_today / self.daily_limit
        return {
            "date":          today.date,
            "tokens_used":   self.tokens_today,
            "daily_limit":   self.daily_limit,
            "pct_used":      f"{pct:.1%}",
            "cost_today":    f"${self.cost_today:.4f}",
            "by_model":      today.tokens_by_model,
            "status":        "🔴 LIMIT REACHED" if pct >= 1.0
                             else "🟡 HIGH USAGE"   if pct >= 0.80
                             else "🟢 OK",
        }

    def status_line(self) -> str:
        """Single-line status for display in the UI header."""
        s = self.status()
        return (
            f"Tokens: {self.tokens_today:,} / {self.daily_limit:,} "
            f"({s['pct_used']}) | Cost: {s['cost_today']} | {s['status']}"
        )
