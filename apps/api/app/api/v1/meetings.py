import json
import uuid
from typing import List, Optional
from uuid import UUID
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, UploadFile, File, Form, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from apps.api.app.core.security import get_current_user_id
from apps.api.app.core.db import get_tenant_session
from apps.api.app.schemas.meeting import (
    MeetingCreate, MeetingUpdate, MeetingResponse, MeetingDetailResponse, ParticipantCreate, ParticipantResponse
)
from apps.api.app.services.queue_service import QueueService
from apps.api.app.services.cost_service import CostService
from apps.api.app.schemas.outcome import (
    OutcomeAnalysisRequest, OutcomeAnalysisResponse, FollowUpDraftResponse, FollowUpDraftUpdate,
    InterMeetingReportSyncResponse
)
from apps.api.app.services.outcome_service import OutcomeService
from apps.api.app.services.inter_meeting_service import InterMeetingService

router = APIRouter(prefix="/meetings", tags=["meetings"])
outcome_service = OutcomeService()
inter_meeting_service = InterMeetingService()

@router.post("", response_model=MeetingDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    payload: MeetingCreate,
    user_id: str = Depends(get_current_user_id)
):
    async with get_tenant_session(user_id) as session:
        # If project_id provided, verify composite FK validity
        if payload.project_id:
            proj_check = await session.execute(
                text("SELECT id FROM public.projects WHERE id = :p_id AND user_id = :u_id;"),
                {"p_id": str(payload.project_id), "u_id": user_id}
            )
            if not proj_check.scalar():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Project {payload.project_id} does not exist or does not belong to user"
                )

        # Insert meeting
        ins_res = await session.execute(
            text("""
            INSERT INTO public.meetings (
                user_id, project_id, title, purpose, meeting_timezone,
                start_time, end_time, user_importance_override, effective_importance, notes
            )
            VALUES (
                :user_id, :project_id, :title, :purpose, :meeting_timezone,
                :start_time, :end_time, :user_importance_override,
                COALESCE(:user_importance_override, 'medium'), :notes
            )
            RETURNING id, user_id, project_id, title, purpose, meeting_timezone,
                      start_time, end_time, status, user_importance_override,
                      effective_importance, meeting_version, active_prep_job_id, notes,
                      created_at, updated_at;
            """),
            {
                "user_id": user_id,
                "project_id": str(payload.project_id) if payload.project_id else None,
                "title": payload.title,
                "purpose": payload.purpose,
                "meeting_timezone": payload.meeting_timezone,
                "start_time": payload.start_time,
                "end_time": payload.end_time,
                "user_importance_override": payload.user_importance_override,
                "notes": payload.notes
            }
        )
        meeting = dict(ins_res.mappings().first())
        meeting_id = meeting["id"]

        # Insert participants if provided
        participants = []
        if payload.participants:
            for p in payload.participants:
                part_ins = await session.execute(
                    text("""
                    INSERT INTO public.meeting_participants (
                        user_id, meeting_id, contact_id, name, role, is_organizer
                    )
                    VALUES (
                        :user_id, :meeting_id, :contact_id, :name, :role, :is_organizer
                    )
                    RETURNING id, user_id, meeting_id, contact_id, name, role, is_organizer;
                    """),
                    {
                        "user_id": user_id,
                        "meeting_id": str(meeting_id),
                        "contact_id": str(p.contact_id) if p.contact_id else None,
                        "name": p.name,
                        "role": p.role,
                        "is_organizer": p.is_organizer
                    }
                )
                participants.append(dict(part_ins.mappings().first()))

        meeting["participants"] = participants

        # Auto-schedule preparation job directly using active tenant session
        prof_res = await session.execute(
            text("SELECT monthly_budget_usd, current_month_spend_usd, prep_lead_time_hours FROM public.user_profiles WHERE id = :u_id;"),
            {"u_id": user_id}
        )
        prof_row = prof_res.mappings().first()
        if prof_row:
            budget = float(prof_row["monthly_budget_usd"] or 25.0)
            spend = float(prof_row["current_month_spend_usd"] or 0.0)
            lead_hours = prof_row["prep_lead_time_hours"] or 2

            if budget <= 0 or (spend / budget) < 0.95:
                scheduled_prep = payload.start_time - timedelta(hours=lead_hours)
                now_utc = datetime.now(timezone.utc)
                if scheduled_prep < now_utc:
                    scheduled_prep = now_utc

                job_id = uuid.uuid4()
                await session.execute(
                    text("""
                    INSERT INTO public.background_jobs (
                        id, user_id, job_type, resource_id, idempotency_key,
                        payload, status, priority, max_attempts, scheduled_for
                    )
                    VALUES (
                        :j_id, :u_id, 'prep_meeting', :res_id, :idem_key,
                        CAST(:payload AS JSONB), 'queued', 10, 3, :sched_for
                    )
                    ON CONFLICT (idempotency_key) DO UPDATE SET updated_at = NOW();
                    """),
                    {
                        "j_id": str(job_id),
                        "u_id": user_id,
                        "res_id": str(meeting_id),
                        "idem_key": f"prep_meeting_{meeting_id}_v{meeting['meeting_version']}",
                        "payload": json.dumps({"meeting_id": str(meeting_id), "meeting_version": meeting["meeting_version"]}),
                        "sched_for": scheduled_prep
                    }
                )
                await session.execute(
                    text("UPDATE public.meetings SET active_prep_job_id = :j_id WHERE id = :m_id;"),
                    {"j_id": str(job_id), "m_id": str(meeting_id)}
                )
                meeting["active_prep_job_id"] = str(job_id)

        return meeting

