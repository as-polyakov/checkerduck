import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy import signal
from scipy.stats import linregress

from checkerduck.db import dao
from checkerduck.db.dao import get_domain_dr, get_domain_traffic_by_country, get_domain_traffic_by_date, \
    get_in_out_num_domains, \
    get_top_pages_traffic, get_anchors_forbidden_words, get_organic_keywords_forbidden_words, get_domain_categories
from checkerduck.db import db
from checkerduck.model.models import RuleEvaluation
from checkerduck.resources.disallowed_words import ForbiddenWordCategory
from sentence_transformers import SentenceTransformer

log = logging.getLogger(__name__)


@dataclass
class EvalContext:
    target_id: str
    domain: str


@dataclass
class GeographyRuleConfig:
    """Knobs for GeographyRule. Edit in a notebook via RuleConfiguration.geography."""
    top_n_countries: Literal[1, 3] = 1


class RuleConfiguration:
    """Central place for per-rule tunable knobs, so they can be tweaked from a notebook."""
    geography = GeographyRuleConfig()


class SeoRule(ABC):
    """Base class for all SEO rules"""

    def __init__(
            self,
            name: str,
            weight: float,
            area: Literal["safety", "authority", "relevance", "traffic"],
            deal_breaker: bool = False
    ):
        self.name = name
        self.weight = weight
        self.area = area
        self.deal_breaker = deal_breaker

    @abstractmethod
    def eval(self, eval_context: EvalContext) -> RuleEvaluation:
        pass

    def safe_eval(self, eval_context: EvalContext) -> RuleEvaluation:
        try:
            return self.eval(eval_context)
        except Exception as e:
            log.warning("rule %s failed for %s: %s", self.name, eval_context.domain, e)
            return RuleEvaluation(eval_context.domain, self.name, score=0.0, critical_violation=False, details=str(e))


class DomainRatingRule(SeoRule):
    """Evaluates domain rating (DR) score"""

    def __init__(self):
        super().__init__(
            name="Domain Rating",
            weight=1.0,
            area="authority",
            deal_breaker=False
        )
        self.min_threshold = 30

    def eval(self, eval_context: EvalContext) -> RuleEvaluation:
        dr = get_domain_dr(eval_context.target_id, eval_context.domain)
        score = min(dr / 100.0, 1.0)
        critical_violation = dr < self.min_threshold
        return RuleEvaluation(eval_context.domain, self.__class__.__name__,
                              score, critical_violation, "")


class OrganicTrafficRule(SeoRule):
    """Evaluates current organic traffic levels"""

    def __init__(self):
        super().__init__(
            name="Organic Traffic",
            weight=1.0,
            area="traffic",
            deal_breaker=False
        )
        self.min_traffic = 10000
        self.max_traffic = 100000

    def eval(self, eval_context: EvalContext) -> RuleEvaluation:
        traffic_by_country = get_domain_traffic_by_country(eval_context.target_id, eval_context.domain)
        total = sum(traffic_by_country.values())

        if len(traffic_by_country) == 0 or total < self.min_traffic:
            return RuleEvaluation(eval_context.domain, self.__class__.__name__, 0, True, "")
        score = min(total / self.max_traffic, 1.0)
        return RuleEvaluation(eval_context.domain, self.__class__.__name__, score, False, "")


class HistoricalOrganicTrafficRule(SeoRule):
    """Evaluates historical organic traffic trends"""

    def __init__(self, weight: float = 0.8, min_avg_traffic: int = 50):
        super().__init__(
            name="Historical Organic Traffic",
            weight=weight,
            area="traffic",
            deal_breaker=False
        )
        self.min_avg_traffic = min_avg_traffic
        self.spike_threshold_1m = 1.0
        self.spike_threshold_2m = 0.9
        self.decline_r2 = 0.7

    def has_traffic_spike(self, traffic_by_date: dict[str, int]) -> bool:
        if not traffic_by_date or len(traffic_by_date) < 3:
            return False

            # Sort by ISO date strings (lexicographically correct)
        dates = sorted(traffic_by_date.keys())
        values = np.array([traffic_by_date[d] for d in dates], dtype=int)

        # Define a dynamic threshold
        threshold = (np.max(values) - np.min(values)) / 3 + np.min(values)

        # Detect peaks above threshold
        peaks, _ = signal.find_peaks(values, threshold=threshold)

        return peaks.size > 0

    def eval(self, eval_context: EvalContext) -> RuleEvaluation:
        traffic_by_date = get_domain_traffic_by_date(eval_context.target_id, eval_context.domain)
        # Sort by date to get time order
        dates = sorted(traffic_by_date.keys())
        traffic = np.array([traffic_by_date[d] for d in dates], dtype=float)

        # --- Spike detection ---
        has_spikes = self.has_traffic_spike(traffic_by_date)

        # --- Steady decline detection ---
        x = np.arange(len(traffic))
        slope, intercept, r_value, p_value, std_err = linregress(x, traffic)
        steady_decline = (slope < 0) and (r_value ** 2 > self.decline_r2)
        score = 1 if not steady_decline else 0.5 if not has_spikes else 0
        return RuleEvaluation(eval_context.domain, self.__class__.__name__, score, False, "")


