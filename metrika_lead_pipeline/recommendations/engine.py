from __future__ import annotations

from typing import Any

from metrika_lead_pipeline.models import PageFact, Recommendation


def _traffic_value(page: PageFact) -> tuple[int, str]:
    if page.visits > 0:
        return page.visits, "визитов"
    return page.pageviews, "просмотров страниц"


def _as_set(value: object) -> set[str]:
    if isinstance(value, list):
        return {str(item) for item in value}
    return set()


def _score_config(rec_rules: dict[str, object]) -> dict[str, float]:
    raw = rec_rules.get("scoring", {})
    scoring = raw if isinstance(raw, dict) else {}
    return {
        "high_intent_threshold": float(scoring.get("high_intent_threshold", 70)),
        "high_opportunity_threshold": float(scoring.get("high_opportunity_threshold", 50)),
        "high_risk_threshold": float(scoring.get("high_risk_threshold", 60)),
        "min_stage_confidence_for_form": float(scoring.get("min_stage_confidence_for_form", 0.55)),
    }


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _share(value: float | None) -> float:
    return float(value) if value is not None else 0.0


def _is_noncanonical_direct_form_url(url: str) -> bool:
    normalized = url.lower()
    return "/amp/" in normalized or "#gallery" in normalized or "#gal" in normalized


def _source_hits(page: PageFact, needles: tuple[str, ...]) -> int:
    total = 0
    for source, visits in page.traffic_sources.items():
        source_l = str(source).lower()
        if any(needle in source_l for needle in needles):
            total += int(visits)
    return total


def _traffic_context(page: PageFact, page_role: str = "unknown") -> str:
    traffic, _ = _traffic_value(page)
    discover_share = _share(page.discover_share)
    discover_hits = _source_hits(page, ("discover", "recommend", "дзен", "рекоменд"))
    if page_role in {"price_or_trims", "test_drive"} and (discover_share >= 0.1 or discover_hits >= traffic * 0.1):
        return "discover"
    if discover_share >= 0.5 or discover_hits > traffic * 0.5:
        return "discover"
    if _share(page.search_traffic_share) >= 0.5 or _source_hits(page, ("search", "organic", "поиск")) > traffic * 0.5:
        return "search"
    if _share(page.internal_share) >= 0.5 or _source_hits(page, ("internal", "внутрен")) > traffic * 0.5:
        return "internal"
    if _source_hits(page, ("direct", "прям")) > traffic * 0.5:
        return "direct"
    if _share(page.social_share) >= 0.5 or _source_hits(page, ("social", "соц")) > traffic * 0.5:
        return "social"
    if page.traffic_sources:
        return "mixed"
    return "unknown"


def _behavior_context(page: PageFact) -> str:
    if page.avg_time_seconds is None and page.page_depth is None and page.bounce_rate is None:
        return "unknown"
    if (page.avg_time_seconds or 0) >= 90 or (page.page_depth or 0) >= 2.0:
        return "engaged"
    if page.bounce_rate is not None and page.bounce_rate >= 70:
        return "shallow_or_bouncy"
    return "neutral"


def _split_signals(signals: list[str], rec_rules: dict[str, object]) -> dict[str, list[str]]:
    purchase = _as_set(rec_rules.get("purchase_signals"))
    choice = _as_set(rec_rules.get("choice_signals"))
    risk = _as_set(rec_rules.get("risk_signals"))
    cold = _as_set(rec_rules.get("cold_news_signals"))
    prohibited = _as_set(rec_rules.get("form_prohibited_signals"))

    # Backward compatibility: older tests and external callers may still pass
    # only commercial_signals. In that case, keep the old behavior by treating
    # those signals as purchase-like commercial signals.
    commercial = _as_set(rec_rules.get("commercial_signals"))
    if not purchase and not choice and not risk and not cold and commercial:
        purchase = commercial

    signal_set = set(signals)
    return {
        "purchase": sorted(signal_set & purchase),
        "choice": sorted(signal_set & choice),
        "risk": sorted(signal_set & risk),
        "cold": sorted(signal_set & cold),
        "prohibited": sorted(signal_set & prohibited),
    }


def _page_role(groups: dict[str, list[str]]) -> str:
    prohibited = set(groups["prohibited"])
    if "аварии и происшествия" in prohibited:
        return "tragedy_or_accident"
    if "отзывная кампания по безопасности" in prohibited:
        return "safety_recall"
    if groups["risk"]:
        return "risk_ownership"
    if "тест-драйв" in groups["purchase"]:
        return "test_drive"
    if {"цены", "комплектации", "дилеры"} & set(groups["purchase"]):
        return "price_or_trims"
    if "сравнение моделей" in groups["choice"]:
        return "comparison"
    if "категория/бюджет" in groups["choice"]:
        return "category_budget"
    if groups["cold"]:
        return "cold_news"
    return "unknown"


