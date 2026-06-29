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

DEFAULT_MARKDOWN_ITEMS = 500
DEFAULT_DECISION_LOG_ITEMS = 1000


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return asdict(value)
    return str(value)


def _int_limit(config: dict[str, Any] | None, key: str, default: int) -> int:
    if not config:
        return default
    try:
        return max(0, int(config.get(key, default)))
    except (TypeError, ValueError):
        return default


def _limited(items: list[Any], limit: int) -> list[Any]:
    if limit <= 0:
        return []
    return items[:limit]


def _truncation_meta(name: str, total: int, stored: int) -> dict[str, int] | None:
    if stored >= total:
        return None
    return {"stored": stored, "total": total}


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


def write_reports(
    pages: list[PageFact],
    signals: list[SignalFinding],
    visits: list[VisitAnalysis],
    recommendations: list[Recommendation],
    decisions: list[DecisionRecord],
    output_dir: Path,
    limitations: list[str],
    output_limits: dict[str, Any] | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    max_markdown_items = _int_limit(output_limits, "max_markdown_items", DEFAULT_MARKDOWN_ITEMS)
    max_decision_log_items = _int_limit(output_limits, "max_decision_log_items", DEFAULT_DECISION_LOG_ITEMS)

    limited_decisions = _limited(decisions, max_decision_log_items)

    _write_table(output_dir / "report_pages.xlsx", [p.model_dump() for p in pages])
    _write_table(output_dir / "report_signals.xlsx", [s.model_dump() for s in signals])
    _write_table(output_dir / "report_visits.xlsx", [v.model_dump() for v in visits])

    (output_dir / "decision_log.json").write_text(
        json.dumps([d.model_dump() for d in limited_decisions], ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    (output_dir / "decision_log.md").write_text(_decision_md(decisions, max_decision_log_items), encoding="utf-8")
    (output_dir / "lead_generation_report.md").write_text(
        _main_report(pages, recommendations, limitations, max_markdown_items),
        encoding="utf-8",
    )

    truncated: dict[str, dict[str, int]] = {}
    decision_meta = _truncation_meta("decision_log", len(decisions), len(limited_decisions))
    if decision_meta:
        truncated["decision_log"] = decision_meta

    metadata = {
        "generated_at": datetime.now().isoformat(),
        "totals": {
            "pages": len(pages),
            "signals": len(signals),
            "visits": len(visits),
            "recommendations": len(recommendations),
            "decision_log": len(decisions),
        },
        "limits": {
            "max_markdown_items": max_markdown_items,
            "max_decision_log_items": max_decision_log_items,
        },
        "truncated": truncated,
    }
    (output_dir / "report_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )


def _format_limited_list(items: list[str], total: int) -> list[str]:
    if not items:
        return ["- Нет"]
    lines = items
    if len(items) < total:
        lines = lines + [f"- Показано {len(items)} из {total}; остальные записи усечены для ограничения размера отчёта."]
    return lines


def _score_summary(r: Recommendation) -> str:
    return (
        f"intent={r.intent_score:.1f}, "
        f"opportunity={r.opportunity_score:.1f}, "
        f"risk={r.risk_score:.1f}, "
        f"stage_confidence={r.stage_confidence:.2f}, "
        f"ranking={r.ranking_score:.1f}"
    )


def _action_line(r: Recommendation) -> str:
    form_state = "форма разрешена" if r.form_allowed else "форма не разрешена"
    if r.form_prohibited:
        form_state = "форма запрещена"
    review_state = "ручная проверка нужна" if r.manual_review_required else "ручная проверка не обязательна"
    experiment = f", experiment={r.experiment_type}" if r.experiment_type else ""
    return (
        f"- {r.url} — action={r.recommendation}, cta={r.recommended_cta_type}, "
        f"{form_state}, {review_state}{experiment}; "
        f"{_score_summary(r)}. {r.reason}"
    )


def _main_report(pages: list[PageFact], recs: list[Recommendation], limitations: list[str], max_items: int = DEFAULT_MARKDOWN_ITEMS) -> str:
    active = [r for r in recs if r.status != "Недостаточно данных"]
    insufficient = [r for r in recs if r.status == "Недостаточно данных"]

    form_candidates = [r for r in active if r.form_allowed and not r.form_prohibited]
    prohibited = [r for r in recs if r.form_prohibited]
    distinguishing_tests = [r for r in active if r.experiment_type == "distinguishing_test"]
    early_or_bridge = [r for r in active if r.recommended_cta_type in {"early_cta", "bridge", "bridge_or_early_cta_vs_form", "early_cta_vs_commitment_cta"}]
    manual_review = [r for r in recs if r.manual_review_required and not r.form_prohibited]

    limited_active = _limited(active, max_items)
    limited_form_candidates = _limited(form_candidates, max_items)
    limited_prohibited = _limited(prohibited, max_items)
    limited_distinguishing_tests = _limited(distinguishing_tests, max_items)
    limited_early_or_bridge = _limited(early_or_bridge, max_items)
    limited_manual_review = _limited(manual_review, max_items)
    limited_insufficient = _limited(insufficient, max_items)

    lines = [
        "# Lead generation report",
        "",
        "## 1. Общая статистика",
        f"- Страниц: {len(pages)}",
    ]

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

    lines += [
        "",
        "## 3. Очередь действий по методологии v2",
        "- Отчёт больше не трактует вовлечённое автомобильное чтение как автоматическое доказательство покупательского намерения.",
        "- Решение строится через отдельные intent_score, opportunity_score, risk_score, stage_confidence и ranking_score.",
    ]
    lines += _format_limited_list([_action_line(r) for r in limited_active], len(active))

    lines += ["", "## 4. Кандидаты, где форма разрешена"]
    lines += _format_limited_list([_action_line(r) for r in limited_form_candidates], len(form_candidates))

    lines += ["", "## 5. Страницы, где форма запрещена"]
    lines += _format_limited_list([_action_line(r) for r in limited_prohibited], len(prohibited))

    lines += ["", "## 6. Risk/ownership, Discover и спорные страницы: различающий тест"]
    lines += _format_limited_list([_action_line(r) for r in limited_distinguishing_tests], len(distinguishing_tests))

    lines += ["", "## 7. Early CTA и bridge вместо преждевременной формы"]
    lines += _format_limited_list([_action_line(r) for r in limited_early_or_bridge], len(early_or_bridge))

    lines += ["", "## 8. Страницы, требующие ручной проверки"]
    lines += _format_limited_list([_action_line(r) for r in limited_manual_review], len(manual_review))

    lines += ["", "## 9. Страницы, по которым недостаточно данных"]
    lines += _format_limited_list([f"- {r.url}: {'; '.join(r.limitations)}" for r in limited_insufficient], len(insufficient))

    lines += ["", "## 10. Ограничения анализа"] + [f"- {l}" for l in limitations]

    if any(
        [
            len(limited_active) < len(active),
            len(limited_form_candidates) < len(form_candidates),
            len(limited_prohibited) < len(prohibited),
            len(limited_distinguishing_tests) < len(distinguishing_tests),
            len(limited_early_or_bridge) < len(early_or_bridge),
            len(limited_manual_review) < len(manual_review),
            len(limited_insufficient) < len(insufficient),
        ]
    ):
        lines += [
            "",
            "## 11. Ограничения размера вывода",
            f"- Markdown-списки ограничены до {max_items} записей на раздел.",
            f"- Активных решений всего: {len(active)}, показано: {len(limited_active)}.",
            f"- Страниц с недостатком данных всего: {len(insufficient)}, показано: {len(limited_insufficient)}.",
        ]

    return "\n".join(lines) + "\n"


def _decision_md(decisions: list[DecisionRecord], max_items: int = DEFAULT_DECISION_LOG_ITEMS) -> str:
    limited_decisions = _limited(decisions, max_items)
    lines = ["# Decision log", "", f"- Всего решений: {len(decisions)}", f"- Показано решений: {len(limited_decisions)}"]
    if len(limited_decisions) < len(decisions):
        lines.append("- Остальные решения усечены для ограничения размера отчёта.")
    lines.append("")

    for d in limited_decisions:
        lines += [
            f"## {d.decision_id}",
            f"- Статус: {d.final_status}",
            f"- Уверенность: {d.confidence:.2f}",
            f"- Recommendation: {d.recommendation}",
            f"- CTA type: {d.recommended_cta_type}",
            f"- Page role: {d.page_role}",
            f"- Job hypothesis: {d.job_hypothesis}",
            f"- Stage hypothesis: {d.stage_hypothesis}",
            f"- Stage confidence: {d.stage_confidence:.2f}",
            f"- Form allowed: {d.form_allowed}",
            f"- Form prohibited: {d.form_prohibited}",
            f"- UX risk: {d.ux_risk_level}",
            f"- Manual review required: {d.manual_review_required}",
            f"- Experiment type: {d.experiment_type or 'none'}",
            f"- Объяснение: {d.explanation}",
        ]

        if d.prohibition_reason:
            lines.append(f"- Причина запрета формы: {d.prohibition_reason}")

        lines += ["### Scores"]
        if d.scores:
            lines += [f"- {key}: {value}" for key, value in d.scores.items()]
        else:
            lines += ["- Нет"]

        lines += ["### Сработавшие сигналы"]
        if d.triggered_signals:
            for group, values in d.triggered_signals.items():
                lines.append(f"- {group}: {', '.join(values) if values else 'нет'}")
        else:
            lines += ["- Нет"]

        lines += ["### Сработавшие ограничения"]
        lines += [f"- {constraint}" for constraint in d.triggered_constraints] or ["- Нет"]

        lines += ["### Сработавшие правила"]
        lines += [f"- {r.rule_id}: {r.reason}" for r in d.triggered_rules] or ["- Нет"]

        lines += ["### Несработавшие правила"]
        lines += [f"- {r.rule_id}: {r.reason}" for r in d.non_triggered_rules] or ["- Нет"]

        lines += ["### Ограничения данных"]
        lines += [f"- {l}" for l in d.data_limitations] or ["- Нет"]

        lines += ["### Все ограничения"]
        lines += [f"- {l}" for l in d.limitations] or ["- Нет"]

    return "\n".join(lines) + "\n"