@router.get("", response_model=List[MeetingResponse])
async def list_meetings(
    status_filter: Optional[str] = Query(None, alias="status"),
    project_id: Optional[UUID] = None,
    user_id: str = Depends(get_current_user_id)
):
    async with get_tenant_session(user_id) as session:
        query = "SELECT * FROM public.meetings WHERE user_id = :user_id"
        params = {"user_id": user_id}

        if status_filter:
            query += " AND status = :status"
            params["status"] = status_filter
        if project_id:
            query += " AND project_id = :project_id"
            params["project_id"] = str(project_id)

        query += " ORDER BY start_time ASC;"
        res = await session.execute(text(query), params)
        return [dict(r) for r in res.mappings().all()]

@router.get("/{meeting_id}", response_model=MeetingDetailResponse)
async def get_meeting(
    meeting_id: UUID,
    user_id: str = Depends(get_current_user_id)
):
    async with get_tenant_session(user_id) as session:
        res = await session.execute(
            text("SELECT * FROM public.meetings WHERE id = :m_id AND user_id = :u_id;"),
            {"m_id": str(meeting_id), "u_id": user_id}
        )
        meeting = res.mappings().first()
        if not meeting:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

        part_res = await session.execute(
            text("SELECT * FROM public.meeting_participants WHERE meeting_id = :m_id AND user_id = :u_id;"),
            {"m_id": str(meeting_id), "u_id": user_id}
        )
        data = dict(meeting)
        data["participants"] = [dict(r) for r in part_res.mappings().all()]
        return data

