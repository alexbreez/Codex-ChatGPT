from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from loguru import logger
except Exception:  # pragma: no cover
    class _Logger:
        def info(self, *a: Any, **k: Any) -> None: pass
    logger = _Logger()

from metrika_lead_pipeline.history.delta import DeltaEngine, DeltaResult
from metrika_lead_pipeline.history.storage import HistoryStorage


class RunComparator:
    def __init__(self, storage: HistoryStorage, delta_engine: DeltaEngine | None = None) -> None:
        self.storage = storage
        self.delta_engine = delta_engine or DeltaEngine()

    def compare_run_ids(self, run_a: str, run_b: str) -> DeltaResult:
        logger.info("Comparing runs {} and {}", run_a, run_b)
        return self.delta_engine.compare(self.storage.load_run(run_a), self.storage.load_run(run_b))

    def compare_with_previous(self, current_snapshot: dict[str, Any]) -> DeltaResult:
        previous = self.storage.previous_run(str(current_snapshot.get("run_id", "")))
        return self.delta_engine.compare(previous, current_snapshot)


def write_changes_report(delta: DeltaResult, output_dir: Path, max_items: int | None = None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "changes_report.md"
    limit = max_items if max_items is not None else 1000000
    lines = ["# Changes report", "", "## 1. Что изменилось с прошлого запуска"]
    if delta.limitations:
        lines += [f"- {item}" for item in delta.limitations]
    lines += [f"- Новые страницы: {len(delta.new_pages)}", f"- Исчезнувшие страницы: {len(delta.disappeared_pages)}"]
    lines += ["", "## 2. Новые кандидаты"] + (_limited_items(delta.new_candidates, limit) or ["- Нет"])
    lines += ["", "## 3. Потерянные кандидаты"] + (_limited_items(delta.lost_candidates, limit) or ["- Нет"])
    lines += ["", "## 4. Изменившиеся рекомендации"] + (_limited_items(delta.recommendation_changes, limit) or ["- Нет"])
    signal_lines = [f"- {u}: новые {v}" for u, v in list(delta.new_commercial_signals.items())[:limit]] + [f"- {u}: исчезли {v}" for u, v in list(delta.disappeared_commercial_signals.items())[:limit]]
    lines += ["", "## 5. Изменившиеся сигналы"] + (signal_lines or ["- Нет"])
    lines += ["", "## 6. Самый большой рост"] + _largest(delta.confidence_changes, reverse=True)
    lines += ["", "## 7. Самое большое падение"] + _largest(delta.confidence_changes, reverse=False)
    lines += ["", "## 8. Изменения источников трафика"] + (_limited_items(delta.source_changes, limit) or ["- Нет"])
    lines += ["", "## 9. Изменения поискового трафика"] + (_limited_items(delta.search_traffic_changes, limit) or ["- Нет"])
    lines += ["", "## 10. Все изменения, которые могли повлиять на эффективность размещения формы"]
    lines += (_limited_items({**delta.new_candidates, **delta.lost_candidates}, limit) or ["- Нет"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _limited_items(values: dict[str, Any], limit: int) -> list[str]:
    return [f"- {u}: {v}" for u, v in list(values.items())[:limit]]


def _largest(values: dict[str, float], reverse: bool) -> list[str]:
    if not values:
        return ["- Нет"]
    url, value = sorted(values.items(), key=lambda item: item[1], reverse=reverse)[0]
    return [f"- {url}: {value:+.3f}"]