class GeographyRule(SeoRule):
    """Evaluates geographic relevance of traffic"""

    def __init__(self):
        super().__init__(
            name="Geography",
            weight=1,
            area="relevance",
            deal_breaker=False
        )


    def eval(self, eval_context: EvalContext) -> RuleEvaluation:
        def get_domain_top_traffic_geographies(target_id: str, domain: str, top_n: int) -> List[str]:
            traffic_by_country = get_domain_traffic_by_country(target_id, domain)
            ranked = sorted(traffic_by_country, key=traffic_by_country.get, reverse=True)
            return ranked[:top_n]

        top_countries = dao.get_domain_top_traffic_geographies(eval_context.target_id, eval_context.domain, RuleConfiguration.geography.top_n_countries)
        matches = RuleConfiguration.geography.target_country in top_countries
        score = 1 if matches else 0
        critical_violation = not matches
        return RuleEvaluation(eval_context.domain, self.__class__.__name__, score, critical_violation, "Country during rule evalution {country}")


class DomainsInOutLinksRatioRule(SeoRule):
    """Evaluates ratio of inbound to outbound links"""

    def __init__(self):
        super().__init__(
            name="Domains In/Out Links Ratio",
            weight=0.5,
            area="authority",
            deal_breaker=False
        )
        self.max_ratio = 5

    def eval(self, eval_context: EvalContext) -> RuleEvaluation:
        in_num, out_num = get_in_out_num_domains(eval_context.target_id, eval_context.domain)
        if not out_num or not out_num:
            return RuleEvaluation(eval_context.domain, self.__class__.__name__, 0, False, "")

        ratio = float(in_num if in_num else 0) / float(out_num)
        critical_violation = ratio > self.max_ratio

        return RuleEvaluation(eval_context.domain, self.__class__.__name__, min(ratio, 1), critical_violation, "")


class SingleTopPageTrafficRule(SeoRule):
    """Evaluates if traffic is too concentrated on single page"""

    def __init__(self):
        super().__init__(
            name="Single Top Page Traffic",
            weight=1,
            area="relevance",
            deal_breaker=False
        )
        self.max_concentration = 0.6

    def eval(self, eval_context: EvalContext) -> RuleEvaluation:
        top_pages = get_top_pages_traffic(eval_context.target_id, eval_context.domain)

        top_pos, (top_title, top_traffic) = max(
            top_pages.items(), key=lambda x: x[1][1]
        )
        total_traffic = sum(v[1] for v in top_pages.values())
        concentration = float(top_traffic) / float(total_traffic)
        # Lower concentration is better (more distributed traffic)
        score = 1.0 - concentration
        return RuleEvaluation(eval_context.domain, self.__class__.__name__, score, False, "")


# we don't check for forbidden/spam words in Backlinks anymore
# instead we grab last 50 (use firstSeenLink:desc) and check isSpam for them

# class ForbiddenWordsBacklinksRule(SeoRule):
#     """Checks for forbidden words in backlink anchor texts"""

#     def __init__(self):
#         super().__init__(
#             name="Forbidden Words in Backlinks",
#             weight=1,
#             area="safety",
#             deal_breaker=True
#         )
#         self.max_count = 50

#     def eval(self, eval_context: EvalContext) -> RuleEvaluation:
#         res = get_anchors_forbidden_words(eval_context.target_id, eval_context.domain,
#                                           db.LinkDirection.IN, ForbiddenWordCategory.FORBIDDEN)

#         violation_count = len(res)
#         score = max(0.0, 1 - violation_count / self.max_count)
#         return RuleEvaluation(eval_context.domain, self.__class__.__name__, score,
#                               True if violation_count >= self.max_count else False, "")


class SpamWordsAnchorsRule(SeoRule):
    """Checks for spam words in anchor texts"""

    def __init__(self, weight: float = 1.0, spam_threshold: float = 0.1):
        super().__init__(
            name="Spam Words in Anchors",
            weight=weight,
            area="safety",
            deal_breaker=True
        )
        self.max_count = 50

    def eval(self, eval_context: EvalContext) -> RuleEvaluation:
        res = get_anchors_forbidden_words(eval_context.target_id, eval_context.domain,
                                          db.LinkDirection.OUT, ForbiddenWordCategory.SPAM)

        violation_count = len(res)
        score = max(0.0, 1 - violation_count / self.max_count)
        return RuleEvaluation(eval_context.domain, self.__class__.__name__, score,
                              True if violation_count >= self.max_count else False, "")


