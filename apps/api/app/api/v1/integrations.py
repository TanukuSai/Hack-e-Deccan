import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from apps.api.app.core.db import get_tenant_session
from apps.api.app.core.security import get_current_user_id
from apps.api.app.services.calendar_sync_service import CalendarSyncService
from apps.api.app.services.google_oauth_service import GoogleOAuthService
from apps.api.app.services.queue_service import QueueService
from apps.api.app.services.transcript_service import (
    TranscriptIngestRequest, TranscriptIngestionService
)
from sqlalchemy import text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])
google_service = GoogleOAuthService()
calendar_sync_service = CalendarSyncService()
transcript_service = TranscriptIngestionService()


# ─────────────────────────────────────────────────────────────────────────────
# Google OAuth
# ─────────────────────────────────────────────────────────────────────────────

class GoogleCallbackPayload(BaseModel):
    code: str = Field(..., description="Authorization code returned by Google OAuth redirect")
    redirect_uri: str = Field(..., description="Redirect URI registered in Google Console")

class GoogleAuthUrlResponse(BaseModel):
    authorization_url: str
    scopes: list[str]

@router.get("/google/auth-url", response_model=GoogleAuthUrlResponse)
async def get_google_auth_url(
    redirect_uri: str = Query(..., description="Redirect URI for Google callback"),
    state: Optional[str] = Query(None, description="Optional CSRF state parameter"),
    user_id: str = Depends(get_current_user_id)
):
    """Generates the Google OAuth 2.0 consent URL for Calendar and Docs access."""
    url = google_service.get_authorization_url(redirect_uri=redirect_uri, state=state)
    return {"authorization_url": url, "scopes": google_service.DEFAULT_SCOPES}

@router.post("/google/callback")
async def handle_google_callback(
    payload: GoogleCallbackPayload,
    user_id: str = Depends(get_current_user_id)
):
    """Exchanges authorization code for Google access/refresh tokens."""
    return await google_service.handle_oauth_callback(
        user_id=user_id, code=payload.code, redirect_uri=payload.redirect_uri
    )

@router.get("/google/status")
async def get_google_status(user_id: str = Depends(get_current_user_id)):
    """Returns current Google Workspace integration status."""
    return await google_service.get_integration_status(user_id=user_id)

@router.post("/google/disconnect")
async def disconnect_google(user_id: str = Depends(get_current_user_id)):
    """Disconnects Google integration and revokes credentials."""
    success = await google_service.disconnect(user_id=user_id)
    return {"provider": "google", "status": "disconnected", "success": success}


# ─────────────────────────────────────────────────────────────────────────────
# Meeting Integrations Configuration
# ─────────────────────────────────────────────────────────────────────────────

class MeetingIntegrationConfig(BaseModel):
    attendance_mode: str = Field("disabled", description="disabled | manual | automatic")
    is_enabled: bool = False
    join_before_minutes: int = Field(2, ge=0, le=30)
    auto_leave_on_end: bool = True
    transcript_capture_enabled: bool = False
    allowed_meeting_types: List[str] = Field(default_factory=list)
    eligible_platforms: List[str] = Field(default_factory=list)
    attendance_rules: Dict[str, Any] = Field(default_factory=dict)


@router.get("/meeting/{integration_type}", summary="Get meeting integration config")
async def get_meeting_integration(
    integration_type: str,
    user_id: str = Depends(get_current_user_id)
):
    """Returns configuration for a specific meeting integration type."""
    async with get_tenant_session(user_id) as session:
        res = await session.execute(
            text("""
                SELECT id, integration_type, attendance_mode, is_enabled,
                       join_before_minutes, auto_leave_on_end, transcript_capture_enabled,
                       allowed_meeting_types, eligible_platforms, health_status,
                       last_sync_at, health_last_checked_at, health_error_message,
                       created_at, updated_at
                FROM public.meeting_integrations
                WHERE user_id = :u_id AND integration_type = :t;
            """),
            {"u_id": user_id, "t": integration_type}
        )
        row = res.mappings().first()
        if not row:
            return {"integration_type": integration_type, "is_enabled": False, "status": "not_configured"}
        return dict(row)


