from __future__ import annotations

from pathlib import Path, PurePath
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response

from app.core import AppContainer
from app.core.time_utils import now_iso
from app.schemas import (
    AudioMetadata,
    CaseDetail,
    CaseListItem,
    CaseMetadata,
    CaseState,
    OperatorDecision,
    OperatorDecisionRequest,
)

router = APIRouter(prefix="/cases", tags=["cases"])


def _resolve_audio_media_type(filename: str, uploaded_content_type: str | None) -> str:
    normalized_content_type = (uploaded_content_type or "").lower().strip()
    lowered_filename = filename.lower()

    if normalized_content_type in {"audio/x-m4a", "audio/m4a"} or lowered_filename.endswith(".m4a"):
        return "audio/mp4"
    if lowered_filename.endswith(".mp3"):
        return "audio/mpeg"
    if lowered_filename.endswith(".wav"):
        return "audio/wav"
    if normalized_content_type:
        return normalized_content_type
    return "application/octet-stream"


def _to_list_item(case: CaseDetail) -> CaseListItem:
    triage = case.triage_result
    return CaseListItem(
        case_id=case.metadata.case_id,
        profile_id=case.resident_profile.profile_id,
        resident_name=case.resident_profile.name,
        postal_code=case.resident_profile.postal_code,
        block=case.resident_profile.block,
        unit=case.resident_profile.unit,
        state=case.metadata.state,
        created_at=case.metadata.created_at,
        updated_at=case.metadata.updated_at,
        urgency_class=triage.urgency_class if triage else None,
        recommended_action=triage.recommended_action if triage else None,
        overall_confidence=triage.overall_confidence if triage else None,
        routing_hint=triage.routing_hint if triage else None,
        operator_action=case.operator_decision.chosen_action if case.operator_decision else None,
    )


@router.post("/intake", response_model=CaseDetail, status_code=status.HTTP_201_CREATED)
async def create_intake_case(
    request: Request,
    profile_id: str | None = Form(default=None),
    resident_id: str | None = Form(default=None),
    audio_file: UploadFile = File(...),
) -> CaseDetail:
    container: AppContainer = request.app.state.container
    resolved_profile_id = (profile_id or resident_id or "").strip()
    if not resolved_profile_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="profile_id is required.")

    resident_profile = container.resident_repository.get_profile(resolved_profile_id)
    if resident_profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resident profile not found.")

    medical_history = container.resident_repository.get_raw_medical_history(resolved_profile_id)
    if medical_history is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medical history not found.")

    call_history = container.resident_repository.get_raw_call_history(resolved_profile_id)
    if call_history is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Call history not found.")

    case_id = f"CASE-{uuid4().hex[:8].upper()}"
    safe_filename = PurePath(audio_file.filename or "alert_audio.wav").name
    stored_filename = f"{case_id}_{safe_filename}"
    destination = container.settings.uploads_dir / stored_filename

    payload = await audio_file.read()
    destination.write_bytes(payload)

    now = now_iso()
    case = CaseDetail(
        metadata=CaseMetadata(
            case_id=case_id,
            profile_id=resolved_profile_id,
            state=CaseState.PENDING_AI_ASSESSMENT,
            created_at=now,
            updated_at=now,
        ),
        audio_metadata=AudioMetadata(
            filename=safe_filename,
            content_type=audio_file.content_type or "application/octet-stream",
            size_bytes=len(payload),
            stored_path=str(destination),
            uploaded_at=now,
        ),
        resident_profile=resident_profile,
        raw_medical_history=medical_history,
        raw_call_history=call_history,
    )
    container.case_store_repository.create_case(case)
    return case


@router.get("", response_model=list[CaseListItem])
def list_cases(
    request: Request,
    state: CaseState | None = Query(default=None, description="Filter cases by workflow state"),
) -> list[CaseListItem]:
    container: AppContainer = request.app.state.container
    return [_to_list_item(case) for case in container.case_store_repository.list_cases(state=state)]


@router.get("/{case_id}", response_model=CaseDetail)
def get_case_detail(request: Request, case_id: str) -> CaseDetail:
    container: AppContainer = request.app.state.container
    case = container.case_store_repository.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    return case


@router.get("/{case_id}/audio")
def get_case_audio(request: Request, case_id: str) -> FileResponse:
    container: AppContainer = request.app.state.container
    case = container.case_store_repository.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

    audio_path = Path(case.audio_metadata.stored_path)
    if not audio_path.exists() or not audio_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio file not found.")

    media_type = _resolve_audio_media_type(
        filename=case.audio_metadata.filename,
        uploaded_content_type=case.audio_metadata.content_type,
    )

    return FileResponse(
        path=audio_path,
        media_type=media_type,
        filename=case.audio_metadata.filename,
    )


@router.post("/{case_id}/process-ai", response_model=CaseDetail)
def process_case_with_ai(request: Request, case_id: str) -> CaseDetail:
    container: AppContainer = request.app.state.container
    case = container.case_store_repository.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

    if case.metadata.state != CaseState.PENDING_AI_ASSESSMENT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invalid transition from {case.metadata.state.value} to ai_assessed.",
        )

    updated_case = container.pipeline.run(case)
    container.case_store_repository.save_case(updated_case)
    return updated_case


@router.post("/{case_id}/operator-decision", response_model=CaseDetail)
def submit_operator_decision(
    request: Request,
    case_id: str,
    payload: OperatorDecisionRequest,
) -> CaseDetail:
    container: AppContainer = request.app.state.container
    case = container.case_store_repository.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

    if case.metadata.state != CaseState.AI_ASSESSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invalid transition from {case.metadata.state.value} to operator_processed.",
        )

    ai_action = case.triage_result.recommended_action if case.triage_result else None
    case.operator_decision = OperatorDecision(
        operator_id=payload.operator_id,
        chosen_action=payload.chosen_action,
        notes=payload.notes,
        processed_at=now_iso(),
        overrides_ai=ai_action is not None and payload.chosen_action != ai_action,
    )
    case.metadata.state = CaseState.OPERATOR_PROCESSED
    case.metadata.updated_at = now_iso()

    container.case_store_repository.save_case(case)
    return case


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_case_record(request: Request, case_id: str) -> Response:
    container: AppContainer = request.app.state.container
    case = container.case_store_repository.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

    deleted = container.case_store_repository.delete_case(case_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")

    audio_path = Path(case.audio_metadata.stored_path)
    if audio_path.exists() and audio_path.is_file():
        try:
            audio_path.unlink()
        except OSError:
            pass

    return Response(status_code=status.HTTP_204_NO_CONTENT)
