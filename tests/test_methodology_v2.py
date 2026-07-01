from __future__ import annotations

from metrika_lead_pipeline.models import PageFact
from metrika_lead_pipeline.recommendations.engine import build_recommendations


def _rules() -> dict[str, dict[str, object]]:
    return {"recommendation_rules": {"min_visits": 100}}


def test_low_traffic_direct_form_is_forced_to_manual_review() -> None:
    page = PageFact(
        url="/cars/model-a-low-traffic-price",
        title="Model A цена комплектации дилер кроссовер",
        pageviews=20,
        visitors=18,
        search_traffic_share=0.9,
        avg_time_seconds=120,
    )

    rec = build_recommendations(
        [page],
        {page.url: ["цены", "комплектации", "дилеры", "категория/бюджет"]},
        _rules(),
    )[0]

    assert rec.status == "Недостаточно данных"
    assert rec.form_allowed is False
    assert rec.recommendation == "manual_review"
    assert rec.recommended_cta_type == "manual_review"
    assert rec.manual_review_required is True
    assert rec.form_prohibited is False
    assert "Недостаточно просмотров страниц" in " ".join(rec.limitations)

    high_traffic_page = PageFact(
        url="/cars/model-a-high-traffic-price",
        title="Model A цена комплектации дилер",
        pageviews=200,
        visitors=150,
        traffic_sources={"Search engine traffic": 180},
    )
    high_traffic_rec = build_recommendations(
        [high_traffic_page],
        {high_traffic_page.url: ["цены", "комплектации", "дилеры"]},
        _rules(),
    )[0]

    assert high_traffic_rec.recommendation == "dealer_offer_form"
    assert high_traffic_rec.recommended_cta_type in {"commitment_cta", "commitment"}
    assert high_traffic_rec.form_allowed is True
