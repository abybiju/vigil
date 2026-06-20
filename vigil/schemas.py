"""Pydantic v2 contracts. These are the source of truth for every model output and DB row.

Field *types* are plain `Literal` string-enums so they serialise cleanly to SQLite and to
strict JSON tool schemas. Range checks (confidence in [0,1]) use validators rather than
`ge`/`le`, because `minimum`/`maximum` keywords are not allowed in strict tool-use schemas.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# --- Controlled vocabularies (kept flat + scalar for strict tool use) ---
Source = Literal["email", "chat", "review"]
JourneyStage = Literal[
    "pre_kit", "post_impression", "preview_approved", "in_treatment", "post_treatment", "unknown"
]
IntentCategory = Literal["impression_kit", "payment_refund", "shipping", "clinical", "other"]
ComplaintBasis = Literal["safety", "performance", "durability", "quality", "none"]
Severity = Literal["none", "minor", "moderate", "serious"]
RoutingDecision = Literal["auto_send", "agent_draft", "clinical_review", "vigilance_review"]
Device = Literal["day_aligner", "night_aligner", "retainer", "impression_kit"]
BodySite = Literal["tooth", "gum", "bite", "other"]
EventType = Literal["malfunction", "injury", "death"]

SEVERITY_ORDER: dict[str, int] = {"none": 0, "minor": 1, "moderate": 2, "serious": 3}


def _check_unit_interval(v: float) -> float:
    if not 0.0 <= float(v) <= 1.0:
        raise ValueError("confidence must be between 0.0 and 1.0")
    return float(v)


# --------------------------------------------------------------------------- #
# Inbound message
# --------------------------------------------------------------------------- #
class Message(BaseModel):
    id: str
    source: Source = "email"
    channel: str | None = None
    received_at: datetime | None = None
    customer_ref: str | None = None  # masked / hashed
    order_ref: str | None = None
    journey_stage: JourneyStage = "unknown"
    raw_text: str  # PII already masked before this is stored or sent to a model


# --------------------------------------------------------------------------- #
# Triage (combined steps 1-5) — the structured model output
# --------------------------------------------------------------------------- #
class Extraction(BaseModel):
    device: Device | None = None
    issue_type: str | None = None
    onset: str | None = None
    duration: str | None = None
    alleged_harm: str | None = None
    body_site: BodySite | None = None
    patient_narrative: str = Field(description="Neutral 1-2 sentence summary, no added detail.")
    event_date: date | None = None
    aligner_step: str | None = None
    photo_requested: bool = False


class Confidence(BaseModel):
    complaint: float = 0.0
    mdr: float = 0.0

    _v = field_validator("complaint", "mdr")(_check_unit_interval)


class TriageResult(BaseModel):
    intent: list[IntentCategory] = Field(description="Multi-label intent.")
    is_complaint: bool
    complaint_basis: ComplaintBasis
    severity: Severity
    potential_mdr: bool
    mdr_rationale: str
    extraction: Extraction
    confidence: Confidence


# --------------------------------------------------------------------------- #
# Clinical-safety pass (step 3) — separate, narrow, recall-tuned, authoritative gate
# --------------------------------------------------------------------------- #
class ClinicalSafety(BaseModel):
    clinical_red_flag: bool
    signals: list[str] = Field(default_factory=list)
    confidence: float = 0.0

    _v = field_validator("confidence")(_check_unit_interval)


# --------------------------------------------------------------------------- #
# Router output (pure Python, never the LLM)
# --------------------------------------------------------------------------- #
class RoutingResult(BaseModel):
    routing_decision: RoutingDecision
    reason: str
    clinical_red_flag: bool
    is_complaint: bool
    potential_mdr: bool


# --------------------------------------------------------------------------- #
# Persisted complaint record + MDR draft
# --------------------------------------------------------------------------- #
class ComplaintRecord(BaseModel):
    device: Device | None = None
    issue_type: str | None = None
    onset: str | None = None
    duration: str | None = None
    alleged_harm: str | None = None
    body_site: BodySite | None = None
    patient_narrative: str | None = None
    event_date: date | None = None
    aligner_step: str | None = None
    photo_requested: bool = False


class MdrDraft(BaseModel):
    event_type: EventType
    device_problem: str
    patient_problem: str
    narrative: str
    draft_status: str = "pending_review"


# --------------------------------------------------------------------------- #
# Grounded safe-lane reply
# --------------------------------------------------------------------------- #
class GroundedReply(BaseModel):
    body: str
    source_title: str | None = None
    source_url: str | None = None
    grounded: bool = False


# --------------------------------------------------------------------------- #
# Eval metrics — shared by the report and the Streamlit Eval tab
# --------------------------------------------------------------------------- #
class DetectorMetrics(BaseModel):
    precision: float
    recall: float
    f1: float
    support: int
    confusion: list[list[int]]  # [[tn, fp], [fn, tp]]


class EvalMetrics(BaseModel):
    n: int
    clinical: DetectorMetrics
    complaint: DetectorMetrics
    mdr_recall: float
    mdr_support: int
    clinical_false_negatives: list[dict] = Field(default_factory=list)
    clinical_auto_sent: int = 0  # MUST be 0
    per_bucket: dict[str, dict] = Field(default_factory=dict)
