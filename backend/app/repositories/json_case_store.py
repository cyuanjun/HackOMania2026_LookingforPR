from __future__ import annotations

import json
from pathlib import Path

from app.repositories.interfaces import CaseStoreRepository
from app.schemas import CaseDetail, CaseState


class JsonCaseStoreRepository(CaseStoreRepository):
    def __init__(self, cases_dir: Path) -> None:
        self._cases_dir = cases_dir
        self._cases_dir.mkdir(parents=True, exist_ok=True)

    def _case_path(self, case_id: str) -> Path:
        return self._cases_dir / f"{case_id}.json"

    def create_case(self, case: CaseDetail) -> CaseDetail:
        case_path = self._case_path(case.metadata.case_id)
        if case_path.exists():
            raise ValueError(f"Case {case.metadata.case_id} already exists.")
        return self.save_case(case)

    def save_case(self, case: CaseDetail) -> CaseDetail:
        case_path = self._case_path(case.metadata.case_id)
        with case_path.open("w", encoding="utf-8") as output:
            json.dump(case.model_dump(mode="json"), output, indent=2)
        return case

    @staticmethod
    def _normalize_legacy_payload(payload: dict[str, object]) -> dict[str, object]:
        def migrate_legacy_id_key(section: object) -> None:
            if not isinstance(section, dict):
                return
            legacy_value = section.pop("resident_id", None)
            if "profile_id" not in section and isinstance(legacy_value, str):
                section["profile_id"] = legacy_value

        migrate_legacy_id_key(payload.get("metadata"))

        resident_profile = payload.get("resident_profile")
        if isinstance(resident_profile, dict):
            migrate_legacy_id_key(resident_profile)
            legacy_unit = resident_profile.pop("unit_no", None)
            if "unit" not in resident_profile or not resident_profile.get("unit"):
                resident_profile["unit"] = legacy_unit if isinstance(legacy_unit, str) else ""
            resident_profile.setdefault("block", "")
            resident_profile.setdefault("postal_code", "")
            resident_profile.setdefault("living_alone", False)
            resident_profile.pop("chronic_conditions", None)

        raw_medical_history = payload.get("raw_medical_history")
        if isinstance(raw_medical_history, dict):
            migrate_legacy_id_key(raw_medical_history)
            legacy_date = raw_medical_history.pop("last_hospitalization_date", None)
            if "last_discharge_date" not in raw_medical_history:
                raw_medical_history["last_discharge_date"] = legacy_date if isinstance(legacy_date, str) else None

        raw_call_history = payload.get("raw_call_history")
        migrate_legacy_id_key(raw_call_history)

        # Non-verbal audio analysis was removed from the pipeline.
        payload.pop("non_verbal_audio_result", None)
        return payload

    def get_case(self, case_id: str) -> CaseDetail | None:
        case_path = self._case_path(case_id)
        if not case_path.exists():
            return None
        with case_path.open("r", encoding="utf-8") as source:
            payload = json.load(source)
        normalized_payload = self._normalize_legacy_payload(payload)
        return CaseDetail.model_validate(normalized_payload)

    def list_cases(self, state: CaseState | None = None) -> list[CaseDetail]:
        cases: list[CaseDetail] = []
        for case_path in self._cases_dir.glob("*.json"):
            with case_path.open("r", encoding="utf-8") as source:
                payload = json.load(source)
                normalized_payload = self._normalize_legacy_payload(payload)
                case = CaseDetail.model_validate(normalized_payload)
                if state is None or case.metadata.state == state:
                    cases.append(case)
        cases.sort(key=lambda item: item.metadata.created_at, reverse=True)
        return cases

    def delete_case(self, case_id: str) -> bool:
        case_path = self._case_path(case_id)
        if not case_path.exists():
            return False
        case_path.unlink()
        return True
