from __future__ import annotations

import re
from typing import Iterable

from metrika_lead_pipeline.models import PageFact, Recommendation

PURCHASE_KEYWORDS = {
    "цена", "стоимость", "комплектац", "налич", "дилер", "салон", "тест-драйв",
    "купить", "кредит", "скидк", "предложен", "прайс",
}
CHOICE_KEYWORDS = {
    "сравнен", "vs", "что выбрать", "лучше", "альтернатив", "рейтинг", "подборк",
    "бюджет", "класс автомобиля", "кроссовер", "седан", "семейный",
}
RISK_KEYWORDS = {
    "поломк", "надёжност", "надежност", "расход", "стоимость владения", "пробег",
    "отзыв владельца", "отзывы владельцев", "ремонт", "слабые места", "гарантия",
    "б/у", "подержан", "неисправност", "проблем", "безопасност",
}
COLD_NEWS_KEYWORDS = {
    "продаж", "рынок", "анонс", "премьер", "показал", "представил", "закон",
    "статистик", "инфоповод", "отзывная кампания", "дтп", "авари", "происшеств",
}
PROHIBITED_KEYWORDS = {"дтп", "авари", "происшеств", "отзывная кампания", "безопасност"}
MODEL_KEYWORDS = {
    "model", "лада", "ваз", "toyota", "hyundai", "kia", "bmw", "mercedes", "audi",
    "volkswagen", "renault", "geely", "haval", "chery", "moskvich", "москвич",
}

OLD_SIGNAL_GROUPS = {
    "цены": "purchase",
    "комплектации": "purchase",
    "дилеры": "purchase",
    "тест-драйв": "purchase",
    "сравнение моделей": "choice",
    "новость": "cold",
}


def _traffic_value(page: PageFact) -> tuple[int, str]:
    if page.visits > 0:
        return page.visits, "визитов"
    return page.pageviews, "просмотров страниц"


def _matches(text: str, keywords: Iterable[str]) -> list[str]:
    values = [keyword for keyword in keywords if keyword in text]
    if re.search(r"до\s+\d+(?:[,.]\d+)?\s*(?:млн|миллион)", text):
        values.append("до N млн")
    return sorted(set(values))


def _primary_source(page: PageFact) -> str:
    if not page.traffic_sources:
        return ""
    return max(page.traffic_sources.items(), key=lambda item: item[1])[0]


def _is_discover(source: str) -> bool:
    lowered = source.lower()
    return "discover" in lowered or "дзен" in lowered or "recommendation system" in lowered or "рекоменд" in lowered


def _is_practical_source(source: str) -> bool:
    lowered = source.lower()
    return any(part in lowered for part in ("search", "поиск", "direct", "internal", "внутрен"))


def _has_model(text: str) -> bool:
    return any(keyword in text for keyword in MODEL_KEYWORDS)


def _group_signals(text: str, extracted: list[str]) -> tuple[list[str], list[str], list[str], list[str]]:
    purchase = _matches(text, PURCHASE_KEYWORDS)
    choice = _matches(text, CHOICE_KEYWORDS)
    risk = _matches(text, RISK_KEYWORDS)
    cold = _matches(text, COLD_NEWS_KEYWORDS)
    for signal in extracted:
        group = OLD_SIGNAL_GROUPS.get(signal)
        if group == "purchase":
            purchase.append(signal)
        elif group == "choice":
            choice.append(signal)
        elif group == "risk":
            risk.append(signal)
        elif group == "cold":
            cold.append(signal)
    return sorted(set(purchase)), sorted(set(choice)), sorted(set(risk)), sorted(set(cold))


def _classify_page_role(purchase: list[str], choice: list[str], risk: list[str], cold: list[str], text: str) -> str:
    if risk:
        return "used_car" if any(k in text for k in ("б/у", "подержан", "пробег")) else "risk_ownership"
    if any(k in text for k in ("статистик", "рынок", "продаж")):
        return "market_stats"
    if cold:
        return "news"
    if choice:
        return "category_budget" if any(k in choice for k in ("бюджет", "класс автомобиля", "кроссовер", "седан")) else "comparison"
    if any("тест-драйв" in s for s in purchase):
        return "test_drive"
    if purchase:
        return "price_trims"
    return "unknown"


def _job_hypothesis(page_role: str, purchase: list[str], choice: list[str], risk: list[str], cold: list[str], source: str, has_model: bool) -> str:
    if risk:
        return "ownership_support" if page_role == "used_car" else "risk_reduction"
    if _is_discover(source) and cold:
        return "news_interest"
    if choice:
        return "alternative_comparison"
    if purchase and has_model and _is_practical_source(source):
        return "test_drive_validation" if any("тест-драйв" in s for s in purchase) else "price_terms_check"
    if purchase and has_model:
        return "cold_brand_interest" if _is_discover(source) else "model_learning"
    if cold:
        return "news_interest"
    return "unclear"


