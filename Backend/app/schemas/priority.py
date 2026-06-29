"""Priority queue schemas."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class PriorityBucket(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class PriorityEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_id: str
    priority_score: float = Field(ge=0.0, le=1.0)
    bucket: PriorityBucket
    drivers: list[str]


class PriorityQueues(BaseModel):
    model_config = ConfigDict(extra="forbid")

    high: list[PriorityEntry] = []
    medium: list[PriorityEntry] = []
    low: list[PriorityEntry] = []
