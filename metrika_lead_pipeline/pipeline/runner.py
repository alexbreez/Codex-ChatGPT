from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

try:
    from loguru import logger
except Exception:  # pragma: no cover
    class _Logger:
        def info(self, *a: object, **k: object) -> None: pass
    logger = _Logger()

from metrika_lead_pipeline.analytics.visits import analyze_visits
from metrika_lead_pipeline.config.loader import default_config_path, load_config, load_yaml
from metrika_lead_pipeline.models import DecisionRecord, PageFact, Recommendation, RuleEvaluation, SignalFinding, VisitFact
from metrika_lead_pipeline.pipeline.facts import build_page_facts
from metrika_lead_pipeline.recommendations.engine import build_recommendations
from metrika_lead_pipeline.reports.writer import write_reports
from metrika_lead_pipeline.signals.extractor import extract_signals

UNAVAILABLE_API_NOTE = "Если Reporting API Яндекс.Метрики не предоставляет выбранный показатель для счетчика или периода, показатель фиксируется как отсутствующий и не используется для выводов."


def run_pipeline(input_rows: list[dict[str, object]], visits: list[dict[str, object]] | None = None, config_path: Path = default_config_path("config.yaml"), output_dir: Path | None = None, limitations: list[str] | None = None) -> tuple[list[PageFact], list[SignalFinding], list[Recommendation]]:
    pages = build_page_facts(input_rows, {str(v.get("entry_url")) for v in (visits or []) if v.get("entry_url")})
    visit_facts = [VisitFact(visit_id=str(v.get("visit_id", i)), entry_url=str(v.get("entry_url")) if v.get("entry_url") else None, page_urls=[str(u) for u in v.get("page_urls", [])]) for i, v in enumerate(visits or [])]
    result = run_pipeline_from_facts(pages, visit_facts, config_path, output_dir, limitations)
    return result[0], result[1], result[2]


def run_pipeline_from_facts(pages: list[PageFact], visits: list[VisitFact] | None = None, config_path: Path = default_config_path("config.yaml"), output_dir: Path | None = None, limitations: list[str] | None = None) -> tuple[list[PageFact], list[SignalFinding], list[Recommendation], list[DecisionRecord]]:
    logger.info("Pipeline started: pages={} visits={}", len(pages), len(visits or []))
    cfg = load_config(config_path)
    signal_cfg = load_yaml(default_config_path("signals.yaml"))
    rules_cfg = load_yaml(default_config_path("rules.yaml"))
    all_signals: list[SignalFinding] = []
    signal_evals: dict[str, list[RuleEvaluation]] = {}
    page_signals: dict[str, list[str]] = {}
    for page in pages:
        findings, evals = extract_signals(page, signal_cfg, cfg.brands + cfg.categories)
        all_signals.extend(findings)
        signal_evals[page.url] = evals
        page_signals[page.url] = [f.signal for f in findings]
    visit_dicts = [v.model_dump() for v in (visits or [])]
    visit_results = analyze_visits(visit_dicts, page_signals, rules_cfg)
    logger.info("Building recommendations")
    recs = build_recommendations(pages, page_signals, rules_cfg)
    effective_limitations = [UNAVAILABLE_API_NOTE, "Без данных о достижении целей/CRM качество лидов не подтверждается; рекомендации остаются гипотезами для теста."] + list(limitations or [])
    decisions = _build_decisions(pages, recs, signal_evals, cfg.version, signal_cfg.get("version", ""), rules_cfg.get("version", ""), effective_limitations)
    logger.info("Writing reports")
    write_reports(pages, all_signals, visit_results, recs, decisions, output_dir or Path(cfg.outputs.get("report_dir", "reports")), effective_limitations)
    logger.info("Pipeline completed")
    return pages, all_signals, recs, decisions


def _build_decisions(pages: list[PageFact], recs: list[Recommendation], evals: dict[str, list[RuleEvaluation]], config_version: str, signal_version: str, rules_version: str, global_limitations: list[str]) -> list[DecisionRecord]:
    by_url = {r.url: r for r in recs}
    records: list[DecisionRecord] = []
    for page in pages:
        rec = by_url[page.url]
        rule_evals = evals.get(page.url, [])
        records.append(DecisionRecord(
            decision_id=str(uuid4()), created_at=datetime.now(timezone.utc), analytics_rules_version=rules_version,
            signal_dictionary_version=signal_version, config_version=config_version,
            facts=page.model_dump(), triggered_rules=[r for r in rule_evals if r.matched], non_triggered_rules=[r for r in rule_evals if not r.matched],
            final_status=rec.status, confidence=rec.confidence, explanation=rec.reason,
            recommendations=[rec.url] if rec.status != "Недостаточно данных" else [], limitations=rec.limitations + global_limitations,
        ))
    return records
