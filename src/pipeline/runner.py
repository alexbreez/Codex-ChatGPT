from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from src.analytics.visits import analyze_visits
from src.config.loader import load_config, load_yaml
from src.models import DecisionRecord, PageFact, Recommendation, RuleEvaluation, SignalFinding
from src.pipeline.facts import build_page_facts
from src.recommendations.engine import build_recommendations
from src.reports.writer import write_reports
from src.signals.extractor import extract_signals

UNAVAILABLE_API_NOTE = "Если Reporting API Яндекс.Метрики не предоставляет выбранный показатель для счетчика или периода, показатель фиксируется как отсутствующий и не используется для выводов."


def run_pipeline(input_rows: list[dict[str, object]], visits: list[dict[str, object]] | None = None, config_path: Path = Path("src/config/config.yaml"), output_dir: Path | None = None) -> tuple[list[PageFact], list[SignalFinding], list[Recommendation]]:
    cfg = load_config(config_path)
    signal_cfg = load_yaml(Path("src/config/signals.yaml"))
    rules_cfg = load_yaml(Path("src/config/rules.yaml"))
    pages = build_page_facts(input_rows, {str(v.get("entry_url")) for v in (visits or []) if v.get("entry_url")})
    all_signals: list[SignalFinding] = []
    signal_evals: dict[str, list[RuleEvaluation]] = {}
    page_signals: dict[str, list[str]] = {}
    for page in pages:
        findings, evals = extract_signals(page, signal_cfg, cfg.brands + cfg.categories)
        all_signals.extend(findings)
        signal_evals[page.url] = evals
        page_signals[page.url] = [f.signal for f in findings]
    visit_results = analyze_visits(visits or [], page_signals, rules_cfg)
    recs = build_recommendations(pages, page_signals, rules_cfg)
    decisions = _build_decisions(pages, recs, signal_evals, cfg.version, signal_cfg.get("version", ""), rules_cfg.get("version", ""))
    limitations = [UNAVAILABLE_API_NOTE, "Без данных о достижении целей/CRM качество лидов не подтверждается; рекомендации остаются гипотезами для теста."]
    write_reports(pages, all_signals, visit_results, recs, decisions, output_dir or Path(cfg.outputs.get("report_dir", "reports")), limitations)
    return pages, all_signals, recs


def _build_decisions(pages: list[PageFact], recs: list[Recommendation], evals: dict[str, list[RuleEvaluation]], config_version: str, signal_version: str, rules_version: str) -> list[DecisionRecord]:
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
            recommendations=[rec.url] if rec.status != "Недостаточно данных" else [], limitations=rec.limitations,
        ))
    return records
