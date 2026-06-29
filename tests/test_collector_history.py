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


def test_cli_collect_passes_config_path(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_collect_and_analyze(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {}

    monkeypatch.setattr("metrika_lead_pipeline.cli.collect_and_analyze", fake_collect_and_analyze)
    config = tmp_path / "integration.yaml"
    assert main(["collect", "--from", "2026-06-01", "--to", "2026-06-27", "--output", str(tmp_path / "reports"), "--config", str(config)]) == 0
    assert captured["config_path"] == config


def test_merge_does_not_copy_global_sources_to_pages() -> None:
    normalizer = MetrikaNormalizer()
    data = normalizer.merge(
        pages=[PageFact(url="/u", title="Title")],
        entry_urls=set(),
        sources=[],
        visits=[],
        search_queries=[],
        goals=[],
        devices=[],
        regions=[],
        limitations=[],
    )
    assert data.pages[0].traffic_sources == {}
    assert data.pages[0].search_traffic_share is None


def test_region_normalization_preserves_country_and_area() -> None:
    payload = {"data": [{"dimensions": [{"name": "Russia"}, {"name": "Moscow and Moscow Oblast"}], "metrics": [12]}]}
    region = MetrikaNormalizer().normalize_regions(payload)[0]
    assert region.country == "Russia"
    assert region.area == "Moscow and Moscow Oblast"
    assert region.region == "Russia / Moscow and Moscow Oblast"


def test_run_normalized_truncates_snapshot_and_reports_limitations(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(
        "version: '1.0'\n"
        "outputs:\n"
        "  report_dir: reports\n"
        "  max_report_pages: 1\n"
        "  max_recommendations: 1\n"
        "  max_decision_log_records: 1\n"
        "  max_snapshot_pages: 1\n"
        "  max_snapshot_signals: 1\n"
        "  max_snapshot_recommendations: 1\n"
        "  max_snapshot_decisions: 1\n"
        "history:\n"
        f"  dir: {tmp_path / 'history'}\n"
        "brands: ['Model A', 'Model B']\n"
        "categories: []\n",
        encoding="utf-8",
    )
    pages = [
        PageFact(url=f"/u{i}", title="Цена Model A", pageviews=150, visitors=100)
        for i in range(3)
    ]
    data = NormalizedMetrikaData(pages=pages, limitations=["API limit", "API limit"])
    snapshot = run_normalized(data, "2026-06-01", "2026-06-27", tmp_path / "reports", config)
    assert snapshot["truncated"]["pages"] == {"stored": 1, "total": 3}
    assert len(snapshot["pages"]) == 1
    decision_log = json.loads((tmp_path / "reports" / "decision_log.json").read_text(encoding="utf-8"))
    assert decision_log["truncated"]["decision_log"] == {"stored": 1, "total": 3}
    report = (tmp_path / "reports" / "lead_generation_report.md").read_text(encoding="utf-8")
    assert "API limit" in report
    assert report.count("API limit") == 1
    assert "Ограничения объёма вывода" in report
    metadata = json.loads((tmp_path / "reports" / "report_metadata.json").read_text(encoding="utf-8"))
    assert metadata["counts"]["pages"] == 3
    assert metadata["truncated"]["pages"] == {"stored": 1, "total": 3}
