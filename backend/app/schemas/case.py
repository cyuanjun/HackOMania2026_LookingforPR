from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


CaseStatus = Literal["unprocessed", "processed", "operator_processed"]
OperatorAction = Literal[
    "operator_callback",
    "community_response",
    "ambulance_dispatch",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IntakeArtifactInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    file_type: str = Field(min_length=1, max_length=50)
    notes: str | None = Field(default=None, max_length=500)


class IntakeArtifact(BaseModel):
    name: str
    file_type: str
    notes: str | None = None
    uploaded_at: datetime = Field(default_factory=utc_now)


class AudioModuleInput(BaseModel):
    speech_cues: list[str] = Field(default_factory=list)
    non_speech_cues: list[str] = Field(default_factory=list)
    speech_distress_score: float | None = Field(default=None, ge=0, le=1)
    non_speech_distress_score: float | None = Field(default=None, ge=0, le=1)
    estimated_emergency_type: str | None = Field(default=None, max_length=100)


class ScoreFactor(BaseModel):
    key: str
    evidence: str
    direction: Literal["risk_up", "risk_down"]
    weight: float
    source_module: str


class ScoreResult(BaseModel):
    score: float
    recommended_priority: Literal[1, 2, 3]
    recommended_action: OperatorAction
    confidence: float
    factors: list[ScoreFactor]


class CaseRecord(BaseModel):
    case_id: str = Field(default_factory=lambda: str(uuid4()))
    profile_id: str
    status: CaseStatus = "unprocessed"
    emergency_type: str | None = Field(default=None, max_length=100)
    distress_level: Literal["high", "medium", "low"] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    false_alarm_probability: float | None = Field(default=None, ge=0, le=1)
    recommended_action: str | None = Field(default=None, max_length=100)
    operator_action: OperatorAction | None = None
    actual_severity: Literal["high", "medium", "low"] | None = None
    actual_action: OperatorAction | None = None
    actual_false_alarm: bool | None = None
    actual_emergency_type: str | None = Field(default=None, max_length=100)
    outcome_notes: str | None = Field(default=None, max_length=500)
    outcome_recorded_at: datetime | None = None
    top_contributing_reasons: list[str] = Field(default_factory=list)
    audio_module: AudioModuleInput | None = None
    intake_artifacts: list[IntakeArtifact] = Field(default_factory=list)
    score_result: ScoreResult | None = None
    created_at: datetime = Field(default_factory=utc_now)
    last_updated_at: datetime = Field(default_factory=utc_now)


class CaseOutcomeRequest(BaseModel):
    actual_severity: Literal["high", "medium", "low"]
    actual_action: OperatorAction | None = None
    actual_false_alarm: bool | None = None
    actual_emergency_type: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=500)


class TrainingRecord(BaseModel):
    case_id: str
    profile_id: str
    unit_patient_information: UnitPatientInformation
    medical_history: MedicalHistory
    historical_call_history: HistoricalCallHistory
    audio_module: AudioModuleInput | None = None
    predicted_emergency_type: str | None = Field(default=None, max_length=100)
    predicted_severity: Literal["high", "medium", "low"] | None = None
    predicted_action: OperatorAction | None = None
    predicted_confidence: float | None = Field(default=None, ge=0, le=1)
    predicted_false_alarm_probability: float | None = Field(default=None, ge=0, le=1)
    predicted_top_contributing_reasons: list[str] = Field(default_factory=list)
    predicted_at: datetime = Field(default_factory=utc_now)
    actual_severity: Literal["high", "medium", "low"] | None = None
    actual_action: OperatorAction | None = None
    actual_false_alarm: bool | None = None
    actual_emergency_type: str | None = Field(default=None, max_length=100)
    outcome_notes: str | None = Field(default=None, max_length=500)
    outcome_recorded_at: datetime | None = None


class UnitPatientInformation(BaseModel):
    unit_block: str | None = Field(default=None, max_length=100)
    resident_name: str | None = Field(default=None, max_length=100)
    age: int = Field(ge=0, le=130)
    living_alone_flag: bool
    mobility_status: str = Field(min_length=1, max_length=100)
    caregiver_available: bool


class MedicalHistory(BaseModel):
    cardiac_risk_flag: bool
    fall_risk_flag: bool
    diabetes_flag: bool
    dementia_risk_flag: bool
    recent_discharge_flag: bool


class HistoricalCallHistory(BaseModel):
    calls_last_7d: int = Field(ge=0)
    calls_last_30d: int = Field(ge=0)
    false_alarm_rate: float = Field(ge=0, le=1)
    last_call_timestamp: datetime = Field(
        description="Timestamp of the most recent call in ISO-8601 format."
    )
    average_call_duration: float = Field(ge=0, description="Average call duration in seconds.")


class ProfileRecord(BaseModel):
    profile_id: str
    unit_patient_information: UnitPatientInformation
    medical_history: MedicalHistory
    historical_call_history: HistoricalCallHistory


class CustomProfileInput(BaseModel):
    profile_id: str | None = Field(default=None, min_length=1, max_length=100)
    unit_patient_information: UnitPatientInformation
    medical_history: MedicalHistory
    historical_call_history: HistoricalCallHistory


class CaseIntakeRequest(BaseModel):
    profile_id: str | None = Field(default=None, min_length=1, max_length=100)
    custom_profile: CustomProfileInput | None = None
    audio_module: AudioModuleInput | None = None
    intake_artifacts: list[IntakeArtifactInput] = Field(default_factory=list, min_length=1)


class OperatorActionRequest(BaseModel):
    action: OperatorAction


class ApiResponse(BaseModel):
    data: dict