@router.put("/meeting/{integration_type}", summary="Configure meeting integration")
async def configure_meeting_integration(
    integration_type: str,
    config: MeetingIntegrationConfig,
    user_id: str = Depends(get_current_user_id)
):
    """Creates or updates meeting integration configuration for a user."""
    valid_types = {"google_meet", "microsoft_teams", "zoom", "openclaw"}
    if integration_type not in valid_types:
        raise HTTPException(status_code=422, detail=f"Unsupported integration type. Valid: {valid_types}")
    valid_modes = {"disabled", "manual", "automatic"}
    if config.attendance_mode not in valid_modes:
        raise HTTPException(status_code=422, detail=f"Invalid attendance_mode. Valid: {valid_modes}")

    async with get_tenant_session(user_id) as session:
        await session.execute(
            text("""
                INSERT INTO public.meeting_integrations (
                    user_id, integration_type, attendance_mode, is_enabled,
                    join_before_minutes, auto_leave_on_end, transcript_capture_enabled,
                    allowed_meeting_types, eligible_platforms, attendance_rules
                ) VALUES (
                    :u_id, :t, :mode, :enabled,
                    :before, :leave, :transcript,
                    :mtypes, :platforms, CAST(:rules AS JSONB)
                )
                ON CONFLICT (user_id, integration_type) DO UPDATE
                SET attendance_mode = EXCLUDED.attendance_mode,
                    is_enabled = EXCLUDED.is_enabled,
                    join_before_minutes = EXCLUDED.join_before_minutes,
                    auto_leave_on_end = EXCLUDED.auto_leave_on_end,
                    transcript_capture_enabled = EXCLUDED.transcript_capture_enabled,
                    allowed_meeting_types = EXCLUDED.allowed_meeting_types,
                    eligible_platforms = EXCLUDED.eligible_platforms,
                    attendance_rules = EXCLUDED.attendance_rules,
                    updated_at = NOW()
                RETURNING id;
            """),
            {
                "u_id": user_id, "t": integration_type, "mode": config.attendance_mode,
                "enabled": config.is_enabled, "before": config.join_before_minutes,
                "leave": config.auto_leave_on_end, "transcript": config.transcript_capture_enabled,
                "mtypes": config.allowed_meeting_types, "platforms": config.eligible_platforms,
                "rules": json.dumps(config.attendance_rules),
            }
        )
    return {"status": "configured", "integration_type": integration_type, **config.model_dump()}


@router.delete("/meeting/{integration_type}", summary="Remove meeting integration config")
async def remove_meeting_integration(
    integration_type: str,
    user_id: str = Depends(get_current_user_id)
):
    """Removes meeting integration configuration and revokes any stored credentials."""
    async with get_tenant_session(user_id) as session:
        res = await session.execute(
            text("""
                DELETE FROM public.meeting_integrations
                WHERE user_id = :u_id AND integration_type = :t RETURNING id;
            """),
            {"u_id": user_id, "t": integration_type}
        )
        deleted = res.scalar()
    return {"status": "removed" if deleted else "not_found", "integration_type": integration_type}


# ─────────────────────────────────────────────────────────────────────────────
# Calendar Synchronization
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/calendar/sync", summary="Trigger calendar synchronization")
async def trigger_calendar_sync(
    force_full: bool = Query(False, description="Force full resync discarding sync token"),
    user_id: str = Depends(get_current_user_id)
):
    """Enqueues a calendar sync job. Results are reflected asynchronously."""
    await QueueService.enqueue(
        user_id=user_id,
        job_type="calendar_sync",
        resource_id=user_id,
        payload={"force_full_sync": force_full},
        idempotency_key=f"calendar_sync_{user_id}",
    )
    return {"status": "queued", "job_type": "calendar_sync", "force_full_sync": force_full}


