from __future__ import annotations

import json
from pathlib import Path

from metrika_lead_pipeline.history.delta import DeltaEngine
from metrika_lead_pipeline.models import PageFact
from metrika_lead_pipeline.pipeline.runner import run_pipeline_from_facts
from metrika_lead_pipeline.recommendations.engine import build_recommendations

RULES = {"recommendation_rules": {"min_visits": 100, "commercial_signals": ["цены", "комплектации", "тест-драйв", "сравнение моделей"]}}


def _rec(page: PageFact):
    return build_recommendations([page], {page.url: []}, RULES)[0]


def test_risk_ownership_does_not_get_direct_form() -> None:
    rec = _rec(PageFact(url="/cars/model-a-risk", title="Model A поломки расход надёжность", pageviews=5000, visitors=3000, avg_time_seconds=260, traffic_sources={"Search engine traffic": 4000}))
    assert rec.risk_score >= 60
    assert rec.intent_score < 60
    assert rec.recommendation in {"bridge", "early_cta", "run_discriminating_test", "manual_review"}
    assert rec.recommendation != "test_drive_form"
    assert "тревож" in rec.explanation


def test_discover_price_page_is_not_automatically_lower_stage() -> None:
    rec = _rec(PageFact(url="/cars/model-a-price", title="Model A цена комплектация", pageviews=3000, visitors=2000, traffic_sources={"Discover": 2800}))
    assert rec.stage_hypothesis != "lower"
    assert rec.stage_confidence < 100
    assert rec.recommendation in {"run_discriminating_test", "bridge", "early_cta", "manual_review"}
    assert rec.recommendation != "test_drive_form"


def test_search_price_model_can_get_commitment_form() -> None:
    rec = _rec(PageFact(url="/cars/model-a-price", title="Model A цена комплектация", visits=300, visitors=200, traffic_sources={"Search engine traffic": 250}))
    assert rec.intent_score >= 60
    assert rec.opportunity_score >= 50
    assert rec.stage_confidence >= 60
    assert rec.recommendation in {"test_drive_form", "dealer_offer_form"}
    assert rec.form_allowed is True


def test_comparison_prefers_selection_or_offer_not_single_test_drive() -> None:
    rec = _rec(PageFact(url="/cars/model-a-vs-model-b", title="Сравнение Model A vs Model B что выбрать", visits=250, visitors=150, traffic_sources={"Search engine traffic": 200}))
    assert rec.job_hypothesis == "alternative_comparison"
    assert rec.recommendation in {"dealer_offer_form", "selection_form", "bridge", "run_discriminating_test"}
    assert rec.recommendation != "test_drive_form"


def test_cold_news_does_not_get_form() -> None:
    rec = _rec(PageFact(url="/news/market", title="Продажи рынок анонс премьера", pageviews=1000, visitors=900, traffic_sources={"Discover": 900}))
    assert rec.intent_score <= 20
    assert rec.recommendation in {"no_action", "bridge", "form_prohibited"}
    assert rec.form_allowed is False


def test_form_prohibited_overrides_score_and_decision_log(tmp_path: Path) -> None:
    page = PageFact(url="/news/crash", title="Model A ДТП авария отзывная кампания безопасность", pageviews=10000, visitors=8000, traffic_sources={"Search engine traffic": 6000})
    rec = _rec(page)
    assert rec.form_prohibited is True
    assert rec.form_allowed is False
    assert rec.recommendation not in {"test_drive_form", "dealer_offer_form", "selection_form"}
    assert rec.prohibition_reason
    run_pipeline_from_facts([page], output_dir=tmp_path)
    payload = json.loads((tmp_path / "decision_log.json").read_text(encoding="utf-8"))
    decision = payload[0] if isinstance(payload, list) else payload["records"][0]
    assert decision["form_prohibited"] is True
    assert decision["prohibition_reason"]
    assert "scores" in decision


def test_ranking_keeps_intent_and_opportunity_separate(tmp_path: Path) -> None:
    high_traffic_weak_intent = _rec(PageFact(url="/news/market", title="Продажи рынок статистика", pageviews=20000, visitors=15000, traffic_sources={"Discover": 15000}))
    lower_traffic_strong_intent = _rec(PageFact(url="/cars/model-a-price", title="Model A цена комплектация", visits=300, visitors=250, traffic_sources={"Search engine traffic": 250}))
    assert lower_traffic_strong_intent.intent_score > high_traffic_weak_intent.intent_score
    assert high_traffic_weak_intent.opportunity_score >= lower_traffic_strong_intent.opportunity_score
    assert lower_traffic_strong_intent.ranking_score >= 0
    run_pipeline_from_facts([
        PageFact(url="/news/market", title="Продажи рынок статистика", pageviews=20000, visitors=15000, traffic_sources={"Discover": 15000}),
        PageFact(url="/cars/model-a-price", title="Model A цена комплектация", visits=300, visitors=250, traffic_sources={"Search engine traffic": 250}),
    ], output_dir=tmp_path)
    report = (tmp_path / "lead_generation_report.md").read_text(encoding="utf-8")
    assert "intent_score" in report
    assert "opportunity_score" in report
    assert "ranking_score" in report


def test_delta_tracks_methodology_fields() -> None:
    delta = DeltaEngine().compare(
        {"pages": [{"url": "/u"}], "signals": [], "recommendations": [{"url": "/u", "intent_score": 20, "recommendation": "bridge", "form_allowed": False}]},
        {"pages": [{"url": "/u"}], "signals": [], "recommendations": [{"url": "/u", "intent_score": 80, "recommendation": "dealer_offer_form", "form_allowed": True}]},
    )
    assert delta.methodology_changes["/u"]["intent_score"] == {"previous": 20, "current": 80}
    assert delta.methodology_changes["/u"]["recommendation"]["current"] == "dealer_offer_form"
