from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

try:
    from loguru import logger
except Exception:  # pragma: no cover
    class _Logger:
        def info(self, *a: object, **k: object) -> None: pass
    logger = _Logger()

ScheduleMode = Literal["manual", "daily", "weekly"]


@dataclass(frozen=True)
class CollectionPeriod:
    date_from: str
    date_to: str
    mode: ScheduleMode = "manual"


class CollectionScheduler:
    def manual(self, date_from: str, date_to: str) -> CollectionPeriod:
        logger.info("Manual collection scheduled {}..{}", date_from, date_to)
        return CollectionPeriod(date_from, date_to, "manual")

    def daily(self, day: date | None = None) -> CollectionPeriod:
        target = day or date.today()
        return CollectionPeriod(target.isoformat(), target.isoformat(), "daily")

    def weekly(self, end_day: date | None = None) -> CollectionPeriod:
        end = end_day or date.today()
        start = end - timedelta(days=6)
        return CollectionPeriod(start.isoformat(), end.isoformat(), "weekly")