def _job_hypothesis(page_role: str) -> str:
    return {
        "tragedy_or_accident": "news_or_incident_context",
        "safety_recall": "safety_risk_check",
        "risk_ownership": "anxiety_risk_or_ownership_check",
        "test_drive": "experience_check_before_action",
        "price_or_trims": "price_trims_or_conditions_check",
        "comparison": "alternative_choice",
        "category_budget": "category_or_budget_choice",
        "cold_news": "news_interest",
    }.get(page_role, "unknown")


def _stage_hypothesis(page_role: str, traffic_context: str) -> str:
    if page_role in {"tragedy_or_accident", "safety_recall"}:
        return "form_prohibited"
    if page_role == "risk_ownership":
        return "risk_or_ownership"
    if traffic_context == "discover" and page_role in {"price_or_trims", "test_drive"}:
        return "commercial_page_but_unproven_visit_stage"
    if page_role in {"price_or_trims", "test_drive"}:
        return "lower_funnel_hypothesis"
    if page_role in {"comparison", "category_budget"}:
        return "middle_funnel_hypothesis"
    if page_role == "cold_news":
        return "upper_funnel"
    return "unknown"


def _intent_score(groups: dict[str, list[str]], page_role: str, traffic_context: str, behavior_context: str) -> float:
    score = 0.0
    score += min(45.0, 18.0 * len(groups["purchase"]))
    score += min(30.0, 15.0 * len(groups["choice"]))

    if traffic_context in {"search", "direct"}:
        score += 18.0
    elif traffic_context == "internal":
        score += 12.0
    elif traffic_context == "discover":
        score -= 12.0
    elif traffic_context == "social":
        score -= 8.0

    if behavior_context == "engaged":
        score += 10.0
    elif behavior_context == "shallow_or_bouncy":
        score -= 12.0

    if page_role == "risk_ownership":
        score -= 25.0
        if not groups["purchase"] and not groups["choice"]:
            score = min(score, 35.0)
    if page_role in {"tragedy_or_accident", "safety_recall", "cold_news"}:
        score = min(score, 25.0)
    if traffic_context == "discover" and page_role in {"price_or_trims", "test_drive"}:
        score = min(score, 60.0)

    return round(_clamp(score), 2)


def _opportunity_score(page: PageFact, groups: dict[str, list[str]], min_visits: int) -> float:
    traffic, _ = _traffic_value(page)
    score = min(45.0, 45.0 * traffic / max(min_visits * 5, 1))
    if groups["purchase"]:
        score += 25.0
    if groups["choice"]:
        score += 18.0
    if groups["risk"]:
        score += 10.0
    if page.title:
        score += 5.0
    if page.url:
        score += 5.0
    return round(_clamp(score), 2)


def _risk_score(groups: dict[str, list[str]], page_role: str, traffic_context: str, behavior_context: str) -> float:
    score = 0.0
    if groups["risk"]:
        score += 60.0
    if groups["prohibited"]:
        score += 90.0
    if page_role == "cold_news":
        score += 35.0
    if traffic_context in {"discover", "social"}:
        score += 15.0
    if behavior_context == "engaged" and groups["risk"]:
        score += 15.0
    return round(_clamp(score), 2)


def _stage_confidence(groups: dict[str, list[str]], traffic_context: str, behavior_context: str) -> float:
    confidence = 0.35
    if traffic_context in {"search", "direct"}:
        confidence += 0.2
    elif traffic_context == "internal":
        confidence += 0.15
    elif traffic_context == "discover":
        confidence -= 0.1

    if behavior_context == "engaged":
        confidence += 0.1
    elif behavior_context == "unknown":
        confidence -= 0.05

    if groups["purchase"] or groups["choice"]:
        confidence += 0.1
    if groups["risk"] and (groups["purchase"] or groups["choice"]):
        confidence -= 0.15
    if groups["prohibited"]:
        confidence += 0.15

    return round(max(0.0, min(1.0, confidence)), 2)


def _ranking_score(intent_score: float, opportunity_score: float, stage_confidence: float, form_prohibited: bool) -> float:
    if form_prohibited:
        return 0.0
    return round((intent_score / 100.0) * (opportunity_score / 100.0) * stage_confidence * 100.0, 2)


