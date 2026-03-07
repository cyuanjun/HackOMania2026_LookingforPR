from fastapi import APIRouter, HTTPException

from app.dependencies import store
from app.schemas.case import (
    CaseIntakeRequest,
    CaseOutcomeRequest,
    OperatorActionRequest,
    ProfileRecord,
)


router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("")
def list_cases() -> dict:
    cases = store.list_cases()
    return {"data": {"cases": [case.model_dump(mode="json") for case in cases]}}


@router.get("/training-records")
def list_training_records() -> dict:
    records = store.list_training_records()
    return {"data": {"training_records": [record.model_dump(mode="json") for record in records]}}


@router.post("/intake")
def intake_case(payload: CaseIntakeRequest) -> dict:
    if payload.profile_id and payload.custom_profile:
        raise HTTPException(
            status_code=400,
            detail="Provide either profile_id or custom_profile, not both.",
        )

    if payload.custom_profile is not None:
        generated_profile_id = store.generate_profile_id()

        custom_profile = ProfileRecord(
            profile_id=generated_profile_id,
            unit_patient_information=payload.custom_profile.unit_patient_information,
            medical_history=payload.custom_profile.medical_history,
            historical_call_history=payload.custom_profile.historical_call_history,
        )
        store.add_profile(custom_profile)
        resolved_profile_id = custom_profile.profile_id
    elif payload.profile_id:
        profile = store.get_profile(payload.profile_id)
        if profile is None:
            raise HTTPException(status_code=400, detail="Unknown profile_id.")
        resolved_profile_id = profile.profile_id
    else:
        raise HTTPException(
            status_code=400,
            detail="Missing profile selection. Provide profile_id or custom_profile.",
        )

    case = store.create_case_from_intake(payload, profile_id=resolved_profile_id)
    processed_case = store.process_case(case.case_id)
    if processed_case is not None:
        case = processed_case
    return {"data": {"case": case.model_dump(mode="json")}}


@router.post("/{case_id}/process")
def process_case(case_id: str) -> dict:
    case = store.mark_case_processed(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Unknown case_id.")

    return {"data": {"case": case.model_dump(mode="json")}}


@router.post("/{case_id}/operator-action")
def set_operator_action(case_id: str, payload: OperatorActionRequest) -> dict:
    case = store.set_operator_action(case_id, payload.action)
    if case is None:
        raise HTTPException(status_code=404, detail="Unknown case_id.")

    return {"data": {"case": case.model_dump(mode="json")}}


@router.post("/{case_id}/outcome")
def set_case_outcome(case_id: str, payload: CaseOutcomeRequest) -> dict:
    case = store.set_case_outcome(case_id, payload)
    if case is None:
        raise HTTPException(status_code=404, detail="Unknown case_id.")

    return {"data": {"case": case.model_dump(mode="json")}}
