from __future__ import annotations

from metrika_lead_pipeline.models import PageFact, Recommendation


def _traffic_value(page: PageFact) -> tuple[int, str]:
    if page.visits > 0:
        return page.visits, "визитов"
    return page.pageviews, "просмотров страниц"


def build_recommendations(pages: list[PageFact], page_signals: dict[str, list[str]], rules: dict[str, object]) -> list[Recommendation]:
    rec_rules = dict(rules.get("recommendation_rules", {}) if isinstance(rules.get("recommendation_rules"), dict) else {})
    min_visits = int(rec_rules.get("min_visits", 100))
    commercial = set(rec_rules.get("commercial_signals", []))
    recs: list[Recommendation] = []
    for page in pages:
        signals = [s for s in page_signals.get(page.url, []) if s != "Сигналы не обнаружены"]
        metrics = page.model_dump(exclude={"raw", "traffic_sources", "url", "title"})
        traffic, traffic_label = _traffic_value(page)
        limitations: list[str] = []
        if traffic < min_visits:
            limitations.append(f"Недостаточно {traffic_label}: {traffic} < {min_visits}.")
        if not set(signals).intersection(commercial):
            limitations.append("Коммерческие сигналы не обнаружены.")
        if limitations:
            status = "Недостаточно данных"
            confidence = 0.0
            reason = "; ".join(limitations)
        else:
            status = "Гипотеза"
            confidence = min(0.9, 0.5 + min(traffic / (min_visits * 10), 0.3) + 0.1 * len(set(signals).intersection(commercial)))
            reason = f"Страница имеет достаточный объем {traffic_label} и наблюдаемые коммерческие сигналы; рекомендуется тест размещения формы, а не утверждение результата."
        recs.append(Recommendation(url=page.url, title=page.title, metrics=metrics, detected_signals=signals, traffic_sources=page.traffic_sources, reason=reason, confidence=confidence, status=status, limitations=limitations))
    return recs
