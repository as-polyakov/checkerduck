"""
Pydantic models for API requests and responses
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from checkerduck.model.models import AnalysisStatus


class DomainInput(BaseModel):
    """Input model for a domain to be analyzed"""
    domain: str = Field(..., description="Domain name to analyze")
    price: Optional[str] = Field(None, description="Optional price information")
    notes: Optional[str] = Field(None, description="Optional notes about the domain")


class StartAnalysisRequest(BaseModel):
    """Request model for starting a new analysis"""
    name: str = Field(..., description="Name of the analysis session")
    domains: List[DomainInput] = Field(..., description="List of domains to analyze")



class AnalysisResponse(BaseModel):
    """Response model for analysis information"""
    id: str = Field(..., description="Unique analysis ID")
    name: str = Field(..., description="Name of the analysis session")
    status: AnalysisStatus = Field(..., description="Current status of the analysis")
    created_at: datetime = Field(..., description="Timestamp when analysis was created")
    completed_at: Optional[datetime] = Field(None, description="Timestamp when analysis was completed")
    total_domains: int = Field(..., description="Total number of domains to analyze")
    domains_analyzed: int = Field(0, description="Number of domains already analyzed")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
class RuleEvaluationResponse(BaseModel):
    rule: str
    score: float  # Normalized score (0-1 typically)
    critical_violation: bool  # Whether this evaluation represents a critical violation
    details: str


class DomainAnalysisResult(BaseModel):
    domain: str
    price: int
    rules_results: dict[str, RuleEvaluationResponse]
    dr: int
    org_traffic:dict[str, int]
    org_traffic_history: dict[str, int]
    geography: dict[str, int]
    ld_lr_ratio: float
    top_page_traffic_pct: int
    backlinks_forbidden_words: int
    anchors_forbidden_words: int
    anchors_spam_words: int
    organic_keywords_forbidden_words: int
    organic_keywords_spam_words: int


class AnalysisResultsResponse(BaseModel):
    analysis: AnalysisResponse
    domain_results: List[DomainAnalysisResult]

class ListAnalysesResponse(BaseModel):
    """Response model for list of analyses"""
    analyses: List[AnalysisResponse]


class ErrorResponse(BaseModel):
    """Error response model"""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")

