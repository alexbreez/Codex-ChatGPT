from __future__ import annotations

from metrika_lead_pipeline.models import PageFact, Recommendation


def build_recommendations(pages: list[PageFact], page_signals: dict[str, list[str]], rules: dict[str, object]) -> list[Recommendation]:
    rec_rules = dict(rules.get("recommendation_rules", {}) if isinstance(rules.get("recommendation_rules"), dict) else {})
    min_visits = int(rec_rules.get("min_visits", 100))
    commercial = set(rec_rules.get("commercial_signals", []))
    recs: list[Recommendation] = []
    for page in pages:
        signals = [s for s in page_signals.get(page.url, []) if s != "Сигналы не обнаружены"]
        metrics = page.model_dump(exclude={"raw", "traffic_sources", "url", "title"})
        limitations: list[str] = []
        if page.visits < min_visits:
            limitations.append(f"Недостаточно визитов: {page.visits} < {min_visits}.")
        if not set(signals).intersection(commercial):
            limitations.append("Коммерческие сигналы не обнаружены.")
        if limitations:
            status = "Недостаточно данных"
            confidence = 0.0
            reason = "; ".join(limitations)
        else:
            status = "Гипотеза"
            confidence = min(0.9, 0.5 + min(page.visits / (min_visits * 10), 0.3) + 0.1 * len(set(signals).intersection(commercial)))
            reason = "Страница имеет достаточный объем визитов и наблюдаемые коммерческие сигналы; рекомендуется тест размещения формы, а не утверждение результата."
        recs.append(Recommendation(url=page.url, title=page.title, metrics=metrics, detected_signals=signals, traffic_sources=page.traffic_sources, reason=reason, confidence=confidence, status=status, limitations=limitations))
    return recs
