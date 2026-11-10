from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Mapping, Sequence, Tuple

from checkerduck import domain
from checkerduck.db.db import LinkDirection, get_thread_connection
from checkerduck.domain.utils import safe_int
from checkerduck.extract.ahrefs_models import *
from checkerduck.extract.lang import get_domain_lang_by_top_traffic
from checkerduck.model import Analysis, AnalysisStatus
from checkerduck.model.models import (
    AnalysisDomain, ClassifiedAnchor, ClassifiedBacklink, ClassifiedKeyword,
    RuleEvaluation, TargetQueryableDomain,
)
from checkerduck.resources.cloudflare_categories import CloudFlareCategory
from checkerduck.resources.disallowed_words import ForbiddenWordCategory
from checkerduck.extract.client_typed import Fetched, Outcome, Failed, NoData
from checkerduck.extract.cloud_flare_models import RadarCategory

log = logging.getLogger(__name__)

IN, OUT = "in", "out"

BATCH_SKIP = ("url", "index", "org_traffic_top_by_country")
ANCHOR_SKIP = ("dofollow_links",)

# Country rows share batch_analysis's fetched_at and are not fresh on their own.
_TTL = timedelta(days=30)
FRESHNESS_TTL: dict[str, timedelta] = {
    "domain_categories": _TTL,
    "batch_analysis": _TTL,
    "ahrefs_metrics_history": _TTL,
    "ahrefs_top_pages": _TTL,
    "ahrefs_organic_keywords": _TTL,
    "ahrefs_backlinks": _TTL,
    "anchors_forbidden_words": _TTL,
}


class MissingFreshData(LookupError):
    def __init__(self, table: str, domain: str) -> None:
        self.table = table
        self.domain = domain
        super().__init__(f"no fresh {table} data for {domain}")


