from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    query: str
    jurisdiction: str = Field(..., description="'India' or 'International'")
    language: str = Field(default="en", description="'en', 'te', 'hi', 'ta', 'ml', or 'sa'")
    # Optional pre-confirmed classification (from the clarification step)
    confirmed_category: Optional[str] = None


class ClassificationResult(BaseModel):
    category: str
    confidence: float
    reason: str
    needs_clarification: bool = False
    clarification_question: Optional[str] = None


class SourceRef(BaseModel):
    id: str
    title: str
    section: str
    authority: str
    jurisdiction: str
    domain: str
    source_type: str
    version_date: str
    retrieved_date: str
    source_url: str
    precision: str
    relevance_score: float


class AbsChecklist(BaseModel):
    biological_resource_involved: bool
    provenance_identified: bool
    abs_framework_identified: bool
    supporting_source_retrieved: bool
    note: str = "Potentially relevant — verify applicability with the competent authority."


class TkdlResemblance(BaseModel):
    score: float
    risk_band: str
    risk_label: str
    matched_terms: List[str]
    matched_tk_sources: List[str]
    breakdown: Dict[str, float]


class ChecklistItem(BaseModel):
    id: str
    title: str
    description: str
    status: str
    required: bool
    authority: str


class RegulatoryChecklist(BaseModel):
    items: List[ChecklistItem]
    total_items: int
    completed_items: int
    progress_percentage: float
    jurisdiction: str
    category: str


class AnalyzeResponse(BaseModel):
    classification: ClassificationResult
    jurisdiction: str
    applicable_areas: List[str]
    answer: str
    confidence: float
    confidence_label: str
    confidence_breakdown: dict
    sources: List[SourceRef]
    abs_checklist: Optional[AbsChecklist] = None
    tk_pointer: Optional[str] = None
    abstained: bool
    disclaimer: str = "Information, not legal advice."
    answer_language: str = "en"
    translation_available: bool = True
    input_language: str = "en"
    retrieval_query: Optional[str] = None
    llm_paraphrased: bool = False
    graph: Optional[dict] = None
    tkdl_resemblance: Optional[TkdlResemblance] = None
    regulatory_checklist: Optional[RegulatoryChecklist] = None


class ConnectorGrantRequest(BaseModel):
    source_id: str
    email: Optional[str] = "user@ayush.gov.in"
    token: Optional[str] = "demo_token_123"


class ConnectorRevokeRequest(BaseModel):
    source_id: str


class PdfExportRequest(BaseModel):
    analysis_data: Dict[str, Any]


class EscalateRequest(BaseModel):
    query: str
    product_category: Optional[str] = None
    jurisdiction: Optional[str] = None
    relevant_ip_area: Optional[List[str]] = None
    retrieved_sources: Optional[List[str]] = None
    contact_email: Optional[str] = None


class FeedbackRequest(BaseModel):
    query: str
    answer_id: Optional[str] = None
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None
