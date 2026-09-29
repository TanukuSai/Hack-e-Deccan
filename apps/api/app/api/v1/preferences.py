from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status

from apps.api.app.core.security import get_current_user_id
from apps.api.app.schemas.preference import PreferenceCreate, PreferenceResponse, PreferenceUndoResponse
from apps.api.app.services.preference_service import PreferenceService

router = APIRouter(prefix="/preferences", tags=["preferences"])
preference_service = PreferenceService()

@router.get("", response_model=List[PreferenceResponse])
async def list_preferences(
    dimension: Optional[str] = Query(None, description="Filter by dimension (briefing_format, topic_priority, preparation_timing)"),
    scope: Optional[str] = Query(None, description="Filter by scope (global, meeting_type, project, contact)"),
    user_id: str = Depends(get_current_user_id)
):
    """
    List active learned and explicit preferences for the authenticated tenant.
    """
    return await preference_service.list_preferences(
        user_id=user_id,
        dimension=dimension,
        scope=scope
    )

@router.post("", response_model=PreferenceResponse, status_code=status.HTTP_201_CREATED)
async def create_explicit_preference(
    payload: PreferenceCreate,
    user_id: str = Depends(get_current_user_id)
):
    """
    Set an explicit preference with 1.0 confidence.
    """
    return await preference_service.set_explicit_preference(
        user_id=user_id,
        dimension=payload.dimension,
        scope=payload.scope,
        scope_id=payload.scope_id,
        key=payload.key,
        value=payload.value
    )

@router.post("/{preference_id}/undo", response_model=PreferenceResponse)
async def undo_preference(
    preference_id: UUID,
    user_id: str = Depends(get_current_user_id)
):
    """
    Reversibly undo a learned preference, reducing confidence to 0.000.
    """
    return await preference_service.undo_learned_preference(
        user_id=user_id,
        preference_id=preference_id
    )
