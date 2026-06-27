from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from loguru import logger
except Exception:  # pragma: no cover
    class _Logger:
        def info(self, *a: Any, **k: Any) -> None: pass
    logger = _Logger()


def _default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class HistoryStorage:
    def __init__(self, history_dir: Path = Path("history")) -> None:
        self.history_dir = history_dir
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def create_run_id(self, at: datetime | None = None) -> str:
        return (at or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")

    def save_run(self, snapshot: dict[str, Any], reports_dir: Path | None = None) -> Path:
        run_id = str(snapshot.get("run_id") or self.create_run_id())
        run_dir = self.history_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "snapshot.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, default=_default), encoding="utf-8")
        if reports_dir and reports_dir.exists():
            target = run_dir / "reports"
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(reports_dir, target)
        logger.info("Saved run history {}", run_dir)
        return run_dir

    def load_run(self, run_id: str) -> dict[str, Any]:
        return dict(json.loads((self.history_dir / run_id / "snapshot.json").read_text(encoding="utf-8")))

    def list_runs(self) -> list[str]:
        return sorted(p.name for p in self.history_dir.iterdir() if (p / "snapshot.json").exists())

    def previous_run(self, current_run_id: str | None = None) -> dict[str, Any] | None:
        runs = self.list_runs()
        if current_run_id and current_run_id in runs:
            runs = runs[:runs.index(current_run_id)]
        if not runs:
            return None
        return self.load_run(runs[-1])
