"""Per-rule evaluation settings owned by an Analysis.

Rules do not receive this at construction time. EvalContext carries the
analysis snapshot, and each rule reads only its own section.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Self, get_origin, get_type_hints


@dataclass(frozen=True)
class DomainRatingRuleConfig:
    min_threshold: int = 30


@dataclass(frozen=True)
class OrganicTrafficRuleConfig:
    min_traffic: int = 10_000
    max_traffic: int = 100_000


@dataclass(frozen=True)
class HistoricalOrganicTrafficRuleConfig:
    min_avg_traffic: int = 50
    spike_threshold_1m: float = 1.0
    spike_threshold_2m: float = 0.9
    decline_r2: float = 0.7


@dataclass(frozen=True)
class GeographyRuleConfig:
    """Knobs for GeographyRule, read as eval_context.config.geography."""
    top_n_countries: Literal[1, 3] = 1
    target_country: str = "us"

    def __post_init__(self) -> None:
        if self.top_n_countries not in (1, 3):
            raise ValueError("top_n_countries must be 1 or 3")


@dataclass(frozen=True)
class DomainsInOutLinksRatioRuleConfig:
    max_ratio: float = 5


@dataclass(frozen=True)
class SingleTopPageTrafficRuleConfig:
    max_concentration: float = 0.6


@dataclass(frozen=True)
class SpamWordsAnchorsRuleConfig:
    max_count: int = 50
    spam_threshold: float = 0.1


@dataclass(frozen=True)
class ForbiddenWordsAnchorRuleConfig:
    max_count: int = 50
    spam_threshold: float = 0.1


@dataclass(frozen=True)
class ForbiddenWordsOrganicKeywordsRuleConfig:
    top10_divisor: float = 10.0
    top50_divisor: float = 40.0


@dataclass(frozen=True)
class SpamWordsOrganicKeywordsRuleConfig:
    top10_divisor: float = 10.0
    top50_divisor: float = 40.0


@dataclass(frozen=True)
class DomainCategoryRuleConfig:
    target_categories: tuple[str, ...] = field(default_factory=lambda: ("Technology",))


def _section_from_mapping(section_cls: type, payload: dict[str, Any]) -> Any:
    hints = get_type_hints(section_cls)
    unknown = set(payload) - set(hints)
    if unknown:
        raise ValueError(f"{section_cls.__name__} has unknown fields: {sorted(unknown)}")
    kwargs: dict[str, Any] = {}
    for name, hint in hints.items():
        if name not in payload:
            continue
        value = payload[name]
        if get_origin(hint) is tuple and isinstance(value, list):
            value = tuple(value)
        kwargs[name] = value
    return section_cls(**kwargs)


@dataclass(frozen=True)
class RuleConfiguration:
    """Immutable snapshot of every rule's evaluation settings for one analysis."""

    domain_rating: DomainRatingRuleConfig = field(default_factory=DomainRatingRuleConfig)
    organic_traffic: OrganicTrafficRuleConfig = field(default_factory=OrganicTrafficRuleConfig)
    historical_organic_traffic: HistoricalOrganicTrafficRuleConfig = field(
        default_factory=HistoricalOrganicTrafficRuleConfig)
    geography: GeographyRuleConfig = field(default_factory=GeographyRuleConfig)
    in_out_links_ratio: DomainsInOutLinksRatioRuleConfig = field(
        default_factory=DomainsInOutLinksRatioRuleConfig)
    single_top_page_traffic: SingleTopPageTrafficRuleConfig = field(
        default_factory=SingleTopPageTrafficRuleConfig)
    spam_words_anchors: SpamWordsAnchorsRuleConfig = field(default_factory=SpamWordsAnchorsRuleConfig)
    forbidden_words_anchors: ForbiddenWordsAnchorRuleConfig = field(
        default_factory=ForbiddenWordsAnchorRuleConfig)
    forbidden_words_organic_keywords: ForbiddenWordsOrganicKeywordsRuleConfig = field(
        default_factory=ForbiddenWordsOrganicKeywordsRuleConfig)
    spam_words_organic_keywords: SpamWordsOrganicKeywordsRuleConfig = field(
        default_factory=SpamWordsOrganicKeywordsRuleConfig)
    domain_category: DomainCategoryRuleConfig = field(default_factory=DomainCategoryRuleConfig)

    def to_json(self) -> str:
        """Complete snapshot. Tuple fields are stored as JSON arrays."""
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_json(cls, raw: str | None) -> Self:
        """Restore a snapshot. Missing sections keep their defaults. Empty means defaults."""
        if raw is None or raw == "":
            return cls()
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("rule configuration snapshot must be a JSON object")
        hints = get_type_hints(cls)
        unknown = set(payload) - set(hints)
        if unknown:
            raise ValueError(f"unknown rule configuration sections: {sorted(unknown)}")
        kwargs = {}
        for name, section_cls in hints.items():
            if name not in payload or payload[name] is None:
                continue
            section = payload[name]
            if not isinstance(section, dict):
                raise ValueError(f"{name} configuration must be a JSON object")
            kwargs[name] = _section_from_mapping(section_cls, section)
        return cls(**kwargs)
