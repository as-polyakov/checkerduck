"""
Data models for database entities
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Self, Protocol
from enum import Enum

from checkerduck.extract.ahrefs_models import OrganicKeyword, Backlink, LinkedAnchor


class AnalysisStatus(str, Enum):
    """Analysis status enum"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AnalysisDomain:
    domain: str
    price_usd: int
    notes: str


@dataclass
class Analysis:
    target_id: str  # Primary key - unique analysis identifier
    name: str  # Name of the analysis session
    status: AnalysisStatus  # Current status (pending, running, completed, failed)
    created_at: datetime  # Timestamp when analysis was created
    completed_at: Optional[datetime]  # Timestamp when analysis completed (None if not completed)
    domains: List[AnalysisDomain]
    processed_domains: int


@dataclass
class RuleEvaluation:
    """Result of a rule evaluation"""
    domain: str
    rule: str
    score: float  # Normalized score (0-1 typically)
    critical_violation: bool  # Whether this evaluation represents a critical violation
    details: str

class HasWord(Protocol):
    def get_word(self) -> str | None: ...

class ClassifiedKeyword(OrganicKeyword, frozen=True, kw_only=True):
    forbidden_word_category: str | None = None

    @classmethod
    def of(cls, dto: OrganicKeyword, forbidden_word_category: str | None) -> Self:
        return cls(
            keyword=dto.keyword,
            keyword_country=dto.keyword_country,
            is_best_position_set_top_3=dto.is_best_position_set_top_3,
            is_best_position_set_top_4_10=dto.is_best_position_set_top_4_10,
            is_best_position_set_top_11_50=dto.is_best_position_set_top_11_50,
            best_position_url=dto.best_position_url,
            forbidden_word_category=forbidden_word_category,
        )


class ClassifiedBacklink(Backlink, frozen=True, kw_only=True):
    forbidden_word_category: str | None = None

    @classmethod
    def of(cls, dto: Backlink, forbidden_word_category: str | None) -> Self:
        return cls(
            ahrefs_rank_source=dto.ahrefs_rank_source,
            ahrefs_rank_target=dto.ahrefs_rank_target,
            alt=dto.alt,
            anchor=dto.anchor,
            broken_redirect_new_target=dto.broken_redirect_new_target,
            broken_redirect_reason=dto.broken_redirect_reason,
            broken_redirect_source=dto.broken_redirect_source,
            class_c=dto.class_c,
            discovered_status=dto.discovered_status,
            domain_rating_source=dto.domain_rating_source,
            domain_rating_target=dto.domain_rating_target,
            drop_reason=dto.drop_reason,
            encoding=dto.encoding,
            first_seen=dto.first_seen,
            first_seen_link=dto.first_seen_link,
            http_code=dto.http_code,
            http_crawl=dto.http_crawl,
            ip_source=dto.ip_source,
            is_alternate=dto.is_alternate,
            is_canonical=dto.is_canonical,
            is_content=dto.is_content,
            is_dofollow=dto.is_dofollow,
            is_form=dto.is_form,
            is_frame=dto.is_frame,
            is_image=dto.is_image,
            is_lost=dto.is_lost,
            is_new=dto.is_new,
            is_nofollow=dto.is_nofollow,
            is_redirect=dto.is_redirect,
            is_redirect_lost=dto.is_redirect_lost,
            is_root_source=dto.is_root_source,
            is_root_target=dto.is_root_target,
            is_rss=dto.is_rss,
            is_spam=dto.is_spam,
            is_sponsored=dto.is_sponsored,
            is_text=dto.is_text,
            is_ugc=dto.is_ugc,
            js_crawl=dto.js_crawl,
            last_seen=dto.last_seen,
            last_visited=dto.last_visited,
            link_group_count=dto.link_group_count,
            link_type=dto.link_type,
            linked_domains_source_domain=dto.linked_domains_source_domain,
            linked_domains_source_page=dto.linked_domains_source_page,
            linked_domains_target_domain=dto.linked_domains_target_domain,
            links_external=dto.links_external,
            links_internal=dto.links_internal,
            lost_reason=dto.lost_reason,
            name_source=dto.name_source,
            name_target=dto.name_target,
            noindex=dto.noindex,
            page_category_source=dto.page_category_source,
            page_size=dto.page_size,
            page_type_source=dto.page_type_source,
            port_source=dto.port_source,
            port_target=dto.port_target,
            positions=dto.positions,
            redirect_code=dto.redirect_code,
            refdomains_source=dto.refdomains_source,
            refdomains_source_domain=dto.refdomains_source_domain,
            refdomains_target_domain=dto.refdomains_target_domain,
            root_name_source=dto.root_name_source,
            root_name_target=dto.root_name_target,
            snippet_left=dto.snippet_left,
            snippet_right=dto.snippet_right,
            source_page_author=dto.source_page_author,
            source_page_publish_date=dto.source_page_publish_date,
            title=dto.title,
            tld_class_source=dto.tld_class_source,
            tld_class_target=dto.tld_class_target,
            traffic=dto.traffic,
            traffic_domain=dto.traffic_domain,
            url_from=dto.url_from,
            url_from_plain=dto.url_from_plain,
            url_rating_source=dto.url_rating_source,
            url_to=dto.url_to,
            forbidden_word_category=forbidden_word_category,
        )


class ClassifiedAnchor(LinkedAnchor, frozen=True, kw_only=True):
    forbidden_word_category: str | None = None

    @classmethod
    def of(cls, dto: LinkedAnchor, forbidden_word_category: str | None) -> Self:
        return cls(
            anchor=dto.anchor,
            dofollow_links=dto.dofollow_links,
            forbidden_word_category=forbidden_word_category,
        )


@dataclass
class TargetQueryableDomain:
    domain: str
    lang: Optional[str] = None
    mode: str = "subdomains"
    protocol: str = "both"

    def __hash__(self):
        return hash((self.domain, self.mode, self.protocol))

    def __eq__(self, other):
        if not isinstance(other, TargetQueryableDomain):
            return False
        return (self.domain, self.mode, self.protocol) == \
            (other.domain, other.mode, other.protocol)
