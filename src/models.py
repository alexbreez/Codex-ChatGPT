from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

DecisionStatus = Literal["Подтверждено данными", "Гипотеза", "Недостаточно данных"]


class DumpMixin:
    def model_dump(self, *args: Any, exclude: set[str] | None = None, **kwargs: Any) -> dict[str, Any]:
        data = asdict(self)
        for key in exclude or set():
            data.pop(key, None)
        return data


@dataclass
class PageFact(DumpMixin):
    url: str
    title: str = ""
    visits: int = 0
    visitors: int = 0
    bounce_rate: float | None = None
    page_depth: float | None = None
    avg_time_seconds: float | None = None
    traffic_sources: dict[str, int] = field(default_factory=dict)
    is_entry_page: bool = False
    is_exit_page: bool | None = None
    search_traffic_share: float | None = None
    discover_share: float | None = None
    internal_share: float | None = None
    social_share: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SignalFinding(DumpMixin):
    url: str
    signal: str
    rule_id: str
    confidence: float
    explanation: str
    matched_values: list[str] = field(default_factory=list)


@dataclass
class RuleEvaluation(DumpMixin):
    rule_id: str
    name: str
    description: str = ""
    matched: bool = False
    reason: str = ""
    values: dict[str, Any] = field(default_factory=dict)


@dataclass
class VisitAnalysis(DumpMixin):
    visit_id: str
    entry_url: str | None = None
    page_urls: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)
    added_signals: list[str] = field(default_factory=list)
    status: DecisionStatus = "Недостаточно данных"
    confidence: float = 0.0
    rule_evaluations: list[RuleEvaluation] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


@dataclass
class Recommendation(DumpMixin):
    url: str
    title: str
    metrics: dict[str, Any]
    detected_signals: list[str]
    traffic_sources: dict[str, int]
    reason: str
    confidence: float
    status: DecisionStatus
    limitations: list[str] = field(default_factory=list)


@dataclass
class DecisionRecord(DumpMixin):
    decision_id: str
    created_at: datetime
    analytics_rules_version: str
    signal_dictionary_version: str
    config_version: str
    facts: dict[str, Any]
    triggered_rules: list[RuleEvaluation]
    non_triggered_rules: list[RuleEvaluation]
    final_status: DecisionStatus
    confidence: float
    explanation: str
    recommendations: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
