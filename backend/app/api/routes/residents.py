from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.core import AppContainer
from app.schemas import ResidentContext, ResidentProfile

router = APIRouter(prefix="/residents", tags=["residents"])


@router.get("", response_model=list[ResidentProfile])
def list_resident_profiles(request: Request) -> list[ResidentProfile]:
    container: AppContainer = request.app.state.container
    return container.resident_repository.list_profiles()


@router.get("/{profile_id}/context", response_model=ResidentContext)
def get_resident_context(request: Request, profile_id: str) -> ResidentContext:
    container: AppContainer = request.app.state.container
    profile = container.resident_repository.get_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Resident profile not found.")

    return ResidentContext(
        resident_profile=profile,
        raw_medical_history=container.resident_repository.get_raw_medical_history(profile_id),
        raw_call_history=container.resident_repository.get_raw_call_history(profile_id),
    )