def _stage_hypothesis(page_role: str, purchase: list[str], choice: list[str], risk: list[str], cold: list[str], source: str, has_model: bool) -> str:
    if risk:
        return "ownership" if page_role == "used_car" else "risk_anxiety"
    if _is_discover(source) and purchase:
        return "unclear"
    if purchase and has_model and _is_practical_source(source):
        return "lower"
    if choice:
        return "middle"
    if cold:
        return "upper"
    return "unclear"


def _bounded(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def build_recommendations(pages: list[PageFact], page_signals: dict[str, list[str]], rules: dict[str, object]) -> list[Recommendation]:
    rec_rules = dict(rules.get("recommendation_rules", {}) if isinstance(rules.get("recommendation_rules"), dict) else {})
    min_visits = int(rec_rules.get("min_visits", 100))
    recs: list[Recommendation] = []
    for page in pages:
        extracted = [s for s in page_signals.get(page.url, []) if s != "Сигналы не обнаружены"]
        text = f"{page.title} {page.url}".lower()
        purchase, choice, risk, cold = _group_signals(text, extracted)
        source = _primary_source(page)
        traffic, traffic_label = _traffic_value(page)
        model_present = _has_model(text)
        page_role = _classify_page_role(purchase, choice, risk, cold, text)
        job = _job_hypothesis(page_role, purchase, choice, risk, cold, source, model_present)
        stage = _stage_hypothesis(page_role, purchase, choice, risk, cold, source, model_present)
        limitations: list[str] = []
        constraints: list[str] = []
        if traffic < min_visits:
            limitations.append(f"Недостаточно {traffic_label}: {traffic} < {min_visits}.")
        if not source:
            limitations.append("Источник трафика недоступен на уровне страницы; стадия определяется только по агрегированным признакам.")
        risk_score = _bounded(len(risk) * 24 + (20 if page_role in {"risk_ownership", "used_car"} else 0) + (10 if page.avg_time_seconds and page.avg_time_seconds > 180 and risk else 0))
        intent_score = len(purchase) * 18 + len(choice) * 8 + (24 if stage == "lower" else 0) + (10 if model_present else 0) + (10 if _is_practical_source(source) else 0)
        if risk_score >= 60:
            intent_score = min(intent_score, 45 if purchase else 30)
            constraints.append("risk_dominates_intent")
        if cold and not purchase and not choice:
            intent_score = min(intent_score, 20)
            constraints.append("cold_news_context")
        if _is_discover(source) and purchase:
            intent_score = min(intent_score, 55)
            constraints.append("discover_purchase_stage_uncertain")
        intent_score = _bounded(intent_score)
        opportunity_score = _bounded(min(80, traffic / max(min_visits, 1) * 40) + min(20, page.visitors / max(min_visits, 1) * 10) + (10 if purchase or choice or risk else 0))
        stage_confidence = 100.0
        if not source:
            stage_confidence -= 20
            constraints.append("missing_page_source")
        if _is_discover(source) and purchase:
            stage_confidence -= 35
        if risk and (purchase or choice):
            stage_confidence -= 25
            constraints.append("conflicting_risk_and_commercial_signals")
        if stage == "unclear":
            stage_confidence -= 20
        if page.avg_time_seconds is None and page.page_depth is None:
            stage_confidence -= 10
            constraints.append("behavior_aggregated_or_missing")
        stage_confidence = _bounded(stage_confidence)
        form_prohibited = bool(_matches(text, PROHIBITED_KEYWORDS)) or (page_role == "market_stats" and not (purchase or choice))
        prohibition_reason = ""
        if form_prohibited:
            prohibition_reason = "Контекст относится к авариям/безопасности/отзывным кампаниям или рыночной статистике без практического выбора автомобиля."
            constraints.append("form_prohibited_context")
        form_allowed = False
        recommendation = "manual_review"
        cta_type = "manual_review"
        experiment_type: str | None = None
        manual_review = False
        ux_risk = "medium"
        if form_prohibited:
            recommendation = "form_prohibited"
            cta_type = "none"
            ux_risk = "high"
        elif risk_score >= 60:
            if purchase or choice or traffic >= min_visits:
                recommendation = "run_discriminating_test"
                cta_type = "manual_review"
                experiment_type = "ab_test_early_vs_commitment"
            else:
                recommendation = "early_cta"
                cta_type = "early_action"
            ux_risk = "high"
        elif _is_discover(source) and purchase:
            recommendation = "run_discriminating_test"
            cta_type = "manual_review"
            experiment_type = "ab_test_early_vs_commitment"
            ux_risk = "medium"
        elif stage_confidence < 50:
            recommendation = "run_discriminating_test"
            cta_type = "manual_review"
            experiment_type = "ab_test_early_vs_commitment"
            manual_review = True
        elif stage == "lower" and purchase and model_present and stage_confidence >= 60:
            form_allowed = True
            cta_type = "commitment"
            recommendation = "test_drive_form" if any("тест-драйв" in s for s in purchase) else "dealer_offer_form"
            ux_risk = "low"
        elif choice:
            recommendation = "selection_form" if not model_present else "dealer_offer_form"
            form_allowed = not risk and stage_confidence >= 60
            cta_type = "commitment" if form_allowed else "bridge"
            ux_risk = "medium"
        elif cold:
            recommendation = "bridge" if traffic >= min_visits else "no_action"
            cta_type = "bridge" if recommendation == "bridge" else "none"
            ux_risk = "medium"
        elif traffic < min_visits or not (purchase or choice):
            recommendation = "no_action"
            cta_type = "none"
        ranking_score = _bounded(intent_score * opportunity_score * stage_confidence / 10000)
        if not form_allowed and recommendation in {"test_drive_form", "dealer_offer_form"}:
            recommendation = "manual_review"
            cta_type = "manual_review"
            manual_review = True
        if traffic < min_visits and recommendation in {"dealer_offer_form", "test_drive_form"} and not form_prohibited:
            recommendation = "manual_review"
            cta_type = "manual_review"
            form_allowed = False
            manual_review = True
            ux_risk = "medium"
            experiment_type = ""
        if form_prohibited:
            ranking_score = 0.0
        status = "Недостаточно данных" if traffic < min_visits and recommendation in {"no_action", "manual_review"} else "Гипотеза"
        confidence = stage_confidence / 100
        explanation = _explain(recommendation, job, stage, purchase, choice, risk, cold, source, traffic, traffic_label, constraints, form_prohibited, prohibition_reason)
        metrics = page.model_dump(exclude={"raw", "traffic_sources", "url", "title"})
        recs.append(Recommendation(
            url=page.url, title=page.title, metrics=metrics, detected_signals=extracted,
            traffic_sources=page.traffic_sources, reason=explanation, confidence=confidence,
            status=status, limitations=limitations, pageviews=page.pageviews, users=page.visitors,
            primary_source=source, page_role=page_role, job_hypothesis=job, stage_hypothesis=stage,
            traffic_context=("discover" if _is_discover(source) else ("practical" if _is_practical_source(source) else "unknown")),
            behavior_context="aggregated" if page.avg_time_seconds is None and page.page_depth is None else "engagement_available",
            purchase_signals=purchase, choice_signals=choice, risk_signals=risk, cold_news_signals=cold,
            intent_score=intent_score, opportunity_score=opportunity_score, risk_score=risk_score,
            stage_confidence=stage_confidence, ranking_score=ranking_score, recommendation=recommendation,
            recommended_cta_type=cta_type, form_allowed=form_allowed, form_prohibited=form_prohibited,
            prohibition_reason=prohibition_reason, ux_risk_level=ux_risk, explanation=explanation,
            data_limitations=limitations, manual_review_required=manual_review,
            experiment_type=experiment_type, triggered_constraints=constraints, score=ranking_score,
            buyer_intent_index=ranking_score,
        ))
    return recs


def _explain(recommendation: str, job: str, stage: str, purchase: list[str], choice: list[str], risk: list[str], cold: list[str], source: str, traffic: int, traffic_label: str, constraints: list[str], form_prohibited: bool, prohibition_reason: str) -> str:
    parts = [f"Гипотеза работы: {job}; стадия: {stage}; трафик: {traffic} {traffic_label}."]
    if purchase:
        parts.append(f"Purchase-сигналы: {', '.join(purchase)}.")
    if choice:
        parts.append(f"Choice-сигналы: {', '.join(choice)}.")
    if risk:
        parts.append(f"Страница содержит risk/ownership-сигналы: {', '.join(risk)}. Длинное чтение не интерпретируется как готовность к лиду, потому что доминирует тревожная работа.")
    if cold:
        parts.append(f"Cold-news-сигналы: {', '.join(cold)}.")
    if form_prohibited:
        parts.append(prohibition_reason)
    if "discover_purchase_stage_uncertain" in constraints:
        parts.append("Источник Discover не считается автоматическим подтверждением lower-stage даже при purchase-сигналах; требуется bridge или различающий тест early CTA против commitment CTA.")
    if recommendation == "run_discriminating_test":
        parts.append(f"Рекомендация: run_discriminating_test, чтобы проверить джобу '{job}' через вариант A early_action и вариант B commitment.")
    else:
        parts.append(f"Рекомендация: {recommendation}.")
    return " ".join(part for part in parts if part)
