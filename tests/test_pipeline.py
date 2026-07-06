from __future__ import annotations

import json
from pathlib import Path

from metrika_lead_pipeline.pipeline.runner import run_pipeline
from metrika_lead_pipeline.signals.extractor import extract_signals
from metrika_lead_pipeline.models import PageFact


def test_signal_extraction_prices() -> None:
    cfg = {"signals": [{"id": "prices", "name": "цены", "confidence": 0.8, "any_patterns": ["(?i)(цена|стоимость)"], "explanation": "price"}]}
    findings, evaluations = extract_signals(PageFact(url="/a", title="Новая цена автомобиля"), cfg)
    assert findings[0].signal == "цены"
    assert evaluations[0].matched is True


def test_no_signal_is_explicit() -> None:
    findings, _ = extract_signals(PageFact(url="/news", title="Обычный материал"), {"signals": []})
    assert findings[0].signal == "Сигналы не обнаружены"


def test_pipeline_writes_reports(tmp_path: Path) -> None:
    rows = [{"url": "/cars/a-vs-b", "title": "Сравнение Model A vs Model B цена", "visits": 150, "visitors": 100, "traffic_sources": {"search": 90, "social": 10}}]
    pages, signals, recs = run_pipeline(rows, visits=[{"visit_id": "1", "entry_url": "/cars/a-vs-b", "page_urls": ["/cars/a-vs-b"]}], output_dir=tmp_path)
    assert pages[0].visits == 150
    assert any(s.signal == "цены" for s in signals)
    assert recs[0].status == "Гипотеза"
    decision_log = json.loads((tmp_path / "decision_log.json").read_text(encoding="utf-8"))
    assert decision_log[0]["facts"]["url"] == "/cars/a-vs-b"
    assert (tmp_path / "report_pages.xlsx").exists()




def test_run_pipeline_groups_canonical_url_variants_before_scoring(tmp_path: Path) -> None:
    rows = [
        {
            "url": "/cars/model-a-price/#gallery",
            "title": "Model A цена комплектации дилер",
            "pageviews": 60,
            "visitors": 40,
            "traffic_sources": {"search": 30},
        },
        {
            "url": "/cars/model-a-price/amp/",
            "title": "Model A цена комплектации дилер",
            "pageviews": 40,
            "visitors": 30,
            "traffic_sources": {"search": 20},
        },
    ]

    pages, _signals, _recs = run_pipeline(rows, output_dir=tmp_path)

    assert len(pages) == 1
    page = pages[0]
    assert page.url == "/cars/model-a-price/"
    assert page.canonical_url == "/cars/model-a-price/"
    assert set(page.url_variants) == {"/cars/model-a-price/#gallery", "/cars/model-a-price/amp/"}
    assert page.pageviews == 100
    assert page.visitors == 70
    assert page.traffic_sources == {"search": 50}

    decision_log = json.loads((tmp_path / "decision_log.json").read_text(encoding="utf-8"))
    facts = decision_log[0]["facts"]
    assert facts["canonical_url"] == "/cars/model-a-price/"
    assert set(facts["url_variants"]) == {"/cars/model-a-price/#gallery", "/cars/model-a-price/amp/"}


def test_report_outputs_are_limited_by_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("""
version: "1.0"
brands: ["Model A", "Model B"]
categories: []
outputs:
  report_dir: reports
  max_markdown_items: 1
  max_decision_log_items: 1
history:
  dir: history
""", encoding="utf-8")
    rows = [
        {"url": f"/cars/{i}", "title": f"Цена Model A {i}", "pageviews": 150, "visitors": 100}
        for i in range(3)
    ]

    run_pipeline(rows, config_path=config_path, output_dir=tmp_path / "reports")

    decision_log = json.loads((tmp_path / "reports" / "decision_log.json").read_text(encoding="utf-8"))
    metadata = json.loads((tmp_path / "reports" / "report_metadata.json").read_text(encoding="utf-8"))
    main_report = (tmp_path / "reports" / "lead_generation_report.md").read_text(encoding="utf-8")

    assert len(decision_log) == 1
    assert metadata["truncated"]["decision_log"] == {"stored": 1, "total": 3}
    assert "Показано 1 из 3" in main_report
