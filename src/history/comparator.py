from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from loguru import logger
except Exception:  # pragma: no cover
    class _Logger:
        def info(self, *a: Any, **k: Any) -> None: pass
    logger = _Logger()

from src.history.delta import DeltaEngine, DeltaResult
from src.history.storage import HistoryStorage


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


def write_changes_report(delta: DeltaResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "changes_report.md"
    lines = ["# Changes report", "", "## 1. Что изменилось с прошлого запуска"]
    if delta.limitations:
        lines += [f"- {item}" for item in delta.limitations]
    lines += [f"- Новые страницы: {len(delta.new_pages)}", f"- Исчезнувшие страницы: {len(delta.disappeared_pages)}"]
    lines += ["", "## 2. Новые кандидаты"] + ([f"- {u}: {r}" for u, r in delta.new_candidates.items()] or ["- Нет"])
    lines += ["", "## 3. Потерянные кандидаты"] + ([f"- {u}: {r}" for u, r in delta.lost_candidates.items()] or ["- Нет"])
    lines += ["", "## 4. Изменившиеся рекомендации"] + ([f"- {u}: {v}" for u, v in delta.recommendation_changes.items()] or ["- Нет"])
    lines += ["", "## 5. Изменившиеся сигналы"] + ([f"- {u}: новые {v}" for u, v in delta.new_commercial_signals.items()] + [f"- {u}: исчезли {v}" for u, v in delta.disappeared_commercial_signals.items()] or ["- Нет"])
    lines += ["", "## 6. Самый большой рост"] + _largest(delta.confidence_changes, reverse=True)
    lines += ["", "## 7. Самое большое падение"] + _largest(delta.confidence_changes, reverse=False)
    lines += ["", "## 8. Изменения источников трафика"] + ([f"- {u}: {v}" for u, v in delta.source_changes.items()] or ["- Нет"])
    lines += ["", "## 9. Изменения поискового трафика"] + ([f"- {u}: {v}" for u, v in delta.search_traffic_changes.items()] or ["- Нет"])
    lines += ["", "## 10. Все изменения, которые могли повлиять на эффективность размещения формы"]
    lines += ([f"- {u}: {r}" for u, r in {**delta.new_candidates, **delta.lost_candidates}.items()] or ["- Нет"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _largest(values: dict[str, float], reverse: bool) -> list[str]:
    if not values:
        return ["- Нет"]
    url, value = sorted(values.items(), key=lambda item: item[1], reverse=reverse)[0]
    return [f"- {url}: {value:+.3f}"]
