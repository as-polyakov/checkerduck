import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
from scipy import signal
from scipy.stats import linregress

from checkerduck.db import store
from checkerduck.db.store import get_domain_dr, get_domain_traffic_by_country, get_domain_traffic_by_date, \
    get_in_out_num_domains, \
    get_top_pages_traffic, get_anchors_forbidden_words, get_organic_keywords_forbidden_words, get_domain_categories
from checkerduck.db import db
from checkerduck.model.models import RuleEvaluation
from checkerduck.resources.disallowed_words import ForbiddenWordCategory
from checkerduck.rules.rule_configuration import RuleConfiguration
from sentence_transformers import SentenceTransformer

log = logging.getLogger(__name__)


@dataclass
class EvalContext:
    """One domain evaluation. `config` is the analysis snapshot, not a rule-local copy."""
    target_id: str
    domain: str
    config: RuleConfiguration


class SeoRule(ABC):
    """Base class for all SEO rules"""

    def __init__(
            self,
            name: str,
            weight: float,
            deal_breaker: bool = False
    ):
        self.name = name
        self.weight = weight
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
            deal_breaker=False
        )

    def eval(self, eval_context: EvalContext) -> RuleEvaluation:
        dr = get_domain_dr(eval_context.domain)
        score = min(dr / 100.0, 1.0)
        critical_violation = dr < eval_context.config.domain_rating.min_threshold
        return RuleEvaluation(eval_context.domain, self.__class__.__name__,
                              score, critical_violation, "")


class OrganicTrafficRule(SeoRule):
    """Evaluates current organic traffic levels"""

    def __init__(self):
        super().__init__(
            name="Organic Traffic",
            weight=1.0,
            deal_breaker=False
        )

    def eval(self, eval_context: EvalContext) -> RuleEvaluation:
        traffic = eval_context.config.organic_traffic
        traffic_by_country = get_domain_traffic_by_country(eval_context.domain)
        total = sum(traffic_by_country.values())

        if len(traffic_by_country) == 0 or total < traffic.min_traffic:
            return RuleEvaluation(eval_context.domain, self.__class__.__name__, 0, True, "")
        score = min(total / traffic.max_traffic, 1.0)
        return RuleEvaluation(eval_context.domain, self.__class__.__name__, score, False, "")


class HistoricalOrganicTrafficRule(SeoRule):
    """Evaluates historical organic traffic trends"""

    def __init__(self, weight: float = 0.8):
        super().__init__(
            name="Historical Organic Traffic",
            weight=weight,
            deal_breaker=False
        )

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
        traffic_by_date = get_domain_traffic_by_date(eval_context.domain)
        # Sort by date to get time order
        dates = sorted(traffic_by_date.keys())
        traffic = np.array([traffic_by_date[d] for d in dates], dtype=float)

        # --- Spike detection ---
        has_spikes = self.has_traffic_spike(traffic_by_date)

        # --- Steady decline detection ---
        x = np.arange(len(traffic))
        slope, intercept, r_value, p_value, std_err = linregress(x, traffic)
        decline_r2 = eval_context.config.historical_organic_traffic.decline_r2
        steady_decline = (slope < 0) and (r_value ** 2 > decline_r2)
        score = 1 if not steady_decline else 0.5 if not has_spikes else 0
        return RuleEvaluation(eval_context.domain, self.__class__.__name__, score, False, "")


class GeographyRule(SeoRule):
    """Evaluates geographic relevance of traffic"""

    def __init__(self):
        super().__init__(
            name="Geography",
            weight=1,
            deal_breaker=False
        )


    def eval(self, eval_context: EvalContext) -> RuleEvaluation:
        geography = eval_context.config.geography
        top_countries = store.get_domain_top_traffic_geographies(
            eval_context.domain, geography.top_n_countries)
        matches = geography.target_country in top_countries
        score = 1 if matches else 0
        critical_violation = not matches
        return RuleEvaluation(eval_context.domain, self.__class__.__name__, score, critical_violation, "Country during rule evalution {country}")


class DomainsInOutLinksRatioRule(SeoRule):
    """Evaluates ratio of inbound to outbound links"""

    def __init__(self):
        super().__init__(
            name="Domains In/Out Links Ratio",
            weight=0.5,
            deal_breaker=False
        )

    def eval(self, eval_context: EvalContext) -> RuleEvaluation:
        in_num, out_num = get_in_out_num_domains(eval_context.domain)
        if not out_num or not out_num:
            return RuleEvaluation(eval_context.domain, self.__class__.__name__, 0, False, "")

        ratio = float(in_num if in_num else 0) / float(out_num)
        critical_violation = ratio > eval_context.config.in_out_links_ratio.max_ratio

        return RuleEvaluation(eval_context.domain, self.__class__.__name__, min(ratio, 1), critical_violation, "")


class SingleTopPageTrafficRule(SeoRule):
    """Evaluates if traffic is too concentrated on single page"""

    def __init__(self):
        super().__init__(
            name="Single Top Page Traffic",
            weight=1,
            deal_breaker=False
        )

    def eval(self, eval_context: EvalContext) -> RuleEvaluation:
        top_pages = get_top_pages_traffic(eval_context.domain)

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
#             deal_breaker=True
#         )
#         self.max_count = 50

#     def eval(self, eval_context: EvalContext) -> RuleEvaluation:
#         res = get_anchors_forbidden_words(eval_context.domain,
#                                           db.LinkDirection.IN, ForbiddenWordCategory.FORBIDDEN)

