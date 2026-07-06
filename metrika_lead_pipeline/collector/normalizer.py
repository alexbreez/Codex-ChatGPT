from __future__ import annotations

from typing import Any

try:
    from loguru import logger
except Exception:  # pragma: no cover
    class _Logger:
        def info(self, *a: Any, **k: Any) -> None: pass
        def error(self, *a: Any, **k: Any) -> None: pass
    logger = _Logger()

from metrika_lead_pipeline.models import DeviceFact, GoalFact, NormalizedMetrikaData, PageFact, RegionFact, SearchQueryFact, SourceFact, VisitFact, canonical_page_url


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


def _source_hits(source_totals: dict[str, int], needles: tuple[str, ...]) -> int:
    total = 0
    for source, visits in source_totals.items():
        source_l = str(source).lower()
        if any(needle in source_l for needle in needles):
            total += int(visits)
    return total


def _source_share(source_totals: dict[str, int], needles: tuple[str, ...]) -> float | None:
    total = sum(int(visits) for visits in source_totals.values())
    if total <= 0:
        return None
    return _source_hits(source_totals, needles) / total


def _attach_source_shares(page: PageFact, source_totals: dict[str, int]) -> None:
    page.search_traffic_share = _source_share(source_totals, ("search engine traffic", "search", "organic", "поиск"))
    page.discover_share = _source_share(source_totals, ("recommendation system traffic", "recommend", "discover", "дзен", "рекоменд"))
    page.internal_share = _source_share(source_totals, ("internal traffic", "internal", "внутрен"))
    page.social_share = _source_share(source_totals, ("social network traffic", "social", "соц"))


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


class MetrikaNormalizer:
    def normalize_pages(self, payload: dict[str, Any]) -> list[PageFact]:
        grouped: dict[str, PageFact] = {}
        order: list[str] = []
        for row in payload.get("data", []):
            try:
                original_url = _dim(row, 0)
                canonical_url = canonical_page_url(original_url)
                if not canonical_url:
                    continue

                page = grouped.get(canonical_url)
                if page is None:
                    page = PageFact(
                        url=canonical_url,
                        title=_dim(row, 1),
                        canonical_url=canonical_url,
                        pageviews=int(_metric(row, 0)),
                        visitors=int(_metric(row, 1)),
                        raw=row,
                    )
                    grouped[canonical_url] = page
                    order.append(canonical_url)
                else:
                    page.pageviews += int(_metric(row, 0))
                    page.visitors += int(_metric(row, 1))
                    if not page.title:
                        page.title = _dim(row, 1)

                _append_unique(page.url_variants, original_url)
            except Exception as exc:
                logger.error("Page normalization error: {}", exc)
        return [grouped[url] for url in order]

    def normalize_entry_pages(self, payload: dict[str, Any]) -> set[str]:
        return {_dim(row, 0) for row in payload.get("data", []) if _dim(row, 0)}

    def normalize_sources(self, payload: dict[str, Any]) -> list[SourceFact]:
        return [SourceFact(source=_dim(row, 0), visits=int(_metric(row, 0)), raw=row) for row in payload.get("data", [])]

    def normalize_page_sources(self, payload: dict[str, Any]) -> list[SourceFact]:
        page_sources: list[SourceFact] = []
        for row in payload.get("data", []):
            url = canonical_page_url(_dim(row, 0))
            source = _dim(row, 1)
            if not url or not source:
                continue
            page_sources.append(SourceFact(source=source, visits=int(_metric(row, 0)), url=url, raw=row))
        return page_sources

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

    def merge(self, pages: list[PageFact], entry_urls: set[str], sources: list[SourceFact], visits: list[VisitFact], search_queries: list[SearchQueryFact], goals: list[GoalFact], devices: list[DeviceFact], regions: list[RegionFact], limitations: list[str], page_sources: list[SourceFact] | None = None) -> NormalizedMetrikaData:
        canonical_entry_urls = {canonical_page_url(url) for url in entry_urls if url}
        page_source_totals: dict[str, dict[str, int]] = {}
        for item in page_sources or []:
            if not item.url:
                continue
            canonical_url = canonical_page_url(item.url)
            source_totals = page_source_totals.setdefault(canonical_url, {})
            source_totals[item.source] = source_totals.get(item.source, 0) + int(item.visits)

        for page in pages:
            page_canonical_url = canonical_page_url(page.url)
            page.url = page_canonical_url
            if not page.canonical_url:
                page.canonical_url = page_canonical_url
            if not page.url_variants and page.url:
                page.url_variants = [page.url]
            page.is_entry_page = page_canonical_url in canonical_entry_urls
            url_source_totals = page_source_totals.get(page_canonical_url)
            if url_source_totals:
                page.traffic_sources = dict(url_source_totals)
                _attach_source_shares(page, url_source_totals)
            elif page.traffic_sources:
                _attach_source_shares(page, page.traffic_sources)

        logger.info("Normalization completed: pages={} visits={}", len(pages), len(visits))
        return NormalizedMetrikaData(pages=pages, visits=visits, sources=sources, goals=goals, search_queries=search_queries, devices=devices, regions=regions, limitations=limitations)
