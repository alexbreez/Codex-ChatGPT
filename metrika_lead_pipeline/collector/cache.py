from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from loguru import logger
except Exception:  # pragma: no cover
    class _Logger:
        def info(self, *a: Any, **k: Any) -> None: pass
        def warning(self, *a: Any, **k: Any) -> None: pass
    logger = _Logger()


class RequestCache:
    def __init__(self, cache_dir: Path = Path(".cache"), enabled: bool = True) -> None:
        self.cache_dir = cache_dir
        self.enabled = enabled
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def key_for(self, params: dict[str, Any]) -> str:
        payload = json.dumps(params, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def path_for(self, params: dict[str, Any]) -> Path:
        return self.cache_dir / f"{self.key_for(params)}.json"

    def get(self, params: dict[str, Any]) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        path = self.path_for(params)
        if not path.exists():
            return None
        logger.info("Metrika cache hit: {}", path)
        return dict(json.loads(path.read_text(encoding="utf-8")))

    def set(self, params: dict[str, Any], value: dict[str, Any]) -> None:
        if not self.enabled:
            return
        path = self.path_for(params)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        logger.info("Metrika response cached: {}", path)
