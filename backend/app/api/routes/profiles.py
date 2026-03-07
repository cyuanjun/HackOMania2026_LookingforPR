from fastapi import APIRouter

from app.dependencies import store


router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("")
def list_profiles() -> dict:
    profiles = [profile.model_dump(mode="json") for profile in store.list_profiles()]
    return {"data": {"profiles": profiles}}
