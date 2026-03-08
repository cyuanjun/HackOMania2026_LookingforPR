from __future__ import annotations

from app.core.time_utils import now_iso
from app.schemas import CaseDetail, CaseState
from app.services import (
    FusionEngineService,
    HistoryFlagService,
    MedicalFlagService,
    SpeechPipelineService,
    SummaryService,
)


class TriagePipeline:
    def __init__(
        self,
        *,
        speech_pipeline: SpeechPipelineService,
        medical_flag_service: MedicalFlagService,
        history_flag_service: HistoryFlagService,
        fusion_engine: FusionEngineService,
        summary_service: SummaryService,
    ) -> None:
        self.speech_pipeline = speech_pipeline
        self.medical_flag_service = medical_flag_service
        self.history_flag_service = history_flag_service
        self.fusion_engine = fusion_engine
        self.summary_service = summary_service

    def run(self, case: CaseDetail) -> CaseDetail:
        case_id = case.metadata.case_id

        case.speech_result = self.speech_pipeline.process(
            case_id=case_id,
            resident_profile=case.resident_profile,
            audio_metadata=case.audio_metadata,
        )
        case.language_routing_result = self.speech_pipeline.to_language_routing_result(case.speech_result)

        case.derived_medical_flags = self.medical_flag_service.derive_flags(
            medical_history=case.raw_medical_history,
            resident_profile=case.resident_profile,
        )
        case.derived_history_flags = self.history_flag_service.derive_flags(call_history=case.raw_call_history)

        case.triage_result = self.fusion_engine.evaluate(
            speech=case.speech_result,
            routing=case.language_routing_result,
            medical_flags=case.derived_medical_flags,
            history_flags=case.derived_history_flags,
            resident_profile=case.resident_profile,
            raw_medical_history=case.raw_medical_history,
            raw_call_history=case.raw_call_history,
            resident_age=case.resident_profile.age,
        )
        case.summary_text = self.summary_service.generate(case)

        case.metadata.state = CaseState.AI_ASSESSED
        case.metadata.updated_at = now_iso()
        return case
