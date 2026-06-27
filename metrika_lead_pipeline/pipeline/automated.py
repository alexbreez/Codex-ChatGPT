from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from loguru import logger
except Exception:  # pragma: no cover
    class _Logger:
        def info(self, *a: Any, **k: Any) -> None: pass
    logger = _Logger()

from metrika_lead_pipeline.collector.cache import RequestCache
from metrika_lead_pipeline.collector.client import MetrikaApiClient
from metrika_lead_pipeline.collector.reports import MetrikaReportCollector
from metrika_lead_pipeline.config.loader import default_config_path, load_config, load_yaml
from metrika_lead_pipeline.history.comparator import RunComparator, write_changes_report
from metrika_lead_pipeline.history.storage import HistoryStorage
from metrika_lead_pipeline.models import NormalizedMetrikaData
from metrika_lead_pipeline.pipeline.runner import run_pipeline_from_facts


def resolve_period(last_days: int | None = None, today: bool = False, yesterday: bool = False, month: str | None = None, date_from: str | None = None, date_to: str | None = None) -> tuple[str, str]:
    now = date.today()
    if today:
        return now.isoformat(), now.isoformat()
    if yesterday:
        day = now - timedelta(days=1)
        return day.isoformat(), day.isoformat()
    if month:
        year, mon = [int(part) for part in month.split("-")]
        start = date(year, mon, 1)
        end = date(year + (mon // 12), (mon % 12) + 1, 1) - timedelta(days=1)
        return start.isoformat(), end.isoformat()
    if date_from and date_to:
        return date_from, date_to
    days = last_days or 30
    return (now - timedelta(days=days - 1)).isoformat(), now.isoformat()


def build_filter(region: str | None = None, brand: str | None = None, category: str | None = None) -> str | None:
    parts: list[str] = []
    if region:
        parts.append(f"ym:s:regionAreaName=='{region}'")
    if brand:
        parts.append(f"ym:s:pageURL=@'{brand}'")
    if category:
        parts.append(f"ym:s:pageURL=@'{category}'")
    return " AND ".join(parts) if parts else None


def collect_and_analyze(last_days: int | None = None, today: bool = False, yesterday: bool = False, month: str | None = None, date_from: str | None = None, date_to: str | None = None, region: str | None = None, brand: str | None = None, category: str | None = None, output: Path = Path("reports"), config_path: Path = default_config_path("config.yaml"), collector: MetrikaReportCollector | None = None) -> dict[str, Any]:
    logger.info("Automated collection run started")
    cfg = load_config(config_path)
    start, end = resolve_period(last_days, today, yesterday, month, date_from, date_to)
    filters = build_filter(region, brand, category)
    if collector is None:
        cache_cfg = cfg.cache
        cache = RequestCache(Path(cache_cfg.get("dir", ".cache")), bool(cache_cfg.get("enabled", True)))
        api_cfg = cfg.api
        client = MetrikaApiClient(counter_id=str(api_cfg.get("counter_id", "")), base_url=str(api_cfg.get("base_url", "https://api-metrika.yandex.net/stat/v1/data")), timeout_seconds=float(api_cfg.get("timeout_seconds", 60)), retry_attempts=int(api_cfg.get("retry_attempts", 3)), retry_backoff_seconds=float(api_cfg.get("retry_backoff_seconds", 1)), rate_limit_per_second=float(api_cfg.get("rate_limit_per_second", 5)), page_limit=int(api_cfg.get("page_limit", 100000)), cache=cache)
        collector = MetrikaReportCollector(client)
    logger.info("Starting data collection")
    normalized = collector.collect_all(start, end, filters)
    return run_normalized(normalized, start, end, output, config_path)


def run_normalized(normalized: NormalizedMetrikaData, date_from: str, date_to: str, output: Path, config_path: Path = default_config_path("config.yaml")) -> dict[str, Any]:
    logger.info("Starting normalization-to-pipeline bridge")
    pages, signals, recommendations, decisions = run_pipeline_from_facts(normalized.pages, normalized.visits, config_path, output, normalized.limitations)
    cfg = load_config(config_path)
    run_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    snapshot = {"run_id": run_id, "created_at": datetime.now().isoformat(), "period": {"from": date_from, "to": date_to}, "config_version": cfg.version, "rules_version": load_yaml(default_config_path("rules.yaml")).get("version", ""), "signals_version": load_yaml(default_config_path("signals.yaml")).get("version", ""), "pages": [p.model_dump() for p in pages], "signals": [s.model_dump() for s in signals], "recommendations": [r.model_dump() for r in recommendations], "decision_log": [d.model_dump() for d in decisions], "limitations": normalized.limitations}
    storage = HistoryStorage(Path(cfg.history.get("dir", "history")))
    comparator = RunComparator(storage)
    delta = comparator.compare_with_previous(snapshot)
    write_changes_report(delta, output)
    snapshot["comparison"] = delta.model_dump()
    storage.save_run(snapshot, output)
    logger.info("Automated run completed: {}", run_id)
    return snapshot
