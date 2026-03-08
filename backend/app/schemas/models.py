from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CaseState(str, Enum):
    PENDING_AI_ASSESSMENT = "pending_ai_assessment"
    AI_ASSESSED = "ai_assessed"
    OPERATOR_PROCESSED = "operator_processed"


class UrgencyClass(str, Enum):
    NON_URGENT = "non-urgent"
    UNCERTAIN = "uncertain"
    URGENT = "urgent"


class RecommendedAction(str, Enum):
    OPERATOR_CALLBACK = "operator_callback"
    COMMUNITY_RESPONSE = "community_response"
    AMBULANCE_DISPATCH = "ambulance_dispatch"


class AudioMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    content_type: str
    size_bytes: int
    stored_path: str
    uploaded_at: str


class CaseMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    profile_id: str
    state: CaseState
    created_at: str
    updated_at: str


class ResidentProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    name: str
    age: int
    postal_code: str
    block: str
    unit: str
    preferred_language: str
    preferred_dialect: str
    emergency_contact: str
    mobility_status: str
    living_alone: bool = False


class ResidentContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resident_profile: ResidentProfile
    raw_medical_history: RawMedicalHistory | None = None
    raw_call_history: RawCallHistory | None = None


class RawMedicalHistory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    diagnoses: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    last_discharge_date: str | None = None
    notes: str | None = None


class DerivedMedicalFlags(BaseModel):
    model_config = ConfigDict(extra="forbid")

    high_fall_risk: bool
    cardio_risk: bool
    respiratory_risk: bool
    cognitive_risk: bool
    polypharmacy_risk: bool
    evidence: list[str] = Field(default_factory=list)


class RawCallHistory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    total_calls_last_30d: int
    urgent_calls_last_30d: int
    false_alarm_count_last_30d: int
    last_call_outcome: str | None = None
    recent_call_summaries: list[str] = Field(default_factory=list)


class DerivedHistoryFlags(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frequent_caller: bool
    recent_urgent_pattern: bool
    repeated_false_alarms: bool
    escalation_trend: bool
    evidence: list[str] = Field(default_factory=list)

class SpeechResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detected_language: str
    detected_dialect: str
    dialect_confidence: float
    dialect_label: str
    transcript_original: str
    transcript_english: str
    speech_confidence: float
    evidence: list[str] = Field(default_factory=list)


class LanguageRoutingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_language: str
    dialect_label: str
    routing_hint: str
    confidence: float
    fallback_used: bool
    evidence: list[str] = Field(default_factory=list)


class TriageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    urgency_class: UrgencyClass
    recommended_action: RecommendedAction
    reasoning: str
    routing_hint: str
    overall_confidence: float
    stage_evidence: dict[str, Any] = Field(default_factory=dict)


class OperatorDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator_id: str
    chosen_action: RecommendedAction
    notes: str | None = None
    processed_at: str
    overrides_ai: bool


class CaseDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: CaseMetadata
    audio_metadata: AudioMetadata
    resident_profile: ResidentProfile
    raw_medical_history: RawMedicalHistory
    derived_medical_flags: DerivedMedicalFlags | None = None
    raw_call_history: RawCallHistory
    derived_history_flags: DerivedHistoryFlags | None = None
    speech_result: SpeechResult | None = None
    language_routing_result: LanguageRoutingResult | None = None
    triage_result: TriageResult | None = None
    summary_text: str | None = None
    operator_decision: OperatorDecision | None = None


class CaseListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    profile_id: str
    resident_name: str
    postal_code: str
    block: str
    unit: str
    state: CaseState
    created_at: str
    updated_at: str
    urgency_class: UrgencyClass | None = None
    recommended_action: RecommendedAction | None = None
    overall_confidence: float | None = None
    routing_hint: str | None = None
    operator_action: RecommendedAction | None = None


class IntakeCaseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case: CaseDetail


class OperatorDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator_id: str = Field(min_length=1)
    chosen_action: RecommendedAction
    notes: str | None = None
