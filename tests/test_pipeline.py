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
