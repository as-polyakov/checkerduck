"""
API routes for SEO Domain Checker
"""
import logging
import traceback
from functools import wraps
from typing import List, Callable, Any

from fastapi import APIRouter, HTTPException, status

log = logging.getLogger(__name__)

from checkerduck.db import dao
from checkerduck.api.analysis_service import (
    create_analysis,
    to_analysis_response,
    list_analyses,
)
from checkerduck.api.models import (
    StartAnalysisRequest,
    AnalysisResponse,
    ListAnalysesResponse, AnalysisResultsResponse, DomainAnalysisResult, RuleEvaluationResponse
)
from checkerduck.db.db import LinkDirection
from checkerduck.resources.disallowed_words import ForbiddenWordCategory

router = APIRouter(prefix="/api", tags=["analysis"])


def handle_exceptions(func: Callable) -> Callable:
    """
    Decorator to handle exceptions uniformly across all routes.
    Catches exceptions, logs stacktrace, and returns formatted error response.
    """

    @wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            # Re-raise FastAPI HTTPExceptions as-is
            raise
        except Exception as e:
            # Capture full stacktrace for debugging
            stack = traceback.format_exc()
            error_detail = f"Error: {str(e)}\n\nStacktrace:\n{stack}"

            log.error("exception in %s:\n%s", func.__name__, error_detail)

            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_detail
            )

    return wrapper


@router.post(
    "/startAnalysis",
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new analysis",
    description="Create and start a new domain analysis session"
)
@handle_exceptions
async def start_analysis(request: StartAnalysisRequest):
    analysis = create_analysis(request)
    return analysis


@router.get(
    "/analyses",
    response_model=ListAnalysesResponse,
    summary="List all analyses",
    description="Get a list of all analysis sessions"
)
@handle_exceptions
async def get_analyses():
    analyses = list_analyses()
    return ListAnalysesResponse(analyses=analyses)


@router.get(
    "/analyses-results/{analysis_id}",
    response_model=AnalysisResultsResponse,
    summary="Get analysis by ID",
    description="Get details of a specific analysis session"
)
@handle_exceptions
async def get_analysis_results_by_id(analysis_id: str) -> AnalysisResultsResponse:
    analysis = dao.get_analysis(analysis_id)
    analysis_domains_by_name = {d.domain: d for d in analysis.domains}
    rule_evaluations_per_domain = dao.get_rule_evaluations(analysis_id)
    domain_results: List[DomainAnalysisResult] = []
    for domain, rule_evaluations in rule_evaluations_per_domain.items():
        ld, lr = dao.get_in_out_num_domains(analysis_id, domain)
        domain_analysis_result = DomainAnalysisResult(
            domain=domain, rules_results={r.rule: RuleEvaluationResponse(
                rule=r.rule, score=r.score, critical_violation=bool(r.critical_violation), details=r.details) for r
                in
                rule_evaluations},
            price=analysis_domains_by_name[domain].price_usd,
            dr=dao.get_domain_dr(analysis_id, domain),
            org_traffic=dao.get_domain_traffic_by_country(analysis_id, domain),
            org_traffic_history=dao.get_domain_traffic_by_date(analysis_id, domain),
            geography=dao.get_domain_traffic_by_country(analysis_id, domain),
            ld_lr_ratio=ld / lr if (ld and ld != 0 and lr and lr != 0) else 0,
            top_page_traffic_pct=dao.get_domain_top_page_traffic_pcs(analysis_id, domain),
            backlinks_forbidden_words=len(dao.get_anchors_forbidden_words(analysis_id, domain, LinkDirection.IN,
                                                                          ForbiddenWordCategory.FORBIDDEN)),
            anchors_forbidden_words=len(dao.get_anchors_forbidden_words(analysis_id, domain, LinkDirection.OUT,
                                                                        ForbiddenWordCategory.FORBIDDEN)),
            anchors_spam_words=len(dao.get_anchors_forbidden_words(analysis_id, domain, LinkDirection.OUT,
                                                                   ForbiddenWordCategory.SPAM)),
            organic_keywords_forbidden_words=len(
                dao.get_organic_keywords_forbidden_words(analysis_id, domain, ForbiddenWordCategory.FORBIDDEN)),
            organic_keywords_spam_words=len(
                dao.get_organic_keywords_forbidden_words(analysis_id, domain, ForbiddenWordCategory.SPAM))
        )
        domain_results.append(domain_analysis_result)

    res = AnalysisResultsResponse(analysis=to_analysis_response(analysis), domain_results=domain_results)
    return res
