"""
Service layer for analysis operations
"""
import logging
import threading
import uuid
from datetime import datetime
from typing import List

from checkerduck.api.models import StartAnalysisRequest, AnalysisResponse, AnalysisStatus
from checkerduck.extract.extractor import DataExtractor
from checkerduck.model import Analysis
from checkerduck.model.models import AnalysisDomain
from checkerduck.rules.rule_aggregator import evaluate_domain
from checkerduck.domain.utils import safe_int
from checkerduck.db import dao


log = logging.getLogger(__name__)


def create_analysis(request: StartAnalysisRequest) -> AnalysisResponse:
    analysis_id = str(uuid.uuid4())
    res = Analysis(analysis_id, request.name, AnalysisStatus.PENDING, datetime.now(), None,
                   [AnalysisDomain(d.domain, safe_int(d.price), d.notes) for d in request.domains], 0)
    dao.persist_analysis(res)

    analysis_data = {
        "id": analysis_id,
        "name": request.name,
        "status": AnalysisStatus.PENDING,
        "created_at": res.created_at,
        "completed_at": None,
        "total_domains": len(request.domains),
        "domains": [domain.dict() for domain in request.domains]
    }

    # Start analysis in background thread
    thread = threading.Thread(target=run_analysis, args=(res,))
    thread.daemon = True
    thread.start()

    return AnalysisResponse(**analysis_data)


#  select target_id,
#        name,
#        status,
#        created_at,
#        completed_at,
#        (select count(*) from analysis_domains where target_id = analysis.target_id) as "total_domains"
#         from analysis where target_id = ?
def to_analysis_response(analysis: Analysis) -> AnalysisResponse:
    return AnalysisResponse(id=analysis.target_id, name=analysis.name, status=AnalysisStatus(analysis.status),
                            created_at=analysis.created_at,
                            completed_at=analysis.completed_at,
                            total_domains=len(analysis.domains), domains_analyzed=analysis.processed_domains)


def list_analyses() -> List[AnalysisResponse]:
    return [AnalysisResponse(id=r["target_id"], name=r["name"], status=r["status"],
                             created_at=dao.safe_date_from_str(r["created_at"]),
                             completed_at=dao.safe_date_from_str(r["completed_at"]),
                             total_domains=r["total_domains"], domains_analyzed=r["processed_domains"])
            for r in dao.get_recent_analysis()]


def run_analysis(analysis: Analysis):
    dao.update_analysis_status(analysis.target_id, AnalysisStatus.RUNNING)
    data_extractor = DataExtractor()
    data_extractor.run_extract(analysis)
    eval_results = [evaluate_domain(analysis.target_id, domain.domain)
                    for domain in analysis.domains]

    dao.persist_rule_evaluations(analysis.target_id, eval_results)
    dao.update_analysis_status(analysis.target_id, AnalysisStatus.COMPLETED)
    log.info("analysis %s completed", analysis.target_id)
