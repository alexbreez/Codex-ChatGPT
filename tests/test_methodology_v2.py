from __future__ import annotations

import json
from pathlib import Path

from metrika_lead_pipeline.config.loader import default_config_path, load_yaml
from metrika_lead_pipeline.models import PageFact
from metrika_lead_pipeline.pipeline.runner import run_pipeline
from metrika_lead_pipeline.recommendations.engine import build_recommendations


def _rules() -> dict[str, object]:
    return load_yaml(default_config_path("rules.yaml"))


def test_high_opportunity_risk_ownership_gets_distinguishing_test_without_allowing_form() -> None:
    page = PageFact(
        url="/cars/model-a-polomki",
        title="Поломки Model A расход надежность",
        pageviews=500,
        visitors=300,
        avg_time_seconds=180,
    )

    rec = build_recommendations([page], {page.url: ["risk/ownership"]}, _rules())[0]

    assert rec.page_role == "risk_ownership"
    assert rec.job_hypothesis == "anxiety_risk_or_ownership_check"
    assert rec.recommendation == "ab_test_early_vs_commitment"
    assert rec.recommended_cta_type == "early_cta_vs_commitment_cta"
    assert rec.experiment_type == "distinguishing_test"
    assert rec.form_allowed is False
    assert rec.form_prohibited is False
    assert rec.manual_review_required is True
    assert rec.risk_score >= 60
    assert rec.intent_score < 70


def test_risk_ownership_with_purchase_signal_gets_distinguishing_test() -> None:
    page = PageFact(
        url="/cars/model-a-bu-price",
        title="Model A б/у цена и слабые места",
        pageviews=500,
        visitors=300,
        avg_time_seconds=180,
    )

    rec = build_recommendations([page], {page.url: ["risk/ownership", "цены"]}, _rules())[0]

    assert rec.page_role == "risk_ownership"
    assert rec.recommendation == "ab_test_early_vs_commitment"
    assert rec.recommended_cta_type == "early_cta_vs_commitment_cta"
    assert rec.experiment_type == "distinguishing_test"
    assert rec.form_allowed is False
    assert rec.manual_review_required is True


def test_discover_price_page_gets_distinguishing_test_not_lower_funnel_form() -> None:
    page = PageFact(
        url="/cars/model-a-price",
        title="Model A цена и комплектации",
        pageviews=800,
        visitors=500,
        discover_share=0.9,
        avg_time_seconds=120,
    )

    rec = build_recommendations([page], {page.url: ["цены", "комплектации"]}, _rules())[0]

    assert rec.page_role == "price_or_trims"
    assert rec.stage_hypothesis == "commercial_page_but_unproven_visit_stage"
    assert rec.recommendation == "ab_test_early_vs_commitment"
    assert rec.recommended_cta_type == "bridge_or_early_cta_vs_form"
    assert rec.experiment_type == "distinguishing_test"
    assert rec.form_allowed is False
    assert any("Discover" in item for item in rec.data_limitations)


def test_recommendation_system_traffic_on_price_page_gets_distinguishing_test() -> None:
    page = PageFact(
        url="/cars/model-a-price",
        title="Model A цена и комплектации",
        pageviews=100,
        visitors=80,
        traffic_sources={"Recommendation system traffic": 90, "Search engine traffic": 10},
        avg_time_seconds=120,
    )

    rec = build_recommendations([page], {page.url: ["цены", "комплектации"]}, _rules())[0]

    assert rec.page_role == "price_or_trims"
    assert rec.traffic_context == "discover"
    assert rec.stage_hypothesis == "commercial_page_but_unproven_visit_stage"
    assert rec.recommendation == "ab_test_early_vs_commitment"
    assert rec.experiment_type == "distinguishing_test"
    assert rec.form_allowed is False


def test_search_price_page_can_allow_dealer_offer_form() -> None:
    page = PageFact(
        url="/cars/model-a-price",
        title="Model A цена комплектации дилер",
        pageviews=800,
        visitors=500,
        search_traffic_share=0.9,
        avg_time_seconds=120,
    )

    rec = build_recommendations([page], {page.url: ["цены", "комплектации", "дилеры"]}, _rules())[0]

    assert rec.page_role == "price_or_trims"
    assert rec.stage_hypothesis == "lower_funnel_hypothesis"
    assert rec.recommendation == "dealer_offer_form"
    assert rec.recommended_cta_type == "commitment_cta"
    assert rec.form_allowed is True
    assert rec.form_prohibited is False
    assert rec.intent_score >= 70


def test_form_prohibited_signal_blocks_form_even_with_purchase_signal() -> None:
    page = PageFact(
        url="/news/accident-price",
        title="ДТП с Model A цена ремонта",
        pageviews=1000,
        visitors=700,
        search_traffic_share=0.8,
    )

    rec = build_recommendations([page], {page.url: ["аварии и происшествия", "цены"]}, _rules())[0]

    assert rec.page_role == "tragedy_or_accident"
    assert rec.recommendation == "no_action"
    assert rec.form_allowed is False
    assert rec.form_prohibited is True
    assert rec.ranking_score == 0.0
    assert "form_prohibited" in rec.reason


def test_decision_log_contains_methodology_v2_fields(tmp_path: Path) -> None:
    rows = [
        {
            "url": "/cars/model-a-polomki",
            "title": "Поломки Model A расход надежность",
            "pageviews": 500,
            "visitors": 300,
            "avg_time_seconds": 180,
        }
    ]

    run_pipeline(rows, output_dir=tmp_path)

    decision_log = json.loads((tmp_path / "decision_log.json").read_text(encoding="utf-8"))
    decision = decision_log[0]

    assert decision["page_role"] == "risk_ownership"
    assert decision["recommendation"] == "ab_test_early_vs_commitment"
    assert decision["recommended_cta_type"] == "early_cta_vs_commitment_cta"
    assert decision["form_allowed"] is False
    assert decision["manual_review_required"] is True
    assert decision["experiment_type"] == "distinguishing_test"
    assert decision["scores"]["risk_score"] >= 60
    assert decision["triggered_signals"]["risk_signals"] == ["risk/ownership"]


def test_pipeline_preserves_pageviews_and_explicit_traffic_shares_for_recommendations(tmp_path: Path) -> None:
    rows = [
        {
            "url": "/cars/model-a-price",
            "title": "Model A цена комплектации дилер",
            "pageviews": 800,
            "visitors": 500,
            "search_traffic_share": 0.9,
            "avg_time_seconds": 120,
        }
    ]

    run_pipeline(rows, output_dir=tmp_path)

    decision_log = json.loads((tmp_path / "decision_log.json").read_text(encoding="utf-8"))
    decision = decision_log[0]

    assert decision["page_role"] == "price_or_trims"
    assert decision["recommendation"] == "dealer_offer_form"
    assert decision["recommended_cta_type"] == "commitment_cta"
    assert decision["form_allowed"] is True
    assert decision["scores"]["intent_score"] >= 70
    assert decision["scores"]["opportunity_score"] >= 50
