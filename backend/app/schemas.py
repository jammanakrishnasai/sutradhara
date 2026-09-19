from typing import List, Optional
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
    # Multilingual-pipeline transparency fields (see main.py debug logging).
    # input_language is detected from the query TEXT, independent of the
    # requested output `language` — the two can differ in principle.
    input_language: str = "en"
    retrieval_query: Optional[str] = None
    # True only if the Groq paraphrase layer ran AND passed its
    # citation-preservation check (see app/llm.py). False means the answer
    # is exactly the template-assembled, source-grounded text.
    llm_paraphrased: bool = False


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
