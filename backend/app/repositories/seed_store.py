from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from sqlalchemy import JSON, Boolean, Column, Float, MetaData, String, Table, create_engine, delete, insert, select
from sqlalchemy.engine import Engine, RowMapping

from app.core.config import (
    CALL_HISTORY_SEED_PATH,
    EXPORT_TRAINING_CSV,
    DATABASE_URL,
    MEDICAL_HISTORY_SEED_PATH,
    TRAINING_RECORDS_CSV_PATH,
    UNIT_INFORMATION_SEED_PATH,
)
from app.schemas.case import (
    CaseIntakeRequest,
    CaseOutcomeRequest,
    CaseRecord,
    IntakeArtifact,
    OperatorAction,
    ProfileRecord,
    TrainingRecord,
)
from app.services.triage import evaluate_case


class SeedStore:
    TRAINING_CSV_COLUMNS = [
        "recorded_at",
        "case_id",
        "profile_id",
        "unit_block",
        "resident_name",
        "age",
        "living_alone_flag",
        "mobility_status",
        "caregiver_available",
        "medical_age",
        "medical_mobility_status",
        "preexisting_conditions",
        "medication_list",
        "discharge_date",
        "prior_falls_count",
        "cognitive_status",
        "cardiac_risk_flag",
        "fall_risk_flag",
        "diabetes_flag",
        "dementia_confusion_risk_flag",
        "recent_discharge_flag",
        "calls_last_7d",
        "calls_last_30d",
        "false_alarm_rate",
        "last_call_timestamp",
        "average_call_duration",
        "speech_cues",
        "non_speech_cues",
        "speech_distress_score",
        "non_speech_distress_score",
        "audio_estimated_emergency_type",
        "predicted_emergency_type",
        "predicted_severity",
        "predicted_action",
        "predicted_confidence",
        "predicted_false_alarm_probability",
        "predicted_top_contributing_reasons",
        "actual_severity",
        "actual_action",
        "actual_false_alarm",
        "actual_emergency_type",
        "outcome_notes",
    ]

    def __init__(
        self,
        unit_information_seed_path: Path = UNIT_INFORMATION_SEED_PATH,
        medical_history_seed_path: Path = MEDICAL_HISTORY_SEED_PATH,
        call_history_seed_path: Path = CALL_HISTORY_SEED_PATH,
        training_records_csv_path: Path = TRAINING_RECORDS_CSV_PATH,
        database_url: str = DATABASE_URL,
        export_training_csv: bool = EXPORT_TRAINING_CSV,
    ) -> None:
        self._unit_information_seed_path = unit_information_seed_path
        self._medical_history_seed_path = medical_history_seed_path
        self._call_history_seed_path = call_history_seed_path
        self._training_records_csv_path = training_records_csv_path
        self._export_training_csv = export_training_csv

        self._engine = self._create_engine(database_url)
        self._metadata = MetaData()
        self._profiles_table = Table(
            "profiles",
            self._metadata,
            Column("profile_id", String(100), primary_key=True),
            Column("unit_patient_information", JSON, nullable=False),
            Column("medical_history", JSON, nullable=False),
            Column("historical_call_history", JSON, nullable=False),
            Column("updated_at", String(40), nullable=False),
        )
        self._cases_table = Table(
            "cases",
            self._metadata,
            Column("case_id", String(100), primary_key=True),
            Column("profile_id", String(100), nullable=False),
            Column("status", String(50), nullable=False),
            Column("emergency_type", String(100), nullable=True),
            Column("distress_level", String(20), nullable=True),
            Column("confidence", Float, nullable=True),
            Column("false_alarm_probability", Float, nullable=True),
            Column("recommended_action", String(100), nullable=True),
            Column("operator_action", String(100), nullable=True),
            Column("actual_severity", String(20), nullable=True),
            Column("actual_action", String(100), nullable=True),
            Column("actual_false_alarm", Boolean, nullable=True),
            Column("actual_emergency_type", String(100), nullable=True),
            Column("outcome_notes", String(500), nullable=True),
            Column("outcome_recorded_at", String(40), nullable=True),
            Column("top_contributing_reasons", JSON, nullable=False),
            Column("audio_module", JSON, nullable=True),
            Column("intake_artifacts", JSON, nullable=False),
            Column("score_result", JSON, nullable=True),
            Column("created_at", String(40), nullable=False),
            Column("last_updated_at", String(40), nullable=False),
        )
        self._training_records_table = Table(
            "training_records",
            self._metadata,
            Column("case_id", String(100), primary_key=True),
            Column("predicted_at", String(40), nullable=False),
            Column("record_json", JSON, nullable=False),
            Column("updated_at", String(40), nullable=False),
        )

        self._metadata.create_all(self._engine)
        self._bootstrap_profiles_from_seed()

    @staticmethod
    def _create_engine(database_url: str) -> Engine:
        if database_url.startswith("sqlite"):
            sqlite_path = database_url.replace("sqlite:///", "", 1)
            if sqlite_path:
                Path(sqlite_path).parent.mkdir(parents=True, exist_ok=True)
            return create_engine(
                database_url,
                future=True,
                connect_args={"check_same_thread": False},
            )
        return create_engine(database_url, future=True)

    @staticmethod
    def _to_iso(value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.astimezone(timezone.utc).isoformat()

    def _bootstrap_profiles_from_seed(self) -> None:
        seed_profiles = self._load_profiles_from_seed()
        if not seed_profiles:
            return

        for profile in seed_profiles.values():
            self.add_profile(profile)

    def _load_profiles_from_seed(self) -> dict[str, ProfileRecord]:
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

        profiles: dict[str, ProfileRecord] = {}
        for profile_id in sorted(complete_ids):
            profiles[profile_id] = ProfileRecord(
                **self._map_profile_rows(
                    unit_rows[profile_id],
                    medical_rows[profile_id],
                    call_rows[profile_id],
                )
            )
        return profiles

    @staticmethod
    def _read_rows_by_profile_id(path: Path) -> dict[str, dict[str, str]]:
        with path.open("r", encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))
        return {row["profile_id"]: row for row in rows if row.get("profile_id")}

    @staticmethod
    def _to_bool(raw: str | None) -> bool:
        if raw is None:
            return False
        normalized = raw.strip().lower()
        return normalized in {"1", "true", "yes", "y"}

    @staticmethod
    def _clean_optional(raw: str | None) -> str | None:
        if raw is None:
            return None
        normalized = raw.strip()
        return normalized or None

    @staticmethod
    def _split_multi_value(raw: str | None) -> list[str]:
        cleaned = SeedStore._clean_optional(raw)
        if cleaned is None:
            return []
        normalized = cleaned.replace(";", "|").replace(",", "|")
        return [item.strip() for item in normalized.split("|") if item.strip()]

    def _map_profile_rows(
        self,
        unit_row: dict[str, str],
        medical_row: dict[str, str],
        call_row: dict[str, str],
    ) -> dict:
        medical_age = int(self._clean_optional(medical_row.get("age")) or unit_row["age"])
        medical_mobility = (
            self._clean_optional(medical_row.get("mobility_status")) or unit_row["mobility_status"]
        )
        prior_falls_count = int(self._clean_optional(medical_row.get("prior_falls_count")) or "0")
        cognitive_status = self._clean_optional(medical_row.get("cognitive_status")) or "unknown"
        dementia_flag_raw = (
            medical_row.get("dementia_confusion_risk_flag") or medical_row.get("dementia_risk_flag")
        )

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
                "age": medical_age,
                "mobility_status": medical_mobility,
                "preexisting_conditions": self._split_multi_value(
                    medical_row.get("preexisting_conditions")
                ),
                "medication_list": self._split_multi_value(medical_row.get("medication_list")),
                "discharge_date": self._clean_optional(medical_row.get("discharge_date")),
                "prior_falls_count": prior_falls_count,
                "cognitive_status": cognitive_status,
                "cardiac_risk_flag": self._to_bool(medical_row.get("cardiac_risk_flag")),
                "fall_risk_flag": self._to_bool(medical_row.get("fall_risk_flag")),
                "diabetes_flag": self._to_bool(medical_row.get("diabetes_flag")),
                "dementia_confusion_risk_flag": self._to_bool(dementia_flag_raw),
                "recent_discharge_flag": self._to_bool(medical_row.get("recent_discharge_flag")),
            },
            "historical_call_history": {
                "calls_last_7d": int(call_row["calls_last_7d"]),
                "calls_last_30d": int(call_row["calls_last_30d"]),
                "false_alarm_rate": float(call_row["false_alarm_rate"]),
                "last_call_timestamp": call_row["last_call_timestamp"],
                "average_call_duration": float(call_row["average_call_duration"]),
            },
        }

    def _profile_from_row(self, row: RowMapping) -> ProfileRecord:
        return ProfileRecord.model_validate(
            {
                "profile_id": row["profile_id"],
                "unit_patient_information": row["unit_patient_information"],
                "medical_history": row["medical_history"],
                "historical_call_history": row["historical_call_history"],
            }
        )

    def _case_from_row(self, row: RowMapping) -> CaseRecord:
        return CaseRecord.model_validate(
            {
                "case_id": row["case_id"],
                "profile_id": row["profile_id"],
                "status": row["status"],
                "emergency_type": row["emergency_type"],
                "distress_level": row["distress_level"],
                "confidence": row["confidence"],
                "false_alarm_probability": row["false_alarm_probability"],
                "recommended_action": row["recommended_action"],
                "operator_action": row["operator_action"],
                "actual_severity": row["actual_severity"],
                "actual_action": row["actual_action"],
                "actual_false_alarm": row["actual_false_alarm"],
                "actual_emergency_type": row["actual_emergency_type"],
                "outcome_notes": row["outcome_notes"],
                "outcome_recorded_at": row["outcome_recorded_at"],
                "top_contributing_reasons": row["top_contributing_reasons"] or [],
                "audio_module": row["audio_module"],
                "intake_artifacts": row["intake_artifacts"] or [],
                "score_result": row["score_result"],
                "created_at": row["created_at"],
                "last_updated_at": row["last_updated_at"],
            }
        )

    def _case_to_row(self, case: CaseRecord) -> dict:
        return {
            "case_id": case.case_id,
            "profile_id": case.profile_id,
            "status": case.status,
            "emergency_type": case.emergency_type,
            "distress_level": case.distress_level,
            "confidence": case.confidence,
            "false_alarm_probability": case.false_alarm_probability,
            "recommended_action": case.recommended_action,
            "operator_action": case.operator_action,
            "actual_severity": case.actual_severity,
            "actual_action": case.actual_action,
            "actual_false_alarm": case.actual_false_alarm,
            "actual_emergency_type": case.actual_emergency_type,
            "outcome_notes": case.outcome_notes,
            "outcome_recorded_at": self._to_iso(case.outcome_recorded_at),
            "top_contributing_reasons": case.top_contributing_reasons,
            "audio_module": (
                case.audio_module.model_dump(mode="json") if case.audio_module is not None else None
            ),
            "intake_artifacts": [item.model_dump(mode="json") for item in case.intake_artifacts],
            "score_result": (
                case.score_result.model_dump(mode="json") if case.score_result is not None else None
            ),
            "created_at": self._to_iso(case.created_at),
            "last_updated_at": self._to_iso(case.last_updated_at),
        }

    def _training_record_to_row(self, record: TrainingRecord) -> dict:
        record_json = record.model_dump(mode="json")
        return {
            "case_id": record.case_id,
            "predicted_at": self._to_iso(record.predicted_at) or "",
            "record_json": record_json,
            "updated_at": self._to_iso(datetime.now(timezone.utc)) or "",
        }

    def _training_record_from_row(self, row: RowMapping) -> TrainingRecord:
        return TrainingRecord.model_validate(row["record_json"])

    def _save_case(self, case: CaseRecord) -> None:
        with self._engine.begin() as connection:
            connection.execute(delete(self._cases_table).where(self._cases_table.c.case_id == case.case_id))
            connection.execute(insert(self._cases_table).values(**self._case_to_row(case)))

    def _get_case(self, case_id: str) -> CaseRecord | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                select(self._cases_table).where(self._cases_table.c.case_id == case_id)
            ).mappings().first()
        if row is None:
            return None
        return self._case_from_row(row)

    def _save_training_record(self, record: TrainingRecord) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                delete(self._training_records_table).where(
                    self._training_records_table.c.case_id == record.case_id
                )
            )
            connection.execute(insert(self._training_records_table).values(**self._training_record_to_row(record)))

    def _get_training_record(self, case_id: str) -> TrainingRecord | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                select(self._training_records_table).where(
                    self._training_records_table.c.case_id == case_id
                )
            ).mappings().first()
        if row is None:
            return None
        return self._training_record_from_row(row)

    def list_profiles(self) -> list[ProfileRecord]:
        with self._engine.begin() as connection:
            rows = connection.execute(select(self._profiles_table)).mappings().all()
        return [self._profile_from_row(row) for row in rows]

    def get_profile(self, profile_id: str) -> ProfileRecord | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                select(self._profiles_table).where(self._profiles_table.c.profile_id == profile_id)
            ).mappings().first()
        if row is None:
            return None
        return self._profile_from_row(row)

    def add_profile(self, profile: ProfileRecord) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                delete(self._profiles_table).where(self._profiles_table.c.profile_id == profile.profile_id)
            )
            connection.execute(
                insert(self._profiles_table).values(
                    profile_id=profile.profile_id,
                    unit_patient_information=profile.unit_patient_information.model_dump(mode="json"),
                    medical_history=profile.medical_history.model_dump(mode="json"),
                    historical_call_history=profile.historical_call_history.model_dump(mode="json"),
                    updated_at=self._to_iso(datetime.now(timezone.utc)) or "",
                )
            )

    def generate_profile_id(self) -> str:
        pattern = re.compile(r"^profile-(\d+)$")
        max_value = 0
        for profile in self.list_profiles():
            match = pattern.match(profile.profile_id)
            if not match:
                continue
            max_value = max(max_value, int(match.group(1)))
        return f"profile-{max_value + 1:03d}"

    def list_cases(self) -> list[CaseRecord]:
        with self._engine.begin() as connection:
            rows = connection.execute(
                select(self._cases_table).order_by(self._cases_table.c.created_at.asc())
            ).mappings().all()
        return [self._case_from_row(row) for row in rows]

    def list_training_records(self) -> list[TrainingRecord]:
        with self._engine.begin() as connection:
            rows = connection.execute(
                select(self._training_records_table).order_by(self._training_records_table.c.predicted_at.desc())
            ).mappings().all()
        return [self._training_record_from_row(row) for row in rows]

    @staticmethod
    def _as_operator_action(value: str | None) -> OperatorAction | None:
        if value in {"operator_callback", "community_response", "ambulance_dispatch"}:
            return cast(OperatorAction, value)
        return None

    def _upsert_training_record(self, case: CaseRecord, profile: ProfileRecord) -> None:
        existing = self._get_training_record(case.case_id)
        predicted_at = existing.predicted_at if existing is not None else case.last_updated_at

        training_record = TrainingRecord(
            case_id=case.case_id,
            profile_id=case.profile_id,
            unit_patient_information=profile.unit_patient_information,
            medical_history=profile.medical_history,
            historical_call_history=profile.historical_call_history,
            audio_module=case.audio_module,
            predicted_emergency_type=case.emergency_type,
            predicted_severity=case.distress_level,
            predicted_action=self._as_operator_action(case.recommended_action),
            predicted_confidence=case.confidence,
            predicted_false_alarm_probability=case.false_alarm_probability,
            predicted_top_contributing_reasons=case.top_contributing_reasons,
            predicted_at=predicted_at,
            actual_severity=case.actual_severity,
            actual_action=case.actual_action,
            actual_false_alarm=case.actual_false_alarm,
            actual_emergency_type=case.actual_emergency_type,
            outcome_notes=case.outcome_notes,
            outcome_recorded_at=case.outcome_recorded_at,
        )
        self._save_training_record(training_record)

    @staticmethod
    def _join_values(values: list[str] | None) -> str:
        if not values:
            return ""
        return " | ".join(values)

    @staticmethod
    def _to_csv_value(value: object | None) -> str:
        if value is None:
            return ""
        return str(value)

    def _append_training_record_csv(self, case_id: str, profile: ProfileRecord) -> None:
        if not self._export_training_csv:
            return

        training_record = self._get_training_record(case_id)
        if training_record is None:
            return

        self._training_records_csv_path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = self._training_records_csv_path.exists()

        unit = profile.unit_patient_information
        medical = profile.medical_history
        calls = profile.historical_call_history
        audio = training_record.audio_module

        row = {
            "recorded_at": self._to_csv_value(training_record.outcome_recorded_at),
            "case_id": training_record.case_id,
            "profile_id": training_record.profile_id,
            "unit_block": self._to_csv_value(unit.unit_block),
            "resident_name": self._to_csv_value(unit.resident_name),
            "age": self._to_csv_value(unit.age),
            "living_alone_flag": self._to_csv_value(unit.living_alone_flag),
            "mobility_status": self._to_csv_value(unit.mobility_status),
            "caregiver_available": self._to_csv_value(unit.caregiver_available),
            "medical_age": self._to_csv_value(medical.age),
            "medical_mobility_status": self._to_csv_value(medical.mobility_status),
            "preexisting_conditions": self._join_values(medical.preexisting_conditions),
            "medication_list": self._join_values(medical.medication_list),
            "discharge_date": self._to_csv_value(medical.discharge_date),
            "prior_falls_count": self._to_csv_value(medical.prior_falls_count),
            "cognitive_status": self._to_csv_value(medical.cognitive_status),
            "cardiac_risk_flag": self._to_csv_value(medical.cardiac_risk_flag),
            "fall_risk_flag": self._to_csv_value(medical.fall_risk_flag),
            "diabetes_flag": self._to_csv_value(medical.diabetes_flag),
            "dementia_confusion_risk_flag": self._to_csv_value(
                medical.dementia_confusion_risk_flag
            ),
            "recent_discharge_flag": self._to_csv_value(medical.recent_discharge_flag),
            "calls_last_7d": self._to_csv_value(calls.calls_last_7d),
            "calls_last_30d": self._to_csv_value(calls.calls_last_30d),
            "false_alarm_rate": self._to_csv_value(calls.false_alarm_rate),
            "last_call_timestamp": self._to_csv_value(calls.last_call_timestamp),
            "average_call_duration": self._to_csv_value(calls.average_call_duration),
            "speech_cues": self._join_values(audio.speech_cues if audio else []),
            "non_speech_cues": self._join_values(audio.non_speech_cues if audio else []),
            "speech_distress_score": self._to_csv_value(
                audio.speech_distress_score if audio else None
            ),
            "non_speech_distress_score": self._to_csv_value(
                audio.non_speech_distress_score if audio else None
            ),
            "audio_estimated_emergency_type": self._to_csv_value(
                audio.estimated_emergency_type if audio else None
            ),
            "predicted_emergency_type": self._to_csv_value(training_record.predicted_emergency_type),
            "predicted_severity": self._to_csv_value(training_record.predicted_severity),
            "predicted_action": self._to_csv_value(training_record.predicted_action),
            "predicted_confidence": self._to_csv_value(training_record.predicted_confidence),
            "predicted_false_alarm_probability": self._to_csv_value(
                training_record.predicted_false_alarm_probability
            ),
            "predicted_top_contributing_reasons": self._join_values(
                training_record.predicted_top_contributing_reasons
            ),
            "actual_severity": self._to_csv_value(training_record.actual_severity),
            "actual_action": self._to_csv_value(training_record.actual_action),
            "actual_false_alarm": self._to_csv_value(training_record.actual_false_alarm),
            "actual_emergency_type": self._to_csv_value(training_record.actual_emergency_type),
            "outcome_notes": self._to_csv_value(training_record.outcome_notes),
        }

        with self._training_records_csv_path.open("a", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=self.TRAINING_CSV_COLUMNS)
            if (not file_exists) or self._training_records_csv_path.stat().st_size == 0:
                writer.writeheader()
            writer.writerow(row)

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
        self._save_case(case)
        return case

    def process_case(self, case_id: str) -> CaseRecord | None:
        case = self._get_case(case_id)
        if case is None:
            return None

        profile = self.get_profile(case.profile_id)
        if profile is None:
            return None

        triage = evaluate_case(profile, case.audio_module)
        case.confidence = triage["confidence"]
        case.false_alarm_probability = triage["false_alarm_probability"]
        case.distress_level = triage["distress_level"]
        case.recommended_action = triage["recommended_action"]
        case.top_contributing_reasons = triage["top_contributing_reasons"]
        case.emergency_type = triage["emergency_type"]
        case.score_result = triage["score_result"]
        case.status = "processed"
        case.last_updated_at = datetime.now(timezone.utc)

        self._save_case(case)
        self._upsert_training_record(case, profile)
        return case

    def mark_case_processed(self, case_id: str) -> CaseRecord | None:
        return self.process_case(case_id)

    def set_operator_action(self, case_id: str, action: OperatorAction) -> CaseRecord | None:
        case = self._get_case(case_id)
        if case is None:
            return None

        case.operator_action = action
        case.actual_action = action
        case.status = "operator_processed"
        case.last_updated_at = datetime.now(timezone.utc)

        self._save_case(case)

        profile = self.get_profile(case.profile_id)
        if profile is not None:
            self._upsert_training_record(case, profile)
        return case

    def set_case_outcome(self, case_id: str, payload: CaseOutcomeRequest) -> CaseRecord | None:
        case = self._get_case(case_id)
        if case is None:
            return None

        case.actual_severity = payload.actual_severity
        case.actual_action = payload.actual_action or case.actual_action or case.operator_action
        case.actual_false_alarm = payload.actual_false_alarm
        case.actual_emergency_type = payload.actual_emergency_type
        case.outcome_notes = payload.notes
        case.outcome_recorded_at = datetime.now(timezone.utc)
        case.last_updated_at = case.outcome_recorded_at

        self._save_case(case)

        profile = self.get_profile(case.profile_id)
        if profile is not None:
            self._upsert_training_record(case, profile)
            self._append_training_record_csv(case.case_id, profile)
        return case
