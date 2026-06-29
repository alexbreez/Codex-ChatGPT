from __future__ import annotations

from datetime import date
from typing import Any

try:
    from loguru import logger
except Exception:  # pragma: no cover
    class _Logger:
        def info(self, *a: Any, **k: Any) -> None: pass
        def warning(self, *a: Any, **k: Any) -> None: pass
    logger = _Logger()

from metrika_lead_pipeline.collector.client import MetrikaApiClient
from metrika_lead_pipeline.collector.normalizer import MetrikaNormalizer
from metrika_lead_pipeline.models import DeviceFact, GoalFact, NormalizedMetrikaData, PageFact, RegionFact, SearchQueryFact, SourceFact, VisitFact


class MetrikaReportCollector:
    def __init__(self, client: MetrikaApiClient, normalizer: MetrikaNormalizer | None = None) -> None:
        self.client = client
        self.normalizer = normalizer or MetrikaNormalizer()
        self.limitations: list[str] = []

    def collect_pages(self, date1: str, date2: str, filters: str | None = None) -> list[PageFact]:
        logger.info("Collecting pages report")
        payload = self.client.request(["ym:pv:pageviews", "ym:pv:users"], ["ym:pv:URL", "ym:pv:title"], date1, date2, filters)
        return self.normalizer.normalize_pages(payload)

    def collect_entry_pages(self, date1: str, date2: str, filters: str | None = None) -> set[str]:
        logger.info("Collecting entry pages report")
        payload = self.client.request(["ym:s:visits"], ["ym:s:startURL"], date1, date2, filters)
        return self.normalizer.normalize_entry_pages(payload)

    def collect_sources(self, date1: str, date2: str, filters: str | None = None) -> list[SourceFact]:
        logger.info("Collecting sources report")
        payload = self.client.request(["ym:s:visits"], ["ym:s:lastsignTrafficSource"], date1, date2, filters)
        return self.normalizer.normalize_sources(payload)

    def collect_visits(self, date1: str, date2: str, filters: str | None = None) -> list[VisitFact]:
        logger.info("Collecting visits/path report")
        try:
            payload = self.client.request(["ym:s:visits"], ["ym:s:visitID", "ym:s:pageViews"], date1, date2, filters)
            return self.normalizer.normalize_visits(payload)
        except Exception as exc:
            msg = f"Последовательность просмотров визита недоступна через выбранный Reporting API/счетчик: {exc}"
            logger.warning(msg)
            self.limitations.append(msg)
            return []

    def collect_search_queries(self, date1: str, date2: str, filters: str | None = None) -> list[SearchQueryFact]:
        logger.info("Collecting search queries report")
        try:
            payload = self.client.request(["ym:s:visits"], ["ym:s:searchPhrase", "ym:s:pageURL"], date1, date2, filters)
            return self.normalizer.normalize_search_queries(payload)
        except Exception as exc:
            msg = f"Поисковые фразы недоступны или скрыты API: {exc}"
            logger.warning(msg)
            self.limitations.append(msg)
            return []

    def collect_goals(self, date1: str, date2: str, filters: str | None = None) -> list[GoalFact]:
        logger.info("Collecting goals report")
        try:
            payload = self.client.request(["ym:s:goal<goal_id>reaches"], ["ym:s:goalID", "ym:s:goal"], date1, date2, filters)
            return self.normalizer.normalize_goals(payload)
        except Exception as exc:
            msg = f"Достижения целей не получены: требуется настройка конкретных goal_id или доступ API: {exc}"
            logger.warning(msg)
            self.limitations.append(msg)
            return []

    def collect_devices(self, date1: str, date2: str, filters: str | None = None) -> list[DeviceFact]:
        logger.info("Collecting devices report")
        payload = self.client.request(["ym:s:visits"], ["ym:s:deviceCategory"], date1, date2, filters)
        return self.normalizer.normalize_devices(payload)

    def collect_regions(self, date1: str, date2: str, filters: str | None = None) -> list[RegionFact]:
        logger.info("Collecting regions report")
        payload = self.client.request(["ym:s:visits"], ["ym:s:regionCountry", "ym:s:regionArea"], date1, date2, filters)
        return self.normalizer.normalize_regions(payload)

    def collect_all(self, date1: str, date2: str, filters: str | None = None) -> NormalizedMetrikaData:
        logger.info("Starting Metrika collection {}..{}", date1, date2)
        pages = self.collect_pages(date1, date2, filters)
        entry = self.collect_entry_pages(date1, date2, filters)
        sources = self.collect_sources(date1, date2, filters)
        visits = self.collect_visits(date1, date2, filters)
        queries = self.collect_search_queries(date1, date2, filters)
        goals = self.collect_goals(date1, date2, filters)
        devices = self.collect_devices(date1, date2, filters)
        regions = self.collect_regions(date1, date2, filters)
        return self.normalizer.merge(pages, entry, sources, visits, queries, goals, devices, regions, self.limitations)
