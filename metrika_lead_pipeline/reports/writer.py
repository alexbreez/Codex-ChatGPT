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
    max_decisions = int(limits.get("max_decision_log_items", limits.get("max_decision_log_records", len(decisions))))
    max_recommendations = int(limits.get("max_recommendations", len(recommendations)))
    max_markdown_items = int(limits.get("max_markdown_items", max_recommendations))
    limited_pages = pages[:max_pages]
    limited_decisions = decisions[:max_decisions]
    limited_recommendations = recommendations[:max_recommendations]
    truncation = _truncation_metadata({"pages": (len(limited_pages), len(pages)), "recommendations": (len(limited_recommendations), len(recommendations)), "decision_log": (len(limited_decisions), len(decisions))})
    _write_table(output_dir / "report_pages.xlsx", [p.model_dump() for p in limited_pages])
    _write_table(output_dir / "report_signals.xlsx", [s.model_dump() for s in signals[:max_pages]])
    _write_table(output_dir / "report_visits.xlsx", [v.model_dump() for v in visits[:max_pages]])
    _write_table(output_dir / "report_recommendations.xlsx", [_recommendation_row(r) for r in limited_recommendations])
    decision_payload: object = {"truncated": truncation, "records": [d.model_dump() for d in limited_decisions]} if truncation else [d.model_dump() for d in limited_decisions]
    (output_dir / "decision_log.json").write_text(json.dumps(decision_payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    (output_dir / "decision_log.md").write_text(_decision_md(limited_decisions[:max_markdown_items], truncation), encoding="utf-8")
    (output_dir / "lead_generation_report.md").write_text(_main_report(limited_pages, limited_recommendations[:max_markdown_items], limitations, truncation), encoding="utf-8")
    _write_report_metadata(output_dir, pages, signals, visits, recommendations, decisions, limits, truncation)



def _write_report_metadata(output_dir: Path, pages: list[PageFact], signals: list[SignalFinding], visits: list[VisitAnalysis], recommendations: list[Recommendation], decisions: list[DecisionRecord], limits: dict[str, int], truncation: dict[str, dict[str, int]]) -> None:
    metadata = {
        "generated_at": datetime.now().isoformat(),
        "counts": {
            "pages": len(pages),
            "signals": len(signals),
            "visits": len(visits),
            "recommendations": len(recommendations),
            "decision_log": len(decisions),
        },
        "limits": limits,
        "truncated": truncation,
    }
    (output_dir / "report_metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")


def _recommendation_row(rec: Recommendation) -> dict[str, Any]:
    data = rec.model_dump()
    return {
        "url": data.get("url"), "title": data.get("title"), "pageviews": data.get("pageviews"),
        "users": data.get("users"), "primary_source": data.get("primary_source"),
        "page_role": data.get("page_role"), "job_hypothesis": data.get("job_hypothesis"),
        "stage_hypothesis": data.get("stage_hypothesis"), "traffic_context": data.get("traffic_context"),
        "behavior_context": data.get("behavior_context"), "purchase_signals": data.get("purchase_signals"),
        "choice_signals": data.get("choice_signals"), "risk_signals": data.get("risk_signals"),
        "cold_news_signals": data.get("cold_news_signals"), "intent_score": data.get("intent_score"),
        "opportunity_score": data.get("opportunity_score"), "risk_score": data.get("risk_score"),
        "stage_confidence": data.get("stage_confidence"), "ranking_score": data.get("ranking_score"),
        "score": data.get("score"), "recommendation": data.get("recommendation"),
        "recommended_cta_type": data.get("recommended_cta_type"), "form_allowed": data.get("form_allowed"),
        "form_prohibited": data.get("form_prohibited"), "prohibition_reason": data.get("prohibition_reason"),
        "ux_risk_level": data.get("ux_risk_level"), "explanation": data.get("explanation"),
        "data_limitations": data.get("data_limitations"), "manual_review_required": data.get("manual_review_required"),
        "experiment_type": data.get("experiment_type"),
    }

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
    lines += ["", "## 3. Материалы с коммерческими сигналами"] + ([f"- {r.url}: purchase={r.purchase_signals}, choice={r.choice_signals}, risk={r.risk_signals}, cold_news={r.cold_news_signals}" for r in recommended] or ["- Недостаточно данных."])
    lines += ["", "## 4. Материалы без коммерческих сигналов"] + ([f"- {r.url}" for r in insufficient if "Коммерческие сигналы не обнаружены." in r.limitations] or ["- Не обнаружены."])
    lines += ["", "## 5. Страницы, которые рекомендуется протестировать для установки формы"] + ([f"- {r.url} — recommendation={r.recommendation}, cta={r.recommended_cta_type}, intent_score={r.intent_score}, opportunity_score={r.opportunity_score}, risk_score={r.risk_score}, stage_confidence={r.stage_confidence}, ranking_score={r.ranking_score}, job_hypothesis={r.job_hypothesis}, stage_hypothesis={r.stage_hypothesis}, form_allowed={r.form_allowed}, form_prohibited={r.form_prohibited}, prohibition_reason={r.prohibition_reason or 'нет'}, experiment_type={r.experiment_type or 'none'}. {r.explanation}" for r in recommended] or ["- Недостаточно данных для рекомендаций."])
    lines += ["", "## 6. Страницы, по которым недостаточно данных"] + ([f"- {r.url}: {'; '.join(r.limitations)}" for r in insufficient] or ["- Нет."])
    manual = [r for r in recs if r.manual_review_required or r.recommendation in {"manual_review", "run_discriminating_test"}]
    lines += ["", "## 7. Страницы, требующие ручной проверки"] + ([f"- {r.url}: {r.recommendation}; {r.explanation}" for r in manual] or ["- Нет."])
    lines += ["", "## 8. Все гипотезы, которые были сформированы системой"] + ([f"- {r.url}: job_hypothesis={r.job_hypothesis}; stage_hypothesis={r.stage_hypothesis}; {r.reason}" for r in recommended] or ["- Гипотезы не сформированы."])
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
        lines += [f"## {d.decision_id}", f"- URL: {d.url}", f"- Статус: {d.final_status}", f"- Recommendation: {d.recommendation}", f"- CTA: {d.recommended_cta_type}", f"- Job: {d.job_hypothesis}", f"- Stage: {d.stage_hypothesis}", f"- Scores: {json.dumps(d.scores, ensure_ascii=False)}", f"- Form allowed: {d.form_allowed}", f"- Form prohibited: {d.form_prohibited}", f"- Prohibition reason: {d.prohibition_reason or 'нет'}", f"- Уверенность: {d.confidence:.2f}", f"- Объяснение: {d.explanation}", "### Сработавшие правила"]
        lines += [f"- {r.rule_id}: {r.reason}" for r in d.triggered_rules] or ["- Нет"]
        lines += ["### Несработавшие правила"] + ([f"- {r.rule_id}: {r.reason}" for r in d.non_triggered_rules] or ["- Нет"])
        lines += ["### Ограничения"] + ([f"- {l}" for l in d.limitations] or ["- Нет"])
    return "\n".join(lines) + "\n"


def _truncation_metadata(items: dict[str, tuple[int, int]]) -> dict[str, dict[str, int]]:
    return {name: {"stored": stored, "total": total} for name, (stored, total) in items.items() if stored < total}
