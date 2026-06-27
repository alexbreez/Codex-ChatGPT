from __future__ import annotations

import csv
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.models import DecisionRecord, PageFact, Recommendation, SignalFinding, VisitAnalysis

try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover
    pd = None


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    return str(value)


def _write_table(path: Path, rows: list[dict[str, Any]]) -> None:
    if pd is not None:
        pd.DataFrame(rows).to_excel(path, index=False)
        return
    # Dependency-light fallback for constrained environments: write CSV content with requested filename.
    with path.open("w", encoding="utf-8", newline="") as fh:
        if not rows:
            fh.write("")
            return
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows({k: json.dumps(v, ensure_ascii=False, default=_json_default) if isinstance(v, (dict, list)) else v for k, v in r.items()} for r in rows)


def write_reports(pages: list[PageFact], signals: list[SignalFinding], visits: list[VisitAnalysis], recommendations: list[Recommendation], decisions: list[DecisionRecord], output_dir: Path, limitations: list[str]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_table(output_dir / "report_pages.xlsx", [p.model_dump() for p in pages])
    _write_table(output_dir / "report_signals.xlsx", [s.model_dump() for s in signals])
    _write_table(output_dir / "report_visits.xlsx", [v.model_dump() for v in visits])
    (output_dir / "decision_log.json").write_text(json.dumps([d.model_dump() for d in decisions], ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    (output_dir / "decision_log.md").write_text(_decision_md(decisions), encoding="utf-8")
    (output_dir / "lead_generation_report.md").write_text(_main_report(pages, recommendations, limitations), encoding="utf-8")


def _main_report(pages: list[PageFact], recs: list[Recommendation], limitations: list[str]) -> str:
    recommended = [r for r in recs if r.status != "Недостаточно данных"]
    insufficient = [r for r in recs if r.status == "Недостаточно данных"]
    lines = ["# Lead generation report", "", "## 1. Общая статистика", f"- Страниц: {len(pages)}", f"- Визитов: {sum(p.visits for p in pages)}", "", "## 2. Источники трафика"]
    sources: dict[str, int] = {}
    for p in pages:
        for k, v in p.traffic_sources.items():
            sources[k] = sources.get(k, 0) + int(v)
    lines += [f"- {k}: {v}" for k, v in sorted(sources.items())] or ["- Недостаточно данных об источниках."]
    lines += ["", "## 3. Материалы с коммерческими сигналами"] + ([f"- {r.url}: {', '.join(r.detected_signals)}" for r in recommended] or ["- Недостаточно данных."])
    lines += ["", "## 4. Материалы без коммерческих сигналов"] + ([f"- {r.url}" for r in insufficient if "Коммерческие сигналы не обнаружены." in r.limitations] or ["- Не обнаружены."])
    lines += ["", "## 5. Страницы, которые рекомендуется протестировать для установки формы"] + ([f"- {r.url} — {r.status}, уверенность {r.confidence:.2f}. {r.reason}" for r in recommended] or ["- Недостаточно данных для рекомендаций."])
    lines += ["", "## 6. Страницы, по которым недостаточно данных"] + ([f"- {r.url}: {'; '.join(r.limitations)}" for r in insufficient] or ["- Нет."])
    lines += ["", "## 7. Страницы, требующие ручной проверки", "- Страницы с гипотезами требуют ручной проверки перед внедрением формы.", "", "## 8. Все гипотезы, которые были сформированы системой"] + ([f"- {r.url}: {r.reason}" for r in recommended] or ["- Гипотезы не сформированы."])
    lines += ["", "## 9. Ограничения анализа"] + [f"- {l}" for l in limitations]
    return "\n".join(lines) + "\n"


def _decision_md(decisions: list[DecisionRecord]) -> str:
    lines = ["# Decision log", ""]
    for d in decisions:
        lines += [f"## {d.decision_id}", f"- Статус: {d.final_status}", f"- Уверенность: {d.confidence:.2f}", f"- Объяснение: {d.explanation}", "### Сработавшие правила"]
        lines += [f"- {r.rule_id}: {r.reason}" for r in d.triggered_rules] or ["- Нет"]
        lines += ["### Несработавшие правила"] + ([f"- {r.rule_id}: {r.reason}" for r in d.non_triggered_rules] or ["- Нет"])
        lines += ["### Ограничения"] + ([f"- {l}" for l in d.limitations] or ["- Нет"])
    return "\n".join(lines) + "\n"
