from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

DocumentType = Literal["invoice", "credit_note", "supporting_attachment", "unknown"]
class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
class LineItem(StrictModel):
    description: str
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    amount: Decimal = Field(ge=0)
class Fields(StrictModel):
    vendor: str | None = None
    customer: str | None = None
    document_number: str | None = None
    document_date: date | None = None
    currency: Literal["USD", "EUR", "GBP", "INR", "CAD", "AUD"] | None = None
    subtotal: Decimal | None = Field(default=None, ge=0)
    tax: Decimal | None = Field(default=None, ge=0)
    total: Decimal | None = Field(default=None, ge=0)
    line_items: list[LineItem] = Field(default_factory=list)
class EvidenceRequest(StrictModel):
    field_path: str
    page: int = Field(ge=1)
    quote: str = Field(min_length=1)
class Candidate(StrictModel):
    document_type: DocumentType
    extracted_fields: Fields
    evidence: list[EvidenceRequest] = Field(default_factory=list)
class Evidence(EvidenceRequest):
    grounded: bool
    value_supported: bool
    bbox: list[float] | None = None
    coordinates: str | None = None
class Check(StrictModel):
    code: str
    passed: bool
    detail: str
class PageSummary(StrictModel):
    page: int
    route: Literal["native_text", "ocr", "vision_only"]
    character_count: int
    ocr_confidence: float | None = None
class DocumentResult(StrictModel):
    document_id: str
    backend: str
    document_type: DocumentType
    extracted_fields: Fields
    evidence: list[Evidence]
    validation_results: list[Check]
    confidence: float = Field(ge=0, le=1)
    confidence_kind: str = "heuristic_quality_not_probability"
    review_required: bool
    warnings: list[str]
    pages: list[PageSummary]
