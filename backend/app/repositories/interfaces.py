from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas import CaseDetail, CaseState, RawCallHistory, RawMedicalHistory, ResidentProfile


class ResidentDataRepository(ABC):
    @abstractmethod
    def list_profiles(self) -> list[ResidentProfile]:
        raise NotImplementedError

    @abstractmethod
    def get_profile(self, profile_id: str) -> ResidentProfile | None:
        raise NotImplementedError

    @abstractmethod
    def get_raw_medical_history(self, profile_id: str) -> RawMedicalHistory | None:
        raise NotImplementedError

    @abstractmethod
    def get_raw_call_history(self, profile_id: str) -> RawCallHistory | None:
        raise NotImplementedError


class CaseStoreRepository(ABC):
    @abstractmethod
    def create_case(self, case: CaseDetail) -> CaseDetail:
        raise NotImplementedError

    @abstractmethod
    def save_case(self, case: CaseDetail) -> CaseDetail:
        raise NotImplementedError

    @abstractmethod
    def get_case(self, case_id: str) -> CaseDetail | None:
        raise NotImplementedError

    @abstractmethod
    def list_cases(self, state: CaseState | None = None) -> list[CaseDetail]:
        raise NotImplementedError

    @abstractmethod
    def delete_case(self, case_id: str) -> bool:
        raise NotImplementedError
