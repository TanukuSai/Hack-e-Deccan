from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from apps.api.app.core.security import get_current_user_id
from apps.api.app.core.db import get_tenant_session
from apps.api.app.services.briefing_service import BriefingService
from apps.api.app.schemas.briefing import (
    BriefingResponse, BriefingGenerationRequest, BriefingFollowUpRequest, BriefingFollowUpResponse
)
from apps.api.app.providers.groq_adapter import GroqAdapter

router = APIRouter(prefix="/briefings", tags=["briefings"])
briefing_service = BriefingService()
groq_adapter = GroqAdapter()


@router.post("/generate", response_model=BriefingResponse, status_code=status.HTTP_200_OK)
async def generate_briefing(
    payload: BriefingGenerationRequest,
    user_id: str = Depends(get_current_user_id)
):
    result = await briefing_service.generate_and_promote_briefing(
        user_id=user_id,
        meeting_id=payload.meeting_id,
        force_refresh=payload.force_refresh
    )
    return result


@router.get("/meeting/{meeting_id}/latest", response_model=BriefingResponse)
async def get_latest_briefing(
    meeting_id: UUID,
    user_id: str = Depends(get_current_user_id)
):
    async with get_tenant_session(user_id) as session:
        # Fetch latest briefing
        b_res = await session.execute(
            text("""
            SELECT id, user_id, meeting_id, version, is_latest,
                   summary AS executive_summary,
                   assumptions_and_gaps AS attendee_profiles,
                   strategic_questions AS strategic_priorities,
                   talking_points,
                   conflicts_detected,
                   NULL AS degraded_reason,
                   created_at
            FROM public.briefings
            WHERE meeting_id = :m_id AND user_id = :u_id AND is_latest = TRUE;
            """),
            {"m_id": str(meeting_id), "u_id": user_id}
        )
        briefing = b_res.mappings().first()
        if not briefing:
            raise HTTPException(status_code=404, detail="No briefing generated for this meeting")

        briefing_dict = dict(briefing)

        # Fetch evidence items
        ev_res = await session.execute(
            text("""
            SELECT id, user_id, briefing_id, epistemic_class AS source_type, claim_text,
                   excerpt AS quote_or_content, source_id AS source_document_id,
                   (verified_at IS NOT NULL) AS verified,
                   NULL AS created_at
            FROM public.evidence_items
            WHERE briefing_id = :b_id AND user_id = :u_id;
            """),
            {"b_id": str(briefing["id"]), "u_id": user_id}
        )
        briefing_dict["evidence_items"] = [dict(r) for r in ev_res.mappings().all()]
        return briefing_dict


@router.get("/meeting/{meeting_id}/history", response_model=List[BriefingResponse])
async def get_briefing_history(
    meeting_id: UUID,
    user_id: str = Depends(get_current_user_id)
):
    async with get_tenant_session(user_id) as session:
        b_res = await session.execute(
            text("""
            SELECT id, user_id, meeting_id, version, is_latest,
                   summary AS executive_summary,
                   assumptions_and_gaps AS attendee_profiles,
                   strategic_questions AS strategic_priorities,
                   talking_points,
                   conflicts_detected,
                   NULL AS degraded_reason,
                   created_at
            FROM public.briefings
            WHERE meeting_id = :m_id AND user_id = :u_id
            ORDER BY version DESC;
            """),
            {"m_id": str(meeting_id), "u_id": user_id}
        )
        results = []
        for row in b_res.mappings().all():
            b_dict = dict(row)
            b_dict["evidence_items"] = []
            results.append(b_dict)
        return results


@router.post("/meeting/{meeting_id}/conversation", response_model=BriefingFollowUpResponse)
async def briefing_follow_up_conversation(
    meeting_id: UUID,
    payload: BriefingFollowUpRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Follow-up conversation with the Agent about the given meeting briefing.
    Allows user to drill down, brainstorm talking points, or anticipate counter-arguments.
    """
    async with get_tenant_session(user_id) as session:
        # 1. Fetch meeting title and details
        m_res = await session.execute(
            text("SELECT id, title, purpose, notes FROM public.meetings WHERE id = :m_id AND user_id = :u_id;"),
            {"m_id": str(meeting_id), "u_id": user_id}
        )
        meeting = m_res.mappings().first()
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")

        # 2. Fetch latest briefing
        b_res = await session.execute(
            text("""
            SELECT id,
                   summary AS executive_summary,
                   assumptions_and_gaps AS attendee_profiles,
                   strategic_questions AS strategic_priorities,
                   talking_points, conflicts_detected
            FROM public.briefings
            WHERE meeting_id = :m_id AND user_id = :u_id AND is_latest = TRUE;
            """),
            {"m_id": str(meeting_id), "u_id": user_id}
        )
        briefing = b_res.mappings().first()
        briefing_ctx = dict(briefing) if briefing else {
            "executive_summary": meeting["purpose"] or meeting["title"],
            "attendee_profiles": [],
            "strategic_priorities": [],
            "talking_points": [],
            "conflicts_detected": [],
        }

    # 3. Call GroqAdapter chat follow-up
    result = groq_adapter.chat_follow_up(
        meeting_title=meeting["title"],
        briefing_context=briefing_ctx,
        question=payload.question,
        history=payload.history
    )

    return BriefingFollowUpResponse(
        meeting_id=str(meeting_id),
        question=payload.question,
        answer=result.get("answer", ""),
        suggested_talking_points=result.get("suggested_talking_points", []),
        action_items=result.get("action_items", [])
    )