@router.get("/calendar/sync-state", summary="Get calendar sync state")
async def get_calendar_sync_state(user_id: str = Depends(get_current_user_id)):
    """Returns the current sync state for calendar integrations."""
    async with get_tenant_session(user_id) as session:
        res = await session.execute(
            text("""
                SELECT integration_type, resource_type, sync_anchor,
                       last_full_sync_at, last_incremental_sync_at,
                       consecutive_errors, last_error
                FROM public.integration_sync_state WHERE user_id = :u_id;
            """),
            {"u_id": user_id}
        )
        rows = [dict(r) for r in res.mappings().all()]
    return {"sync_states": rows}


# ─────────────────────────────────────────────────────────────────────────────
# Meeting Attendance Sessions
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/attendance/{meeting_id}", summary="Get attendance session for a meeting")
async def get_attendance_session(
    meeting_id: UUID,
    user_id: str = Depends(get_current_user_id)
):
    """Returns the current or most recent attendance session for a meeting."""
    async with get_tenant_session(user_id) as session:
        res = await session.execute(
            text("""
                SELECT id, status, provider, provider_session_id,
                       scheduled_at, joined_at, completed_at,
                       transcript_requested, transcript_delivered,
                       failure_reason, retry_count, created_at, updated_at
                FROM public.meeting_attendance_sessions
                WHERE user_id = :u_id AND meeting_id = :m_id
                ORDER BY created_at DESC LIMIT 1;
            """),
            {"u_id": user_id, "m_id": str(meeting_id)}
        )
        row = res.mappings().first()
        if not row:
            return {"meeting_id": str(meeting_id), "status": "no_session"}
        return dict(row)


class ManualAttendanceRequest(BaseModel):
    transcript_capture: bool = False
    consent_verified: bool = False


@router.post("/attendance/{meeting_id}/request", summary="Manually request bot attendance")
async def request_manual_attendance(
    meeting_id: UUID,
    payload: ManualAttendanceRequest,
    user_id: str = Depends(get_current_user_id)
):
    """
    Manually requests the agent bot to join a specific meeting.
    Consent must be verified if transcript capture is requested.
    """
    if payload.transcript_capture and not payload.consent_verified:
        raise HTTPException(
            status_code=422,
            detail="Transcript capture requires explicit participant consent verification"
        )
    async with get_tenant_session(user_id) as session:
        res = await session.execute(
            text("SELECT id, join_url, meeting_version FROM public.meetings WHERE id = :m_id AND user_id = :u_id;"),
            {"m_id": str(meeting_id), "u_id": user_id}
        )
        meeting = res.mappings().first()
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")
        if not meeting["join_url"]:
            raise HTTPException(status_code=422, detail="Meeting has no accessible join URL")

        ins = await session.execute(
            text("""
                INSERT INTO public.meeting_attendance_sessions (
                    user_id, meeting_id, meeting_version, status,
                    provider, transcript_requested, consent_verified
                ) VALUES (:u_id, :m_id, :m_ver, 'eligible', 'openclaw', :transcript, :consent)
                ON CONFLICT DO NOTHING RETURNING id;
            """),
            {
                "u_id": user_id, "m_id": str(meeting_id),
                "m_ver": meeting["meeting_version"],
                "transcript": payload.transcript_capture, "consent": payload.consent_verified,
            }
        )
        session_id = ins.scalar()
    return {
        "status": "eligible", "meeting_id": str(meeting_id),
        "session_id": str(session_id) if session_id else None,
        "transcript_requested": payload.transcript_capture,
    }


@router.delete("/attendance/{meeting_id}/cancel", summary="Cancel pending attendance session")
async def cancel_attendance_session(
    meeting_id: UUID,
    user_id: str = Depends(get_current_user_id)
):
    """Cancels a pending or eligible attendance session for a meeting."""
    async with get_tenant_session(user_id) as session:
        await session.execute(
            text("""
                UPDATE public.meeting_attendance_sessions
                SET status = 'cancelled', completed_at = NOW(), updated_at = NOW()
                WHERE user_id = :u_id AND meeting_id = :m_id
                  AND status NOT IN ('completed', 'failed', 'cancelled');
            """),
            {"u_id": user_id, "m_id": str(meeting_id)}
        )
    return {"status": "cancelled", "meeting_id": str(meeting_id)}


# ─────────────────────────────────────────────────────────────────────────────
# Transcript Management
# ─────────────────────────────────────────────────────────────────────────────

