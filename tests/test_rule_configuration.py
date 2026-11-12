"""Rule settings live on the analysis, not on the rule instances."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from checkerduck.db.db import memory_database
from checkerduck.db.store import get_analysis, persist_analysis
from checkerduck.model.models import Analysis, AnalysisDomain, AnalysisStatus
from checkerduck.rules.rule_configuration import (
    DomainCategoryRuleConfig,
    DomainRatingRuleConfig,
    GeographyRuleConfig,
    OrganicTrafficRuleConfig,
    RuleConfiguration,
)
from checkerduck.rules.seo_rule import DomainRatingRule, EvalContext, GeographyRule

ALEMBIC_INI = str(Path(__file__).resolve().parents[1] / "alembic.ini")


@pytest.fixture
def conn():
    with memory_database(ALEMBIC_INI) as connection:
        yield connection


def test_configuration_is_frozen_and_sections_are_not_shared():
    first = RuleConfiguration()
    second = RuleConfiguration()
    assert first == second
    assert first.geography is not second.geography
    assert first.domain_category.target_categories == ("Technology",)

    with pytest.raises(FrozenInstanceError):
        first.geography.top_n_countries = 3
    with pytest.raises(ValueError):
        GeographyRuleConfig(top_n_countries=2)

    tuned = replace(first, geography=GeographyRuleConfig(top_n_countries=3, target_country="de"))
    assert first.geography.target_country == "us"
    assert tuned.geography.top_n_countries == 3


def test_json_snapshot_round_trip_keeps_every_section():
    original = RuleConfiguration(
        geography=GeographyRuleConfig(top_n_countries=3, target_country="de"),
        organic_traffic=OrganicTrafficRuleConfig(min_traffic=1, max_traffic=5),
        domain_category=DomainCategoryRuleConfig(target_categories=("News", "Sports")),
        domain_rating=DomainRatingRuleConfig(min_threshold=10),
    )
    raw = original.to_json()
    payload = json.loads(raw)
    assert set(payload) == {item.name for item in fields(RuleConfiguration)}
    assert payload["domain_category"]["target_categories"] == ["News", "Sports"]
    assert RuleConfiguration.from_json(raw) == original
    assert RuleConfiguration.from_json(None) == RuleConfiguration()
    assert RuleConfiguration.from_json('{"geography": {"target_country": "fr"}}') == RuleConfiguration(
        geography=GeographyRuleConfig(target_country="fr"),
    )
    with pytest.raises(ValueError):
        RuleConfiguration.from_json('{"nope": {}}')


def test_analysis_persists_the_configuration_snapshot(conn, monkeypatch):
    monkeypatch.setattr("checkerduck.db.store.get_thread_connection", lambda: conn)
    config = RuleConfiguration(
        geography=GeographyRuleConfig(top_n_countries=3, target_country="de"),
    )
    analysis = Analysis(
        target_id="cfg-1",
        name="config snapshot",
        status=AnalysisStatus.PENDING,
        created_at="2026-11-10T00:00:00+00:00",
        completed_at=None,
        domains=[AnalysisDomain("example.com", 0, "")],
        processed_domains=0,
        rule_configuration=config,
    )
    persist_analysis(analysis)

    loaded = get_analysis("cfg-1")
    assert loaded.rule_configuration == config
    stored = json.loads(conn.execute(
        "SELECT rule_configuration FROM analysis WHERE target_id = ?", ("cfg-1",),
    ).fetchone()["rule_configuration"])
    assert stored["geography"] == {"target_country": "de", "top_n_countries": 3}
    assert set(stored) == {item.name for item in fields(RuleConfiguration)}

    conn.execute(
        "INSERT INTO analysis (target_id, name, status, created_at) VALUES (?, ?, ?, ?)",
        ("legacy", "old", "pending", "2026-01-01T00:00:00+00:00"),
    )
    assert get_analysis("legacy").rule_configuration == RuleConfiguration()


def test_one_rule_instance_reads_each_analysis_configuration(monkeypatch):
    monkeypatch.setattr("checkerduck.rules.seo_rule.get_domain_dr", lambda domain: 20)
    monkeypatch.setattr(
        "checkerduck.rules.seo_rule.store.get_domain_top_traffic_geographies",
        lambda domain, top_n: ["de", "us"][:top_n],
    )

    rating = DomainRatingRule()
    strict = EvalContext("a", "example.com", RuleConfiguration())
    loose = EvalContext("b", "example.com", RuleConfiguration(
        domain_rating=DomainRatingRuleConfig(min_threshold=10),
    ))
    assert rating.eval(strict).critical_violation is True
    assert rating.eval(loose).critical_violation is False

    geography = GeographyRule()
    united_states = geography.eval(strict)
    germany = geography.eval(EvalContext("b", "example.com", RuleConfiguration(
        geography=GeographyRuleConfig(top_n_countries=3, target_country="de"),
    )))
    assert united_states.score == 0
    assert germany.score == 1
    assert germany.critical_violation is False