@router.patch("/{meeting_id}", response_model=MeetingResponse)
async def update_meeting(
    meeting_id: UUID,
    payload: MeetingUpdate,
    user_id: str = Depends(get_current_user_id)
):
    async with get_tenant_session(user_id) as session:
        # Check existence and current version
        res = await session.execute(
            text("SELECT * FROM public.meetings WHERE id = :m_id AND user_id = :u_id FOR UPDATE;"),
            {"m_id": str(meeting_id), "u_id": user_id}
        )
        existing = res.mappings().first()
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

        # Determine if version bump is required (e.g., rescheduled start/end time)
        time_changed = (
            (payload.start_time is not None and payload.start_time != existing["start_time"]) or
            (payload.end_time is not None and payload.end_time != existing["end_time"])
        )
        version_bump = 1 if time_changed else 0

        updates = []
        params = {"m_id": str(meeting_id), "u_id": user_id}

        if payload.title is not None:
            updates.append("title = :title")
            params["title"] = payload.title
        if payload.purpose is not None:
            updates.append("purpose = :purpose")
            params["purpose"] = payload.purpose
        if payload.start_time is not None:
            updates.append("start_time = :start_time")
            params["start_time"] = payload.start_time
        if payload.end_time is not None:
            updates.append("end_time = :end_time")
            params["end_time"] = payload.end_time
        if payload.status is not None:
            updates.append("status = :status")
            params["status"] = payload.status
        if payload.user_importance_override is not None:
            updates.append("user_importance_override = :user_importance_override")
            updates.append("effective_importance = :user_importance_override")
            params["user_importance_override"] = payload.user_importance_override
        if payload.notes is not None:
            updates.append("notes = :notes")
            params["notes"] = payload.notes

        if version_bump:
            updates.append("meeting_version = meeting_version + 1")

        updates.append("updated_at = NOW()")

        query = f"UPDATE public.meetings SET {', '.join(updates)} WHERE id = :m_id AND user_id = :u_id RETURNING *;"
        up_res = await session.execute(text(query), params)
        updated = dict(up_res.mappings().first())

        # If meeting was rescheduled (version bumped), supersede obsolete jobs and re-schedule
        if version_bump:
            await QueueService.supersede_meeting_jobs(user_id, meeting_id, updated["meeting_version"])
            budget_status = await CostService.get_budget_status(user_id)
            if budget_status["status"] not in ("prep_suspended", "hard_stop"):
                pref_res = await session.execute(
                    text("SELECT prep_lead_time_hours FROM public.user_profiles WHERE id = :u_id;"),
                    {"u_id": user_id}
                )
                lead_hours = pref_res.scalar() or 2
                scheduled_prep = updated["start_time"] - timedelta(hours=lead_hours)
                now_utc = datetime.now(timezone.utc)
                if scheduled_prep < now_utc:
                    scheduled_prep = now_utc

                new_job_id = await QueueService.enqueue_job(
                    user_id=user_id,
                    job_type="prep_meeting",
                    resource_id=meeting_id,
                    idempotency_key=f"prep_meeting_{meeting_id}_v{updated['meeting_version']}",
                    payload={"meeting_id": str(meeting_id), "meeting_version": updated["meeting_version"]},
                    scheduled_for=scheduled_prep
                )
                if new_job_id:
                    await session.execute(
                        text("UPDATE public.meetings SET active_prep_job_id = :j_id WHERE id = :m_id;"),
                        {"j_id": str(new_job_id), "m_id": str(meeting_id)}
                    )
                    updated["active_prep_job_id"] = new_job_id

        return updated

@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(
    meeting_id: UUID,
    user_id: str = Depends(get_current_user_id)
):
    async with get_tenant_session(user_id) as session:
        del_res = await session.execute(
            text("DELETE FROM public.meetings WHERE id = :m_id AND user_id = :u_id RETURNING id;"),
            {"m_id": str(meeting_id), "u_id": user_id}
        )
        if not del_res.scalar():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

@router.get("/{meeting_id}/participants", response_model=List[ParticipantResponse])
async def list_meeting_participants(
    meeting_id: UUID,
    user_id: str = Depends(get_current_user_id)
):
    async with get_tenant_session(user_id) as session:
        res = await session.execute(
            text("SELECT * FROM public.meeting_participants WHERE meeting_id = :m_id AND user_id = :u_id;"),
            {"m_id": str(meeting_id), "u_id": user_id}
        )
        return [dict(r) for r in res.mappings().all()]

@router.post("/{meeting_id}/participants", response_model=ParticipantResponse, status_code=status.HTTP_201_CREATED)
async def add_meeting_participant(
    meeting_id: UUID,
    payload: ParticipantCreate,
    user_id: str = Depends(get_current_user_id)
):
    async with get_tenant_session(user_id) as session:
        # Verify meeting belongs to user
        m_check = await session.execute(
            text("SELECT id FROM public.meetings WHERE id = :m_id AND user_id = :u_id;"),
            {"m_id": str(meeting_id), "u_id": user_id}
        )
        if not m_check.scalar():
            raise HTTPException(status_code=404, detail="Meeting not found")

        res = await session.execute(
            text("""
            INSERT INTO public.meeting_participants (user_id, meeting_id, contact_id, name, role, is_organizer)
            VALUES (:u_id, :m_id, :c_id, :name, :role, :is_org)
            RETURNING id, user_id, meeting_id, contact_id, name, role, is_organizer;
            """),
            {
                "u_id": user_id,
                "m_id": str(meeting_id),
                "c_id": str(payload.contact_id) if payload.contact_id else None,
                "name": payload.name,
                "role": payload.role,
                "is_org": payload.is_organizer
            }
        )
        return dict(res.mappings().first())

