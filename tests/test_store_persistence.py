"""Persist the same rows DataExtractor writes, then read them back.

The database is an in-memory SQLite migrated with the Alembic scripts in
migrations/. A value that the schema can store must come back unchanged.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import msgspec
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from checkerduck.db.db import memory_database
from checkerduck.db.store import OUT, Store
from checkerduck.extract.ahrefs_models import (
    AnalysedDomain,
    Backlink,
    BatchAnalysisTarget,
    LinkedAnchor,
    MetricHistoryPoint,
    OrganicKeyword,
    TopPage,
)
from checkerduck.extract.client_typed import Failed, Fetched, NoData
from checkerduck.extract.cloud_flare_models import RadarCategory
from checkerduck.model.models import (
    ClassifiedAnchor,
    ClassifiedBacklink,
    ClassifiedKeyword,
    TargetQueryableDomain,
)

ALEMBIC_INI = str(Path(__file__).resolve().parents[1] / "alembic.ini")
TARGET = "analysis-1"
FETCHED_AT = "2026-03-01T00:00:00+00:00"

APPLICATION_TABLES = frozenset({
    "domain_categories",
    "batch_analysis",
    "ahrefs_org_traffic_country",
    "ahrefs_metrics_history",
    "ahrefs_top_pages",
    "ahrefs_organic_keywords",
    "ahrefs_backlinks",
    "anchors_forbidden_words",
    "query_errors",
    "fetched",
    "analysis",
    "analysis_domains",
    "rules_evaluation_results",
})

# Struct fields the baseline schema has no column for. org_traffic_top_by_country
# is stored in ahrefs_org_traffic_country, and the batch url is stored as domain.
BATCH_NOT_STORED = frozenset({"index", "url", "org_traffic_top_by_country"})
ANCHOR_NOT_STORED = frozenset({"dofollow_links"})

_BACKLINK_BOOLS = (
    "http_crawl", "is_alternate", "is_canonical", "is_content", "is_dofollow",
    "is_form", "is_frame", "is_image", "is_lost", "is_new", "is_nofollow",
    "is_redirect", "is_redirect_lost", "is_root_source", "is_root_target",
    "is_rss", "is_spam", "is_sponsored", "is_text", "is_ugc", "js_crawl", "noindex",
)


@pytest.fixture
def conn():
    with memory_database(ALEMBIC_INI) as connection:
        database_file = connection.execute("PRAGMA database_list").fetchone()["file"]
        assert not database_file
        yield connection


@pytest.fixture
def store(conn):
    # Store asks for a connection on every write. The memory database dies
    # with this connection, so every call must get the same one.
    return Store(lambda: conn)


def test_memory_database_is_migrated_schema(conn):
    names = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }
    assert names == APPLICATION_TABLES | {"alembic_version"}

    head = ScriptDirectory.from_config(Config(ALEMBIC_INI)).get_current_head()
    version = conn.execute("SELECT version_num FROM alembic_version").fetchone()["version_num"]
    assert version == head

    columns = list(conn.execute("PRAGMA table_info(ahrefs_metrics_history)"))
    assert [row["name"] for row in columns] == [
        "fetched_at", "domain", "date", "org_cost", "org_traffic", "paid_cost", "paid_traffic",
    ]
    assert "target_id" not in [row["name"] for row in columns]
    # pk filter follows definition order (fetched_at, domain, date), not key order.
    assert sorted((row["pk"], row["name"]) for row in columns if row["pk"]) == [
        (1, "domain"), (2, "fetched_at"), (3, "date"),
    ]

    error_columns = list(conn.execute("PRAGMA table_info(query_errors)"))
    assert [row["name"] for row in error_columns] == ["fetched_at", "domain", "table_name", "error"]
    assert sorted((row["pk"], row["name"]) for row in error_columns if row["pk"]) == [
        (1, "fetched_at"), (2, "domain"), (3, "table_name"),
    ]

    fetched_columns = list(conn.execute("PRAGMA table_info(fetched)"))
    assert [row["name"] for row in fetched_columns] == [
        "fetched_at", "domain", "table_name", "records_count",
    ]
    assert sorted((row["pk"], row["name"]) for row in fetched_columns if row["pk"]) == [
        (1, "fetched_at"), (2, "domain"), (3, "table_name"),
    ]


def test_extractor_rows_round_trip(conn, store):
    alpha = TargetQueryableDomain(domain="alpha.example", lang="de")
    beta = TargetQueryableDomain(domain="beta.example", lang="en")

    alpha_metrics = BatchAnalysisTarget(
        index=7,
        url="https://alpha.example/path",
        mode="subdomains",
        protocol="https",
        ip="203.0.113.10",
        ahrefs_rank=100,
        domain_rating=42.5,
        url_rating=11.25,
        backlinks=10,
        backlinks_dofollow=6,
        backlinks_internal=1,
        backlinks_nofollow=3,
        backlinks_redirect=0,
        refdomains=20,
        refdomains_dofollow=14,
        refdomains_nofollow=6,
        refips=9,
        refips_subnets=4,
        linked_domains=8,
        linked_domains_dofollow=5,
        outgoing_links=30,
        outgoing_links_dofollow=12,
        org_cost=1500,
        org_traffic=800,
        org_keywords=40,
        org_keywords_1_3=4,
        org_keywords_4_10=6,
        org_keywords_11_20=8,
        org_keywords_21_50=10,
        org_keywords_51_plus=12,
        org_traffic_top_by_country=[("US", 80), ("DE", 20)],
        paid_cost=3,
        paid_traffic=2,
        paid_keywords=1,
        paid_ads=0,
    )
    beta_metrics = BatchAnalysisTarget(
        index=8,
        url="https://www.beta.example/",
        mode="domain",
        protocol="both",
        ip=None,
        ahrefs_rank=2500,
        domain_rating=0.0,
        url_rating=1.5,
        backlinks=0,
        backlinks_dofollow=0,
        backlinks_internal=0,
        backlinks_nofollow=0,
        backlinks_redirect=0,
        refdomains=1,
        refdomains_dofollow=1,
        refdomains_nofollow=0,
        refips=1,
        refips_subnets=1,
        linked_domains=2,
        linked_domains_dofollow=2,
        outgoing_links=4,
        outgoing_links_dofollow=4,
        org_cost=0,
        org_traffic=90,
        org_keywords=5,
        org_keywords_1_3=0,
        org_keywords_4_10=1,
        org_keywords_11_20=1,
        org_keywords_21_50=1,
        org_keywords_51_plus=2,
        org_traffic_top_by_country=[("FR", 10), ("DE", 90)],
        paid_cost=0,
        paid_traffic=0,
        paid_keywords=0,
        paid_ads=0,
    )
    analysed = [
        AnalysedDomain(domain=alpha.domain, metrics=alpha_metrics),
        AnalysedDomain(domain=beta.domain, metrics=beta_metrics),
    ]

    alpha_history = [
        MetricHistoryPoint(
            date=dt.datetime(2026, 1, 15, tzinfo=dt.timezone.utc),
            org_cost=100, org_traffic=50, paid_cost=0, paid_traffic=0,
        ),
        MetricHistoryPoint(
            date=dt.datetime(2026, 2, 1, 12, 30, 15),
            org_cost=0, org_traffic=0, paid_cost=25, paid_traffic=7,
        ),
    ]
    beta_history = [
        MetricHistoryPoint(
            date=dt.datetime(2026, 1, 31, tzinfo=dt.timezone.utc),
            org_cost=9, org_traffic=90, paid_cost=1, paid_traffic=1,
        ),
    ]

    alpha_pages = [
        TopPage(top_keyword_best_position_title="Lower traffic", sum_traffic=10),
        TopPage(top_keyword_best_position_title="Higher traffic", sum_traffic=999),
        TopPage(top_keyword_best_position_title=None, sum_traffic=None),
    ]
    beta_pages = [
        TopPage(top_keyword_best_position_title="Beta page", sum_traffic=4),
    ]

    alpha_backlinks = [
        ClassifiedBacklink.of(
            _backlink("https://source.example/a", anchor="casino bonus", title="A title"),
            "gambling",
        ),
        ClassifiedBacklink.of(
            _backlink(
                "https://other.example/b",
                anchor="casino's бонус",
                alt="banner",
                broken_redirect_new_target="https://alpha.example/new",
                broken_redirect_reason="301",
                broken_redirect_source="https://old.example",
                discovered_status="page_found",
                drop_reason="removed",
                ip_source="198.51.100.8",
                last_seen="2026-02-20T00:00:00Z",
                lost_reason="lostpage",
                page_category_source="article",
                page_type_source="article",
                redirect_code=301,
                source_page_author="Ada",
                source_page_publish_date="2026-01-01",
                title="Other title",
                **{name: not _BACKLINK_DEFAULTS[name] for name in _BACKLINK_BOOLS},
            ),
            None,
        ),
    ]
    beta_backlinks = [
        ClassifiedBacklink.of(
            _backlink("https://ref.example/beta", anchor="beta anchor", title="Beta"),
            "news",
        ),
    ]

    alpha_anchors = [
        ClassifiedAnchor.of(LinkedAnchor(anchor="best casino", dofollow_links=4), "gambling"),
        ClassifiedAnchor.of(LinkedAnchor(anchor="plain link", dofollow_links=0), None),
    ]
    beta_anchors = [
        ClassifiedAnchor.of(LinkedAnchor(anchor="sports book", dofollow_links=2), "betting"),
    ]

    alpha_keywords = [
        ClassifiedKeyword.of(
            OrganicKeyword(
                keyword="online casino",
                keyword_country="US",
                is_best_position_set_top_3=True,
                is_best_position_set_top_4_10=False,
                is_best_position_set_top_11_50=False,
                best_position_url="https://alpha.example/slots",
            ),
            "gambling",
        ),
        ClassifiedKeyword.of(
            OrganicKeyword(
                keyword=None,
                keyword_country="DE",
                is_best_position_set_top_3=False,
                is_best_position_set_top_4_10=True,
                is_best_position_set_top_11_50=False,
                best_position_url=None,
            ),
            None,
        ),
    ]
    beta_keywords = [
        ClassifiedKeyword.of(
            OrganicKeyword(
                keyword="sportwetten",
                keyword_country="DE",
                is_best_position_set_top_3=False,
                is_best_position_set_top_4_10=False,
                is_best_position_set_top_11_50=True,
                best_position_url="https://beta.example/de",
            ),
            "betting",
        ),
    ]

    alpha_categories = [
        RadarCategory(id=17, name="Gambling", super_category_id=3),
        RadarCategory(id=4, name="News", super_category_id=None),
    ]
    beta_categories = [
        RadarCategory(id=8, name="Sports", super_category_id=2),
    ]

    conn.execute(
        "INSERT INTO analysis (target_id, name, status, created_at) VALUES (?, ?, ?, ?)",
        (TARGET, "Spring batch", "running", "2026-03-01 00:00:00"),
    )
    conn.commit()

    # Same order as DataExtractor.run_extract / process_single_domain.
    store.persist_domain_categories_cloudflare(FETCHED_AT, {
        alpha: Fetched(domain=alpha.domain, rows=alpha_categories),
        beta: Fetched(domain=beta.domain, rows=beta_categories, truncated=True),
    })
    store.persist_batch_analysis(FETCHED_AT, analysed, {alpha.domain: "de"})
    store.persist_domain_categories({alpha.domain: "Gambling", beta.domain: "News"})
    store.persist_metrics_history(FETCHED_AT, Fetched(domain=alpha.domain, rows=alpha_history))
    store.persist_metrics_history(FETCHED_AT, Fetched(domain=beta.domain, rows=beta_history))
    store.persist_top_pages(
        FETCHED_AT, Fetched(domain=alpha.domain, rows=alpha_pages), "2026-03-01", country_code="us",
    )
    store.persist_top_pages(FETCHED_AT, Fetched(domain=beta.domain, rows=beta_pages), "2026-03-02")
    store.persist_backlinks(
        FETCHED_AT, Fetched(domain=alpha.domain, rows=alpha_backlinks, truncated=True),
    )
    store.persist_backlinks(FETCHED_AT, Fetched(domain=beta.domain, rows=beta_backlinks))
    store.persist_outgoing_anchors(FETCHED_AT, Fetched(domain=alpha.domain, rows=alpha_anchors))
    store.persist_outgoing_anchors(FETCHED_AT, Fetched(domain=beta.domain, rows=beta_anchors))
    store.persist_organic_keywords(
        FETCHED_AT, Fetched(domain=alpha.domain, rows=alpha_keywords), "2026-03-01",
    )
    store.persist_organic_keywords(
        FETCHED_AT, Fetched(domain=beta.domain, rows=beta_keywords), "2026-03-02",
    )
    store.set_processed(TARGET, 2)

    assert _count(conn, "domain_categories", fetched_at=FETCHED_AT) == 3
    assert _count(conn, "batch_analysis", fetched_at=FETCHED_AT) == 2
    assert _count(conn, "ahrefs_org_traffic_country", fetched_at=FETCHED_AT) == 4
    assert _count(conn, "ahrefs_metrics_history", fetched_at=FETCHED_AT) == 3
    assert _count(conn, "ahrefs_top_pages", fetched_at=FETCHED_AT) == 4
    assert _count(conn, "ahrefs_backlinks", fetched_at=FETCHED_AT) == 3
    assert _count(conn, "anchors_forbidden_words", fetched_at=FETCHED_AT) == 3
    assert _count(conn, "ahrefs_organic_keywords", fetched_at=FETCHED_AT) == 3
    assert _count(conn, "query_errors", fetched_at=FETCHED_AT) == 0
    assert _count(conn, "fetched", fetched_at=FETCHED_AT) == 14
    assert _count(conn, "fetched", fetched_at=FETCHED_AT, table_name="ahrefs_org_traffic_country") == 0
    fetch_counts = {
        (row["domain"], row["table_name"]): row["records_count"]
        for row in _select(conn, "fetched", fetched_at=FETCHED_AT)
    }
    assert fetch_counts[("alpha.example", "domain_categories")] == 2
    assert fetch_counts[("alpha.example", "ahrefs_metrics_history")] == 2
    assert fetch_counts[("beta.example", "ahrefs_organic_keywords")] == 1
    assert fetch_counts[("alpha.example", "batch_analysis")] == 1

    for category, domain in (
        *[(row, alpha.domain) for row in alpha_categories],
        *[(row, beta.domain) for row in beta_categories],
    ):
        _assert_round_trip(
            conn, "domain_categories", category,
            {"fetched_at": FETCHED_AT, "domain": domain, "id": category.id},
            extra={"fetched_at": FETCHED_AT, "domain": domain},
        )

    for item, detected_lang, lang_by_traffic, category in (
        (analysed[0], "de", "en", "Gambling"),
        (analysed[1], None, "de", "News"),
    ):
        _assert_round_trip(
            conn, "batch_analysis", item.metrics,
            {"fetched_at": FETCHED_AT, "domain": item.domain},
            extra={
                "fetched_at": FETCHED_AT,
                "domain": item.domain,
                "detected_lang": detected_lang,
                "lang_by_top_traffic": lang_by_traffic,
                "domain_category": category,
            },
            not_stored=BATCH_NOT_STORED,
            present=("created_at", "updated_at"),
        )
        got_countries = sorted(
            (row["country_code"], row["traffic"])
            for row in _select(
                conn, "ahrefs_org_traffic_country",
                fetched_at=FETCHED_AT, domain=item.domain,
            )
        )
        assert got_countries == sorted(item.metrics.org_traffic_top_by_country)

    for point, domain in (
        *[(row, alpha.domain) for row in alpha_history],
        *[(row, beta.domain) for row in beta_history],
    ):
        _assert_round_trip(
            conn, "ahrefs_metrics_history", point,
            {"fetched_at": FETCHED_AT, "domain": domain, "date": point.date.isoformat()},
            extra={"fetched_at": FETCHED_AT, "domain": domain},
        )

    for index, page in enumerate(alpha_pages, start=1):
        _assert_round_trip(
            conn, "ahrefs_top_pages", page,
            {"fetched_at": FETCHED_AT, "domain": alpha.domain, "country_code": "us", "date": "2026-03-01", "position": index},
            extra={
                "fetched_at": FETCHED_AT, "domain": alpha.domain, "country_code": "us",
                "date": "2026-03-01", "position": index,
            },
        )
    _assert_round_trip(
        conn, "ahrefs_top_pages", beta_pages[0],
        {"fetched_at": FETCHED_AT, "domain": beta.domain, "country_code": "", "date": "2026-03-02", "position": 1},
        extra={
            "fetched_at": FETCHED_AT, "domain": beta.domain, "country_code": "",
            "date": "2026-03-02", "position": 1,
        },
    )

    for link, domain in (
        *[(row, alpha.domain) for row in alpha_backlinks],
        *[(row, beta.domain) for row in beta_backlinks],
    ):
        _assert_round_trip(
            conn, "ahrefs_backlinks", link,
            {"fetched_at": FETCHED_AT, "domain": domain, "url_from": link.url_from},
            extra={"fetched_at": FETCHED_AT, "domain": domain},
        )

    for anchor, domain in (
        *[(row, alpha.domain) for row in alpha_anchors],
        *[(row, beta.domain) for row in beta_anchors],
    ):
        _assert_round_trip(
            conn, "anchors_forbidden_words", anchor,
            {"fetched_at": FETCHED_AT, "domain": domain, "direction": OUT, "anchor": anchor.anchor, "url_from": ""},
            extra={"fetched_at": FETCHED_AT, "domain": domain, "direction": OUT, "url_from": ""},
            not_stored=ANCHOR_NOT_STORED,
        )

    for keyword, domain, query_date in (
        *[(row, alpha.domain, "2026-03-01") for row in alpha_keywords],
        *[(row, beta.domain, "2026-03-02") for row in beta_keywords],
    ):
        _assert_round_trip(
            conn, "ahrefs_organic_keywords", keyword,
            {
                "fetched_at": FETCHED_AT, "domain": domain, "keyword": keyword.keyword,
                "keyword_country": keyword.keyword_country, "date": query_date,
            },
            extra={"fetched_at": FETCHED_AT, "domain": domain, "date": query_date},
        )

    processed = conn.execute(
        "SELECT processed_domains FROM analysis WHERE target_id = ?", (TARGET,),
    ).fetchone()
    assert processed["processed_domains"] == 2


def test_failed_outcome_records_error_without_dropping_rows(conn, store):
    kept = ClassifiedBacklink.of(
        _backlink("https://source.example/kept", anchor="kept", title="Kept"),
        None,
    )
    store.persist_backlinks(FETCHED_AT, Fetched(domain="alpha.example", rows=[kept]))

    error = "x" * 2500
    store.persist_backlinks(
        FETCHED_AT, Failed(domain="beta.example", error=error, status=500),
    )
    store.persist_metrics_history(FETCHED_AT, NoData(domain="alpha.example"))

    errors = _select(conn, "query_errors", fetched_at=FETCHED_AT)
    assert len(errors) == 1
    assert errors[0]["domain"] == "beta.example"
    assert errors[0]["table_name"] == "ahrefs_backlinks"
    assert errors[0]["error"] == error[:2000]
    assert _count(conn, "ahrefs_backlinks", fetched_at=FETCHED_AT) == 1
    assert _count(conn, "ahrefs_metrics_history", fetched_at=FETCHED_AT) == 0
    fetch_counts = {
        (row["domain"], row["table_name"]): row["records_count"]
        for row in _select(conn, "fetched", fetched_at=FETCHED_AT)
    }
    assert fetch_counts == {
        ("alpha.example", "ahrefs_backlinks"): 1,
        ("alpha.example", "ahrefs_metrics_history"): 0,
    }
    _assert_round_trip(
        conn, "ahrefs_backlinks", kept,
        {"fetched_at": FETCHED_AT, "domain": "alpha.example", "url_from": kept.url_from},
        extra={"fetched_at": FETCHED_AT, "domain": "alpha.example"},
    )


_BACKLINK_DEFAULTS = dict(
    ahrefs_rank_source=10,
    ahrefs_rank_target=20,
    alt=None,
    broken_redirect_new_target=None,
    broken_redirect_reason=None,
    broken_redirect_source=None,
    class_c=1,
    discovered_status=None,
    domain_rating_source=15.5,
    domain_rating_target=40.0,
    drop_reason=None,
    encoding="utf-8",
    first_seen="2026-01-02T00:00:00Z",
    first_seen_link="2026-01-02T00:00:00Z",
    http_code=200,
    http_crawl=True,
    ip_source=None,
    is_alternate=False,
    is_canonical=False,
    is_content=True,
    is_dofollow=True,
    is_form=False,
    is_frame=False,
    is_image=False,
    is_lost=False,
    is_new=True,
    is_nofollow=False,
    is_redirect=False,
    is_redirect_lost=False,
    is_root_source=False,
    is_root_target=True,
    is_rss=False,
    is_spam=False,
    is_sponsored=False,
    is_text=True,
    is_ugc=False,
    js_crawl=True,
    last_seen=None,
    last_visited="2026-02-01T00:00:00Z",
    link_group_count=1,
    link_type="text",
    linked_domains_source_domain=3,
    linked_domains_source_page=4,
    linked_domains_target_domain=5,
    links_external=6,
    links_internal=7,
    lost_reason=None,
    name_source="Source",
    name_target="Target",
    noindex=False,
    page_category_source=None,
    page_size=1024,
    page_type_source=None,
    port_source=443,
    port_target=443,
    positions=2,
    redirect_code=None,
    refdomains_source=8,
    refdomains_source_domain=9,
    refdomains_target_domain=10,
    root_name_source="source.example",
    root_name_target="alpha.example",
    snippet_left="left",
    snippet_right="right",
    source_page_author=None,
    source_page_publish_date=None,
    tld_class_source="normal",
    tld_class_target="normal",
    traffic=12,
    traffic_domain=120,
    url_from_plain="source.example/a",
    url_rating_source=3.5,
    url_to="https://alpha.example/",
)


def _backlink(url_from: str, **overrides) -> Backlink:
    return Backlink(url_from=url_from, **{**_BACKLINK_DEFAULTS, **overrides})


def _column_types(conn, table: str) -> dict[str, str]:
    return {
        row["name"]: (row["type"] or "").upper()
        for row in conn.execute(f"PRAGMA table_info({table})")
    }


def _where(criteria: dict[str, Any]) -> tuple[str, list[Any]]:
    parts: list[str] = []
    params: list[Any] = []
    for column, value in criteria.items():
        if value is None:
            parts.append(f"{column} IS NULL")
        else:
            parts.append(f"{column} = ?")
            params.append(value)
    return " AND ".join(parts), params


def _select(conn, table: str, **criteria):
    clause, params = _where(criteria)
    return conn.execute(f"SELECT * FROM {table} WHERE {clause}", params).fetchall()


def _count(conn, table: str, **criteria) -> int:
    clause, params = _where(criteria)
    sql = f"SELECT COUNT(*) AS n FROM {table}"
    if clause:
        sql += f" WHERE {clause}"
    return conn.execute(sql, params).fetchone()["n"]


def _encoded(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _same(stored: Any, expected: Any, column_type: str) -> bool:
    if expected is None:
        return stored is None
    if stored == expected:
        return True
    # TEXT affinity stores an int as its decimal text. The digits are still there.
    if "TEXT" in column_type and type(expected) is int and isinstance(stored, str):
        return stored == str(expected)
    if isinstance(expected, float) and isinstance(stored, (int, float)) and not isinstance(stored, bool):
        return float(stored) == expected
    return False


def _assert_round_trip(
        conn,
        table: str,
        struct,
        where: dict[str, Any],
        *,
        extra: dict[str, Any],
        not_stored: frozenset[str] = frozenset(),
        present: tuple[str, ...] = (),
) -> None:
    types = _column_types(conn, table)
    field_names = [field.name for field in msgspec.structs.fields(type(struct))]
    missing = [name for name in field_names if name not in types and name not in not_stored]
    skipped_but_present = [name for name in not_stored if name in types]
    assert missing == [], f"{table} has no column for {missing}"
    assert skipped_but_present == [], f"{table} can store {skipped_but_present}, but the write skips it"

    rows = _select(conn, table, **where)
    assert len(rows) == 1, (table, where, len(rows))
    row = rows[0]
    for name in field_names:
        if name in not_stored:
            continue
        expected = _encoded(getattr(struct, name))
        stored = row[name]
        assert _same(stored, expected, types[name]), (
            f"{table}.{name}: stored {stored!r}, expected {expected!r}"
        )
    for name, value in extra.items():
        expected = _encoded(value)
        stored = row[name]
        assert _same(stored, expected, types[name]), (
            f"{table}.{name}: stored {stored!r}, expected {expected!r}"
        )
    for name in present:
        assert row[name] is not None, f"{table}.{name} should be filled by the schema default"
