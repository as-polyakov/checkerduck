import traceback
from typing import List

from checkerduck.rules.seo_rule import *


def evaluate_domain(target_id: str, domain: str) -> List[RuleEvaluation]:
    eval_context = EvalContext(target_id, domain)

    try:
        rules = [DomainRatingRule(), OrganicTrafficRule(),
                 HistoricalOrganicTrafficRule(),
                 GeographyRule(),
                 DomainsInOutLinksRatioRule(),
                 SingleTopPageTrafficRule(),
                 ForbiddenWordsBacklinksRule(),
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
        print(f"Failed to evaluate domain {domain}: {e}")
        raise