class ForbiddenWordsAnchorRule(SeoRule):
    """Checks for forbidden words specifically in anchor texts"""

    def __init__(self, weight: float = 1.0, spam_threshold: float = 0.1):
        super().__init__(
            name="Spam Words in Anchors",
            weight=weight,
            area="safety",
            deal_breaker=True
        )
        self.max_count = 50

    def eval(self, eval_context: EvalContext) -> RuleEvaluation:
        res = get_anchors_forbidden_words(eval_context.target_id, eval_context.domain,
                                          db.LinkDirection.OUT, ForbiddenWordCategory.FORBIDDEN)

        violation_count = len(res)
        score = max(0.0, 1 - violation_count / self.max_count)
        return RuleEvaluation(eval_context.domain, self.__class__.__name__, score,
                              True if violation_count >= self.max_count else False, "")


class ForbiddenWordsOrganicKeywordsRule(SeoRule):
    """Checks for forbidden words in organic keywords"""

    def __init__(self, weight: float = 1.0, forbidden_words: list = None):
        super().__init__(
            name="Forbidden Words in Organic Keywords",
            weight=weight,
            area="safety",
            deal_breaker=True
        )

    def eval(self, eval_context: EvalContext) -> RuleEvaluation:
        # keyword, keyword_country, is_best_position_set_top_3, is_best_position_set_top_4_10, is_best_position_set_top_11_50, best_position_url
        forbidden_organic_keywords = get_organic_keywords_forbidden_words(eval_context.target_id, eval_context.domain,
                                                                          ForbiddenWordCategory.FORBIDDEN)

        critical_violation = any(bool(w["is_best_position_set_top_3"]) for w in forbidden_organic_keywords)
        if critical_violation:
            return RuleEvaluation(eval_context.domain, self.__class__.__name__, 0, True, "")

        top10_violation_count = sum(bool(w["is_best_position_set_top_4_10"]) for w in forbidden_organic_keywords)
        top50_violation_count = sum(bool(w["is_best_position_set_top_11_50"]) for w in forbidden_organic_keywords)

        score = max(0.0, 1 - top10_violation_count / 10.0 + top50_violation_count / 40.0)

        return RuleEvaluation(eval_context.domain, self.__class__.__name__, score, critical_violation, "")


class SpamWordsOrganicKeywordsRule(SeoRule):
    """Checks for forbidden words in organic keywords"""

    def __init__(self, weight: float = 1.0, forbidden_words: list = None):
        super().__init__(
            name="Forbidden Words in Organic Keywords",
            weight=weight,
            area="safety",
            deal_breaker=True
        )

    def eval(self, eval_context: EvalContext) -> RuleEvaluation:
        # keyword, keyword_country, is_best_position_set_top_3, is_best_position_set_top_4_10, is_best_position_set_top_11_50, best_position_url
        forbidden_organic_keywords = get_organic_keywords_forbidden_words(eval_context.target_id, eval_context.domain,
                                                                          ForbiddenWordCategory.SPAM)

        critical_violation = any(bool(w["is_best_position_set_top_3"]) for w in forbidden_organic_keywords)
        if critical_violation:
            return RuleEvaluation(eval_context.domain, self.__class__.__name__, 0, True, "")

        top10_violation_count = sum(bool(w["is_best_position_set_top_4_10"]) for w in forbidden_organic_keywords)
        top50_violation_count = sum(bool(w["is_best_position_set_top_11_50"]) for w in forbidden_organic_keywords)

        score = max(0.0, 1 - top10_violation_count / 10.0 + top50_violation_count / 40.0)

        return RuleEvaluation(eval_context.domain, self.__class__.__name__, score, critical_violation, "")


class DomainCategoryRule(SeoRule):

    model = SentenceTransformer("all-MiniLM-L6-v2")

    def __init__(self, tgt_category: str, weight: float = 1.0):
        super().__init__(
            name="Domain categories",
            weight=weight,
            area="safety",
            deal_breaker=True
        )
        self.tgt_category = tgt_category

    def domain_similarity(self,
            categories_a: list[str],
            categories_b: list[str],
    ) -> float:
        embeddings_a = self.model.encode(categories_a)
        embeddings_b = self.model.encode(categories_b)

        embeddings_a /= np.linalg.norm(embeddings_a, axis=1, keepdims=True)
        embeddings_b /= np.linalg.norm(embeddings_b, axis=1, keepdims=True)

        similarities = embeddings_a @ embeddings_b.T

        return float(np.average(similarities))

    def eval(self, eval_context: EvalContext) -> RuleEvaluation:
        tgt_categories = ["Technology"]
        categories = [c.full_category() for c in get_domain_categories(eval_context.target_id, eval_context.domain)]
        print(f"domain {eval_context.domain}, category {categories}")

        return RuleEvaluation(eval_context.domain, self.__class__.__name__,
                              self.domain_similarity(tgt_categories, categories), False, "")