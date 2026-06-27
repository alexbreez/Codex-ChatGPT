from __future__ import annotations

from typing import Any

from metrika_lead_pipeline.models import RuleEvaluation, VisitAnalysis


def analyze_visits(visits: list[dict[str, Any]], page_signals: dict[str, list[str]], rules_config: dict[str, Any]) -> list[VisitAnalysis]:
    results: list[VisitAnalysis] = []
    for i, visit in enumerate(visits):
        urls = [str(u) for u in visit.get("page_urls", [])]
        entry = str(visit.get("entry_url") or (urls[0] if urls else "")) or None
        signals = sorted({s for url in urls for s in page_signals.get(url, []) if s != "Сигналы не обнаружены"})
        analysis = VisitAnalysis(visit_id=str(visit.get("visit_id", i)), entry_url=entry, page_urls=urls, signals=signals)
        for rule in rules_config.get("visit_rules", []):
            matched = False
            reason = "Условия правила не выполнены"
            if rule.get("entry_signals_any"):
                entry_signals = page_signals.get(entry or "", [])
                matched = any(s in entry_signals for s in rule["entry_signals_any"])
                reason = "Страница входа содержит требуемый сигнал" if matched else "Страница входа не содержит требуемых сигналов"
            elif rule.get("only_signals_any") is not None:
                allowed = set(rule.get("only_signals_any", []))
                matched = not signals or set(signals).issubset(allowed)
                reason = "В визите нет коммерческих сигналов" if matched else "В визите есть сигналы вне разрешенного списка"
            ev = RuleEvaluation(rule_id=str(rule["id"]), name=str(rule["name"]), description=str(rule.get("description", "")), matched=matched, reason=reason, values={"signals": signals, "entry_url": entry})
            analysis.rule_evaluations.append(ev)
            if matched:
                analysis.added_signals.append(str(rule["name"]))
                analysis.status = rule.get("status", "Гипотеза")
                analysis.confidence = max(analysis.confidence, float(rule.get("confidence", 0.5)))
        if not analysis.rule_evaluations:
            analysis.limitations.append("Правила анализа визитов не настроены.")
        results.append(analysis)
    return results
