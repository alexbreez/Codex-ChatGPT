from __future__ import annotations

from typing import Any

from metrika_lead_pipeline.models import PageFact, canonical_page_url


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


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _first_non_none(current: float | None, value: float | None) -> float | None:
    return current if current is not None else value


def build_page_facts(rows: list[dict[str, Any]], entry_urls: set[str] | None = None) -> list[PageFact]:
    grouped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    entries = {canonical_page_url(url) for url in (entry_urls or set()) if url}

    for row in rows:
        original_url = str(row.get("url", ""))
        canonical_url = canonical_page_url(original_url)
        if not canonical_url:
            continue

        item = grouped.get(canonical_url)
        if item is None:
            item = {
                "title": str(row.get("title", "")),
                "visits": 0,
                "pageviews": 0,
                "visitors": 0,
                "bounce_rate": None,
                "page_depth": None,
                "avg_time_seconds": None,
                "traffic_sources": {},
                "url_variants": [],
                "raw": row,
                "search_traffic_share": None,
                "discover_share": None,
                "internal_share": None,
                "social_share": None,
            }
            grouped[canonical_url] = item
            order.append(canonical_url)

        if not item["title"]:
            item["title"] = str(row.get("title", ""))

        item["visits"] += _int_value(row.get("visits"))
        item["pageviews"] += _int_value(row.get("pageviews"))
        item["visitors"] += _int_value(row.get("visitors"))
        item["bounce_rate"] = _first_non_none(item["bounce_rate"], _float_or_none(row.get("bounce_rate")))
        item["page_depth"] = _first_non_none(item["page_depth"], _float_or_none(row.get("page_depth")))
        item["avg_time_seconds"] = _first_non_none(item["avg_time_seconds"], _float_or_none(row.get("avg_time_seconds")))
        item["search_traffic_share"] = _first_non_none(item["search_traffic_share"], _float_or_none(row.get("search_traffic_share")))
        item["discover_share"] = _first_non_none(item["discover_share"], _float_or_none(row.get("discover_share")))
        item["internal_share"] = _first_non_none(item["internal_share"], _float_or_none(row.get("internal_share")))
        item["social_share"] = _first_non_none(item["social_share"], _float_or_none(row.get("social_share")))

        sources = dict(row.get("traffic_sources", {}) or {})
        totals = item["traffic_sources"]
        for source, value in sources.items():
            totals[str(source)] = _int_value(totals.get(str(source), 0)) + _int_value(value)

        _append_unique(item["url_variants"], original_url)

    facts: list[PageFact] = []
    for canonical_url in order:
        item = grouped[canonical_url]
        sources = dict(item["traffic_sources"])
        total_source = sum(_int_value(v) for v in sources.values())

        def computed_share(*names: str) -> float | None:
            if total_source == 0:
                return None
            return sum(_int_value(sources.get(n, 0)) for n in names) / total_source

        def explicit_or_computed(key: str, *names: str) -> float | None:
            explicit = item.get(key)
            if explicit is not None:
                return explicit
            return computed_share(*names)

        facts.append(
            PageFact(
                url=canonical_url,
                title=str(item["title"]),
                canonical_url=canonical_url,
                url_variants=list(item["url_variants"]),
                visits=_int_value(item["visits"]),
                pageviews=_int_value(item["pageviews"]),
                visitors=_int_value(item["visitors"]),
                bounce_rate=item["bounce_rate"],
                page_depth=item["page_depth"],
                avg_time_seconds=item["avg_time_seconds"],
                traffic_sources=sources,
                is_entry_page=canonical_url in entries,
                search_traffic_share=explicit_or_computed("search_traffic_share", "search", "organic"),
                discover_share=explicit_or_computed("discover_share", "discover"),
                internal_share=explicit_or_computed("internal_share", "internal"),
                social_share=explicit_or_computed("social_share", "social"),
                raw=item["raw"],
            )
        )

    return facts
