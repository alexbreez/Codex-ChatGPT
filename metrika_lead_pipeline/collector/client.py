from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

try:
    from loguru import logger
except Exception:  # pragma: no cover
    class _Logger:
        def info(self, *a: Any, **k: Any) -> None: pass
        def warning(self, *a: Any, **k: Any) -> None: pass
        def error(self, *a: Any, **k: Any) -> None: pass
    logger = _Logger()

from metrika_lead_pipeline.collector.cache import RequestCache


class Transport(Protocol):
    def get(self, url: str, headers: dict[str, str], params: dict[str, Any], timeout: float) -> dict[str, Any]: ...


class UrllibTransport:
    def get(self, url: str, headers: dict[str, str], params: dict[str, Any], timeout: float) -> dict[str, Any]:
        full_url = f"{url}?{urlencode(params, doseq=True)}"
        request = Request(full_url, headers=headers, method="GET")
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 official configured API endpoint only
            return dict(json.loads(response.read().decode("utf-8")))


@dataclass
class MetrikaApiClient:
    counter_id: str
    token: str | None = None
    base_url: str = "https://api-metrika.yandex.net/stat/v1/data"
    timeout_seconds: float = 60
    retry_attempts: int = 3
    retry_backoff_seconds: float = 1.0
    rate_limit_per_second: float = 5
    page_limit: int = 100000
    cache: RequestCache | None = None
    transport: Transport | None = None

    def __post_init__(self) -> None:
        self.token = self.token or os.getenv("YANDEX_METRIKA_TOKEN", "")
        self.transport = self.transport or UrllibTransport()
        self._last_request_at = 0.0

    def request(self, metrics: list[str], dimensions: list[str], date1: str, date2: str, filters: str | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.token or not self.counter_id:
            raise ValueError("YANDEX_METRIKA_TOKEN and counter_id are required for API collection")
        offset = 1
        rows: list[dict[str, Any]] = []
        totals: list[Any] = []
        base_params: dict[str, Any] = {"ids": self.counter_id, "metrics": ",".join(metrics), "dimensions": ",".join(dimensions), "date1": date1, "date2": date2, "limit": self.page_limit}
        if filters:
            base_params["filters"] = filters
        if extra:
            base_params.update(extra)
        while True:
            params = dict(base_params, offset=offset)
            cached = self.cache.get(params) if self.cache else None
            payload = cached if cached is not None else self._request_with_retry(params)
            if self.cache and cached is None:
                self.cache.set(params, payload)
            if "errors" in payload:
                logger.error("Metrika API errors: {}", payload["errors"])
                raise RuntimeError(f"Metrika API error: {payload['errors']}")
            data = list(payload.get("data", []))
            rows.extend(data)
            totals = list(payload.get("totals", totals))
            if len(data) < self.page_limit:
                break
            offset += self.page_limit
        result = {"data": rows, "totals": totals, "query": base_params}
        logger.info("Collected Metrika report dimensions={} metrics={} rows={}", dimensions, metrics, len(rows))
        return result

    def _request_with_retry(self, params: dict[str, Any]) -> dict[str, Any]:
        headers = {"Authorization": f"OAuth {self.token}"}
        last_error: Exception | None = None
        for attempt in range(1, self.retry_attempts + 1):
            self._rate_limit()
            try:
                assert self.transport is not None
                return self.transport.get(self.base_url, headers, params, self.timeout_seconds)
            except HTTPError as exc:
                last_error = exc
                if exc.code not in {429, 500, 502, 503, 504}:
                    logger.error("Non-retryable Metrika HTTP error {}", exc.code)
                    raise
                logger.warning("Retryable Metrika HTTP error {}, attempt {}", exc.code, attempt)
            except (URLError, TimeoutError) as exc:
                last_error = exc
                logger.warning("Temporary Metrika transport error {}, attempt {}", exc, attempt)
            time.sleep(self.retry_backoff_seconds * attempt)
        raise RuntimeError(f"Metrika request failed after retries: {last_error}")

    def _rate_limit(self) -> None:
        if self.rate_limit_per_second <= 0:
            return
        min_interval = 1.0 / self.rate_limit_per_second
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_at = time.monotonic()
