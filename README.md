# Metrika Lead Pipeline

Python 3.12+ project for collecting observable facts from the official Yandex Metrica Reporting API and building a reproducible analytics pipeline for finding pages worth testing for automobile test-drive forms.

The system never invents conclusions. Every recommendation is marked as `Подтверждено данными`, `Гипотеза`, or `Недостаточно данных`, and each run writes `decision_log.json` plus `decision_log.md` so the reasoning chain can be audited.

## Layers

1. `src/api` — OAuth Reporting API client and raw JSON/CSV/XLSX persistence.
2. `src/pipeline` — fact-base construction from observed Metrica data only.
3. `src/signals` — objective configurable signal extraction without funnel-stage classification.
4. `src/analytics` — visit-level rule analysis; rules live in YAML.
5. `src/recommendations` — explainable recommendations with statuses and limitations.
6. `src/reports` — XLSX, Markdown, and decision-log generation.

## Configuration

All tunable settings are outside code:

- `src/config/config.yaml` — periods, regions, brands, categories, API and output settings.
- `src/config/signals.yaml` — signal dictionaries and regular expressions.
- `src/config/rules.yaml` — visit and recommendation rules.
- `.env` — OAuth token (`YANDEX_METRIKA_TOKEN`).

## CLI

```bash
metrika-leads run --input-json pages.json --visits-json visits.json --output-dir reports
```

The input JSON format mirrors normalized Metrica rows, for example:

```json
[
  {"url":"/cars/a-vs-b","title":"Сравнение Model A vs Model B цена","visits":150,"visitors":120,"traffic_sources":{"search":90}}
]
```

Generated files include `report_pages.xlsx`, `report_signals.xlsx`, `report_visits.xlsx`, `lead_generation_report.md`, `decision_log.json`, and `decision_log.md`.
