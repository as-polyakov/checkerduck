import os
from typing import Any, Callable, Sequence, Mapping, Collection

import requests

from checkerduck.extract.ahrefs_models import *
from checkerduck.model.models import TargetQueryableDomain
from checkerduck.domain.utils import url_to_domain

def construct_field_or(field: str, conditions: Collection) -> dict:
    # conditions = conditions[:1]
    if len(conditions) == 0:
        return {}
    return {"or": [
        {"field": field,
         "modifier": "lowercase",
         "is": ["phrase_match", cond]} for cond in conditions]}

@dataclass(frozen=True)
class Endpoint[E, R]:
    path: str
    row: type[R]
    extract: Callable[[E], list[R]]
    decoder: msgspec.json.Decoder[E]
    select: str


def new_endpoint[E, R](path: str, envelope: type[E], row: type[R],
                       extract: Callable[[E], list[R]]) -> Endpoint[E, R]:
    return Endpoint(path, row, extract, msgspec.json.Decoder(envelope), select_for(row))


class AhrefsClient:
    BASE_URL = "https://api.ahrefs.com/v3"

    BATCH_ANALYSIS_ENDPOINT = "/batch-analysis/batch-analysis"
    METRICS_HISTORY_ENDPOINT = new_endpoint("/site-explorer/metrics-history", MetricsHistoryResponse,
                                            MetricHistoryPoint, lambda r: r.metrics)
    TOP_PAGES_ENDPOINT = new_endpoint("/site-explorer/top-pages", TopPagesResponse, TopPage, lambda r: r.pages)
    BACKLINKS_ENDPOINT = new_endpoint("/site-explorer/all-backlinks", BacklinksResponse, Backlink,
                                      lambda r: r.backlinks)
    OUTGOING_EXTERNAL_ANCHORS_ENDPOINT = new_endpoint("/site-explorer/linked-anchors-external",
                                                      LinkedAnchorsResponse, LinkedAnchor,
                                                      lambda r: r.linkedanchors)
    ORGANIC_KEYWORDS_ENDPOINT = new_endpoint("/site-explorer/organic-keywords", OrganicKeywordsResponse,
                                             OrganicKeyword, lambda r: r.keywords)

    def __init__(self, api_token: str, timeout: int = 90):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            }
        )
        self.mocked = os.environ.get("AHREF_MOCKED", False)

    def _get_bytes(self, endpoint: str, params: dict[str, Any]) -> bytes:
        r = self.session.get(f"{self.BASE_URL}{endpoint}", params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.content

    def _post_bytes(self, endpoint: str, payload: dict[str, Any]) -> bytes:
        r = self.session.post(f"{self.BASE_URL}{endpoint}", json=payload, timeout=self.timeout)
        r.raise_for_status()
        return r.content

    def _fetch_rows[E, R](self, domain: str, endpoint: Endpoint[E, R],
                          params: dict, limit: int | None = None) -> Outcome[R]:
        """One domain, one endpoint. Never raises; returns an Outcome.

        Archive `raw` before decoding if you want replayable extraction —
        parse failures then cost nothing you already paid for.
        """
        try:
            raw = self._get_bytes(endpoint.path, params)
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            return Failed(domain=domain, error=str(e), status=status)
        except requests.RequestException as e:
            return Failed(domain=domain, error=str(e))

        try:
            rows = endpoint.extract(endpoint.decoder.decode(raw))
        except msgspec.ValidationError as e:
            # Shape/type mismatch: Ahrefs changed the schema, fix the struct.
            return Failed(domain=domain, error=f"schema mismatch: {e}")
        except msgspec.DecodeError as e:
            # Not JSON at all: auth wall, proxy page, truncated body.
            return Failed(domain=domain, error=f"malformed body: {e}")

        if not rows:
            return NoData(domain=domain)

        # We request limit+1 so a full page is distinguishable from truncation.
        truncated = limit is not None and len(rows) > limit
        if truncated:
            rows = rows[:limit]
        return Fetched(domain=domain, rows=rows, truncated=truncated)

    # ------------------------------------------------------------ batch analysis

    def batch_analysis(
            self,
            targets: Sequence[TargetQueryableDomain],
            top_countries: int = 5,
    ) -> list[AnalysedDomain]:
        payload = {
            "targets": [
                {"url": d.domain, "mode": d.mode, "protocol": d.protocol}
                for d in targets
            ],
            "select": select_list_for(BatchAnalysisTarget),
            "top_countries": top_countries,
        }
        raw = self._post_bytes(self.BATCH_ANALYSIS_ENDPOINT, payload)
        parsed = msgspec.json.decode(raw, type=BatchAnalysisResponse)
        return [AnalysedDomain.of(t, url_to_domain) for t in parsed.targets]

    def query_metric_history(
            self, targets: Sequence[TargetQueryableDomain], date_from: str
    ) -> dict[TargetQueryableDomain, Outcome]:
        out: dict[TargetQueryableDomain, Outcome] = {}
        for t in targets:
            out[t] = self._fetch_rows(
                t.domain,
                self.METRICS_HISTORY_ENDPOINT,
                {
                    "date_from": date_from,
                    "target": t.domain,
                    "protocol": t.protocol,
                    "mode": t.mode,
                    "select": select_for(MetricHistoryPoint),
                },
            )
        return out

    def query_top_pages(
            self, targets: Sequence[TargetQueryableDomain], date: str, limit: int = 10
    ) -> dict[TargetQueryableDomain, Outcome]:
        out: dict[TargetQueryableDomain, Outcome] = {}
        for t in targets:
            out[t] = self._fetch_rows(
                t.domain,
                self.TOP_PAGES_ENDPOINT,
                {
                    "date": date,
                    "target": t.domain,
                    "protocol": t.protocol,
                    "mode": t.mode,
                    "select": select_for(TopPage),
                    "order_by": "sum_traffic",
                    "limit": limit + 1,
                },
                limit=limit,
            )
        return out

    def query_organic_keywords(
            self,
            targets: Sequence[TargetQueryableDomain],
            date: str,
            words_by_category_by_lang: Mapping[str, Mapping[str, str]],
            limit: int = 50,
    ) -> dict[TargetQueryableDomain, Outcome]:
        out: dict[TargetQueryableDomain, Outcome] = {}
        for t in targets:
            words_by_category = words_by_category_by_lang.get(t.lang) if t.lang else {}
            if not words_by_category:
                out[t] = NoData(domain=t.domain)
                continue

            out[t] = self._fetch_rows(
                t.domain,
                self.ORGANIC_KEYWORDS_ENDPOINT,
                {
                    "date": date,
                    "target": t.domain,
                    "protocol": t.protocol,
                    "mode": t.mode,
                    "select": select_for(OrganicKeyword),
                    "limit": limit + 1,
                    "where": msgspec.json.encode(construct_field_or("keyword", words_by_category.keys())).decode(),
                },
                limit=limit,
            )
        return out

    def query_incoming_anchors(
            self,
            targets: Sequence[TargetQueryableDomain],
            words_by_category_by_lang: Mapping[str, Mapping[str, str]],
            limit: int = 50,
    ) -> dict[TargetQueryableDomain, Outcome]:
        return self.query_anchors(self.BACKLINKS_ENDPOINT, targets, words_by_category_by_lang, limit)

    def query_outgoing_anchors(
            self,
            targets: Sequence[TargetQueryableDomain],
            words_by_category_by_lang: Mapping[str, Mapping[str, str]],
            limit: int = 50,
    ) -> dict[TargetQueryableDomain, Outcome]:
        return self.query_anchors(self.OUTGOING_EXTERNAL_ANCHORS_ENDPOINT, targets, words_by_category_by_lang, limit)

    def query_anchors(
            self,
            endpoint: Endpoint,
            targets: Sequence[TargetQueryableDomain],
            words_by_category_by_lang: Mapping[str, Mapping[str, str]],
            limit: int = 50,
    ) -> dict[TargetQueryableDomain, Outcome]:
        out: dict[TargetQueryableDomain, Outcome] = {}
        for t in targets:
            words_by_category = words_by_category_by_lang.get(t.lang) if t.lang else {}
            if not words_by_category:
                out[t] = NoData(domain=t.domain)
                continue

            out[t] = self._fetch_rows(
                t.domain,
                endpoint,
                {
                    "target": t.domain,
                    "protocol": t.protocol,
                    "mode": t.mode,
                    "select": select_for(Backlink),
                    "limit": limit + 1,
                    "where": msgspec.json.encode(
                        construct_field_or("anchor", words_by_category.keys())
                    ).decode(),
                },
                limit=limit,
            )
        return out