class ManualTranscriptUpload(BaseModel):
    meeting_id: UUID
    transcript_text: str = Field(..., min_length=10, description="Full transcript text")
    source_platform: Optional[str] = Field(None, description="Platform: google_meet, zoom, teams")
    completeness: str = Field("unknown", description="partial | complete | unknown")
    consent_verified: bool = False
    retention_policy: str = "standard"


@router.post("/transcripts/upload", summary="Upload a meeting transcript manually")
async def upload_transcript(
    payload: ManualTranscriptUpload,
    user_id: str = Depends(get_current_user_id)
):
    """
    Ingest a manually uploaded transcript for a meeting.
    Duplicate content is detected and rejected gracefully.
    Analysis job is automatically queued on successful ingestion.
    """
    if not payload.consent_verified:
        raise HTTPException(
            status_code=422,
            detail="Transcript upload requires explicit participant consent verification"
        )

    async with get_tenant_session(user_id) as session:
        res = await session.execute(
            text("SELECT id, meeting_version FROM public.meetings WHERE id = :m_id AND user_id = :u_id;"),
            {"m_id": str(payload.meeting_id), "u_id": user_id}
        )
        meeting = res.mappings().first()
        if not meeting:
            raise HTTPException(status_code=404, detail="Meeting not found")

    req = TranscriptIngestRequest(
        user_id=user_id,
        meeting_id=str(payload.meeting_id),
        meeting_version=meeting["meeting_version"],
        source_type="manual_upload",
        source_platform=payload.source_platform,
        normalized_text=payload.transcript_text,
        completeness=payload.completeness,
        consent_verified=payload.consent_verified,
        retention_policy=payload.retention_policy,
    )
    result = await transcript_service.ingest(req)
    if not result.success:
        raise HTTPException(status_code=422, detail=result.error or "Ingestion failed")

    if not result.duplicate and result.transcript_source_id:
        await QueueService.enqueue(
            user_id=user_id,
            job_type="transcript_analysis",
            resource_id=str(payload.meeting_id),
            payload={"transcript_source_id": result.transcript_source_id},
            idempotency_key=f"analysis_{result.transcript_source_id}",
        )
    return {
        "transcript_source_id": result.transcript_source_id,
        "duplicate": result.duplicate,
        "segments_ingested": result.segments_ingested,
        "analysis_job_queued": not result.duplicate,
    }


@router.get("/transcripts/{meeting_id}", summary="List transcripts for a meeting")
async def list_meeting_transcripts(
    meeting_id: UUID,
    user_id: str = Depends(get_current_user_id)
):
    """Returns all transcript sources available for a meeting."""
    async with get_tenant_session(user_id) as session:
        res = await session.execute(
            text("""
                SELECT id, source_type, source_platform, completeness,
                       processing_status, consent_verified, retrieved_at,
                       meeting_started_at, meeting_ended_at, participants
                FROM public.transcript_sources
                WHERE user_id = :u_id AND meeting_id = :m_id
                ORDER BY retrieved_at DESC;
            """),
            {"u_id": user_id, "m_id": str(meeting_id)}
        )
        rows = [dict(r) for r in res.mappings().all()]
    return {"meeting_id": str(meeting_id), "transcripts": rows}


# ─────────────────────────────────────────────────────────────────────────────
# Integration Health Overview
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/health", summary="Integration health overview")
async def get_integration_health(user_id: str = Depends(get_current_user_id)):
    """Returns health status of all configured meeting and calendar integrations."""
    async with get_tenant_session(user_id) as session:
        res = await session.execute(
            text("""
                SELECT integration_type, is_enabled, attendance_mode,
                       health_status, health_last_checked_at, health_error_message,
                       last_sync_at, transcript_capture_enabled
                FROM public.meeting_integrations WHERE user_id = :u_id;
            """),
            {"u_id": user_id}
        )
        integrations = [dict(r) for r in res.mappings().all()]
    return {
        "integrations": integrations,
        "total": len(integrations),
        "healthy_count": sum(1 for i in integrations if i["health_status"] == "healthy"),
    }
