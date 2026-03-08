from __future__ import annotations

from app.core.config import Settings
from app.core.pipeline import TriagePipeline
from app.repositories import CsvResidentDataRepository, JsonCaseStoreRepository
from app.services import (
    FusionEngineService,
    HistoryFlagService,
    MedicalFlagService,
    SpeechPipelineService,
    SummaryService,
)


class AppContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.resident_repository = CsvResidentDataRepository(settings.csv_dir)
        self.case_store_repository = JsonCaseStoreRepository(settings.cases_dir)

        self.speech_pipeline = SpeechPipelineService()
        self.medical_flag_service = MedicalFlagService()
        self.history_flag_service = HistoryFlagService()
        self.fusion_engine = FusionEngineService(emergency_min_actions=settings.emergency_min_actions)
        self.summary_service = SummaryService()

        self.pipeline = TriagePipeline(
            speech_pipeline=self.speech_pipeline,
            medical_flag_service=self.medical_flag_service,
            history_flag_service=self.history_flag_service,
            fusion_engine=self.fusion_engine,
            summary_service=self.summary_service,
        )
