from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


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
    age: int = Field(default=0, ge=0, le=130)
    mobility_status: str = Field(default="unknown", min_length=1, max_length=100)
    preexisting_conditions: list[str] = Field(default_factory=list)
    medication_list: list[str] = Field(default_factory=list)
    discharge_date: date | None = None
    prior_falls_count: int = Field(default=0, ge=0)
    cognitive_status: str = Field(default="unknown", min_length=1, max_length=100)
    fall_risk_flag: bool = False
    cardiac_risk_flag: bool = False
    diabetes_flag: bool = False
    dementia_confusion_risk_flag: bool = False
    recent_discharge_flag: bool = False

    @field_validator("preexisting_conditions", "medication_list", mode="before")
    @classmethod
    def _normalize_string_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            parts = [chunk.strip() for chunk in value.replace(";", "|").replace(",", "|").split("|")]
            return [part for part in parts if part]
        return []

    @model_validator(mode="after")
    def _compute_derived_flags(self) -> "MedicalHistory":
        conditions = " ".join(item.lower() for item in self.preexisting_conditions)
        medications = " ".join(item.lower() for item in self.medication_list)
        mobility = self.mobility_status.strip().lower()
        cognitive = self.cognitive_status.strip().lower()

        cardiac_terms = ("cardiac", "heart", "arrhythmia", "hypertension", "stroke", "coronary", "chf")
        diabetes_terms = ("diabetes", "insulin", "metformin", "glucose")
        dementia_terms = ("dementia", "confusion", "alzheimer", "cognitive")

        cardiac_derived = any(term in conditions for term in cardiac_terms) or any(
            term in medications for term in cardiac_terms
        )
        diabetes_derived = any(term in conditions for term in diabetes_terms) or any(
            term in medications for term in diabetes_terms
        )
        dementia_derived = any(term in conditions for term in dementia_terms) or any(
            term in cognitive for term in dementia_terms
        )
        mobility_derived = mobility in {"limited", "wheelchair", "bedridden"} or ("limited" in mobility)
        fall_derived = self.prior_falls_count > 0 or mobility_derived or dementia_derived or self.age >= 75

        recent_discharge_derived = False
        if self.discharge_date is not None:
            days_since_discharge = (date.today() - self.discharge_date).days
            recent_discharge_derived = 0 <= days_since_discharge <= 30

        self.cardiac_risk_flag = bool(self.cardiac_risk_flag or cardiac_derived)
        self.diabetes_flag = bool(self.diabetes_flag or diabetes_derived)
        self.dementia_confusion_risk_flag = bool(
            self.dementia_confusion_risk_flag or dementia_derived
        )
        self.fall_risk_flag = bool(self.fall_risk_flag or fall_derived)
        self.recent_discharge_flag = bool(self.recent_discharge_flag or recent_discharge_derived)
        return self


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
