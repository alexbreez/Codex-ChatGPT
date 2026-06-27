from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from metrika_lead_pipeline.history.comparator import RunComparator, write_changes_report
from metrika_lead_pipeline.history.storage import HistoryStorage
from metrika_lead_pipeline.pipeline.automated import collect_and_analyze, resolve_period


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="metrika-leads", description="Automated Yandex Metrica lead analytics pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect", help="Collect Metrika data and run the full analytics pipeline")
    _add_period_args(collect)
    collect.add_argument("--region")
    collect.add_argument("--brand")
    collect.add_argument("--category")
    collect.add_argument("--output", type=Path, default=Path("reports"))
    collect.add_argument("--config", type=Path, default=None)
    compare = sub.add_parser("compare", help="Compare saved runs from history")
    compare.add_argument("--run-id", action="append", dest="run_ids")
    _add_period_args(compare)
    compare.add_argument("--against")
    compare.add_argument("--history-dir", type=Path, default=Path("history"))
    compare.add_argument("--output", type=Path, default=Path("reports"))
    return parser


def _add_period_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--last-days", type=int)
    parser.add_argument("--today", action="store_true")
    parser.add_argument("--yesterday", action="store_true")
    parser.add_argument("--month")
    parser.add_argument("--from", dest="date_from")
    parser.add_argument("--to", dest="date_to")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "collect":
        collect_and_analyze(last_days=args.last_days, today=args.today, yesterday=args.yesterday, month=args.month, date_from=args.date_from, date_to=args.date_to, region=args.region, brand=args.brand, category=args.category, output=args.output, config_path=args.config)
        return 0
    if args.command == "compare":
        storage = HistoryStorage(args.history_dir)
        comparator = RunComparator(storage)
        if args.run_ids and len(args.run_ids) == 2:
            delta = comparator.compare_run_ids(args.run_ids[0], args.run_ids[1])
        else:
            runs = storage.list_runs()
            if args.against == "previous-period" or args.against:
                if len(runs) < 2:
                    delta = comparator.delta_engine.compare(None, {})
                else:
                    delta = comparator.compare_run_ids(runs[-2], runs[-1])
            else:
                raise SystemExit("compare requires two --run-id values or --against")
        write_changes_report(delta, args.output)
        return 0
    return 1


def app() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    app()
