from __future__ import annotations

from typing import Any

from metrika_lead_pipeline.models import PageFact


def _int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_page_facts(rows: list[dict[str, Any]], entry_urls: set[str] | None = None) -> list[PageFact]:
    facts: list[PageFact] = []
    entries = entry_urls or set()

    for row in rows:
        visits = _int_value(row.get("visits"))
        pageviews = _int_value(row.get("pageviews"))
        sources = dict(row.get("traffic_sources", {}) or {})
        total_source = sum(_int_value(v) for v in sources.values())

        def computed_share(*names: str) -> float | None:
            if total_source == 0:
                return None
            return sum(_int_value(sources.get(n, 0)) for n in names) / total_source

        def explicit_or_computed(key: str, *names: str) -> float | None:
            explicit = _float_or_none(row.get(key))
            if explicit is not None:
                return explicit
            return computed_share(*names)

        facts.append(
            PageFact(
                url=str(row.get("url", "")),
                title=str(row.get("title", "")),
                visits=visits,
                pageviews=pageviews,
                visitors=_int_value(row.get("visitors")),
                bounce_rate=_float_or_none(row.get("bounce_rate")),
                page_depth=_float_or_none(row.get("page_depth")),
                avg_time_seconds=_float_or_none(row.get("avg_time_seconds")),
                traffic_sources=sources,
                is_entry_page=str(row.get("url", "")) in entries,
                search_traffic_share=explicit_or_computed("search_traffic_share", "search", "organic"),
                discover_share=explicit_or_computed("discover_share", "discover"),
                internal_share=explicit_or_computed("internal_share", "internal"),
                social_share=explicit_or_computed("social_share", "social"),
                raw=row,
            )
        )

    return facts
