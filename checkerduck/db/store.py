from __future__ import annotations

import logging
import sqlite3
from typing import Any, Callable, Mapping, Sequence

from checkerduck import domain
from checkerduck.extract.ahrefs_models import *
from checkerduck.extract.lang import get_domain_lang_by_top_traffic
from checkerduck.model.models import ClassifiedKeyword, ClassifiedBacklink, TargetQueryableDomain
from checkerduck.extract.client_typed import Fetched, Outcome, Failed, NoData
from checkerduck.extract.cloud_flare_models import RadarCategory

log = logging.getLogger(__name__)

IN, OUT = "in", "out"

BATCH_SKIP = ("url", "index", "org_traffic_top_by_country")
ANCHOR_SKIP = ("dofollow_links",)


def _encode(v: Any) -> Any:
    if isinstance(v, bool):
        return int(v)
    if hasattr(v, "isoformat"):  # date / datetime
        return v.isoformat()
    return v


def _fields(row_type, skip: Sequence[str] = ()) -> list[str]:
    return [f.name for f in msgspec.structs.fields(row_type)
            if f.name not in skip]


def _values(row, skip: Sequence[str] = ()) -> tuple:
    return tuple(_encode(getattr(row, f.name))
                 for f in msgspec.structs.fields(type(row))
                 if f.encode_name not in skip)


def _insert_sql(table: str, prefix: Sequence[str], row_type, skip: Sequence[str] = ()) -> str:
    cols = [*prefix, *_fields(row_type, skip)]
    return (f"INSERT OR REPLACE INTO {table} ({','.join(cols)}) "
            f"VALUES ({','.join('?' * len(cols))})")


# --------------------------------------------------------------------------


class Store:
    def __init__(self, connect: Callable[[], sqlite3.Connection]):
        self._connect = connect

    @property
    def conn(self) -> sqlite3.Connection:
        return self._connect()

    def _error(self, target_id: str, domain: str, api: str, error) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO query_errors (target_id, domain, api, error) "
                "VALUES (?, ?, ?, ?)",
                (target_id, domain, api, str(error)[:2000]),
            )

    def _persist(
            self,
            target_id: str,
            outcome: Outcome,
            api: str,
            sql: str,
            params: Callable[[str, Sequence], list[tuple]],
    ) -> None:
        match outcome:
            case Fetched(domain=domain, rows=rows) if rows:
                with self.conn:
                    self.conn.executemany(sql, params(domain, rows))
            case Failed(domain=domain, error=err):
                self._error(target_id, domain, api, err)
            case NoData(domain=domain):
                log.debug("%s: no data from %s", domain, api)
            case _:
                raise TypeError(f"Unexpected outcome type: {type(outcome).__name__}")

    # -------------------------------------------------------- per endpoint
    def persist_domain_categories_cloudflare(
            self, target_id: str, outcomes: Mapping[TargetQueryableDomain, Outcome[RadarCategory]]
    ) -> None:
        sql = _insert_sql("domain_categories",
                          ("target_id", "domain"), RadarCategory)
        for queryable_domain, outcome in outcomes.items():
            self._persist(
                target_id, outcome, "cloudflare_domain_categories", sql,
                lambda domain, rows: [(target_id, domain, *_values(r)) for r in rows],
            )

    def persist_metrics_history(
            self, target_id: str, outcome: Outcome[MetricHistoryPoint]
    ) -> None:
        sql = _insert_sql("ahrefs_metrics_history",
                          ("target_id", "domain"), MetricHistoryPoint)
        self._persist(
            target_id, outcome, "metrics_history", sql,
            lambda domain, rows: [(target_id, domain, *_values(r)) for r in rows],
        )

    def persist_top_pages(
            self,
            target_id: str,
            outcome: Outcome[TopPage],
            date: str,
            country_code: str = "",
    ) -> None:
        sql = _insert_sql("ahrefs_top_pages",
                          ("target_id", "domain", "country_code", "date", "position"),
                          TopPage)
        self._persist(
            target_id, outcome, "top_pages", sql,
            lambda domain, rows: [(target_id, domain, country_code, date, i + 1, *_values(r))
                                  for i, r in enumerate(rows)],
        )

    def persist_organic_keywords(self, target_id: str,
                                 outcome: Outcome[ClassifiedKeyword],
                                 date: str) -> None:
        sql = _insert_sql("ahrefs_organic_keywords",
                          ("target_id", "domain", "date"), ClassifiedKeyword)
        self._persist(
            target_id, outcome, "organic_keywords", sql,
            lambda domain, rows: [(target_id, domain, date, *_values(r)) for r in rows],
        )

    def persist_backlinks(self, target_id: str,
                          outcome: Outcome[ClassifiedBacklink]) -> None:
        sql = _insert_sql("ahrefs_backlinks",
                          ("target_id", "domain"), ClassifiedBacklink)
        self._persist(
            target_id, outcome, "backlinks", sql,
            lambda domain, rows: [(target_id, domain, *_values(r)) for r in rows],
        )

    def persist_outgoing_anchors(
            self, target_id: str, outcome: Outcome[LinkedAnchor]) -> None:
        sql = _insert_sql("anchors_forbidden_words",
                          ("target_id", "domain", "direction", "url_from"),
                          LinkedAnchor, ANCHOR_SKIP)
        self._persist(
            target_id, outcome, "outgoing_anchors", sql,
            lambda domain, rows: [(target_id, domain, OUT, "", *_values(r, ANCHOR_SKIP))
                                  for r in rows],
        )

    # ------------------------------------------------------ batch analysis

    def persist_batch_analysis(
            self,
            target_id: str,
            analysed: Sequence[AnalysedDomain],
            langs_by_domain: Mapping[str, str],
    ) -> None:
        sql = _insert_sql(
            "batch_analysis",
            ("target_id", "domain", "detected_lang", "lang_by_top_traffic"),
            BatchAnalysisTarget, BATCH_SKIP,
        )
        country_sql = (
            "INSERT OR REPLACE INTO ahrefs_org_traffic_country "
            "(target_id, domain, country_code, traffic) VALUES (?, ?, ?, ?)"
        )
        with self.conn:
            self.conn.executemany(
                sql,
                [
                    (target_id, a.domain, langs_by_domain.get(a.domain),
                     get_domain_lang_by_top_traffic(a.metrics.org_traffic_top_by_country),
                     *_values(a.metrics, BATCH_SKIP))
                    for a in analysed
                ],
            )
            self.conn.executemany(
                country_sql,
                [
                    (target_id, a.domain, country_code, traffic)
                    for a in analysed
                    for country_code, traffic in a.metrics.org_traffic_top_by_country
                ],
            )

    def persist_domain_categories(
            self, target_id: str, categories: Mapping[str, str]
    ) -> None:
        with self.conn:
            self.conn.executemany(
                "UPDATE batch_analysis SET domain_category = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE target_id = ? AND domain = ?",
                [(cat, target_id, domain) for domain, cat in categories.items()],
            )

    def set_processed(self, target_id: str, count: int) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE analysis SET processed_domains = ? WHERE target_id = ?",
                (count, target_id),
            )


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