def fetched_at_now(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    truncated = now.astimezone(timezone.utc).replace(second=0, microsecond=0)
    # timespec seconds keeps the minute boundary as ":00", never "Z".
    return truncated.isoformat(timespec="seconds")


def _cutoff(max_age: timedelta) -> str:
    return fetched_at_now(datetime.now(timezone.utc) - max_age)


def _latest_fetched_at(
        conn: sqlite3.Connection, table: str, domain: str, max_age: timedelta | None = None,
) -> str | None:
    # KeyError is the allowlist: the table name is interpolated below.
    ttl = max_age if max_age is not None else FRESHNESS_TTL[table]
    row = conn.execute(
        f"SELECT MAX(fetched_at) FROM {table} WHERE domain = ? AND fetched_at >= ?",
        (domain, _cutoff(ttl)),
    ).fetchone()
    if row is None or row[0] is None:
        return None
    return row[0]


def latest_fresh_fetched_at(conn: sqlite3.Connection, table: str, domain: str) -> str:
    fetched_at = _latest_fetched_at(conn, table, domain)
    if fetched_at is None:
        raise MissingFreshData(table, domain)
    return fetched_at


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

    def _error(self, fetched_at: str, domain: str, api: str, error) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO query_errors (fetched_at, domain, api, error) "
                "VALUES (?, ?, ?, ?)",
                (fetched_at, domain, api, str(error)[:2000]),
            )

    def _persist(
            self,
            fetched_at: str,
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
                self._error(fetched_at, domain, api, err)
            case NoData(domain=domain):
                log.debug("%s: no data from %s", domain, api)
            case _:
                raise TypeError(f"Unexpected outcome type: {type(outcome).__name__}")

    # -------------------------------------------------------- per endpoint
    def persist_domain_categories_cloudflare(
            self, fetched_at: str,
            outcomes: Mapping[TargetQueryableDomain, Outcome[RadarCategory]],
    ) -> None:
        sql = _insert_sql("domain_categories",
                          ("fetched_at", "domain"), RadarCategory)
        for queryable_domain, outcome in outcomes.items():
            self._persist(
                fetched_at, outcome, "cloudflare_domain_categories", sql,
                lambda domain, rows: [(fetched_at, domain, *_values(r)) for r in rows],
            )

    def persist_metrics_history(
            self, fetched_at: str, outcome: Outcome[MetricHistoryPoint],
    ) -> None:
        sql = _insert_sql("ahrefs_metrics_history",
                          ("fetched_at", "domain"), MetricHistoryPoint)
        self._persist(
            fetched_at, outcome, "metrics_history", sql,
            lambda domain, rows: [(fetched_at, domain, *_values(r)) for r in rows],
        )

    def persist_top_pages(
            self,
            fetched_at: str,
            outcome: Outcome[TopPage],
            date: str,
            country_code: str = "",
    ) -> None:
        sql = _insert_sql("ahrefs_top_pages",
                          ("fetched_at", "domain", "country_code", "date", "position"),
                          TopPage)
        self._persist(
            fetched_at, outcome, "top_pages", sql,
            lambda domain, rows: [(fetched_at, domain, country_code, date, i + 1, *_values(r))
                                  for i, r in enumerate(rows)],
        )

    def persist_organic_keywords(self, fetched_at: str,
                                 outcome: Outcome[ClassifiedKeyword],
                                 date: str) -> None:
        sql = _insert_sql("ahrefs_organic_keywords",
                          ("fetched_at", "domain", "date"), ClassifiedKeyword)
        self._persist(
            fetched_at, outcome, "organic_keywords", sql,
            lambda domain, rows: [(fetched_at, domain, date, *_values(r)) for r in rows],
        )

    def persist_backlinks(self, fetched_at: str,
                          outcome: Outcome[ClassifiedBacklink]) -> None:
        sql = _insert_sql("ahrefs_backlinks",
                          ("fetched_at", "domain"), ClassifiedBacklink)
        self._persist(
            fetched_at, outcome, "backlinks", sql,
            lambda domain, rows: [(fetched_at, domain, *_values(r)) for r in rows],
        )

    def persist_outgoing_anchors(
            self, fetched_at: str, outcome: Outcome[ClassifiedAnchor]) -> None:
        sql = _insert_sql("anchors_forbidden_words",
                          ("fetched_at", "domain", "direction", "url_from"),
                          ClassifiedAnchor, ANCHOR_SKIP)
        self._persist(
            fetched_at, outcome, "outgoing_anchors", sql,
            lambda domain, rows: [(fetched_at, domain, OUT, "", *_values(r, ANCHOR_SKIP))
                                  for r in rows],
        )

    # ------------------------------------------------------ batch analysis

    def persist_batch_analysis(
            self,
            fetched_at: str,
            analysed: Sequence[AnalysedDomain],
            langs_by_domain: Mapping[str, str],
    ) -> None:
        sql = _insert_sql(
            "batch_analysis",
            ("fetched_at", "domain", "detected_lang", "lang_by_top_traffic"),
            BatchAnalysisTarget, BATCH_SKIP,
        )
        country_sql = (
            "INSERT OR REPLACE INTO ahrefs_org_traffic_country "
            "(fetched_at, domain, country_code, traffic) VALUES (?, ?, ?, ?)"
        )
        # Country rows are not fetched on their own; they share this batch snapshot.
        with self.conn:
            self.conn.executemany(
                sql,
                [
                    (fetched_at, a.domain, langs_by_domain.get(a.domain),
                     get_domain_lang_by_top_traffic(a.metrics.org_traffic_top_by_country),
                     *_values(a.metrics, BATCH_SKIP))
                    for a in analysed
                ],
            )
            self.conn.executemany(
                country_sql,
                [
                    (fetched_at, a.domain, country_code, traffic)
                    for a in analysed
                    for country_code, traffic in a.metrics.org_traffic_top_by_country
                ],
            )

    def persist_domain_categories(self, categories: Mapping[str, str]) -> None:
        # No new timestamp: stamp the newest snapshot already stored for the domain.
        with self.conn:
            self.conn.executemany(
                "UPDATE batch_analysis SET domain_category = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE domain = ? AND fetched_at = ("
                "SELECT MAX(fetched_at) FROM batch_analysis WHERE domain = ?)",
                [(cat, domain, domain) for domain, cat in categories.items()],
            )

    def set_processed(self, target_id: str, count: int) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE analysis SET processed_domains = ? WHERE target_id = ?",
                (count, target_id),
            )

    def is_domain_categories_fresh(self, domain: str, max_age: timedelta | None = None) -> bool:
        return _latest_fetched_at(self.conn, "domain_categories", domain, max_age) is not None

    def is_batch_analysis_fresh(self, domain: str, max_age: timedelta | None = None) -> bool:
        return _latest_fetched_at(self.conn, "batch_analysis", domain, max_age) is not None

    def is_metrics_history_fresh(self, domain: str, max_age: timedelta | None = None) -> bool:
        return _latest_fetched_at(self.conn, "ahrefs_metrics_history", domain, max_age) is not None

    def is_top_pages_fresh(self, domain: str, max_age: timedelta | None = None) -> bool:
        return _latest_fetched_at(self.conn, "ahrefs_top_pages", domain, max_age) is not None

    def is_backlinks_fresh(self, domain: str, max_age: timedelta | None = None) -> bool:
        return _latest_fetched_at(self.conn, "ahrefs_backlinks", domain, max_age) is not None

    def is_outgoing_anchors_fresh(self, domain: str, max_age: timedelta | None = None) -> bool:
        return _latest_fetched_at(self.conn, "anchors_forbidden_words", domain, max_age) is not None

    def is_organic_keywords_fresh(self, domain: str, max_age: timedelta | None = None) -> bool:
        return _latest_fetched_at(self.conn, "ahrefs_organic_keywords", domain, max_age) is not None

    def detected_lang(self, domain: str) -> str:
        fetched_at = latest_fresh_fetched_at(self.conn, "batch_analysis", domain)
        row = self.conn.execute(
            "SELECT detected_lang FROM batch_analysis WHERE domain = ? AND fetched_at = ?",
            (domain, fetched_at),
        ).fetchone()
        if row is None:
            raise MissingFreshData("batch_analysis", domain)
        return row["detected_lang"]


