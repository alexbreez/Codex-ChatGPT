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


def canonical_page_url(url: str) -> str:
    """Return a canonical page URL for grouping URL variants before scoring.

    Methodology v3 requires grouping fragments and AMP variants before
    opportunity_score is calculated. This helper intentionally stays narrow:
    it removes URL fragments and maps trailing /amp or /amp/ variants to the
    article URL, without broad URL parsing or query stripping.
    """
    normalized = str(url or "")
    if "#" in normalized:
        normalized = normalized.split("#", 1)[0]

    body, sep, query = normalized.partition("?")
    body = body.replace("/content/amp/news/", "/content/news/")
    body = body.replace("/content/amp/articles/", "/content/articles/")

    if body.endswith("/amp/"):
        body = body[:-4]
    elif body.endswith("/amp"):
        body = body[:-3]

    return body + (sep + query if sep else "")


@dataclass
class PageFact(DumpMixin):
    url: str
    title: str = ""
    canonical_url: str = ""
    url_variants: list[str] = field(default_factory=list)
    visits: int = 0
    pageviews: int = 0
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
class VisitFact(DumpMixin):
    visit_id: str
    entry_url: str | None = None
    page_urls: list[str] = field(default_factory=list)
    goal_ids: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    device: str | None = None
    region: str | None = None
    source: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SourceFact(DumpMixin):
    source: str
    visits: int = 0
    url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class GoalFact(DumpMixin):
    goal_id: str
    goal_name: str = ""
    url: str | None = None
    visits: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchQueryFact(DumpMixin):
    query: str
    visits: int = 0
    url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeviceFact(DumpMixin):
    device: str
    visits: int = 0
    url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class RegionFact(DumpMixin):
    region: str
    visits: int = 0
    url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedMetrikaData(DumpMixin):
    pages: list[PageFact] = field(default_factory=list)
    visits: list[VisitFact] = field(default_factory=list)
    sources: list[SourceFact] = field(default_factory=list)
    goals: list[GoalFact] = field(default_factory=list)
    search_queries: list[SearchQueryFact] = field(default_factory=list)
    devices: list[DeviceFact] = field(default_factory=list)
    regions: list[RegionFact] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


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

    # Methodology v2 fields. These defaults preserve backward compatibility with
    # existing tests and callers while allowing the recommendation engine to expose
    # separate intent, opportunity, risk, confidence and ranking dimensions.
    page_role: str = "unknown"
    job_hypothesis: str = "unknown"
    stage_hypothesis: str = "unknown"
    traffic_context: str = "unknown"
    behavior_context: str = "unknown"
    purchase_signals: list[str] = field(default_factory=list)
    choice_signals: list[str] = field(default_factory=list)
    risk_signals: list[str] = field(default_factory=list)
    cold_news_signals: list[str] = field(default_factory=list)
    intent_score: float = 0.0
    opportunity_score: float = 0.0
    risk_score: float = 0.0
    stage_confidence: float = 0.0
    ranking_score: float = 0.0
    recommendation: str = "manual_review"
    recommended_cta_type: str = "manual_review"
    form_allowed: bool = False
    form_prohibited: bool = False
    prohibition_reason: str = ""
    ux_risk_level: str = "unknown"
    data_limitations: list[str] = field(default_factory=list)
    manual_review_required: bool = True
    experiment_type: str = ""


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
    event_type: str = "analytical_decision"
    previous_state: dict[str, Any] | None = None
    new_state: dict[str, Any] | None = None

    # Methodology v2 audit fields. Decision Log must explain not only why a form
    # is recommended, but also why it is prohibited, postponed, replaced by bridge
    # or routed to early CTA / manual review.
    page_role: str = "unknown"
    job_hypothesis: str = "unknown"
    stage_hypothesis: str = "unknown"
    traffic_context: str = "unknown"
    behavior_context: str = "unknown"
    stage_confidence: float = 0.0
    scores: dict[str, float] = field(default_factory=dict)
    triggered_signals: dict[str, list[str]] = field(default_factory=dict)
    triggered_constraints: list[str] = field(default_factory=list)
    recommendation: str = "manual_review"
    recommended_cta_type: str = "manual_review"
    form_allowed: bool = False
    form_prohibited: bool = False
    prohibition_reason: str = ""
    ux_risk_level: str = "unknown"
    rationale: str = ""
    data_limitations: list[str] = field(default_factory=list)
    manual_review_required: bool = True
    experiment_type: str = ""
