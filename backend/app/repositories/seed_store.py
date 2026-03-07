import csv
from datetime import datetime, timezone
from pathlib import Path
import re

from app.core.config import (
    CALL_HISTORY_SEED_PATH,
    MEDICAL_HISTORY_SEED_PATH,
    UNIT_INFORMATION_SEED_PATH,
)
from app.schemas.case import (
    CaseIntakeRequest,
    CaseRecord,
    IntakeArtifact,
    OperatorAction,
    ProfileRecord,
)
from app.services.triage import evaluate_case


class SeedStore:
    def __init__(
        self,
        unit_information_seed_path: Path = UNIT_INFORMATION_SEED_PATH,
        medical_history_seed_path: Path = MEDICAL_HISTORY_SEED_PATH,
        call_history_seed_path: Path = CALL_HISTORY_SEED_PATH,
    ) -> None:
        self._unit_information_seed_path = unit_information_seed_path
        self._medical_history_seed_path = medical_history_seed_path
        self._call_history_seed_path = call_history_seed_path
        self._profiles = self._load_profiles()
        self._cases: list[CaseRecord] = []

    def _load_profiles(self) -> dict[str, ProfileRecord]:
        if (
            not self._unit_information_seed_path.exists()
            or not self._medical_history_seed_path.exists()
            or not self._call_history_seed_path.exists()
        ):
            return {}

        unit_rows = self._read_rows_by_profile_id(self._unit_information_seed_path)
        medical_rows = self._read_rows_by_profile_id(self._medical_history_seed_path)
        call_rows = self._read_rows_by_profile_id(self._call_history_seed_path)

        all_ids = set(unit_rows) | set(medical_rows) | set(call_rows)
        complete_ids = set(unit_rows) & set(medical_rows) & set(call_rows)
        if complete_ids != all_ids:
            missing_unit = sorted(all_ids - set(unit_rows))
            missing_medical = sorted(all_ids - set(medical_rows))
            missing_call = sorted(all_ids - set(call_rows))
            raise ValueError(
                "Seed CSV profile_id mismatch. "
                f"Missing in unit_information.csv: {missing_unit}; "
                f"missing in medical_history.csv: {missing_medical}; "
                f"missing in call_history.csv: {missing_call}"
            )

        return {
            profile_id: ProfileRecord(
                **self._map_profile_rows(
                    unit_rows[profile_id],
                    medical_rows[profile_id],
                    call_rows[profile_id],
                )
            )
            for profile_id in sorted(complete_ids)
        }

    @staticmethod
    def _read_rows_by_profile_id(path: Path) -> dict[str, dict[str, str]]:
        with path.open("r", encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))

        return {row["profile_id"]: row for row in rows if row.get("profile_id")}

    @staticmethod
    def _to_bool(raw: str) -> bool:
        normalized = raw.strip().lower()
        return normalized in {"1", "true", "yes", "y"}

    @staticmethod
    def _clean_optional(raw: str | None) -> str | None:
        if raw is None:
            return None

        normalized = raw.strip()
        return normalized or None

    def _map_profile_rows(
        self,
        unit_row: dict[str, str],
        medical_row: dict[str, str],
        call_row: dict[str, str],
    ) -> dict:
        return {
            "profile_id": unit_row["profile_id"],
            "unit_patient_information": {
                "unit_block": self._clean_optional(unit_row.get("unit_block")),
                "resident_name": self._clean_optional(unit_row.get("resident_name")),
                "age": int(unit_row["age"]),
                "living_alone_flag": self._to_bool(unit_row["living_alone_flag"]),
                "mobility_status": unit_row["mobility_status"],
                "caregiver_available": self._to_bool(unit_row["caregiver_available"]),
            },
            "medical_history": {
                "cardiac_risk_flag": self._to_bool(medical_row["cardiac_risk_flag"]),
                "fall_risk_flag": self._to_bool(medical_row["fall_risk_flag"]),
                "diabetes_flag": self._to_bool(medical_row["diabetes_flag"]),
                "dementia_risk_flag": self._to_bool(medical_row["dementia_risk_flag"]),
                "recent_discharge_flag": self._to_bool(medical_row["recent_discharge_flag"]),
            },
            "historical_call_history": {
                "calls_last_7d": int(call_row["calls_last_7d"]),
                "calls_last_30d": int(call_row["calls_last_30d"]),
                "false_alarm_rate": float(call_row["false_alarm_rate"]),
                "time_since_last_call": int(call_row["time_since_last_call"]),
                "average_call_duration": float(call_row["average_call_duration"]),
            },
        }

    def list_profiles(self) -> list[ProfileRecord]:
        return list(self._profiles.values())

    def get_profile(self, profile_id: str) -> ProfileRecord | None:
        return self._profiles.get(profile_id)

    def add_profile(self, profile: ProfileRecord) -> None:
        self._profiles[profile.profile_id] = profile

    def generate_profile_id(self) -> str:
        pattern = re.compile(r"^profile-(\d+)$")
        max_value = 0
        for profile_id in self._profiles:
            match = pattern.match(profile_id)
            if not match:
                continue

            max_value = max(max_value, int(match.group(1)))

        return f"profile-{max_value + 1:03d}"

    def list_cases(self) -> list[CaseRecord]:
        return self._cases

    def create_case_from_intake(self, payload: CaseIntakeRequest, profile_id: str) -> CaseRecord:
        artifacts = [
            IntakeArtifact(
                name=item.name,
                file_type=item.file_type,
                notes=item.notes,
            )
            for item in payload.intake_artifacts
        ]

        case = CaseRecord(
            profile_id=profile_id,
            audio_module=payload.audio_module,
            intake_artifacts=artifacts,
            status="unprocessed",
        )

        self._cases.append(case)
        return case

    def process_case(self, case_id: str) -> CaseRecord | None:
        for case in self._cases:
            if case.case_id != case_id:
                continue

            profile = self.get_profile(case.profile_id)
            if profile is None:
                return None

            triage = evaluate_case(profile, case.audio_module)
            case.confidence = triage["confidence"]
            case.distress_level = triage["distress_level"]
            case.recommended_action = triage["recommended_action"]
            case.top_contributing_reasons = triage["top_contributing_reasons"]
            case.emergency_type = triage["emergency_type"]
            case.score_result = triage["score_result"]
            case.status = "processed"
            case.last_updated_at = datetime.now(timezone.utc)
            return case

        return None

    def mark_case_processed(self, case_id: str) -> CaseRecord | None:
        return self.process_case(case_id)

    def set_operator_action(self, case_id: str, action: OperatorAction) -> CaseRecord | None:
        for case in self._cases:
            if case.case_id != case_id:
                continue

            case.operator_action = action
            case.status = "operator_processed"
            case.last_updated_at = datetime.now(timezone.utc)
            return case

        return None
