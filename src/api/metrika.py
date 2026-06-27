from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from loguru import logger


class MetrikaClient:
    def __init__(self, counter_id: str, token: str | None = None, base_url: str = "https://api-metrika.yandex.net/stat/v1/data") -> None:
        self.counter_id = counter_id
        self.token = token or os.getenv("YANDEX_METRIKA_TOKEN", "")
        self.base_url = base_url

    def fetch_report(self, metrics: list[str], dimensions: list[str], date1: str, date2: str, filters: str | None = None, limit: int = 100000) -> dict[str, Any]:
        if not self.token or not self.counter_id:
            raise ValueError("YANDEX_METRIKA_TOKEN and counter_id are required for API collection")
        params: dict[str, Any] = {"ids": self.counter_id, "metrics": ",".join(metrics), "dimensions": ",".join(dimensions), "date1": date1, "date2": date2, "limit": limit}
        if filters:
            params["filters"] = filters
        response = requests.get(self.base_url, headers={"Authorization": f"OAuth {self.token}"}, params=params, timeout=60)
        response.raise_for_status()
        return dict(response.json())


def save_dataset(rows: list[dict[str, Any]], stem: str, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_json(output_dir / f"{stem}.json", orient="records", force_ascii=False, indent=2)
    df.to_csv(output_dir / f"{stem}.csv", index=False)
    df.to_excel(output_dir / f"{stem}.xlsx", index=False)
    logger.info("Saved {} rows to {}", len(rows), output_dir)
