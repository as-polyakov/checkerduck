"""
Typed models for the Ahrefs API v3 endpoints used by AhrefsClient.

Field names, types and nullability are transcribed from the official reference
(fetched 2026-09-04):

  organic-keywords         https://docs.ahrefs.com/en/api/reference/site-explorer/get-organic-keywords
  top-pages                https://docs.ahrefs.com/en/api/reference/site-explorer/get-top-pages
  metrics-history          https://docs.ahrefs.com/en/api/reference/site-explorer/get-metrics-history
  all-backlinks            https://docs.ahrefs.com/en/api/reference/site-explorer/get-all-backlinks
  linked-anchors-external  https://docs.ahrefs.com/en/api/reference/site-explorer/get-linked-anchors-external
  batch-analysis           https://docs.ahrefs.com/en/api/reference/batch-analysis/post-batch-analysis

DESIGN RULES
------------
1. One struct per (endpoint, select-set). The `select` parameter is DERIVED from
   the struct via `select_for()`, so the requested columns and the decoded
   columns cannot drift.

2. These are provider DTOs. They mirror Ahrefs' wire format exactly. They are
   not storage rows and not rule-engine inputs — map them onward.

3. `| None` here means "Ahrefs documents this column as nullable", not "we
   might not have asked for it". Because select is derived from the struct, a
   missing key is a real error and should raise.

4. Nothing in this module knows about forbidden words, target_id, or SQLite.
   Classification is a separate, replayable pass (see `classify.py` note at
   the bottom).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal, TypeVar

import msgspec
from msgspec import Struct

T = TypeVar("T")


def select_for(row_type: type[Struct]) -> str:
    return ",".join(f.encode_name for f in msgspec.structs.fields(row_type))


def select_list_for(row_type: type[Struct]) -> list[str]:
    return [f.encode_name for f in msgspec.structs.fields(row_type)]


Protocol = Literal["both", "http", "https"]
Mode = Literal["exact", "prefix", "domain", "subdomains"]
PositionSet = Literal["top_3", "top_4_10", "top_11_50", "top_51_more"]
LinkType = Literal["redirect", "frame", "text", "form", "canonical", "alternate", "rss", "image"]
TldClass = Literal["gov", "edu", "normal"]
PageStatus = Literal["left", "right", "both"]


# --------------------------------------------------------------------------
# GET /v3/site-explorer/organic-keywords   ->  {}
# --------------------------------------------------------------------------
class OrganicKeyword(Struct, frozen=True, kw_only=True):
    keyword: str | None
    keyword_country: str  # uppercase ISO 3166-1 alpha-2, non-null
    is_best_position_set_top_3: bool
    is_best_position_set_top_4_10: bool
    is_best_position_set_top_11_50: bool
    best_position_url: str | None

    def get_word(self) -> str | None:
        return self.keyword


class OrganicKeywordsResponse(Struct, frozen=True):
    keywords: list[OrganicKeyword] = []



# --------------------------------------------------------------------------
# GET /v3/site-explorer/top-pages   ->  {"pages": [...]}
# --------------------------------------------------------------------------
class TopPage(Struct, frozen=True, kw_only=True):
    top_keyword_best_position_title: str | None
    sum_traffic: int | None


class TopPagesResponse(Struct, frozen=True):
    pages: list[TopPage] = []


# --------------------------------------------------------------------------
# GET /v3/site-explorer/metrics-history   ->  {"metrics": [...]}
# --------------------------------------------------------------------------
class MetricHistoryPoint(Struct, frozen=True, kw_only=True):
    date: dt.datetime
    org_cost: int  # USD cents
    org_traffic: int
    paid_cost: int  # USD cents
    paid_traffic: int


class MetricsHistoryResponse(Struct, frozen=True):
    metrics: list[MetricHistoryPoint] = []


# --------------------------------------------------------------------------
# GET /v3/site-explorer/all-backlinks   ->  {"backlinks": [...]}
# --------------------------------------------------------------------------
class Backlink(Struct, frozen=True, kw_only=True):
    anchor: str
    title: str
    url_from: str
    snippet_left: str
    snippet_right: str

    def get_word(self) -> str | None:
        return self.anchor


class BacklinksResponse(Struct, frozen=True):
    backlinks: list[Backlink] = []



# --------------------------------------------------------------------------
# GET /v3/site-explorer/linked-anchors-external -> {"linkedanchors": [...]}
# --------------------------------------------------------------------------
class LinkedAnchor(Struct, frozen=True, kw_only=True):
    anchor: str
    dofollow_links: int

    def get_word(self) -> str | None:
        return self.anchor


class LinkedAnchorsResponse(Struct, frozen=True):
    linkedanchors: list[LinkedAnchor] = []



# --------------------------------------------------------------------------
# POST /v3/batch-analysis/batch-analysis   ->  {"targets": [...]}
# --------------------------------------------------------------------------
class BatchAnalysisTarget(Struct, frozen=True, kw_only=True):
    index: int
    url: str
    mode: str
    protocol: str
    ip: str | None

    ahrefs_rank: int
    domain_rating: float
    url_rating: float

    backlinks: int
    backlinks_dofollow: int
    backlinks_internal: int
    backlinks_nofollow: int
    backlinks_redirect: int

    refdomains: int
    refdomains_dofollow: int
    refdomains_nofollow: int
    refips: int
    refips_subnets: int

    linked_domains: int
    linked_domains_dofollow: int
    outgoing_links: int
    outgoing_links_dofollow: int

    org_cost: int
    org_traffic: int
    org_keywords: int
    org_keywords_1_3: int
    org_keywords_4_10: int
    org_keywords_11_20: int
    org_keywords_21_50: int
    org_keywords_51_plus: int
    org_traffic_top_by_country: list[tuple[str, int]]

    paid_cost: int
    paid_traffic: int
    paid_keywords: int
    paid_ads: int


class BatchAnalysisResponse(Struct, frozen=True):
    targets: list[BatchAnalysisTarget] = []


class AnalysedDomain(Struct, frozen=True, kw_only=True):
    domain: str
    metrics: BatchAnalysisTarget

    @classmethod
    def of(cls, target: BatchAnalysisTarget, url_to_domain) -> "AnalysedDomain":
        return cls(domain=url_to_domain(target.url), metrics=target)


@dataclass(frozen=True)
class Fetched[R]:
    domain: str
    rows: list[R]
    truncated: bool = False


@dataclass(frozen=True)
class NoData:
    domain: str


@dataclass(frozen=True)
class Failed:
    domain: str
    error: str
    status: int | None = None


type Outcome[R] = Fetched[R] | NoData | Failed