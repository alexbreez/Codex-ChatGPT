from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

COMMERCIAL_SIGNALS = {"цены", "сравнение моделей", "комплектации", "дилеры", "тест-драйв"}


@dataclass
class DeltaResult:
    new_pages: list[str] = field(default_factory=list)
    disappeared_pages: list[str] = field(default_factory=list)
    new_commercial_signals: dict[str, list[str]] = field(default_factory=dict)
    disappeared_commercial_signals: dict[str, list[str]] = field(default_factory=dict)
    recommendation_changes: dict[str, dict[str, Any]] = field(default_factory=dict)
    status_changes: dict[str, dict[str, str]] = field(default_factory=dict)
    confidence_changes: dict[str, float] = field(default_factory=dict)
    source_changes: dict[str, dict[str, Any]] = field(default_factory=dict)
    search_traffic_changes: dict[str, dict[str, Any]] = field(default_factory=dict)
    reading_time_changes: dict[str, dict[str, Any]] = field(default_factory=dict)
    bounce_rate_changes: dict[str, dict[str, Any]] = field(default_factory=dict)
    entry_page_changes: dict[str, dict[str, Any]] = field(default_factory=dict)
    new_candidates: dict[str, str] = field(default_factory=dict)
    lost_candidates: dict[str, str] = field(default_factory=dict)
    methodology_changes: dict[str, dict[str, Any]] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)

    def model_dump(self) -> dict[str, Any]:
        return self.__dict__.copy()


class DeltaEngine:
    def compare(self, previous: dict[str, Any] | None, current: dict[str, Any]) -> DeltaResult:
        result = DeltaResult()
        if previous is None:
            result.limitations.append("Сравнение невозможно — предыдущий запуск отсутствует.")
            return result
        prev_pages = {p["url"]: p for p in previous.get("pages", [])}
        curr_pages = {p["url"]: p for p in current.get("pages", [])}
        result.new_pages = sorted(set(curr_pages) - set(prev_pages))
        result.disappeared_pages = sorted(set(prev_pages) - set(curr_pages))
        prev_rec = {r["url"]: r for r in previous.get("recommendations", [])}
        curr_rec = {r["url"]: r for r in current.get("recommendations", [])}
        prev_sig = self._signals_by_url(previous)
        curr_sig = self._signals_by_url(current)
        for url in sorted(set(prev_pages) | set(curr_pages)):
            if url in prev_sig or url in curr_sig:
                new = sorted((curr_sig.get(url, set()) - prev_sig.get(url, set())) & COMMERCIAL_SIGNALS)
                gone = sorted((prev_sig.get(url, set()) - curr_sig.get(url, set())) & COMMERCIAL_SIGNALS)
                if new:
                    result.new_commercial_signals[url] = new
                if gone:
                    result.disappeared_commercial_signals[url] = gone
            if url in prev_rec and url in curr_rec:
                if prev_rec[url].get("reason") != curr_rec[url].get("reason"):
                    result.recommendation_changes[url] = {"previous": prev_rec[url].get("reason"), "current": curr_rec[url].get("reason")}
                if prev_rec[url].get("status") != curr_rec[url].get("status"):
                    result.status_changes[url] = {"previous": prev_rec[url].get("status", ""), "current": curr_rec[url].get("status", "")}
                confidence_delta = float(curr_rec[url].get("confidence", 0)) - float(prev_rec[url].get("confidence", 0))
                if confidence_delta:
                    result.confidence_changes[url] = confidence_delta
                self._methodology_delta(result, url, prev_rec[url], curr_rec[url])
            if url in prev_pages and url in curr_pages:
                self._metric_delta(result.search_traffic_changes, url, prev_pages[url], curr_pages[url], "search_traffic_share")
                self._metric_delta(result.reading_time_changes, url, prev_pages[url], curr_pages[url], "avg_time_seconds")
                self._metric_delta(result.bounce_rate_changes, url, prev_pages[url], curr_pages[url], "bounce_rate")
                if prev_pages[url].get("is_entry_page") != curr_pages[url].get("is_entry_page"):
                    result.entry_page_changes[url] = {"previous": prev_pages[url].get("is_entry_page"), "current": curr_pages[url].get("is_entry_page")}
                if prev_pages[url].get("traffic_sources") != curr_pages[url].get("traffic_sources"):
                    result.source_changes[url] = {"previous": prev_pages[url].get("traffic_sources"), "current": curr_pages[url].get("traffic_sources")}
        self._candidates(result, prev_rec, curr_rec)
        return result

    def _methodology_delta(self, result: DeltaResult, url: str, prev: dict[str, Any], curr: dict[str, Any]) -> None:
        keys = [
            "intent_score", "opportunity_score", "risk_score", "stage_confidence",
            "ranking_score", "job_hypothesis", "stage_hypothesis", "recommendation",
            "form_allowed", "form_prohibited", "manual_review_required", "experiment_type",
        ]
        changes = {key: {"previous": prev.get(key), "current": curr.get(key)} for key in keys if prev.get(key) != curr.get(key)}
        if changes:
            result.methodology_changes[url] = changes

    def _signals_by_url(self, snapshot: dict[str, Any]) -> dict[str, set[str]]:
        grouped: dict[str, set[str]] = {}
        for signal in snapshot.get("signals", []):
            grouped.setdefault(signal.get("url", ""), set()).add(signal.get("signal", ""))
        return grouped

    def _metric_delta(self, target: dict[str, dict[str, Any]], url: str, prev: dict[str, Any], curr: dict[str, Any], key: str) -> None:
        if prev.get(key) != curr.get(key):
            target[url] = {"previous": prev.get(key), "current": curr.get(key)}

    def _candidates(self, result: DeltaResult, prev_rec: dict[str, Any], curr_rec: dict[str, Any]) -> None:
        for url, rec in curr_rec.items():
            if rec.get("status") != "Недостаточно данных" and (url not in prev_rec or prev_rec[url].get("status") == "Недостаточно данных"):
                reasons = []
                if url in result.new_commercial_signals:
                    reasons.append("появление коммерческих сигналов")
                if url in result.search_traffic_changes:
                    reasons.append("изменение поискового трафика")
                if url in result.reading_time_changes:
                    reasons.append("изменение времени чтения")
                result.new_candidates[url] = "; ".join(reasons) or "изменение статуса рекомендации"
        for url, rec in prev_rec.items():
            if rec.get("status") != "Недостаточно данных" and curr_rec.get(url, {}).get("status") == "Недостаточно данных":
                reasons = []
                if url in result.disappeared_commercial_signals:
                    reasons.append("исчезновение коммерческих сигналов")
                if url in result.bounce_rate_changes:
                    reasons.append("изменение показателя отказов")
                result.lost_candidates[url] = "; ".join(reasons) or "недостаточность данных или изменение правил"
