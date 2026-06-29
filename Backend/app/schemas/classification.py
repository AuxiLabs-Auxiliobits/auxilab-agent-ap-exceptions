"""Classification schemas."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class PrimaryExceptionType(str, Enum):
    PRICE_VARIANCE = "Price Variance"
    QUANTITY_MISMATCH = "Quantity Mismatch"
    MISSING_PO = "Missing PO"
    DUPLICATE = "Duplicate"
    UNAPPROVED_VENDOR = "Unapproved Vendor"
    GRN_NOT_RECEIVED = "GRN Not Received"
    OTHER = "Other"


class Severity(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ClassificationResult(BaseModel):
    """Output of the AI classification node, post severity validation."""

    model_config = ConfigDict(extra="forbid")

    invoice_id: str
    primary_exception_type: PrimaryExceptionType
    root_cause: str = Field(max_length=280)
    severity_ai_suggested: Severity
    severity: Severity
    confidence_score: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(max_length=500)
    model_id: str
    prompt_version: str


class AIClassificationOutput(BaseModel):
    """Raw tool-call schema returned by the model. Used for validation only."""

    model_config = ConfigDict(extra="forbid")

    invoice_id: str
    primary_exception_type: PrimaryExceptionType
    root_cause: str = Field(max_length=280)
    severity: Severity
    confidence_score: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(max_length=500)
