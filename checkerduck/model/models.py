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
            anchor=dto.anchor,
            title=dto.title,
            url_from=dto.url_from,
            snippet_left=dto.snippet_left,
            snippet_right=dto.snippet_right,
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
