from app.schemas import (
    DerivedHistoryFlags,
    DerivedMedicalFlags,
    LanguageRoutingResult,
    RawMedicalHistory,
    ResidentProfile,
    SpeechResult,
    UrgencyClass,
)
from app.services.fusion_engine import FusionEngineService
from app.services.medical_flag_service import MedicalFlagService
from app.services.speech_pipeline import resolve_dialect_label


def test_non_urgent_low_confidence_is_promoted_to_uncertain() -> None:
    service = FusionEngineService()
    speech = SpeechResult(
        detected_language="English",
        detected_dialect="Singapore English",
        dialect_confidence=0.56,
        dialect_label="English (general)",
        transcript_original="[English] Need help.",
        transcript_english="Need help.",
        speech_confidence=0.56,
        evidence=[],
    )
    routing = LanguageRoutingResult(
        primary_language="English",
        dialect_label="English (general)",
        routing_hint="Standard English operator queue",
        confidence=0.56,
        fallback_used=True,
        evidence=[],
    )
    medical_flags = DerivedMedicalFlags(
        high_fall_risk=False,
        cardio_risk=False,
        respiratory_risk=False,
        cognitive_risk=False,
        polypharmacy_risk=False,
        evidence=[],
    )
    history_flags = DerivedHistoryFlags(
        frequent_caller=False,
        recent_urgent_pattern=False,
        repeated_false_alarms=False,
        escalation_trend=False,
        evidence=[],
    )

    triage = service.evaluate(
        speech=speech,
        routing=routing,
        medical_flags=medical_flags,
        history_flags=history_flags,
    )

    assert triage.overall_confidence < 0.6
    assert triage.urgency_class == UrgencyClass.UNCERTAIN
    assert triage.stage_evidence["guardrail_triggered"] is True


def test_emergency_min_action_policy_escalates_to_ambulance() -> None:
    service = FusionEngineService()
    speech = SpeechResult(
        detected_language="English",
        detected_dialect="Singapore English",
        dialect_confidence=0.9,
        dialect_label="Singapore English",
        transcript_original="[English] I have chest pain and cannot breathe well.",
        transcript_english="I have chest pain and cannot breathe well.",
        speech_confidence=0.82,
        evidence=[],
    )
    routing = LanguageRoutingResult(
        primary_language="English",
        dialect_label="Singapore English",
        routing_hint="English queue",
        confidence=0.9,
        fallback_used=False,
        evidence=[],
    )
    medical_flags = DerivedMedicalFlags(
        high_fall_risk=False,
        cardio_risk=False,
        respiratory_risk=False,
        cognitive_risk=False,
        polypharmacy_risk=False,
        evidence=[],
    )
    history_flags = DerivedHistoryFlags(
        frequent_caller=False,
        recent_urgent_pattern=False,
        repeated_false_alarms=False,
        escalation_trend=False,
        evidence=[],
    )

    triage = service.evaluate(
        speech=speech,
        routing=routing,
        medical_flags=medical_flags,
        history_flags=history_flags,
    )

    assert triage.recommended_action.value == "ambulance_dispatch"
    assert triage.urgency_class == UrgencyClass.URGENT
    assert triage.stage_evidence["emergency_min_override_triggered"] is True


def test_dialect_label_fallback_threshold() -> None:
    low_label, low_fallback = resolve_dialect_label(
        language="Chinese",
        exact_dialect="Hokkien",
        dialect_confidence=0.74,
    )
    high_label, high_fallback = resolve_dialect_label(
        language="Chinese",
        exact_dialect="Hokkien",
        dialect_confidence=0.75,
    )

    assert low_label == "Chinese (Southern dialect group)"
    assert low_fallback is True
    assert high_label == "Hokkien"
    assert high_fallback is False


def test_medical_flag_derivation() -> None:
    service = MedicalFlagService()
    history = RawMedicalHistory(
        profile_id="p100",
        diagnoses=["atrial_fibrillation", "osteoporosis", "copd"],
        allergies=["none"],
        medications=["a", "b", "c", "d"],
        last_discharge_date="2025-10-10",
        notes="Recent fall episode while walking.",
    )
    resident = ResidentProfile(
        profile_id="p100",
        name="Test Resident",
        age=80,
        postal_code="000001",
        block="Blk 0",
        unit="#00-001",
        preferred_language="English",
        preferred_dialect="Singapore English",
        emergency_contact="90000000",
        mobility_status="walker",
    )

    flags = service.derive_flags(medical_history=history, resident_profile=resident)

    assert flags.high_fall_risk is True
    assert flags.cardio_risk is True
    assert flags.respiratory_risk is True
    assert flags.polypharmacy_risk is True
