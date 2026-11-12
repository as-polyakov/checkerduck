import logging
import traceback
from typing import List

from checkerduck.model.models import Analysis
from checkerduck.rules.seo_rule import *

log = logging.getLogger(__name__)


def evaluate_domain(analysis: Analysis, domain: str) -> List[RuleEvaluation]:
    eval_context = EvalContext(analysis.target_id, domain, analysis.rule_configuration)

    try:
        rules = [DomainRatingRule(), OrganicTrafficRule(),
                 HistoricalOrganicTrafficRule(),
                 GeographyRule(),
                 DomainsInOutLinksRatioRule(),
                 SingleTopPageTrafficRule(),
                 # ForbiddenWordsBacklinksRule(),
                 SpamWordsAnchorsRule(),
                 ForbiddenWordsAnchorRule(),
                 ForbiddenWordsOrganicKeywordsRule(),
                 SpamWordsOrganicKeywordsRule()]
        results = [rule.safe_eval(eval_context) for rule in rules]
        avg_score = sum(r.score for r in results) / len(results)
        critical_violation = any(r.critical_violation for r in results)
        return results + [RuleEvaluation(domain, "overall", avg_score, critical_violation, "")]
    except Exception as e:
        traceback.print_exc()
        log.exception("%s: evaluation failed", domain)
        raise
