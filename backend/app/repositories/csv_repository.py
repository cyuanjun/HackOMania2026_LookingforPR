from __future__ import annotations

import csv
from pathlib import Path

from app.repositories.interfaces import ResidentDataRepository
from app.schemas import RawCallHistory, RawMedicalHistory, ResidentProfile


class CsvResidentDataRepository(ResidentDataRepository):
    def __init__(self, csv_dir: Path) -> None:
        self._unit_patient_info_path = csv_dir / "unit_patient_info.csv"
        self._medical_history_path = csv_dir / "medical_history.csv"
        self._call_history_path = csv_dir / "call_history.csv"

    @staticmethod
    def _split_list(value: str | None) -> list[str]:
        if not value:
            return []
        return [item.strip() for item in value.split("|") if item.strip() and item.strip().lower() != "none"]

    @staticmethod
    def _parse_bool(value: str | None) -> bool:
        if value is None:
            return False
        return value.strip().lower() in {"1", "true", "yes", "y"}

    @staticmethod
    def _infer_block(unit: str) -> str:
        if not unit.startswith("#"):
            return ""
        floor_or_block = unit[1:].split("-", maxsplit=1)[0]
        if not floor_or_block.isdigit():
            return ""
        return f"Blk {int(floor_or_block)}"

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            rows: list[dict[str, str]] = []
            for raw_row in reader:
                normalized_row: dict[str, str] = {}
                for key, value in raw_row.items():
                    if key is None:
                        continue
                    normalized_row[key.strip()] = (value or "").strip()
                if any(normalized_row.values()):
                    rows.append(normalized_row)
            return rows

    def list_profiles(self) -> list[ResidentProfile]:
        rows = self._read_csv(self._unit_patient_info_path)
        profiles: list[ResidentProfile] = []
        for row in rows:
            profile_id = row.get("profile_id") or row.get("resident_id") or ""
            unit = row.get("unit") or row.get("unit_no") or ""
            block = row.get("block") or self._infer_block(unit)
            if not profile_id:
                continue
            profiles.append(
                ResidentProfile(
                    profile_id=profile_id,
                    name=row["name"],
                    age=int(row["age"]),
                    postal_code=row.get("postal_code") or "",
                    block=block,
                    unit=unit,
                    preferred_language=row["preferred_language"],
                    preferred_dialect=row["preferred_dialect"],
                    emergency_contact=row["emergency_contact"],
                    mobility_status=row["mobility_status"],
                    living_alone=self._parse_bool(row.get("living_alone")),
                )
            )
        return profiles

    def get_profile(self, profile_id: str) -> ResidentProfile | None:
        profiles = self.list_profiles()
        for profile in profiles:
            if profile.profile_id == profile_id:
                return profile
        return None

    def get_raw_medical_history(self, profile_id: str) -> RawMedicalHistory | None:
        rows = self._read_csv(self._medical_history_path)
        for row in rows:
            row_profile_id = row.get("profile_id") or row.get("resident_id") or ""
            if row_profile_id == profile_id:
                return RawMedicalHistory(
                    profile_id=profile_id,
                    diagnoses=self._split_list(row.get("diagnoses")),
                    allergies=self._split_list(row.get("allergies")),
                    medications=self._split_list(row.get("medications")),
                    last_discharge_date=row.get("last_discharge_date") or row.get("last_hospitalization_date") or None,
                    notes=row.get("notes") or None,
                )
        return None

    def get_raw_call_history(self, profile_id: str) -> RawCallHistory | None:
        rows = self._read_csv(self._call_history_path)
        for row in rows:
            row_profile_id = row.get("profile_id") or row.get("resident_id") or ""
            if row_profile_id == profile_id:
                return RawCallHistory(
                    profile_id=profile_id,
                    total_calls_last_30d=int(row["total_calls_last_30d"]),
                    urgent_calls_last_30d=int(row["urgent_calls_last_30d"]),
                    false_alarm_count_last_30d=int(row["false_alarm_count_last_30d"]),
                    last_call_outcome=row.get("last_call_outcome") or None,
                    recent_call_summaries=self._split_list(row.get("recent_call_summaries")),
                )
        return None
