"""Cloud spend ledger: every hosted call is estimated and recorded BEFORE it is submitted, and settled after.

Why: the owner's cloud budget is a hard $5-10 total (default stop $9, `ECHOTALES_CLOUD_BUDGET_USD`). A check that only
reads the running total after the fact cannot honour that, so `reserve` refuses before anything is sent and raises
`BudgetExceeded`. The file is `paths.CLOUD_LEDGER_PATH` (JSON) so the total survives restarts.

Numbers here are ESTIMATES built from `ECHOTALES_CLOUD_GPU_USD_PER_HOUR` (an assumption, not a measurement) and the
per-job seconds in `JOB_SECONDS` (also assumptions). Nothing in this repository has made a paid call (2026-11-21); the
first real run should replace these with the provider's billed figure through `settle(actual_usd=...)`.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from echotales.pipeline import paths  # type: ignore[import-untyped]

#: Assumed GPU seconds per job kind, used only for the pre-submit estimate. Unmeasured.
JOB_SECONDS: dict[str, float] = {"video": 150.0, "edit": 25.0, "lora": 1800.0}
#: ElevenLabs bills credits by characters on the user's plan; this per-1000-characters figure is a plan-dependent guess.
ELEVENLABS_USD_PER_1K_CHARS = 0.30


class BudgetExceeded(RuntimeError):
    """A reservation would take the total past the budget; raised before anything is submitted."""


@dataclass(slots=True)
class LedgerEntry:
    id: str
    provider: str
    kind: str
    estimated_usd: float
    actual_usd: float | None = None
    job_id: str = ""
    status: str = "reserved"
    note: str = ""
    ts: float = 0.0

    @property
    def cost(self) -> float:
        """What counts against the budget: the actual figure once known, otherwise the (conservative) estimate."""
        return self.actual_usd if self.actual_usd is not None else self.estimated_usd


def estimate_gpu_usd(seconds: float, usd_per_hour: float) -> float:
    return round(max(0.0, seconds) * usd_per_hour / 3600.0, 4)


def estimate_job_usd(kind: str, units: int = 1, usd_per_hour: float | None = None) -> float:
    """Estimated cost of `units` jobs of `kind` ('video' | 'edit' | 'lora')."""
    if kind not in JOB_SECONDS:
        raise ValueError(f"unknown cloud job kind {kind!r}; use one of {', '.join(JOB_SECONDS)}")
    if usd_per_hour is None:
        from echotales.pipeline.config import get_settings  # type: ignore[import-untyped]

        usd_per_hour = float(get_settings().cloud_gpu_usd_per_hour)
    return round(estimate_gpu_usd(JOB_SECONDS[kind], usd_per_hour) * max(0, units), 4)


class CloudLedger:
    def __init__(self, path: Path | str | None = None, budget_usd: float | None = None) -> None:
        self.path = Path(path) if path else paths.CLOUD_LEDGER_PATH
        if budget_usd is None:
            from echotales.pipeline.config import get_settings

            budget_usd = float(get_settings().cloud_budget_usd)
        self.budget_usd = float(budget_usd)
        self.entries: list[LedgerEntry] = []
        if self.path.is_file():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.entries = [LedgerEntry(**e) for e in raw.get("entries", [])]

    @property
    def spent_usd(self) -> float:
        return round(sum(e.cost for e in self.entries), 4)

    @property
    def remaining_usd(self) -> float:
        return round(self.budget_usd - self.spent_usd, 4)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"entries": [asdict(e) for e in self.entries]}, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def reserve(self, provider: str, kind: str, estimated_usd: float, note: str = "") -> LedgerEntry:
        """Record the estimate; refuse (and record nothing) if it would pass the budget. Call before submitting."""
        if self.spent_usd + estimated_usd > self.budget_usd + 1e-9:
            raise BudgetExceeded(
                f"cloud budget ${self.budget_usd:.2f} would be exceeded: ${self.spent_usd:.2f} spent, this "
                f"{provider} {kind} call is estimated at ${estimated_usd:.2f}; nothing was submitted "
                "(raise ECHOTALES_CLOUD_BUDGET_USD only on purpose)")
        entry = LedgerEntry(uuid.uuid4().hex[:12], provider, kind, round(estimated_usd, 4), note=note, ts=time.time())
        self.entries.append(entry)
        self._save()
        return entry

    def attach_job(self, entry: LedgerEntry, job_id: str) -> None:
        entry.job_id, entry.status = job_id, "submitted"
        self._save()

    def settle(self, entry: LedgerEntry, actual_usd: float | None, status: str = "completed") -> None:
        """Record the billed/measured cost. `actual_usd=None` keeps the estimate as the charge."""
        entry.actual_usd = None if actual_usd is None else round(actual_usd, 4)
        entry.status = status
        self._save()

    def summary(self) -> dict[str, Any]:
        by: dict[str, float] = {}
        for e in self.entries:
            by[e.provider] = round(by.get(e.provider, 0.0) + e.cost, 4)
        return {"budget_usd": self.budget_usd, "spent_usd": self.spent_usd, "remaining_usd": self.remaining_usd,
                "calls": len(self.entries), "by_provider": by, "path": str(self.path)}


def dry_run_report(kind: str, units: int, ledger: CloudLedger | None = None) -> dict[str, Any]:
    """Estimated cost of a run against the budget. Submits nothing and writes nothing."""
    est = estimate_job_usd(kind, units)
    ledger = ledger or CloudLedger()
    return {"kind": kind, "units": units, "estimated_usd": est, "spent_usd": ledger.spent_usd,
            "budget_usd": ledger.budget_usd, "would_exceed": ledger.spent_usd + est > ledger.budget_usd,
            "assumed_seconds_each": JOB_SECONDS[kind], "submitted": False}
