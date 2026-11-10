"""Ahrefs unit-cost headers are appended per domain and endpoint."""

from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor

import requests

from checkerduck.extract.ahrefs_client_typed import AhrefsClient
from checkerduck.extract.client_typed import Failed, NoData
from checkerduck.model.models import TargetQueryableDomain


def _response(body: bytes, headers: dict[str, str], status: int = 200) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response.reason = "OK" if status < 400 else "ERR"
    response.url = "https://api.ahrefs.com/v3/test"
    response.headers.update(headers)
    response._content = body
    response.encoding = "utf-8"
    return response


def _read(path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _install(client: AhrefsClient, responses: list[requests.Response]) -> None:
    pending = iter(responses)

    def request(method, url, timeout=None, **kwargs):
        return next(pending)

    client.session.request = request


def test_site_explorer_cost_is_kept_on_that_domain(tmp_path):
    path = tmp_path / "usage.csv"
    client = AhrefsClient("token", usage_path=path)
    domain = TargetQueryableDomain("example.com")
    headers = {
        "x-api-rows": "11",
        "x-api-units-cost-row": "8",
        "x-api-units-cost-total": "88",
        "x-api-units-cost-total-actual": "88",
        "x-api-cache": "miss",
    }
    _install(client, [
        _response(b'{"pages":[]}', headers),
        _response(b'{"metrics":[]}', {**headers, "x-api-rows": "4", "x-api-cache": "hit",
                                       "x-api-units-cost-total-actual": "0"}),
    ])

    assert isinstance(client.query_top_pages(domain, "2026-11-10"), NoData)
    assert isinstance(client.query_metric_history(domain, "2026-01-01"), NoData)

    rows = _read(path)
    assert [(row["domain"], row["endpoint"], row["rows"], row["units_cost_total_actual"], row["cache"])
            for row in rows] == [
        ("example.com", "/site-explorer/top-pages", "11", "88", "miss"),
        ("example.com", "/site-explorer/metrics-history", "4", "0", "hit"),
    ]
    assert rows[0]["units_cost_row"] == "8"
    assert rows[0]["units_cost_total"] == "88"
    assert all(row["recorded_at"] for row in rows)


def test_batch_analysis_cost_is_split_across_its_domains(tmp_path):
    path = tmp_path / "usage.csv"
    client = AhrefsClient("token", usage_path=path)
    domains = [TargetQueryableDomain(name) for name in ("a.com", "b.com", "c.com")]
    _install(client, [_response(b'{"targets":[]}', {
        "x-api-rows": "10",
        "x-api-units-cost-row": "9",
        "x-api-units-cost-total": "100",
        "x-api-units-cost-total-actual": "50",
        "x-api-cache": "no_cache",
    })])

    assert client.batch_analysis(domains) == []

    rows = _read(path)
    assert [row["domain"] for row in rows] == ["a.com", "b.com", "c.com"]
    assert {row["endpoint"] for row in rows} == {"/batch-analysis/batch-analysis"}
    assert {row["units_cost_row"] for row in rows} == {"9"}
    assert {row["cache"] for row in rows} == {"no_cache"}
    assert sorted(int(row["rows"]) for row in rows) == [3, 3, 4]
    assert sorted(int(row["units_cost_total"]) for row in rows) == [33, 33, 34]
    assert sorted(int(row["units_cost_total_actual"]) for row in rows) == [16, 17, 17]
    assert sum(int(row["units_cost_total_actual"]) for row in rows) == 50


def test_error_response_is_still_recorded(tmp_path):
    path = tmp_path / "usage.csv"
    client = AhrefsClient("token", usage_path=path)
    _install(client, [_response(b"nope", {
        "x-api-rows": "0",
        "x-api-units-cost-row": "1",
        "x-api-units-cost-total": "50",
        "x-api-units-cost-total-actual": "50",
        "x-api-cache": "miss",
    }, status=500)])

    result = client.query_top_pages(TargetQueryableDomain("example.com"), "2026-11-10")
    assert isinstance(result, Failed)
    rows = _read(path)
    assert len(rows) == 1
    assert rows[0]["units_cost_total_actual"] == "50"
    assert rows[0]["endpoint"] == "/site-explorer/top-pages"


def test_query_that_never_calls_ahrefs_writes_nothing(tmp_path):
    path = tmp_path / "usage.csv"
    client = AhrefsClient("token", usage_path=path)

    def request(*args, **kwargs):
        raise AssertionError("no http")

    client.session.request = request
    result = client.query_organic_keywords(
        TargetQueryableDomain("example.com"), "2026-11-10", {},
    )
    assert isinstance(result, NoData)
    assert not path.exists()


def test_parallel_calls_append_one_row_each(tmp_path):
    path = tmp_path / "usage.csv"
    client = AhrefsClient("token", usage_path=path)
    headers = {
        "x-api-rows": "1",
        "x-api-units-cost-row": "50",
        "x-api-units-cost-total": "50",
        "x-api-units-cost-total-actual": "50",
        "x-api-cache": "miss",
    }

    def request(method, url, timeout=None, **kwargs):
        return _response(b'{"pages":[]}', headers)

    client.session.request = request
    domain = TargetQueryableDomain("example.com")
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: client.query_top_pages(domain, "2026-11-10"), range(40)))

    rows = _read(path)
    assert len(rows) == 40
    assert sum(int(row["units_cost_total_actual"]) for row in rows) == 2000
    assert all(row["domain"] == "example.com" for row in rows)
