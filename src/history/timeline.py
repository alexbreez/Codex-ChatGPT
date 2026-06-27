from __future__ import annotations

from typing import Any

from src.history.storage import HistoryStorage


class Timeline:
    def __init__(self, storage: HistoryStorage) -> None:
        self.storage = storage

    def page_history(self, url: str) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        for run_id in self.storage.list_runs():
            snapshot = self.storage.load_run(run_id)
            page = next((p for p in snapshot.get("pages", []) if p.get("url") == url), None)
            rec = next((r for r in snapshot.get("recommendations", []) if r.get("url") == url), None)
            signals = [s.get("signal") for s in snapshot.get("signals", []) if s.get("url") == url]
            if page or rec or signals:
                history.append({"run_id": run_id, "page": page, "recommendation": rec, "signals": signals})
        return history

    def recommendation_history(self, url: str) -> list[dict[str, Any]]:
        return [item for item in self.page_history(url) if item.get("recommendation")]
