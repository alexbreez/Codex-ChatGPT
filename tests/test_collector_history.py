from __future__ import annotations

import json
from pathlib import Path

from metrika_lead_pipeline.cli import main
from metrika_lead_pipeline.collector.cache import RequestCache
from metrika_lead_pipeline.collector.client import MetrikaApiClient
from metrika_lead_pipeline.collector.normalizer import MetrikaNormalizer
from metrika_lead_pipeline.collector.reports import MetrikaReportCollector
from metrika_lead_pipeline.history.delta import DeltaEngine, DeltaResult
from metrika_lead_pipeline.history.comparator import write_changes_report
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
        if "ym:s:startURL,ym:s:lastsignTrafficSource" in dimensions:
            return {"data": [
                {"dimensions": [{"name": "/cars/a-vs-b"}, {"name": "Search engine traffic"}], "metrics": [90]},
                {"dimensions": [{"name": "/cars/a-vs-b"}, {"name": "Recommendation system traffic"}], "metrics": [60]},
            ]}
        if "ym:s:startURL" in dimensions:
            return {"data": [{"dimensions": [{"name": "/cars/a-vs-b"}], "metrics": [150]}]}
        if "ym:s:lastsignTrafficSource" in dimensions:
            return {"data": [{"dimensions": [{"name": "Search engine traffic"}], "metrics": [120]}]}
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
    assert data.pages[0].traffic_sources == {"Search engine traffic": 90, "Recommendation system traffic": 60}
    assert data.pages[0].search_traffic_share == 0.6
    assert data.pages[0].discover_share == 0.4
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


def test_normalizer_merges_page_level_sources_without_copying_aggregate_sources() -> None:
    normalizer = MetrikaNormalizer()
    pages = [
        PageFact(url="/cars/a", title="Model A цена"),
        PageFact(url="/cars/b", title="Model B цена"),
    ]
    page_sources = normalizer.normalize_page_sources({"data": [
        {"dimensions": [{"name": "/cars/a"}, {"name": "Search engine traffic"}], "metrics": [80]},
        {"dimensions": [{"name": "/cars/a"}, {"name": "Recommendation system traffic"}], "metrics": [20]},
        {"dimensions": [{"name": "/cars/a"}, {"name": "Search engine traffic"}], "metrics": [20]},
    ]})

    data = normalizer.merge(
        pages,
        set(),
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        page_sources=page_sources,
    )

    assert data.pages[0].traffic_sources == {"Search engine traffic": 100, "Recommendation system traffic": 20}
    assert round(data.pages[0].search_traffic_share or 0, 4) == 0.8333
    assert round(data.pages[0].discover_share or 0, 4) == 0.1667
    assert data.pages[1].traffic_sources == {}




def test_normalizer_groups_canonical_url_variants_before_source_merge() -> None:
    normalizer = MetrikaNormalizer()
    pages = normalizer.normalize_pages({"data": [
        {"dimensions": [{"name": "/content/articles/123-car/#gallery"}, {"name": "Model A"}], "metrics": [60, 40]},
        {"dimensions": [{"name": "/content/amp/articles/123-car/"}, {"name": "Model A AMP"}], "metrics": [40, 30]},
    ]})
    page_sources = normalizer.normalize_page_sources({"data": [
        {"dimensions": [{"name": "/content/articles/123-car/#gallery"}, {"name": "Search engine traffic"}], "metrics": [30]},
        {"dimensions": [{"name": "/content/amp/articles/123-car/"}, {"name": "Recommendation system traffic"}], "metrics": [20]},
    ]})

    data = normalizer.merge(
        pages,
        set(),
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        page_sources=page_sources,
    )

    assert len(data.pages) == 1
    page = data.pages[0]
    assert page.url == "/content/articles/123-car/"
    assert page.canonical_url == "/content/articles/123-car/"
    assert set(page.url_variants) == {
        "/content/articles/123-car/#gallery",
        "/content/amp/articles/123-car/",
    }
    assert page.pageviews == 100
    assert page.visitors == 70
    assert page.traffic_sources == {"Search engine traffic": 30, "Recommendation system traffic": 20}
    assert page.search_traffic_share == 0.6
    assert page.discover_share == 0.4


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



def test_cli_collect_passes_config_path(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_collect_and_analyze(**kwargs: object) -> dict[str, bool]:
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr("metrika_lead_pipeline.cli.collect_and_analyze", fake_collect_and_analyze)

    assert main([
        "collect",
        "--from", "2026-06-01",
        "--to", "2026-06-27",
        "--output", "reports_integration",
        "--config", ".integration_config.yaml",
    ]) == 0

    assert captured["date_from"] == "2026-06-01"
    assert captured["date_to"] == "2026-06-27"
    assert captured["output"] == Path("reports_integration")
    assert captured["config_path"] == Path(".integration_config.yaml")

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


def test_changes_report_limits_items(tmp_path: Path) -> None:
    delta = DeltaResult(new_candidates={f"/u{i}": "reason" for i in range(3)})

    write_changes_report(delta, tmp_path, max_items=1)

    text = (tmp_path / "changes_report.md").read_text(encoding="utf-8")
    assert "/u0" in text
    assert "/u1" not in text
    assert "Показано 1 из 3" in text


def test_run_normalized_truncates_history_snapshot(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    history_dir = tmp_path / "history"
    config_path.write_text(f"""
version: "1.0"
brands: ["Model A", "Model B"]
categories: []
outputs:
  report_dir: reports
  max_markdown_items: 1
  max_decision_log_items: 1
  max_changes_report_items: 1
history:
  dir: "{history_dir}"
  max_snapshot_pages: 2
  max_snapshot_signals: 2
  max_snapshot_recommendations: 2
  max_snapshot_decisions: 2
  max_snapshot_comparison_items: 1
""", encoding="utf-8")
    data = NormalizedMetrikaData(
        pages=[
            PageFact(url=f"/cars/{i}", title=f"Цена Model A {i}", pageviews=150, visitors=100)
            for i in range(3)
        ],
        limitations=[],
    )

    snapshot = run_normalized(data, "2026-01-01", "2026-01-31", tmp_path / "reports", config_path)

    assert len(snapshot["pages"]) == 2
    assert len(snapshot["decision_log"]) == 2
    assert snapshot["truncated"]["pages"] == {"stored": 2, "total": 3}
    saved_snapshot_path = next(history_dir.glob("*/snapshot.json"))
    saved_snapshot = json.loads(saved_snapshot_path.read_text(encoding="utf-8"))
    assert len(saved_snapshot["pages"]) == 2
    assert saved_snapshot["truncated"]["decision_log"] == {"stored": 2, "total": 3}