def select_one(query: str, params: tuple = ()) -> dict | None:
    cur = get_thread_connection().cursor()
    cur.execute(query, params)
    row = cur.fetchone()
    return dict(row) if row else None


def select_all(query: str, params: tuple = ()) -> list[dict]:
    cur = get_thread_connection().cursor()
    cur.execute(query, params)
    return [dict(row) for row in cur.fetchall()]


def insert_one(query: str, params: tuple = ()):
    cur = get_thread_connection().cursor()
    cur.execute(query, params)
    get_thread_connection().commit()


def update_analysis_status(analysis_id: str, status: AnalysisStatus) -> None:
    cur = get_thread_connection().cursor()
    cur.execute("update analysis set status = ? where target_id = ?", (status, analysis_id))
    get_thread_connection().commit()


def get_rule_evaluations(analysis_id: str) -> dict[str, List[RuleEvaluation]]:
    res: dict[str, List[RuleEvaluation]] = {}
    rows = select_all(
        "select domain, rule, score, critical_violation, details from rules_evaluation_results where target_id = ?",
        (analysis_id,))
    for row in rows:
        res.setdefault(row["domain"], []).append(
            RuleEvaluation(row["domain"], row["rule"], row["score"], row["critical_violation"], row["details"]))
    return res


def persist_rule_evaluations(analysis_id: str, evals: list[list[RuleEvaluation]]) -> None:
    cur = get_thread_connection().cursor()
    for eval_by_domain in evals:
        for evaluation in eval_by_domain:
            cur.execute(
                "insert into rules_evaluation_results (target_id, domain, rule, score, critical_violation, details) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (analysis_id, evaluation.domain, evaluation.rule, evaluation.score,
                 evaluation.critical_violation, evaluation.details))
    get_thread_connection().commit()


def persist_analysis(analysis: Analysis) -> None:
    insert_one(
        "insert into analysis (target_id, name, status, created_at, completed_at) VALUES (?, ?, ?, ?, ?)",
        (analysis.target_id, analysis.name, analysis.status, analysis.created_at,
         safe_date_to_str(analysis.completed_at)))
    for item in analysis.domains:
        insert_one(
            "insert into analysis_domains (target_id, domain, price_usd, notes) VALUES (?, ?, ?, ?)",
            (analysis.target_id, item.domain, item.price_usd, item.notes))
    get_thread_connection().commit()


def safe_date_to_str(date: datetime | None) -> str | None:
    return date.strftime("%Y-%m-%d %H:%M:%S") if date else None


def safe_date_from_str(datestr: str | None) -> datetime | None:
    if not datestr:
        return None
    try:
        return datetime.strptime(datestr, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.fromisoformat(datestr)


def get_recent_analysis() -> list[dict]:
    return select_all(
        """
        select target_id, name, status, created_at, completed_at,
               (select count(*) from analysis_domains where target_id = analysis.target_id) as "total_domains",
               processed_domains
        from analysis
        order by created_at, completed_at desc
        """, ())


def get_analysis(analysis_id: str) -> Analysis:
    header = select_one(
        """
        select target_id, name, status, created_at, completed_at,
               (select count(*) from analysis_domains where target_id = analysis.target_id) as "total_domains",
               processed_domains
        from analysis
        where target_id = ?
        """, (analysis_id,))
    domains = select_all(
        "select domain, price_usd, notes from analysis_domains where target_id = ?", (analysis_id,))
    return Analysis(
        header["target_id"], header["name"], header["status"],
        header["created_at"], safe_date_from_str(header["completed_at"]),
        [AnalysisDomain(item["domain"], item["price_usd"], item["notes"]) for item in domains],
        int(header["processed_domains"]))


def store_rule_evaluations(analysis_id: str, res: List[RuleEvaluation]) -> None:
    cur = get_thread_connection().cursor()
    for rule_ev in res:
        cur.execute(
            "insert into rules_evaluation_results (target_id, domain, rule, score, critical_violation, details) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (analysis_id, rule_ev.domain, rule_ev.__class__.__name__, rule_ev.score,
             rule_ev.critical_violation, rule_ev.details))


def _require(table: str, domain: str) -> str:
    return latest_fresh_fetched_at(get_thread_connection(), table, domain)


