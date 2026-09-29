from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status

from apps.api.app.core.security import get_current_user_id
from apps.api.app.schemas.outcome import CommitmentResponse, CommitmentUpdate
from apps.api.app.services.outcome_service import OutcomeService

router = APIRouter(prefix="/commitments", tags=["commitments"])
outcome_service = OutcomeService()

@router.get("", response_model=List[CommitmentResponse])
async def list_commitments(
    meeting_id: Optional[UUID] = Query(None, description="Filter by meeting ID"),
    project_id: Optional[UUID] = Query(None, description="Filter by project ID"),
    commitment_status: Optional[str] = Query(None, alias="status", description="Filter by status (pending, in_progress, completed, missed, cancelled)"),
    is_confirmed: Optional[bool] = Query(None, description="Filter by confirmation status"),
    user_id: str = Depends(get_current_user_id)
):
    """
    List commitments for the authenticated tenant with optional filtering.
    """
    return await outcome_service.list_commitments(
        user_id=user_id,
        meeting_id=meeting_id,
        project_id=project_id,
        commitment_status=commitment_status,
        is_confirmed=is_confirmed
    )

@router.post("/{commitment_id}/confirm", response_model=CommitmentResponse)
async def confirm_commitment(
    commitment_id: UUID,
    user_id: str = Depends(get_current_user_id)
):
    """
    Explicitly confirm an inferred commitment (is_confirmed: False -> True).
    Invariant: AI-proposed commitments require human confirmation.
    """
    return await outcome_service.confirm_commitment(
        user_id=user_id,
        commitment_id=commitment_id
    )

@router.patch("/{commitment_id}", response_model=CommitmentResponse)
async def update_commitment(
    commitment_id: UUID,
    payload: CommitmentUpdate,
    user_id: str = Depends(get_current_user_id)
):
    """
    Update commitment status, due date, description, or owner.
    """
    return await outcome_service.update_commitment(
        user_id=user_id,
        commitment_id=commitment_id,
        payload=payload
    )
