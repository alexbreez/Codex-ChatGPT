from __future__ import annotations

from typing import Any

from src.models import PageFact


def build_page_facts(rows: list[dict[str, Any]], entry_urls: set[str] | None = None) -> list[PageFact]:
    facts: list[PageFact] = []
    entries = entry_urls or set()
    for row in rows:
        visits = int(row.get("visits", 0) or 0)
        sources = dict(row.get("traffic_sources", {}) or {})
        total_source = sum(int(v) for v in sources.values())
        def share(*names: str) -> float | None:
            if total_source == 0:
                return None
            return sum(int(sources.get(n, 0)) for n in names) / total_source
        facts.append(PageFact(
            url=str(row.get("url", "")), title=str(row.get("title", "")), visits=visits,
            visitors=int(row.get("visitors", 0) or 0), bounce_rate=row.get("bounce_rate"),
            page_depth=row.get("page_depth"), avg_time_seconds=row.get("avg_time_seconds"),
            traffic_sources=sources, is_entry_page=str(row.get("url", "")) in entries,
            search_traffic_share=share("search", "organic"), discover_share=share("discover"),
            internal_share=share("internal"), social_share=share("social"), raw=row,
        ))
    return facts
