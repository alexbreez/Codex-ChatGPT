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

DEFAULT_CHANGE_REPORT_ITEMS = 500


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


def write_changes_report(delta: DeltaResult, output_dir: Path, max_items: int = DEFAULT_CHANGE_REPORT_ITEMS) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "changes_report.md"
    safe_limit = max(0, int(max_items))
    lines = ["# Changes report", "", "## 1. Что изменилось с прошлого запуска"]
    if delta.limitations:
        lines += [f"- {item}" for item in delta.limitations]
    lines += [f"- Новые страницы: {len(delta.new_pages)}", f"- Исчезнувшие страницы: {len(delta.disappeared_pages)}"]

    lines += ["", "## 2. Новые кандидаты"] + _format_limited_mapping(delta.new_candidates, safe_limit, lambda u, r: f"- {u}: {r}")
    lines += ["", "## 3. Потерянные кандидаты"] + _format_limited_mapping(delta.lost_candidates, safe_limit, lambda u, r: f"- {u}: {r}")
    lines += ["", "## 4. Изменившиеся рекомендации"] + _format_limited_mapping(delta.recommendation_changes, safe_limit, lambda u, v: f"- {u}: {v}")

    signal_pairs = (
        [("новые", url, values) for url, values in delta.new_commercial_signals.items()]
        + [("исчезли", url, values) for url, values in delta.disappeared_commercial_signals.items()]
    )
    signal_lines = _format_limited_signal_changes(signal_pairs, safe_limit)
    lines += ["", "## 5. Изменившиеся сигналы"] + signal_lines

    lines += ["", "## 6. Самый большой рост"] + _largest(delta.confidence_changes, reverse=True)
    lines += ["", "## 7. Самое большое падение"] + _largest(delta.confidence_changes, reverse=False)
    lines += ["", "## 8. Изменения источников трафика"] + _format_limited_mapping(delta.source_changes, safe_limit, lambda u, v: f"- {u}: {v}")
    lines += ["", "## 9. Изменения поискового трафика"] + _format_limited_mapping(delta.search_traffic_changes, safe_limit, lambda u, v: f"- {u}: {v}")

    combined_candidates = {**delta.new_candidates, **delta.lost_candidates}
    lines += ["", "## 10. Все изменения, которые могли повлиять на эффективность размещения формы"]
    lines += _format_limited_mapping(combined_candidates, safe_limit, lambda u, r: f"- {u}: {r}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _format_limited_mapping(values: dict[str, Any], limit: int, formatter: Any) -> list[str]:
    return _format_limited_pairs(list(values.items()), limit, formatter)


def _format_limited_pairs(pairs: list[tuple[str, Any]], limit: int, formatter: Any) -> list[str]:
    if not pairs:
        return ["- Нет"]
    limited = pairs[:limit] if limit > 0 else []
    lines = [formatter(url, value) for url, value in limited]
    if len(limited) < len(pairs):
        lines.append(f"- Показано {len(limited)} из {len(pairs)} изменений; остальные усечены для ограничения размера отчёта.")
    return lines or ["- Нет"]


def _format_limited_signal_changes(pairs: list[tuple[str, str, Any]], limit: int) -> list[str]:
    if not pairs:
        return ["- Нет"]
    limited = pairs[:limit] if limit > 0 else []
    lines = [f"- {url}: {label} {values}" for label, url, values in limited]
    if len(limited) < len(pairs):
        lines.append(f"- Показано {len(limited)} из {len(pairs)} изменений; остальные усечены для ограничения размера отчёта.")
    return lines or ["- Нет"]


def _largest(values: dict[str, float], reverse: bool) -> list[str]:
    if not values:
        return ["- Нет"]
    url, value = sorted(values.items(), key=lambda item: item[1], reverse=reverse)[0]
    return [f"- {url}: {value:+.3f}"]
