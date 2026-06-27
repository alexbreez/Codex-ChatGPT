from __future__ import annotations

import csv
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from metrika_lead_pipeline.models import DecisionRecord, PageFact, Recommendation, SignalFinding, VisitAnalysis

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
    with path.open("w", encoding="utf-8", newline="") as fh:
        if not rows:
            fh.write("")
            return
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows({k: json.dumps(v, ensure_ascii=False, default=_json_default) if isinstance(v, (dict, list)) else v for k, v in r.items()} for r in rows)


def write_reports(pages: list[PageFact], signals: list[SignalFinding], visits: list[VisitAnalysis], recommendations: list[Recommendation], decisions: list[DecisionRecord], output_dir: Path, limitations: list[str], output_limits: dict[str, int] | None = None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    limits = output_limits or {}
    max_pages = int(limits.get("max_report_pages", len(pages)))
    max_decisions = int(limits.get("max_decision_log_records", len(decisions)))
    max_recommendations = int(limits.get("max_recommendations", len(recommendations)))
    limited_pages = pages[:max_pages]
    limited_decisions = decisions[:max_decisions]
    limited_recommendations = recommendations[:max_recommendations]
    truncation = _truncation_metadata({"pages": (len(limited_pages), len(pages)), "recommendations": (len(limited_recommendations), len(recommendations)), "decision_log": (len(limited_decisions), len(decisions))})
    _write_table(output_dir / "report_pages.xlsx", [p.model_dump() for p in limited_pages])
    _write_table(output_dir / "report_signals.xlsx", [s.model_dump() for s in signals[:max_pages]])
    _write_table(output_dir / "report_visits.xlsx", [v.model_dump() for v in visits[:max_pages]])
    decision_payload: object = {"truncated": truncation, "records": [d.model_dump() for d in limited_decisions]} if truncation else [d.model_dump() for d in limited_decisions]
    (output_dir / "decision_log.json").write_text(json.dumps(decision_payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    (output_dir / "decision_log.md").write_text(_decision_md(limited_decisions, truncation), encoding="utf-8")
    (output_dir / "lead_generation_report.md").write_text(_main_report(limited_pages, limited_recommendations, limitations, truncation), encoding="utf-8")


def _main_report(pages: list[PageFact], recs: list[Recommendation], limitations: list[str], truncation: dict[str, dict[str, int]] | None = None) -> str:
    recommended = [r for r in recs if r.status != "Недостаточно данных"]
    insufficient = [r for r in recs if r.status == "Недостаточно данных"]
    lines = ["# Lead generation report", "", "## 1. Общая статистика", f"- Страниц в отчёте: {len(pages)}"]
    total_visits = sum(p.visits for p in pages)
    total_pageviews = sum(p.pageviews for p in pages)
    if total_visits:
        lines.append(f"- Визитов: {total_visits}")
    if total_pageviews:
        lines.append(f"- Просмотров страниц: {total_pageviews}")
    if not total_visits and not total_pageviews:
        lines.append("- Недостаточно данных о трафике страниц.")
    lines += ["", "## 2. Источники трафика"]
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
    lines += ["", "## 9. Ограничения анализа"]
    unique_limitations = list(dict.fromkeys(limitations))
    lines += ([f"- {l}" for l in unique_limitations] or ["- Ограничения данных не зафиксированы."])
    if unique_limitations:
        lines.append("- Ограничения данных могут снижать уверенность рекомендаций; отсутствующие показатели не используются для усиления выводов.")
    if truncation:
        lines += ["", "## Ограничения объёма вывода"]
        lines += [f"- {name}: показано {meta['stored']} из {meta['total']}" for name, meta in truncation.items() if meta['stored'] < meta['total']] or ["- Вывод не был усечён."]
    return "\n".join(lines) + "\n"


def _decision_md(decisions: list[DecisionRecord], truncation: dict[str, dict[str, int]] | None = None) -> str:
    lines = ["# Decision log", ""]
    if truncation and truncation.get("decision_log", {}).get("stored", 0) < truncation.get("decision_log", {}).get("total", 0):
        meta = truncation["decision_log"]
        lines += [f"Показано {meta['stored']} из {meta['total']} записей Decision Log.", ""]
    for d in decisions:
        lines += [f"## {d.decision_id}", f"- Статус: {d.final_status}", f"- Уверенность: {d.confidence:.2f}", f"- Объяснение: {d.explanation}", "### Сработавшие правила"]
        lines += [f"- {r.rule_id}: {r.reason}" for r in d.triggered_rules] or ["- Нет"]
        lines += ["### Несработавшие правила"] + ([f"- {r.rule_id}: {r.reason}" for r in d.non_triggered_rules] or ["- Нет"])
        lines += ["### Ограничения"] + ([f"- {l}" for l in d.limitations] or ["- Нет"])
    return "\n".join(lines) + "\n"


def _truncation_metadata(items: dict[str, tuple[int, int]]) -> dict[str, dict[str, int]]:
    return {name: {"stored": stored, "total": total} for name, (stored, total) in items.items() if stored < total}
