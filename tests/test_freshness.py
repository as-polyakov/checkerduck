"""Freshness is per domain snapshot, not per analysis target."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config

from checkerduck.db import store as dao
from checkerduck.db.db import memory_database
from checkerduck.db.store import MissingFreshData, Store, fetched_at_now, _latest_fetched_at
from checkerduck.extract.client_typed import NoData
from checkerduck.extract.extractor import DataExtractor
from checkerduck.model.models import TargetQueryableDomain

ALEMBIC_INI = str(Path(__file__).resolve().parents[1] / "alembic.ini")
BASELINE = "713b140fbad5"
FROZEN = datetime(2026, 11, 8, 14, 32, 45, tzinfo=timezone.utc)

# method name, table. Country traffic is not in this list: it follows batch_analysis.
FRESH_TABLES = (
    ("is_domain_categories_fresh", "domain_categories"),
    ("is_batch_analysis_fresh", "batch_analysis"),
    ("is_metrics_history_fresh", "ahrefs_metrics_history"),
    ("is_top_pages_fresh", "ahrefs_top_pages"),
    ("is_backlinks_fresh", "ahrefs_backlinks"),
    ("is_outgoing_anchors_fresh", "anchors_forbidden_words"),
    ("is_organic_keywords_fresh", "ahrefs_organic_keywords"),
)


@pytest.fixture
def conn():
    with memory_database(ALEMBIC_INI) as connection:
        yield connection


@pytest.fixture
def store(conn):
    return Store(lambda: conn)


@pytest.fixture
def dao_conn(conn, monkeypatch):
    monkeypatch.setattr("checkerduck.db.store.get_thread_connection", lambda: conn)
    return conn


def _freeze(monkeypatch) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return FROZEN

    monkeypatch.setattr("checkerduck.db.store.datetime", FrozenDateTime)


def _insert_snapshot(conn, table: str, fetched_at: str, domain: str) -> None:
    if table == "domain_categories":
        conn.execute(
            "INSERT INTO domain_categories (fetched_at, domain, id) VALUES (?, ?, '1')",
            (fetched_at, domain),
        )
    elif table == "batch_analysis":
        conn.execute(
            "INSERT INTO batch_analysis (fetched_at, domain, protocol, mode) "
            "VALUES (?, ?, 'https', 'domain')",
            (fetched_at, domain),
        )
    elif table == "ahrefs_metrics_history":
        conn.execute(
            "INSERT INTO ahrefs_metrics_history (fetched_at, domain, date, org_traffic) "
            "VALUES (?, ?, '2026-01-01', 1)",
            (fetched_at, domain),
        )
    elif table == "ahrefs_top_pages":
        conn.execute(
            "INSERT INTO ahrefs_top_pages "
            "(fetched_at, domain, country_code, date, position, sum_traffic) "
            "VALUES (?, ?, '', '2026-01-01', 1, 1)",
            (fetched_at, domain),
        )
    elif table == "ahrefs_backlinks":
        conn.execute(
            "INSERT INTO ahrefs_backlinks (fetched_at, domain, url_from) VALUES (?, ?, ?)",
            (fetched_at, domain, f"https://from.example/{domain}"),
        )
    elif table == "anchors_forbidden_words":
        conn.execute(
            "INSERT INTO anchors_forbidden_words "
            "(fetched_at, domain, direction, anchor, url_from) VALUES (?, ?, 'out', 'a', '')",
            (fetched_at, domain),
        )
    elif table == "ahrefs_organic_keywords":
        conn.execute(
            "INSERT INTO ahrefs_organic_keywords "
            "(fetched_at, domain, keyword, keyword_country, date) "
            "VALUES (?, ?, 'kw', 'US', '2026-01-01')",
            (fetched_at, domain),
        )
    else:
        raise AssertionError(table)


def _batch(conn, fetched_at: str, domain: str, lang: str | None, rating: float = 1) -> None:
    conn.execute(
        "INSERT INTO batch_analysis "
        "(fetched_at, domain, protocol, mode, detected_lang, domain_rating, "
        "linked_domains_dofollow, refdomains_dofollow) "
        "VALUES (?, ?, 'https', 'domain', ?, ?, 5, 4)",
        (fetched_at, domain, lang, rating),
    )


@pytest.mark.parametrize("method,table", FRESH_TABLES)
def test_fresh_window(conn, store, monkeypatch, method, table):
    _freeze(monkeypatch)
    now_stamp = fetched_at_now(FROZEN)
    old_stamp = fetched_at_now(FROZEN - timedelta(days=40))
    cutoff_stamp = fetched_at_now(FROZEN - timedelta(days=30))
    before_cutoff = fetched_at_now(FROZEN - timedelta(days=30) - timedelta(minutes=1))

    fresh_domain = f"{table}.now"
    old_domain = f"{table}.old"
    cutoff_domain = f"{table}.cutoff"
    before_domain = f"{table}.before"
    _insert_snapshot(conn, table, now_stamp, fresh_domain)
    _insert_snapshot(conn, table, old_stamp, old_domain)
    _insert_snapshot(conn, table, cutoff_stamp, cutoff_domain)
    _insert_snapshot(conn, table, before_cutoff, before_domain)

    is_fresh = getattr(store, method)
    assert is_fresh(fresh_domain) is True
    assert is_fresh(old_domain) is False
    assert is_fresh(cutoff_domain) is True
    assert is_fresh(before_domain) is False
    # max_age replaces the map. The 40-day row sits on that cutoff.
    assert is_fresh(old_domain, timedelta(days=40)) is True
    assert is_fresh(old_domain, timedelta(days=39)) is False


def test_latest_fetched_at_rejects_unlisted_table(conn):
    with pytest.raises(KeyError):
        _latest_fetched_at(conn, "ahrefs_org_traffic_country", "x.example")


def test_nodata_does_not_make_domain_fresh(store):
    store.persist_metrics_history(fetched_at_now(), NoData(domain="empty.example"))
    assert store.is_metrics_history_fresh("empty.example") is False


def test_dao_reads_only_newer_fresh_snapshot(dao_conn):
    domain = "hist.example"
    now = fetched_at_now()
    older = fetched_at_now(datetime.now(timezone.utc) - timedelta(days=10))
    stale = fetched_at_now(datetime.now(timezone.utc) - timedelta(days=40))
    for stamp, day, traffic in (
        (stale, "2020-01-01", 9),
        (older, "2026-01-01", 2),
        (now, "2026-02-01", 3),
    ):
        dao_conn.execute(
            "INSERT INTO ahrefs_metrics_history (fetched_at, domain, date, org_traffic) "
            "VALUES (?, ?, ?, ?)",
            (stamp, domain, day, traffic),
        )
    for stamp, rating in ((stale, 1), (older, 10), (now, 77)):
        _batch(dao_conn, stamp, domain, "de", rating)

    assert dao.get_domain_traffic_by_date(domain) == {"2026-02-01": 3}
    assert dao.get_domain_dr(domain) == 77
    assert dao.get_in_out_num_domains(domain) == (5, 4)


def test_freshness_grid_marks_each_table(conn, monkeypatch):
    monkeypatch.setattr("checkerduck.rules.debug.get_thread_connection", lambda: conn)
    from checkerduck.rules.debug import _FRESH_CHECKS, data_freshness

    now = fetched_at_now()
    _insert_snapshot(conn, "batch_analysis", now, "full.example")
    _insert_snapshot(conn, "domain_categories", now, "full.example")
    _insert_snapshot(conn, "ahrefs_backlinks", now, "partial.example")

    grid = data_freshness(["full.example", "partial.example", "none.example"])
    tables = [table for table, _ in _FRESH_CHECKS]
    assert list(grid.columns) == ["Domain", *tables]
    assert list(grid["Domain"]) == ["full.example", "partial.example", "none.example"]

    full = grid.set_index("Domain").loc["full.example"]
    # Country traffic shares the batch-analysis check, so both columns match.
    assert full["batch_analysis"] == full["ahrefs_org_traffic_country"] == "✅"
    assert full["domain_categories"] == "✅"
    assert full["ahrefs_backlinks"] == "❌"
    partial = grid.set_index("Domain").loc["partial.example"]
    assert partial["ahrefs_backlinks"] == "✅"
    assert partial["batch_analysis"] == "❌"
    assert (grid.set_index("Domain").loc["none.example"] == "❌").all()
    assert (grid == "✅").sum().sum() == 4


def test_country_traffic_uses_batch_snapshot_not_country_max(dao_conn):
    now = fetched_at_now()
    batch_at = fetched_at_now(datetime.now(timezone.utc) - timedelta(days=10))
    older = fetched_at_now(datetime.now(timezone.utc) - timedelta(days=20))
    stale = fetched_at_now(datetime.now(timezone.utc) - timedelta(days=40))

    _batch(dao_conn, batch_at, "geo.example", "de")
    dao_conn.executemany(
        "INSERT INTO ahrefs_org_traffic_country (fetched_at, domain, country_code, traffic) "
        "VALUES (?, ?, ?, ?)",
        [
            (batch_at, "geo.example", "US", 10),
            (older, "geo.example", "FR", 5),
            (now, "geo.example", "US", 99),
            (now, "geo.example", "DE", 1),
        ],
    )
    assert dao.get_domain_traffic_by_country("geo.example") == {"US": 10}

    _batch(dao_conn, stale, "oldgeo.example", "en")
    dao_conn.executemany(
        "INSERT INTO ahrefs_org_traffic_country (fetched_at, domain, country_code, traffic) "
        "VALUES (?, ?, ?, ?)",
        [
            (stale, "oldgeo.example", "US", 7),
            (now, "oldgeo.example", "US", 100),
        ],
    )
    with pytest.raises(MissingFreshData):
        dao.get_domain_traffic_by_country("oldgeo.example")


def test_missing_snapshot_raises(dao_conn):
    for call in (
        lambda: dao.get_domain_dr("missing.example"),
        lambda: dao.get_in_out_num_domains("missing.example"),
        lambda: dao.get_domain_top_page_traffic_pcs("missing.example"),
        lambda: dao.get_domain_traffic_by_date("missing.example"),
        lambda: dao.get_domain_traffic_by_country("missing.example"),
    ):
        with pytest.raises(MissingFreshData):
            call()

    now = fetched_at_now()
    dao_conn.execute(
        "INSERT INTO ahrefs_top_pages "
        "(fetched_at, domain, country_code, date, position, sum_traffic) "
        "VALUES (?, 'zero.example', '', '2026-01-01', 1, 0)",
        (now,),
    )
    dao_conn.execute(
        "INSERT INTO ahrefs_top_pages "
        "(fetched_at, domain, country_code, date, position, sum_traffic) "
        "VALUES (?, 'second.example', '', '2026-01-01', 2, 10)",
        (now,),
    )
    with pytest.raises(MissingFreshData):
        dao.get_domain_top_page_traffic_pcs("zero.example")
    with pytest.raises(MissingFreshData):
        dao.get_domain_top_page_traffic_pcs("second.example")


def test_detected_lang_keeps_null_and_rejects_stale(conn, store):
    now = fetched_at_now()
    stale = fetched_at_now(datetime.now(timezone.utc) - timedelta(days=40))
    _batch(conn, stale, "fresh.example", "en")
    _batch(conn, now, "fresh.example", "de")
    _batch(conn, now, "null.example", None)
    _batch(conn, stale, "stale.example", "fr")

    assert store.detected_lang("fresh.example") == "de"
    assert store.detected_lang("null.example") is None
    with pytest.raises(MissingFreshData):
        store.detected_lang("stale.example")


def test_enrich_targets_with_lang_uses_latest_fresh_snapshot(conn, store):
    now = fetched_at_now()
    older = fetched_at_now(datetime.now(timezone.utc) - timedelta(days=10))
    stale = fetched_at_now(datetime.now(timezone.utc) - timedelta(days=40))
    _batch(conn, older, "fresh.example", "en")
    _batch(conn, now, "fresh.example", "de")
    _batch(conn, now, "null.example", None)
    _batch(conn, stale, "stale.example", "fr")

    extractor = DataExtractor.__new__(DataExtractor)
    extractor.store = store
    targets = [
        TargetQueryableDomain("fresh.example"),
        TargetQueryableDomain("null.example"),
    ]
    extractor.enrich_targets_with_lang(targets)

    assert [target.lang for target in targets] == ["de", None]
    with pytest.raises(MissingFreshData):
        extractor.enrich_targets_with_lang([TargetQueryableDomain("stale.example")])


def test_fetch_if_stale_skips_when_fresh(caplog):
    calls = []
    with caplog.at_level("DEBUG", logger="checkerduck.extract.extractor"):
        DataExtractor._fetch_if_stale(
            None, "example.com", "metrics history", True,
            lambda: calls.append("fetch"), lambda *args: calls.append(args),
        )
    assert calls == []
    assert "example.com: skipping fresh metrics history" in caplog.text


def test_fetch_if_stale_persists_result_and_timestamp():
    seen = {}
    extractor = DataExtractor.__new__(DataExtractor)
    extractor.fetched_at = "2026-11-08T14:32:00+00:00"
    DataExtractor._fetch_if_stale(
        extractor,
        "example.com",
        "metrics history",
        False,
        lambda: "rows",
        lambda result, fetched_at: seen.update(result=result, fetched_at=fetched_at),
    )
    assert seen == {"result": "rows", "fetched_at": "2026-11-08T14:32:00+00:00"}


def test_fetched_at_now_truncates_to_utc_minute():
    assert fetched_at_now(
        datetime(2026, 11, 8, 14, 32, 45, 1, tzinfo=timezone.utc),
    ) == "2026-11-08T14:32:00+00:00"
    ahead = timezone(timedelta(hours=2))
    assert fetched_at_now(
        datetime(2026, 11, 8, 16, 32, 59, tzinfo=ahead),
    ) == "2026-11-08T14:32:00+00:00"


def test_migration_rewrites_fetched_at_from_analysis_created_at():
    uri = f"file:checkerduck_{uuid4().hex}?mode=memory&cache=shared"
    anchor = sqlite3.connect(uri, uri=True)
    anchor.row_factory = sqlite3.Row
    cfg = Config(ALEMBIC_INI)
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{uri}&uri=true")
    try:
        command.upgrade(cfg, BASELINE)
        anchor.executemany(
            "INSERT INTO analysis (target_id, name, status, created_at) VALUES (?, ?, ?, ?)",
            [
                ("a1", "first", "done", "2026-05-01 10:00:10"),
                ("a2", "second", "done", "2026-05-01 10:00:40"),
                ("a3", "later", "done", "2026-06-15 08:07:59"),
            ],
        )
        anchor.executemany(
            "INSERT INTO ahrefs_metrics_history "
            "(target_id, domain, date, org_cost, org_traffic, paid_cost, paid_traffic) "
            "VALUES (?, ?, ?, ?, ?, 0, 0)",
            [
                ("a1", "collapse.example", "2026-01-01", 1, 11),
                ("a2", "collapse.example", "2026-01-01", 2, 22),
                ("a3", "trunc.example", "2026-04-01", 3, 5),
                ("missing", "orphan.example", "2026-01-01", 0, 1),
            ],
        )
        anchor.execute(
            "INSERT INTO batch_analysis (target_id, domain, protocol, mode) "
            "VALUES ('a3', 'trunc.example', 'https', 'domain')",
        )
        anchor.execute(
            "INSERT INTO ahrefs_org_traffic_country (target_id, domain, country_code, traffic) "
            "VALUES ('a3', 'trunc.example', 'US', 8)",
        )
        anchor.commit()

        command.upgrade(cfg, "head")

        collapsed = anchor.execute(
            "SELECT fetched_at, org_traffic FROM ahrefs_metrics_history "
            "WHERE domain = 'collapse.example' AND date = '2026-01-01'",
        ).fetchall()
        assert len(collapsed) == 1
        assert collapsed[0]["fetched_at"] == "2026-05-01T10:00:00+00:00"
        assert collapsed[0]["org_traffic"] == 22

        trunc = anchor.execute(
            "SELECT fetched_at, org_traffic FROM ahrefs_metrics_history WHERE domain = 'trunc.example'",
        ).fetchone()
        assert trunc["fetched_at"] == "2026-06-15T08:07:00+00:00"
        assert trunc["org_traffic"] == 5

        orphan = anchor.execute(
            "SELECT fetched_at FROM ahrefs_metrics_history WHERE domain = 'orphan.example'",
        ).fetchone()
        assert orphan["fetched_at"] == "1970-01-01T00:00:00+00:00"

        batch = anchor.execute(
            "SELECT fetched_at FROM batch_analysis WHERE domain = 'trunc.example'",
        ).fetchone()
        country = anchor.execute(
            "SELECT fetched_at, traffic FROM ahrefs_org_traffic_country WHERE domain = 'trunc.example'",
        ).fetchone()
        assert batch["fetched_at"] == country["fetched_at"] == "2026-06-15T08:07:00+00:00"
        assert country["traffic"] == 8

        analysis_cols = [row["name"] for row in anchor.execute("PRAGMA table_info(analysis)")]
        assert "target_id" in analysis_cols
        assert anchor.execute("SELECT COUNT(*) AS n FROM analysis").fetchone()["n"] == 3
        metric_cols = [row["name"] for row in anchor.execute("PRAGMA table_info(ahrefs_metrics_history)")]
        assert "target_id" not in metric_cols
        assert "fetched_at" in metric_cols

        command.downgrade(cfg, BASELINE)
        downgraded = [row["name"] for row in anchor.execute("PRAGMA table_info(ahrefs_metrics_history)")]
        assert "target_id" in downgraded
        assert "fetched_at" not in downgraded
        migrated = anchor.execute(
            "SELECT target_id FROM ahrefs_metrics_history WHERE domain = 'trunc.example'",
        ).fetchone()
        assert migrated["target_id"] == "migrated"
        version = anchor.execute("SELECT version_num FROM alembic_version").fetchone()["version_num"]
        assert version == BASELINE
    finally:
        anchor.close()
