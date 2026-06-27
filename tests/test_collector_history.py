from __future__ import annotations

import json
from pathlib import Path

from metrika_lead_pipeline.cli import main
from metrika_lead_pipeline.collector.cache import RequestCache
from metrika_lead_pipeline.collector.client import MetrikaApiClient
from metrika_lead_pipeline.collector.normalizer import MetrikaNormalizer
from metrika_lead_pipeline.collector.reports import MetrikaReportCollector
from metrika_lead_pipeline.history.delta import DeltaEngine
from metrika_lead_pipeline.history.storage import HistoryStorage
from metrika_lead_pipeline.models import NormalizedMetrikaData, PageFact, SignalFinding, Recommendation
from metrika_lead_pipeline.pipeline.automated import run_normalized
from metrika_lead_pipeline.recommendations.engine import build_recommendations


class FakeTransport:
    def __init__(self) -> None:
        self.calls = 0

    def get(self, url: str, headers: dict[str, str], params: dict[str, object], timeout: float) -> dict[str, object]:
        self.calls += 1
        dimensions = str(params.get("dimensions", ""))
        if "ym:pv:URL,ym:pv:title" in dimensions:
            return {"data": [{"dimensions": [{"name": "/cars/a-vs-b"}, {"name": "Сравнение Model A vs Model B цена"}], "metrics": [150, 100]}]}
        if "ym:s:startURL" in dimensions:
            return {"data": [{"dimensions": [{"name": "/cars/a-vs-b"}], "metrics": [150]}]}
        if "ym:s:lastsignTrafficSource" in dimensions:
            return {"data": [{"dimensions": [{"name": "search"}], "metrics": [120]}]}
        if "ym:s:visitID" in dimensions:
            return {"data": [{"dimensions": [{"name": "v1"}, {"name": "/cars/a-vs-b"}], "metrics": [1]}]}
        if "ym:s:searchPhrase" in dimensions:
            return {"data": [{"dimensions": [{"name": "цена model a"}, {"name": "/cars/a-vs-b"}], "metrics": [10]}]}
        if "ym:s:goalID" in dimensions:
            return {"data": []}
        if "ym:s:deviceCategory" in dimensions:
            return {"data": [{"dimensions": [{"name": "desktop"}], "metrics": [50]}]}
        if "ym:s:regionCountry" in dimensions:
            return {"data": [{"dimensions": [{"name": "Russia"}], "metrics": [50]}]}
        return {"data": []}


def test_cache_reuses_identical_params(tmp_path: Path) -> None:
    cache = RequestCache(tmp_path)
    params = {"date1": "2026-01-01", "date2": "2026-01-31", "metrics": "m", "dimensions": "d"}
    cache.set(params, {"data": [1]})
    assert cache.get(dict(reversed(list(params.items())))) == {"data": [1]}


def test_client_uses_cache_and_typed_collection(tmp_path: Path) -> None:
    transport = FakeTransport()
    client = MetrikaApiClient(counter_id="1", token="token", cache=RequestCache(tmp_path), transport=transport, rate_limit_per_second=0)
    collector = MetrikaReportCollector(client)
    data = collector.collect_all("2026-01-01", "2026-01-31")
    assert data.pages[0].url == "/cars/a-vs-b"
    assert data.pages[0].pageviews == 150
    assert data.pages[0].visits == 0
    assert data.visits[0].visit_id == "v1"
    first_calls = transport.calls
    collector.collect_pages("2026-01-01", "2026-01-31")
    assert transport.calls == first_calls


def test_normalizer_maps_page_fields() -> None:
    payload = {"data": [{"dimensions": [{"name": "/u"}, {"name": "Title"}], "metrics": [3, 2]}]}
    page = MetrikaNormalizer().normalize_pages(payload)[0]
    assert page.pageviews == 3
    assert page.visits == 0
    assert page.visitors == 2
    assert page.avg_time_seconds is None


def test_delta_engine_detects_candidate_changes() -> None:
    previous = {"pages": [{"url": "/u", "search_traffic_share": 0.1}], "signals": [], "recommendations": [{"url": "/u", "status": "Недостаточно данных", "confidence": 0.0}]}
    current = {"pages": [{"url": "/u", "search_traffic_share": 0.5}], "signals": [{"url": "/u", "signal": "цены"}], "recommendations": [{"url": "/u", "status": "Гипотеза", "confidence": 0.8, "reason": "ok"}]}
    delta = DeltaEngine().compare(previous, current)
    assert delta.new_commercial_signals["/u"] == ["цены"]
    assert "/u" in delta.new_candidates


def test_cli_compare_writes_report(tmp_path: Path) -> None:
    storage = HistoryStorage(tmp_path / "history")
    storage.save_run({"run_id": "a", "pages": [], "signals": [], "recommendations": []})
    storage.save_run({"run_id": "b", "pages": [{"url": "/new"}], "signals": [], "recommendations": []})
    assert main(["compare", "--run-id", "a", "--run-id", "b", "--history-dir", str(tmp_path / "history"), "--output", str(tmp_path / "reports")]) == 0
    assert (tmp_path / "reports" / "changes_report.md").exists()


def test_recommendations_use_pageviews_without_mislabeling_visits() -> None:
    page = PageFact(url="/u", title="Цена Model A", pageviews=150, visitors=100)
    rec = build_recommendations([page], {"/u": ["цены"]}, {"recommendation_rules": {"min_visits": 100, "commercial_signals": ["цены"]}})[0]
    assert rec.status == "Гипотеза"
    assert "просмотров страниц" in rec.reason
    assert "визитов" not in rec.reason


def test_full_integration_history_and_changes(tmp_path: Path) -> None:
    data = NormalizedMetrikaData(pages=[PageFact(url="/cars/a-vs-b", title="Сравнение Model A vs Model B цена", visits=150, visitors=100, traffic_sources={"search": 100}, search_traffic_share=1.0)], limitations=[])
    snapshot = run_normalized(data, "2026-01-01", "2026-01-31", tmp_path / "reports")
    assert snapshot["recommendations"][0]["status"] == "Гипотеза"
    assert (tmp_path / "reports" / "decision_log.json").exists()
    assert (tmp_path / "reports" / "changes_report.md").exists()
