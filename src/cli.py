from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from loguru import logger

from src.pipeline.runner import run_pipeline

app = typer.Typer(help="Yandex Metrica lead-generation analytics pipeline")


@app.command()
def run(input_json: Annotated[Path, typer.Option(help="JSON with page rows already collected from Metrica")], visits_json: Annotated[Path | None, typer.Option(help="Optional JSON with visit paths")] = None, output_dir: Annotated[Path, typer.Option()] = Path("reports")) -> None:
    rows = json.loads(input_json.read_text(encoding="utf-8"))
    visits = json.loads(visits_json.read_text(encoding="utf-8")) if visits_json else []
    pages, signals, recs = run_pipeline(rows, visits, output_dir=output_dir)
    logger.info("Processed {} pages, {} signal rows, {} recommendations", len(pages), len(signals), len(recs))


if __name__ == "__main__":
    app()
