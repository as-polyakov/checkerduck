import csv
import logging
import os
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence, Mapping, Collection

from checkerduck.domain.utils import url_to_domain
from checkerduck.extract.ahrefs_models import *
from checkerduck.extract.ahrefs_models import select_for, Backlink
from checkerduck.extract.client_typed import TypedHTTPJSONClient, new_endpoint, Outcome, NoData
from checkerduck.model.models import TargetQueryableDomain

T = TypeVar("T")
log = logging.getLogger(__name__)

# Append-only ledger. Column names are the Ahrefs x-api-* response headers:
# rows, units-cost-row, units-cost-total, units-cost-total-actual, cache.
DEFAULT_USAGE_PATH = Path("data/ahrefs_api_usage.csv")
_USAGE_COLUMNS = (
    "recorded_at",
    "domain",
    "endpoint",
    "rows",
    "units_cost_row",
    "units_cost_total",
    "units_cost_total_actual",
    "cache",
)


def _chunks(seq: Sequence, n: int):
    for i in range(0, len(seq), n):
        yield seq[i: i + n]


def all_keys(value: T) -> Mapping[str, T]:
    return defaultdict(lambda: value)


@dataclass(frozen=True)
class _ApiCost:
    domain: str
    endpoint: str
    rows: int | None
    units_cost_row: int | None
    units_cost_total: int | None
    units_cost_total_actual: int | None
    cache: str | None

    def as_row(self, recorded_at: str) -> list[object]:
        return [
            recorded_at,
            self.domain,
            self.endpoint,
            self.rows,
            self.units_cost_row,
            self.units_cost_total,
            self.units_cost_total_actual,
            self.cache,
        ]


def _header_int(headers, name: str) -> int | None:
    raw = headers.get(name)
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _split_across(total: int | None, count: int) -> list[int | None]:
    """Split a request total so the parts sum back to it."""
    if count <= 0:
        return []
    if total is None:
        return [None] * count
    share, extra = divmod(total, count)
    return [share + (1 if index < extra else 0) for index in range(count)]


def _request_domains(request_kwargs: Mapping) -> list[str]:
    params = request_kwargs.get("params")
    if isinstance(params, Mapping):
        target = params.get("target")
        if target:
            return [str(target)]

    payload = request_kwargs.get("json")
    if isinstance(payload, Mapping):
        targets = payload.get("targets")
        if isinstance(targets, Sequence) and not isinstance(targets, (str, bytes)):
            domains = [
                str(item["url"])
                for item in targets
                if isinstance(item, Mapping) and item.get("url")
            ]
            if domains:
                return domains
    return [""]


def _costs_for(domains: Sequence[str], endpoint: str, headers) -> list[_ApiCost]:
    """Attribute one response to each domain that request asked about.

    Site Explorer calls name one domain, so that domain keeps the headers.
    Batch analysis is one request for many domains. Its row count and unit
    totals are split across those domains so a sum of the file still equals
    the units the request reported. ``units_cost_row`` and ``cache`` describe
    the request, so each domain keeps the same value.
    """
    rows = _header_int(headers, "x-api-rows")
    per_row = _header_int(headers, "x-api-units-cost-row")
    total = _header_int(headers, "x-api-units-cost-total")
    actual = _header_int(headers, "x-api-units-cost-total-actual")
    cache = headers.get("x-api-cache")
    cache = str(cache).strip() or None if cache else None
    count = len(domains)
    return [
        _ApiCost(
            domain=domain,
            endpoint=endpoint,
            rows=row_share,
            units_cost_row=per_row,
            units_cost_total=total_share,
            units_cost_total_actual=actual_share,
            cache=cache,
        )
        for domain, row_share, total_share, actual_share in zip(
            domains,
            _split_across(rows, count),
            _split_across(total, count),
            _split_across(actual, count),
            strict=True,
        )
    ]


def construct_field_or(field: str, conditions: Collection) -> dict:
    # conditions = conditions[:1]
    if len(conditions) == 0:
        return {}
    return {"or": [
        {"field": field,
         "modifier": "lowercase",
         "is": ["phrase_match", cond]} for cond in conditions]}


def valid_output(t: BatchAnalysisTarget) -> bool:
    if not t.org_traffic_top_by_country:
        log.warning("No org_traffic_top_by_country for batch result %s", t)
        return False
    return True


