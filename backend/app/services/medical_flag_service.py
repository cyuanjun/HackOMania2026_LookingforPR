from __future__ import annotations

from app.schemas import DerivedMedicalFlags, RawMedicalHistory, ResidentProfile


class MedicalFlagService:
    def derive_flags(self, *, medical_history: RawMedicalHistory, resident_profile: ResidentProfile) -> DerivedMedicalFlags:
        diagnoses = {item.lower() for item in medical_history.diagnoses}
        notes = (medical_history.notes or "").lower()
        mobility = resident_profile.mobility_status.lower()

        high_fall_risk = (
            "osteoporosis" in diagnoses
            or "neuropathy" in diagnoses
            or "fall" in notes
            or mobility in {"walker", "wheelchair"}
        )
        cardio_risk = bool({"hypertension", "atrial_fibrillation", "heart_failure"} & diagnoses)
        respiratory_risk = bool({"asthma", "copd"} & diagnoses)
        cognitive_risk = bool({"dementia", "alzheimer"} & diagnoses)
        polypharmacy_risk = len(medical_history.medications) >= 4

        evidence: list[str] = []
        if high_fall_risk:
            evidence.append("fall risk factors present in diagnosis, notes, or mobility profile")
        if cardio_risk:
            evidence.append("cardiovascular condition found in diagnosis history")
        if respiratory_risk:
            evidence.append("respiratory condition found in diagnosis history")
        if cognitive_risk:
            evidence.append("cognitive condition found in diagnosis history")
        if polypharmacy_risk:
            evidence.append("polypharmacy threshold reached (4+ medications)")

        return DerivedMedicalFlags(
            high_fall_risk=high_fall_risk,
            cardio_risk=cardio_risk,
            respiratory_risk=respiratory_risk,
            cognitive_risk=cognitive_risk,
            polypharmacy_risk=polypharmacy_risk,
            evidence=evidence,
        )

