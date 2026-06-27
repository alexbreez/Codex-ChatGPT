from __future__ import annotations

import re
from typing import Any

from src.models import PageFact, RuleEvaluation, SignalFinding


def extract_signals(page: PageFact, signal_config: dict[str, Any], models: list[str] | None = None) -> tuple[list[SignalFinding], list[RuleEvaluation]]:
    text = f"{page.title} {page.url}"
    findings: list[SignalFinding] = []
    evaluations: list[RuleEvaluation] = []
    car_models = models or []
    for rule in signal_config.get("signals", []):
        matched_values: list[str] = []
        ok = True
        for pattern in rule.get("all_patterns", []) or []:
            found = re.findall(str(pattern), text)
            ok = ok and bool(found)
            matched_values.extend([str(x) for x in found])
        any_patterns = rule.get("any_patterns", []) or []
        if any_patterns:
            any_found: list[str] = []
            for pattern in any_patterns:
                any_found.extend([str(x) for x in re.findall(str(pattern), text)])
            ok = ok and bool(any_found)
            matched_values.extend(any_found)
        min_models = int(rule.get("min_model_mentions", 0) or 0)
        if min_models:
            mentioned = [m for m in car_models if re.search(re.escape(m), text, re.IGNORECASE)]
            ok = ok and len(mentioned) >= min_models
            matched_values.extend(mentioned)
        evaluations.append(RuleEvaluation(rule_id=str(rule["id"]), name=str(rule["name"]), description=str(rule.get("explanation", "")), matched=ok, reason="Правило сработало" if ok else "Условия правила не выполнены", values={"matched_values": matched_values}))
        if ok:
            findings.append(SignalFinding(url=page.url, signal=str(rule["name"]), rule_id=str(rule["id"]), confidence=float(rule.get("confidence", 0.5)), explanation=str(rule.get("explanation", "")), matched_values=matched_values))
    if not findings:
        findings.append(SignalFinding(url=page.url, signal="Сигналы не обнаружены", rule_id="no_signal", confidence=1.0, explanation="Ни одно правило сигналов не сработало."))
    return findings, evaluations
