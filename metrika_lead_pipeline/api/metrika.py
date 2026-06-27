from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from metrika_lead_pipeline.collector.client import MetrikaApiClient as MetrikaClient


def save_dataset(rows: list[dict[str, Any]], stem: str, output_dir: Path) -> None:
    """Backward-compatible raw dataset writer.

    The active Reporting API client lives in ``metrika_lead_pipeline.collector.client``. This helper remains for
    callers that used the old API module and writes JSON/CSV plus an XLSX-named table. When
    pandas/openpyxl are installed, reports/writer handles true Excel output for final reports.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{stem}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output_dir / f"{stem}.csv").open("w", encoding="utf-8", newline="") as fh:
        if rows:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    with (output_dir / f"{stem}.xlsx").open("w", encoding="utf-8", newline="") as fh:
        if rows:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