def _recommendation(
    page_role: str,
    groups: dict[str, list[str]],
    intent_score: float,
    opportunity_score: float,
    risk_score: float,
    stage_confidence: float,
    traffic_context: str,
    form_prohibited: bool,
    scoring: dict[str, float],
) -> tuple[str, str, bool, bool, str, str, bool, str]:
    high_intent = intent_score >= scoring["high_intent_threshold"]
    high_opportunity = opportunity_score >= scoring["high_opportunity_threshold"]
    high_risk = risk_score >= scoring["high_risk_threshold"]
    enough_confidence = stage_confidence >= scoring["min_stage_confidence_for_form"]

    if form_prohibited:
        return (
            "no_action",
            "none",
            False,
            True,
            "Страница попала в класс form_prohibited: коммерческая форма запрещена независимо от score.",
            "high",
            True,
            "",
        )

    if page_role == "risk_ownership":
        if groups["purchase"] or groups["choice"] or high_opportunity:
            return (
                "ab_test_early_vs_commitment",
                "early_cta_vs_commitment_cta",
                False,
                False,
                "",
                "high",
                True,
                "distinguishing_test",
            )
        return ("early_cta", "early_cta", False, False, "", "medium", True, "")

    if traffic_context == "discover" and page_role in {"price_or_trims", "test_drive"}:
        return (
            "ab_test_early_vs_commitment",
            "bridge_or_early_cta_vs_form",
            False,
            False,
            "",
            "medium",
            True,
            "distinguishing_test",
        )

    if page_role == "test_drive" and high_intent and high_opportunity and enough_confidence and not high_risk:
        return ("test_drive_form", "commitment_cta", True, False, "", "low", False, "")

    if page_role == "price_or_trims" and high_intent and high_opportunity and enough_confidence and not high_risk:
        return ("dealer_offer_form", "commitment_cta", True, False, "", "low", False, "")

    if page_role in {"comparison", "category_budget"} and high_opportunity:
        return ("selection_or_dealer_offer", "soft_commitment_cta", False, False, "", "medium", True, "")

    if page_role == "cold_news":
        return ("bridge", "bridge", False, False, "", "medium", False, "")

    if not groups["purchase"] and not groups["choice"] and not groups["risk"] and not groups["cold"]:
        return ("manual_review", "manual_review", False, False, "", "unknown", True, "")

    return ("manual_review", "manual_review", False, False, "", "medium", True, "")


def _reason(
    recommendation: str,
    traffic: int,
    traffic_label: str,
    groups: dict[str, list[str]],
    page_role: str,
    job_hypothesis: str,
    stage_hypothesis: str,
    form_allowed: bool,
    form_prohibited: bool,
    prohibition_reason: str,
) -> str:
    if form_prohibited:
        return prohibition_reason

    base = (
        f"Страница имеет {traffic} {traffic_label}; "
        f"роль материала: {page_role}; гипотеза работы: {job_hypothesis}; "
        f"гипотеза стадии: {stage_hypothesis}."
    )

    if recommendation in {"test_drive_form", "dealer_offer_form"} and form_allowed:
        return base + " Достаточный объем трафика и purchase-сигналы позволяют тестировать commitment CTA, но это остается гипотезой до целей/CRM."

    if recommendation == "ab_test_early_vs_commitment":
        return base + " Сигналы спорные: нужен различающий тест early CTA против commitment CTA."

    if recommendation == "early_cta":
        return base + " Risk/ownership-сигналы не интерпретируются как готовность к лид-форме; рекомендуется ранний CTA."

    if recommendation == "bridge":
        return base + " Новостной или холодный контекст не подтверждает готовность к форме; рекомендуется bridge или no action."

    if recommendation == "selection_or_dealer_offer":
        return base + " Пользователь выбирает альтернативы; преждевременно вести его в форму тест-драйва одной модели."

    if groups["purchase"] or groups["choice"] or groups["risk"] or groups["cold"]:
        return base + " Требуется ручная проверка из-за ограниченной уверенности или смешанных сигналов."

    return "Коммерческие сигналы не обнаружены."


