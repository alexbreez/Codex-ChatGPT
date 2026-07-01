from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


@dataclass
class AppConfig:
    version: str = "1.0"
    api: dict[str, Any] = field(default_factory=dict)
    periods: list[dict[str, Any]] = field(default_factory=list)
    regions: list[dict[str, Any]] = field(default_factory=list)
    content_filters: dict[str, list[str]] = field(default_factory=dict)
    brands: list[str] = field(default_factory=lambda: ["Model A", "Model B"])
    categories: list[str] = field(default_factory=list)
    outputs: dict[str, str] = field(default_factory=lambda: {"raw_dir": "data/raw", "report_dir": "reports"})
    thresholds: dict[str, Any] = field(default_factory=dict)
    cache: dict[str, Any] = field(default_factory=lambda: {"enabled": True, "dir": ".cache"})
    history: dict[str, Any] = field(default_factory=lambda: {"dir": "history"})
    comparison: dict[str, Any] = field(default_factory=dict)


def default_config_path(name: str = "config.yaml") -> Path:
    return Path(str(resources.files("metrika_lead_pipeline.config").joinpath(name)))


def load_yaml(path: Path | None) -> dict[str, Any]:
    resolved = path or default_config_path()
    name = resolved.name
    if resolved.exists() and (yaml is not None or name not in {"signals.yaml", "rules.yaml"}):
        with resolved.open("r", encoding="utf-8") as fh:
            if yaml is not None:
                return dict(yaml.safe_load(fh) or {})
            return _fallback_yaml(fh.read())
    if name == "signals.yaml":
        return {"version": "1.0", "signals": [
            {"id": "comparison", "name": "сравнение моделей", "confidence": 0.8, "all_patterns": [r"(?i)(сравнение|vs|или|против)"], "min_model_mentions": 2, "explanation": "В заголовке найдены слова сравнения и минимум две модели из конфигурации."},
            {"id": "prices", "name": "цены", "confidence": 0.85, "any_patterns": [r"(?i)(цена|стоимость|сколько стоит)"], "explanation": "В тексте страницы обнаружены слова про цену или стоимость."},
            {"id": "trims", "name": "комплектации", "confidence": 0.8, "any_patterns": [r"(?i)(комплектац|версия|оснащение)"], "explanation": "Обнаружены слова про комплектации, версии или оснащение."},
            {"id": "dealers", "name": "дилеры", "confidence": 0.8, "any_patterns": [r"(?i)(где купить|дилер|салон)"], "explanation": "Обнаружены слова про дилеров."},
            {"id": "test_drive", "name": "тест-драйв", "confidence": 0.9, "any_patterns": [r"(?i)(тест[ -]?драйв)"], "explanation": "Обнаружено словосочетание тест-драйв."},
            {"id": "news", "name": "новость", "confidence": 0.7, "any_patterns": [r"(?i)(представили|анонсировали|показали|премьера)"], "explanation": "Обнаружены новостные слова."},
        ]}
    if name == "rules.yaml":
        return {"version": "1.0", "visit_rules": [{"id": "possible_commercial_intent", "name": "возможное коммерческое намерение", "description": "Визит начался со страницы с сигналом цены или сравнение моделей.", "entry_signals_any": ["цены", "сравнение моделей"], "status": "Гипотеза", "confidence": 0.65}], "recommendation_rules": {"min_visits": 100, "commercial_signals": ["цены", "сравнение моделей", "комплектации", "дилеры", "тест-драйв"]}}
    return {}


def _fallback_yaml(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current: str | None = None
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        if not raw_line.startswith(" ") and ":" in raw_line:
            key, value = raw_line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value:
                data[key] = _parse_scalar(value)
                current = None
            else:
                data[key] = {}
                current = key
        elif current and ":" in raw_line:
            key, value = raw_line.strip().split(":", 1)
            data[current][key.strip()] = _parse_scalar(value.strip())
    return data


def _parse_scalar(value: str) -> Any:
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip("'\"") for item in inner.split(",")]
    cleaned = value.strip().strip("'\"")
    if cleaned.isdigit():
        return int(cleaned)
    return cleaned


def load_config(path: Path | None = None) -> AppConfig:
    data = load_yaml(path or default_config_path("config.yaml"))
    return AppConfig(**{k: v for k, v in data.items() if k in AppConfig.__dataclass_fields__})