class AhrefsClient(TypedHTTPJSONClient):
    BATCH_ANALYSIS_CHUNK = 100
    BATCH_ANALYSIS_ENDPOINT = "/batch-analysis/batch-analysis"
    METRICS_HISTORY_ENDPOINT = new_endpoint("/site-explorer/metrics-history",
                                            MetricsHistoryResponse,
                                            MetricHistoryPoint,
                                            lambda r: all_keys(r.metrics))
    TOP_PAGES_ENDPOINT = new_endpoint("/site-explorer/top-pages",
                                      TopPagesResponse, TopPage,
                                      lambda r: all_keys(r.pages))
    BACKLINKS_ENDPOINT = new_endpoint("/site-explorer/all-backlinks",
                                      BacklinksResponse, Backlink,
                                      lambda r: all_keys(r.backlinks))
    OUTGOING_EXTERNAL_ANCHORS_ENDPOINT = new_endpoint("/site-explorer/linked-anchors-external",
                                                      LinkedAnchorsResponse, LinkedAnchor,
                                                      lambda r: all_keys(r.linkedanchors))
    ORGANIC_KEYWORDS_ENDPOINT = new_endpoint("/site-explorer/organic-keywords",
                                             OrganicKeywordsResponse, OrganicKeyword,
                                             lambda r: all_keys(r.keywords))

    def __init__(self, api_token: str, timeout: int = 90,
                 usage_path: str | Path | None = None):
        super().__init__("https://api.ahrefs.com/v3", api_token, timeout)
        self.mocked = os.environ.get("AHREFS_MOCKED", False)
        configured = usage_path if usage_path is not None else os.environ.get("AHREFS_USAGE_FILE")
        self.usage_path = Path(configured or DEFAULT_USAGE_PATH)
        self._usage_lock = threading.Lock()

    def _on_response(self, endpoint: str, response, request_kwargs: Mapping) -> None:
        try:
            costs = _costs_for(_request_domains(request_kwargs), endpoint, response.headers)
            self._append_usage(costs)
        except Exception:
            log.exception("ahrefs usage was not recorded for %s", endpoint)

    def _append_usage(self, costs: Sequence[_ApiCost]) -> None:
        if not costs:
            return
        recorded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        path = self.usage_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._usage_lock:
            write_header = not path.exists() or path.stat().st_size == 0
            with path.open("a", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                if write_header:
                    writer.writerow(_USAGE_COLUMNS)
                writer.writerows(cost.as_row(recorded_at) for cost in costs)

    def batch_analysis(
            self,
            targets: Sequence[TargetQueryableDomain],
            top_countries: int = 5,
    ) -> list[AnalysedDomain]:
        def query_chunk(ch: Sequence[TargetQueryableDomain]) -> list[AnalysedDomain]:
            payload = {
                "targets": [
                    {"url": d.domain, "mode": d.mode, "protocol": d.protocol}
                    for d in ch
                ],
                "select": select_list_for(BatchAnalysisTarget),
                "top_countries": top_countries,
            }
            raw = self._post_bytes(self.BATCH_ANALYSIS_ENDPOINT, payload)
            parsed = msgspec.json.decode(raw, type=BatchAnalysisResponse)
            return [AnalysedDomain.of(t, url_to_domain) for t in parsed.targets if valid_output(t)]

        analysed = []
        for chunk in _chunks(targets, self.BATCH_ANALYSIS_CHUNK):
            analysed.extend(query_chunk(chunk))

        return analysed

    def query_metric_history(
            self, target: TargetQueryableDomain, date_from: str
    ) -> Outcome:
        out: Outcome
        return self._fetch_per_domain_rows(
            target,
            self.METRICS_HISTORY_ENDPOINT,
            {
                "date_from": date_from,
                "target": target.domain,
                "protocol": target.protocol,
                "mode": target.mode,
                "select": select_for(MetricHistoryPoint),
            },
        )

    def query_top_pages(
            self, target: TargetQueryableDomain, date: str, limit: int = 10
    ) -> Outcome:
        return self._fetch_per_domain_rows(
            target,
            self.TOP_PAGES_ENDPOINT,
            {
                "date": date,
                "target": target.domain,
                "protocol": target.protocol,
                "mode": target.mode,
                "select": select_for(TopPage),
                "order_by": "sum_traffic",
                "limit": limit + 1,
            })

    def query_organic_keywords(
            self,
            target: TargetQueryableDomain,
            date: str,
            words_by_category_by_lang: Mapping[str, Mapping[str, str]],
            limit: int = 50,
    ) -> Outcome[OrganicKeyword]:
        words_by_category = words_by_category_by_lang.get(target.lang) if target.lang else {}
        if not words_by_category:
            return NoData(domain=target.domain)

        return self._fetch_per_domain_rows(
            target,
            self.ORGANIC_KEYWORDS_ENDPOINT,
            {
                "date": date,
                "target": target.domain,
                "protocol": target.protocol,
                "mode": target.mode,
                "select": select_for(OrganicKeyword),
                "limit": limit + 1,
                "where": msgspec.json.encode(construct_field_or("keyword", words_by_category.keys())).decode(),
            },
        )

    def query_backlinks(
            self,
            target: TargetQueryableDomain,
            limit: int = 50,
    ) -> Outcome:
        return self._fetch_per_domain_rows(
            target,
            self.BACKLINKS_ENDPOINT,
            {
                "target": target.domain,
                "protocol": target.protocol,
                "mode": target.mode,
                "select": select_for(Backlink),
                "aggregation": "1_per_domain",
                "limit": limit + 1,
            },
        )

    def query_outgoing_anchors(
            self,
            target: TargetQueryableDomain,
            words_by_category_by_lang: Mapping[str, Mapping[str, str]],
            limit: int = 50,
    ) -> Outcome[LinkedAnchor]:
        words_by_category = words_by_category_by_lang.get(target.lang) if target.lang else {}
        if not words_by_category:
            return NoData(domain=target.domain)

        return self._fetch_per_domain_rows(
            target,
            self.OUTGOING_EXTERNAL_ANCHORS_ENDPOINT,
            {
                "target": target.domain,
                "protocol": target.protocol,
                "mode": target.mode,
                "select": select_for(LinkedAnchor),
                "limit": limit + 1,
                "where": msgspec.json.encode(
                    construct_field_or("anchor", words_by_category.keys())
                ).decode(),
            },
        )