def get_organic_keywords_forbidden_words(domain: str, category: ForbiddenWordCategory) -> list[dict[str, str]]:
    fetched_at = _require("ahrefs_organic_keywords", domain)
    return select_all(
        "select keyword, keyword_country, is_best_position_set_top_3, is_best_position_set_top_4_10, "
        "is_best_position_set_top_11_50, best_position_url from ahrefs_organic_keywords "
        "where domain = ? and fetched_at = ? and forbidden_word_category = ?",
        (domain, fetched_at, category))


def get_backlinks(domain: str) -> list[dict[str, str]]:
    fetched_at = _require("ahrefs_backlinks", domain)
    return select_all(
        "select anchor, is_spam from ahrefs_backlinks where domain = ? and fetched_at = ?",
        (domain, fetched_at))


def get_anchors_forbidden_words(domain: str, direction: LinkDirection,
                                category: ForbiddenWordCategory) -> list[dict[str, str]]:
    fetched_at = _require("anchors_forbidden_words", domain)
    return select_all(
        "select anchor, forbidden_word_category, title from anchors_forbidden_words "
        "where domain = ? and fetched_at = ? and direction = ? and forbidden_word_category = ?",
        (domain, fetched_at, direction, category))


def get_top_pages_traffic(domain: str) -> Dict[int, Tuple[str, int]]:
    fetched_at = _require("ahrefs_top_pages", domain)
    rows = select_all(
        "select position, top_keyword_best_position_title, sum_traffic from ahrefs_top_pages "
        "where domain = ? and fetched_at = ?",
        (domain, fetched_at))
    if not rows:
        raise MissingFreshData("ahrefs_top_pages", domain)
    return {row["position"]: (row["top_keyword_best_position_title"], int(row["sum_traffic"])) for row in rows}


def get_domain_top_page_traffic_pcs(domain: str) -> int:
    traffic_by_position = get_top_pages_traffic(domain)
    top = traffic_by_position.get(1)
    if top is None:
        raise MissingFreshData("ahrefs_top_pages", domain)
    total = sum(int(item[1]) for item in traffic_by_position.values())
    if not total:
        raise MissingFreshData("ahrefs_top_pages", domain)
    return int(100 * int(top[1]) / total)


def get_in_out_num_domains(domain: str) -> tuple[int, int]:
    fetched_at = _require("batch_analysis", domain)
    res = select_one(
        "select linked_domains_dofollow, refdomains_dofollow from batch_analysis "
        "where domain = ? and fetched_at = ?",
        (domain, fetched_at))
    if not res:
        raise MissingFreshData("batch_analysis", domain)
    return safe_int(res["linked_domains_dofollow"]), safe_int(res["refdomains_dofollow"])


def get_domain_top_traffic_geographies(domain: str, top_n: int) -> List[str]:
    traffic_by_country = get_domain_traffic_by_country(domain)
    ranked = sorted(traffic_by_country, key=traffic_by_country.get, reverse=True)
    return ranked[:top_n]


def get_domain_traffic_by_date(domain: str) -> Dict[str, int]:
    fetched_at = _require("ahrefs_metrics_history", domain)
    rows = select_all(
        "select date, org_traffic from ahrefs_metrics_history where domain = ? and fetched_at = ?",
        (domain, fetched_at))
    if not rows:
        raise MissingFreshData("ahrefs_metrics_history", domain)
    return {row["date"]: int(row["org_traffic"]) for row in rows}


def get_domain_traffic_by_country(domain: str) -> Dict[str, int]:
    # Country rows are not fresh on their own. Use the batch snapshot's timestamp.
    fetched_at = _require("batch_analysis", domain)
    rows = select_all(
        "select country_code, traffic from ahrefs_org_traffic_country where domain = ? and fetched_at = ?",
        (domain, fetched_at))
    if not rows:
        raise MissingFreshData("ahrefs_org_traffic_country", domain)
    return {row["country_code"]: int(row["traffic"]) for row in rows}


def get_domain_dr(domain: str) -> int:
    fetched_at = _require("batch_analysis", domain)
    rating = select_one(
        "SELECT domain_rating FROM batch_analysis WHERE domain = ? AND fetched_at = ?",
        (domain, fetched_at),
    )
    if not rating or not rating["domain_rating"]:
        raise MissingFreshData("batch_analysis", domain)
    return int(rating["domain_rating"])


def get_domain_categories(domain: str) -> Sequence[CloudFlareCategory]:
    fetched_at = _require("domain_categories", domain)
    categories = select_all(
        "select id, super_category_id from domain_categories WHERE domain = ? AND fetched_at = ?",
        (domain, fetched_at))
    if not categories:
        raise MissingFreshData("domain_categories", domain)
    return [CloudFlareCategory(row["id"], row["super_category_id"]) for row in categories]