@router.post("/{meeting_id}/outcomes/analyze", response_model=OutcomeAnalysisResponse)
async def analyze_meeting_outcomes(
    meeting_id: UUID,
    payload: OutcomeAnalysisRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Analyze post-meeting notes and transcript.
    Extracts decisions, proposes commitments (is_confirmed=False), creates follow-up draft,
    marks meeting completed, and settles cost in ledger.
    """
    return await outcome_service.analyze_and_store_outcomes(
        user_id=user_id,
        meeting_id=meeting_id,
        notes=payload.notes,
        transcript=payload.transcript
    )

@router.get("/{meeting_id}/follow-up", response_model=FollowUpDraftResponse)
async def get_follow_up_draft(
    meeting_id: UUID,
    user_id: str = Depends(get_current_user_id)
):
    """
    Get the latest follow-up draft for a meeting.
    Invariant: Draft-only external communications. Zero client-send capability.
    """
    return await outcome_service.get_follow_up_draft(user_id=user_id, meeting_id=meeting_id)

@router.patch("/{meeting_id}/follow-up/{draft_id:uuid}", response_model=FollowUpDraftResponse)
async def update_follow_up_draft(
    meeting_id: UUID,
    draft_id: UUID,
    payload: FollowUpDraftUpdate,
    user_id: str = Depends(get_current_user_id)
):
    """
    Update follow-up draft content or status (draft, reviewed, discarded).
    Invariant: No send endpoint exists.
    """
    return await outcome_service.update_follow_up_draft(
        user_id=user_id,
        draft_id=draft_id,
        payload=payload
    )

class InterMeetingReportRequest(BaseModel):
    report_text: str = Field(..., min_length=5, description="Text describing tasks carried out between meetings")
    filename: Optional[str] = Field("inter_meeting_task_report.txt", description="Report document filename")


@router.get("/{meeting_id}/inter-meeting-context", summary="Get context and candidate reminders between this meeting and prior meeting of same people")
async def get_inter_meeting_context(
    meeting_id: UUID,
    user_id: str = Depends(get_current_user_id)
):
    """
    Finds previous meeting with the same participants and candidate reminders to track.
    """
    return await inter_meeting_service.get_inter_meeting_context(
        user_id=user_id,
        meeting_id=meeting_id
    )


@router.post("/{meeting_id}/task-report", response_model=InterMeetingReportSyncResponse, summary="Ingest inter-meeting task report (JSON) and sync reminders")
async def ingest_task_report_json(
    meeting_id: UUID,
    payload: InterMeetingReportRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Ingests text report of tasks carried out between 2 meetings of the same people,
    and synchronizes reminder statuses in database & briefing.
    """
    return await inter_meeting_service.sync_task_report(
        user_id=user_id,
        meeting_id=meeting_id,
        report_text=payload.report_text,
        filename=payload.filename or "inter_meeting_task_report.txt"
    )


@router.post("/{meeting_id}/task-report/upload", response_model=InterMeetingReportSyncResponse, summary="Upload inter-meeting task report file (PDF/DOCX/TXT) and sync reminders")
async def upload_task_report_file(
    meeting_id: UUID,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id)
):
    """
    Uploads a file (PDF, DOCX, TXT, MD) containing tasks carried out between meetings,
    extracts contents, and synchronizes reminders & briefing.
    """
    raw_content = await file.read()
    file_type = DocumentService.validate_file(raw_content, file.filename or "unknown.txt")
    extraction = DocumentService.extract_text(raw_content, file_type)
    text_content = extraction.text

    return await inter_meeting_service.sync_task_report(
        user_id=user_id,
        meeting_id=meeting_id,
        report_text=text_content,
        filename=file.filename or "inter_meeting_task_report.txt",
        file_content=raw_content
    )


@router.api_route("/{meeting_id}/follow-up/send", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
@router.api_route("/{meeting_id}/send-follow-up", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
async def no_send_endpoint_forbidden():
    """Invariant enforcement: Zero email send endpoints exist."""
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Send endpoint does not exist. System is draft-only.")
