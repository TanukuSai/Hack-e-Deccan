"""
Calendar Sync Service
======================
Orchestrates calendar synchronization for a tenant.
Uses incremental sync via integration_sync_state table.

Flow:
1. Load OAuth tokens from tenant_integrations
2. Call GoogleCalendarProvider.get_sync_result()
3. For each event: upsert to meetings table
4. For new/updated meetings: enqueue prep jobs via QueueService
5. Update integration_sync_state with new sync token
6. Update meeting_integrations.last_sync_at and health

Security:
- OAuth tokens retrieved under tenant RLS session
- Never logs token values
- Sanitized error messages only
"""
import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import text

from apps.api.app.core.db import get_tenant_session
from apps.api.app.providers.calendar_provider import (
    CalendarEvent, CalendarProvider, GoogleCalendarProvider, SyncResult, get_calendar_provider
)
from apps.api.app.services.queue_service import QueueService

logger = logging.getLogger(__name__)

# Lookahead window for upcoming meetings to enqueue prep jobs
PREP_LOOKAHEAD_HOURS = 48


class CalendarSyncService:
    """
    Tenant-scoped calendar synchronization service.
    Handles incremental sync, meeting upserts, and prep job scheduling.
    """

    async def sync_for_user(
        self,
        user_id: str,
        force_full_sync: bool = False
    ) -> Dict[str, Any]:
        """
        Run incremental calendar sync for a user.
        Returns summary dict with counts and next_sync_token.
        """
        # 1. Load integration credentials
        integration = await self._load_integration(user_id, "google_calendar")
        if not integration:
            return {"error": "google_calendar integration not configured"}

        access_token = integration.get("oauth_token_encrypted")
        if not access_token:
            return {"error": "No valid access token available"}

        # 2. Load sync state
        sync_state = await self._load_sync_state(user_id, "google_calendar", "events")
        sync_token = None if force_full_sync else sync_state.get("sync_token")
        sync_anchor = sync_state.get("sync_anchor") if not sync_token else None

        # 3. Perform sync via provider
        provider = GoogleCalendarProvider()
        result: SyncResult = await provider.get_sync_result(
            access_token=access_token,
            sync_token=sync_token,
            sync_anchor=sync_anchor,
        )

        if result.error:
            await self._update_integration_health(user_id, "google_calendar", "error", result.error[:200])
            return {"error": result.error}

        # 4. Upsert events into meetings table
        meetings_created, meetings_updated, meetings_cancelled = 0, 0, 0
        prep_jobs_queued = 0
        now = datetime.now(timezone.utc)

        for event in result.events_updated:
            was_created, meeting_id, meeting_version = await self._upsert_meeting(user_id, event)
            if was_created:
                meetings_created += 1
            else:
                meetings_updated += 1

            # Enqueue prep job for upcoming meetings
            if meeting_id and event.start_time > now and event.start_time < now + timedelta(hours=PREP_LOOKAHEAD_HOURS):
                await self._enqueue_prep_job(user_id, meeting_id, meeting_version)
                prep_jobs_queued += 1

        for cancelled_event_id in result.events_cancelled:
            await self._cancel_meeting_by_calendar_id(user_id, cancelled_event_id)
            meetings_cancelled += 1

        # 5. Update sync state
        await self._save_sync_state(
            user_id, "google_calendar", "events",
            sync_token=result.next_sync_token,
            sync_anchor=now,
        )

        # 6. Update integration health
        await self._update_integration_health(user_id, "google_calendar", "healthy")

        summary = {
            "provider": "google_calendar",
            "meetings_created": meetings_created,
            "meetings_updated": meetings_updated,
            "meetings_cancelled": meetings_cancelled,
            "prep_jobs_queued": prep_jobs_queued,
            "sync_token_updated": result.next_sync_token is not None,
        }
        logger.info(f"[CalendarSync] user={user_id}: {summary}")
        return summary

    # -------------------------------------------------------------------------
    # DB helpers (all tenant-scoped)
    # -------------------------------------------------------------------------

    async def _load_integration(self, user_id: str, integration_type: str) -> Optional[Dict[str, Any]]:
        async with get_tenant_session(user_id) as session:
            res = await session.execute(
                text("""
                    SELECT oauth_token_encrypted, refresh_token_encrypted, token_expires_at,
                           attendance_mode, transcript_capture_enabled, attendance_rules
                    FROM public.meeting_integrations
                    WHERE user_id = :u_id AND integration_type = :t AND is_enabled = true;
                """),
                {"u_id": user_id, "t": integration_type}
            )
            row = res.mappings().first()
            return dict(row) if row else None

    async def _load_sync_state(self, user_id: str, integration_type: str, resource_type: str) -> Dict[str, Any]:
        async with get_tenant_session(user_id) as session:
            res = await session.execute(
                text("""
                    SELECT sync_token, sync_anchor, last_full_sync_at, last_incremental_sync_at
                    FROM public.integration_sync_state
                    WHERE user_id = :u_id AND integration_type = :t AND resource_type = :r;
                """),
                {"u_id": user_id, "t": integration_type, "r": resource_type}
            )
            row = res.mappings().first()
            return dict(row) if row else {}

    async def _save_sync_state(
        self,
        user_id: str,
        integration_type: str,
        resource_type: str,
        sync_token: Optional[str],
        sync_anchor: Optional[datetime],
    ) -> None:
        async with get_tenant_session(user_id) as session:
            await session.execute(
                text("""
                    INSERT INTO public.integration_sync_state (
                        user_id, integration_type, resource_type,
                        sync_token, sync_anchor, last_incremental_sync_at
                    ) VALUES (
                        :u_id, :t, :r, :token, :anchor, NOW()
                    )
                    ON CONFLICT (user_id, integration_type, resource_type) DO UPDATE
                    SET sync_token = EXCLUDED.sync_token,
                        sync_anchor = COALESCE(EXCLUDED.sync_anchor, integration_sync_state.sync_anchor),
                        last_incremental_sync_at = NOW(),
                        updated_at = NOW();
                """),
                {"u_id": user_id, "t": integration_type, "r": resource_type,
                 "token": sync_token, "anchor": sync_anchor}
            )

    async def _upsert_meeting(
        self, user_id: str, event: CalendarEvent
    ) -> Tuple[bool, Optional[str], Optional[int]]:
        """
        Upsert a CalendarEvent into meetings table.
        Returns (was_created, meeting_id, meeting_version).
        """
        async with get_tenant_session(user_id) as session:
            # Check existing
            res = await session.execute(
                text("""
                    SELECT id, meeting_version, start_time, end_time
                    FROM public.meetings
                    WHERE user_id = :u_id AND calendar_event_id = :ev_id;
                """),
                {"u_id": user_id, "ev_id": event.provider_event_id}
            )
            existing = res.mappings().first()

            attendees_json = json.dumps([{"email": e} for e in event.attendee_emails[:50]])
            status = "cancelled" if event.status == "cancelled" else "upcoming"

            if existing:
                # Update if times or title changed
                if (
                    existing["start_time"] != event.start_time
                    or existing["end_time"] != event.end_time
                ):
                    upd = await session.execute(
                        text("""
                            UPDATE public.meetings
                            SET title = :title, start_time = :start, end_time = :end,
                                join_url = :join_url, status = :status,
                                meeting_version = meeting_version + 1,
                                sync_last_seen_at = NOW(), updated_at = NOW()
                            WHERE id = :m_id AND user_id = :u_id
                            RETURNING id, meeting_version;
                        """),
                        {
                            "title": event.title[:500],
                            "start": event.start_time,
                            "end": event.end_time,
                            "join_url": event.join_url,
                            "status": status,
                            "m_id": str(existing["id"]),
                            "u_id": user_id,
                        }
                    )
                    row = upd.mappings().first()
                    return False, str(row["id"]), row["meeting_version"]
                else:
                    # Touch sync timestamp only
                    await session.execute(
                        text("UPDATE public.meetings SET sync_last_seen_at = NOW() WHERE id = :m_id AND user_id = :u_id;"),
                        {"m_id": str(existing["id"]), "u_id": user_id}
                    )
                    return False, str(existing["id"]), existing["meeting_version"]
            else:
                # Create new meeting
                ins = await session.execute(
                    text("""
                        INSERT INTO public.meetings (
                            user_id, title, start_time, end_time, join_url,
                            status, calendar_event_id, calendar_source, sync_last_seen_at
                        ) VALUES (
                            :u_id, :title, :start, :end, :join_url,
                            :status, :ev_id, :src, NOW()
                        )
                        RETURNING id, meeting_version;
                    """),
                    {
                        "u_id": user_id,
                        "title": event.title[:500],
                        "start": event.start_time,
                        "end": event.end_time,
                        "join_url": event.join_url,
                        "status": status,
                        "ev_id": event.provider_event_id,
                        "src": event.provider,
                    }
                )
                row = ins.mappings().first()
                return True, str(row["id"]), row["meeting_version"]

    async def _cancel_meeting_by_calendar_id(self, user_id: str, calendar_event_id: str) -> None:
        async with get_tenant_session(user_id) as session:
            await session.execute(
                text("""
                    UPDATE public.meetings
                    SET status = 'cancelled', meeting_version = meeting_version + 1,
                        sync_last_seen_at = NOW(), updated_at = NOW()
                    WHERE user_id = :u_id AND calendar_event_id = :ev_id;
                """),
                {"u_id": user_id, "ev_id": calendar_event_id}
            )

    async def _enqueue_prep_job(self, user_id: str, meeting_id: str, meeting_version: int) -> None:
        try:
            await QueueService.enqueue(
                user_id=user_id,
                job_type="prep_meeting",
                resource_id=meeting_id,
                payload={"meeting_version": meeting_version, "triggered_by": "calendar_sync"},
                idempotency_key=f"prep_{meeting_id}_v{meeting_version}",
            )
        except Exception as exc:
            logger.warning(f"[CalendarSync] Failed to enqueue prep job for meeting {meeting_id}: {exc}")

    async def _update_integration_health(
        self, user_id: str, integration_type: str,
        health_status: str, error_message: Optional[str] = None
    ) -> None:
        async with get_tenant_session(user_id) as session:
            await session.execute(
                text("""
                    UPDATE public.meeting_integrations
                    SET health_status = :status,
                        health_last_checked_at = NOW(),
                        health_error_message = :err,
                        last_sync_at = CASE WHEN :status = 'healthy' THEN NOW() ELSE last_sync_at END,
                        updated_at = NOW()
                    WHERE user_id = :u_id AND integration_type = :t;
                """),
                {"u_id": user_id, "t": integration_type, "status": health_status, "err": error_message}
            )
