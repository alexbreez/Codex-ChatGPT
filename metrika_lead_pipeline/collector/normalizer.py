from __future__ import annotations

from typing import Any

try:
    from loguru import logger
except Exception:  # pragma: no cover
    class _Logger:
        def info(self, *a: Any, **k: Any) -> None: pass
        def error(self, *a: Any, **k: Any) -> None: pass
    logger = _Logger()

from metrika_lead_pipeline.models import DeviceFact, GoalFact, NormalizedMetrikaData, PageFact, RegionFact, SearchQueryFact, SourceFact, VisitFact


def _dim(row: dict[str, Any], index: int, default: str = "") -> str:
    dims = row.get("dimensions", []) or []
    if index >= len(dims):
        return default
    item = dims[index]
    if isinstance(item, dict):
        return str(item.get("name") or item.get("id") or default)
    return str(item or default)


def _metric(row: dict[str, Any], index: int, default: float = 0) -> float:
    metrics = row.get("metrics", []) or []
    if index >= len(metrics) or metrics[index] is None:
        return default
    return float(metrics[index])


class MetrikaNormalizer:
    def normalize_pages(self, payload: dict[str, Any]) -> list[PageFact]:
        pages: list[PageFact] = []
        for row in payload.get("data", []):
            try:
                pages.append(PageFact(url=_dim(row, 0), title=_dim(row, 1), pageviews=int(_metric(row, 0)), visitors=int(_metric(row, 1)), raw=row))
            except Exception as exc:
                logger.error("Page normalization error: {}", exc)
        return pages

    def normalize_entry_pages(self, payload: dict[str, Any]) -> set[str]:
        return {_dim(row, 0) for row in payload.get("data", []) if _dim(row, 0)}

    def normalize_sources(self, payload: dict[str, Any]) -> list[SourceFact]:
        return [SourceFact(source=_dim(row, 0), visits=int(_metric(row, 0)), raw=row) for row in payload.get("data", [])]

    def normalize_visits(self, payload: dict[str, Any]) -> list[VisitFact]:
        visits: list[VisitFact] = []
        for idx, row in enumerate(payload.get("data", [])):
            path = [part for part in _dim(row, 1).split(" > ") if part]
            visits.append(VisitFact(visit_id=_dim(row, 0, str(idx)), entry_url=path[0] if path else None, page_urls=path, raw=row))
        return visits

    def normalize_search_queries(self, payload: dict[str, Any]) -> list[SearchQueryFact]:
        return [SearchQueryFact(query=_dim(row, 0), url=_dim(row, 1, None), visits=int(_metric(row, 0)), raw=row) for row in payload.get("data", [])]

    def normalize_goals(self, payload: dict[str, Any]) -> list[GoalFact]:
        return [GoalFact(goal_id=_dim(row, 0), goal_name=_dim(row, 1), visits=int(_metric(row, 0)), raw=row) for row in payload.get("data", [])]

    def normalize_devices(self, payload: dict[str, Any]) -> list[DeviceFact]:
        return [DeviceFact(device=_dim(row, 0), visits=int(_metric(row, 0)), raw=row) for row in payload.get("data", [])]

    def normalize_regions(self, payload: dict[str, Any]) -> list[RegionFact]:
        return [RegionFact(region=_dim(row, 0), visits=int(_metric(row, 0)), raw=row) for row in payload.get("data", [])]

    def merge(self, pages: list[PageFact], entry_urls: set[str], sources: list[SourceFact], visits: list[VisitFact], search_queries: list[SearchQueryFact], goals: list[GoalFact], devices: list[DeviceFact], regions: list[RegionFact], limitations: list[str]) -> NormalizedMetrikaData:
        source_totals = {s.source: s.visits for s in sources}
        for page in pages:
            page.is_entry_page = page.url in entry_urls
            page.traffic_sources = dict(source_totals)
            total = sum(source_totals.values())
            if total:
                page.search_traffic_share = (source_totals.get("Search engine traffic", 0) + source_totals.get("search", 0)) / total
                page.social_share = (source_totals.get("Social network traffic", 0) + source_totals.get("social", 0)) / total
        logger.info("Normalization completed: pages={} visits={}", len(pages), len(visits))
        return NormalizedMetrikaData(pages=pages, visits=visits, sources=sources, goals=goals, search_queries=search_queries, devices=devices, regions=regions, limitations=limitations)