#         violation_count = len(res)
#         score = max(0.0, 1 - violation_count / self.max_count)
#         return RuleEvaluation(eval_context.domain, self.__class__.__name__, score,
#                               True if violation_count >= self.max_count else False, "")


class SpamWordsAnchorsRule(SeoRule):
    """Checks for spam words in anchor texts"""

    def __init__(self, weight: float = 1.0):
        super().__init__(
            name="Spam Words in Anchors",
            weight=weight,
            deal_breaker=True
        )

    def eval(self, eval_context: EvalContext) -> RuleEvaluation:
        max_count = eval_context.config.spam_words_anchors.max_count
        res = get_anchors_forbidden_words(eval_context.domain,
                                          db.LinkDirection.OUT, ForbiddenWordCategory.SPAM)

        violation_count = len(res)
        score = max(0.0, 1 - violation_count / max_count)
        return RuleEvaluation(eval_context.domain, self.__class__.__name__, score,
                              True if violation_count >= max_count else False, "")


class ForbiddenWordsAnchorRule(SeoRule):
    """Checks for forbidden words specifically in anchor texts"""

    def __init__(self, weight: float = 1.0):
        super().__init__(
            name="Spam Words in Anchors",
            weight=weight,
            deal_breaker=True
        )

    def eval(self, eval_context: EvalContext) -> RuleEvaluation:
        max_count = eval_context.config.forbidden_words_anchors.max_count
        res = get_anchors_forbidden_words(eval_context.domain,
                                          db.LinkDirection.OUT, ForbiddenWordCategory.FORBIDDEN)

        violation_count = len(res)
        score = max(0.0, 1 - violation_count / max_count)
        return RuleEvaluation(eval_context.domain, self.__class__.__name__, score,
                              True if violation_count >= max_count else False, "")


class ForbiddenWordsOrganicKeywordsRule(SeoRule):
    """Checks for forbidden words in organic keywords"""

    def __init__(self, weight: float = 1.0):
        super().__init__(
            name="Forbidden Words in Organic Keywords",
            weight=weight,
            deal_breaker=True
        )

    def eval(self, eval_context: EvalContext) -> RuleEvaluation:
        # keyword, keyword_country, is_best_position_set_top_3, is_best_position_set_top_4_10, is_best_position_set_top_11_50, best_position_url
        penalties = eval_context.config.forbidden_words_organic_keywords
        forbidden_organic_keywords = get_organic_keywords_forbidden_words(eval_context.domain,
                                                                          ForbiddenWordCategory.FORBIDDEN)

        critical_violation = any(bool(w["is_best_position_set_top_3"]) for w in forbidden_organic_keywords)
        if critical_violation:
            return RuleEvaluation(eval_context.domain, self.__class__.__name__, 0, True, "")

        top10_violation_count = sum(bool(w["is_best_position_set_top_4_10"]) for w in forbidden_organic_keywords)
        top50_violation_count = sum(bool(w["is_best_position_set_top_11_50"]) for w in forbidden_organic_keywords)

        score = max(0.0, 1 - top10_violation_count / penalties.top10_divisor
                    + top50_violation_count / penalties.top50_divisor)

        return RuleEvaluation(eval_context.domain, self.__class__.__name__, score, critical_violation, "")


class SpamWordsOrganicKeywordsRule(SeoRule):
    """Checks for forbidden words in organic keywords"""

    def __init__(self, weight: float = 1.0):
        super().__init__(
            name="Forbidden Words in Organic Keywords",
            weight=weight,
            deal_breaker=True
        )

    def eval(self, eval_context: EvalContext) -> RuleEvaluation:
        # keyword, keyword_country, is_best_position_set_top_3, is_best_position_set_top_4_10, is_best_position_set_top_11_50, best_position_url
        penalties = eval_context.config.spam_words_organic_keywords
        forbidden_organic_keywords = get_organic_keywords_forbidden_words(eval_context.domain,
                                                                          ForbiddenWordCategory.SPAM)

        critical_violation = any(bool(w["is_best_position_set_top_3"]) for w in forbidden_organic_keywords)
        if critical_violation:
            return RuleEvaluation(eval_context.domain, self.__class__.__name__, 0, True, "")

        top10_violation_count = sum(bool(w["is_best_position_set_top_4_10"]) for w in forbidden_organic_keywords)
        top50_violation_count = sum(bool(w["is_best_position_set_top_11_50"]) for w in forbidden_organic_keywords)

        score = max(0.0, 1 - top10_violation_count / penalties.top10_divisor
                    + top50_violation_count / penalties.top50_divisor)

        return RuleEvaluation(eval_context.domain, self.__class__.__name__, score, critical_violation, "")


class DomainCategoryRule(SeoRule):

    model = SentenceTransformer("all-MiniLM-L6-v2")

    def __init__(self, weight: float = 1.0):
        super().__init__(
            name="Domain categories",
            weight=weight,
            deal_breaker=True
        )

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
        tgt_categories = list(eval_context.config.domain_category.target_categories)
        categories = [c.full_category() for c in get_domain_categories(eval_context.domain)]
        print(f"domain {eval_context.domain}, category {categories}")

        return RuleEvaluation(eval_context.domain, self.__class__.__name__,
                              self.domain_similarity(tgt_categories, categories), False, "")