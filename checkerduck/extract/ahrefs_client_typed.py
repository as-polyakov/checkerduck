import os
from collections import defaultdict
from typing import Sequence, Mapping, Collection

from checkerduck.domain.utils import url_to_domain
from checkerduck.extract.ahrefs_models import *
from checkerduck.extract.ahrefs_models import select_for, Backlink
from checkerduck.extract.client_typed import TypedHTTPJSONClient, new_endpoint, Outcome, NoData
from checkerduck.model.models import TargetQueryableDomain

T = TypeVar("T")


def _chunks(seq: Sequence, n: int):
    for i in range(0, len(seq), n):
        yield seq[i: i + n]


def all_keys(value: T) -> Mapping[str, T]:
    return defaultdict(lambda: value)


def construct_field_or(field: str, conditions: Collection) -> dict:
    # conditions = conditions[:1]
    if len(conditions) == 0:
        return {}
    return {"or": [
        {"field": field,
         "modifier": "lowercase",
         "is": ["phrase_match", cond]} for cond in conditions]}


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

    def __init__(self, api_token: str, timeout: int = 90):
        super().__init__("https://api.ahrefs.com/v3", api_token, timeout)
        self.mocked = os.environ.get("AHREFS_MOCKED", False)

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
            return [AnalysedDomain.of(t, url_to_domain) for t in parsed.targets]

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