def build_recommendations(
    pages: list[PageFact],
    page_signals: dict[str, list[str]],
    rules: dict[str, object],
) -> list[Recommendation]:
    rec_rules = dict(
        rules.get("recommendation_rules", {})
        if isinstance(rules.get("recommendation_rules"), dict)
        else {}
    )
    min_visits = int(rec_rules.get("min_visits", 100))
    commercial = _as_set(rec_rules.get("commercial_signals"))
    scoring = _score_config(rec_rules)
    prohibited_roles = _as_set(rec_rules.get("form_prohibited_page_roles"))

    recs: list[Recommendation] = []
    for page in pages:
        signals = [s for s in page_signals.get(page.url, []) if s != "Сигналы не обнаружены"]
        signal_set = set(signals)
        metrics = page.model_dump(exclude={"raw", "traffic_sources", "url", "title"})
        traffic, traffic_label = _traffic_value(page)

        groups = _split_signals(signals, rec_rules)
        page_role = _page_role(groups)
        job_hypothesis = _job_hypothesis(page_role)
        traffic_context = _traffic_context(page, page_role)
        behavior_context = _behavior_context(page)
        stage_hypothesis = _stage_hypothesis(page_role, traffic_context)

        intent = _intent_score(groups, page_role, traffic_context, behavior_context)
        opportunity = _opportunity_score(page, groups, min_visits)
        risk = _risk_score(groups, page_role, traffic_context, behavior_context)
        stage_conf = _stage_confidence(groups, traffic_context, behavior_context)

        form_prohibited = bool(groups["prohibited"]) or page_role in prohibited_roles
        ranking = _ranking_score(intent, opportunity, stage_conf, form_prohibited)

        limitations: list[str] = []
        data_limitations: list[str] = []

        if traffic < min_visits:
            limitations.append(f"Недостаточно {traffic_label}: {traffic} < {min_visits}.")
        if not signal_set.intersection(commercial) and not groups["risk"] and not groups["cold"] and not groups["prohibited"]:
            limitations.append("Коммерческие сигналы не обнаружены.")
        if traffic_context == "unknown":
            data_limitations.append("Источник трафика не определен.")
        if behavior_context == "unknown":
            data_limitations.append("Поведенческие признаки недоступны или агрегированы.")
        if traffic_context == "discover" and page_role in {"price_or_trims", "test_drive"}:
            data_limitations.append("Discover-трафик на коммерческой странице не доказывает нижнюю стадию визита.")

        (
            recommendation,
            cta_type,
            form_allowed,
            form_prohibited,
            prohibition_reason,
            ux_risk_level,
            manual_review,
            experiment_type,
        ) = _recommendation(
            page_role=page_role,
            groups=groups,
            intent_score=intent,
            opportunity_score=opportunity,
            risk_score=risk,
            stage_confidence=stage_conf,
            traffic_context=traffic_context,
            form_prohibited=form_prohibited,
            scoring=scoring,
        )
        if (
            traffic < min_visits
            and recommendation in {"dealer_offer_form", "test_drive_form"}
            and form_prohibited is False
        ):
            recommendation = "manual_review"
            cta_type = "manual_review"
            form_allowed = False
            manual_review = True
            ux_risk_level = "medium"
            experiment_type = ""

        if (
            _is_noncanonical_direct_form_url(page.url)
            and recommendation in {"dealer_offer_form", "test_drive_form"}
            and form_prohibited is False
        ):
            recommendation = "manual_review"
            cta_type = "manual_review"
            form_allowed = False
            manual_review = True
            ux_risk_level = "medium"
            experiment_type = ""


        reason = _reason(
            recommendation=recommendation,
            traffic=traffic,
            traffic_label=traffic_label,
            groups=groups,
            page_role=page_role,
            job_hypothesis=job_hypothesis,
            stage_hypothesis=stage_hypothesis,
            form_allowed=form_allowed,
            form_prohibited=form_prohibited,
            prohibition_reason=prohibition_reason,
        )

        if "Коммерческие сигналы не обнаружены." in limitations and not groups["risk"] and not groups["cold"] and not groups["prohibited"]:
            status = "Недостаточно данных"
            confidence = 0.0
            reason = "; ".join(limitations)
        elif traffic < min_visits and not form_prohibited:
            status = "Недостаточно данных"
            confidence = 0.0
        else:
            status = "Гипотеза"
            confidence = round(max(stage_conf, ranking / 100.0), 2)

        recs.append(
            Recommendation(
                url=page.url,
                title=page.title,
                metrics=metrics,
                detected_signals=signals,
                traffic_sources=page.traffic_sources,
                reason=reason,
                confidence=confidence,
                status=status,
                limitations=limitations,
                page_role=page_role,
                job_hypothesis=job_hypothesis,
                stage_hypothesis=stage_hypothesis,
                traffic_context=traffic_context,
                behavior_context=behavior_context,
                purchase_signals=groups["purchase"],
                choice_signals=groups["choice"],
                risk_signals=groups["risk"],
                cold_news_signals=groups["cold"],
                intent_score=intent,
                opportunity_score=opportunity,
                risk_score=risk,
                stage_confidence=stage_conf,
                ranking_score=ranking,
                recommendation=recommendation,
                recommended_cta_type=cta_type,
                form_allowed=form_allowed,
                form_prohibited=form_prohibited,
                prohibition_reason=prohibition_reason,
                ux_risk_level=ux_risk_level,
                data_limitations=data_limitations,
                manual_review_required=manual_review,
                experiment_type=experiment_type,
            )
        )

    return recs
