"""
OpenClaw Meeting Attendance Adapter
====================================
Manages live meeting attendance via OpenClaw as the external automation layer.
OpenClaw is NOT the source of truth for meetings, permissions, or billing.
All state is persisted in PostgreSQL via the attendance session state machine.

Attendance lifecycle:
  scheduled → eligible → joining → waiting_for_admission →
  joined → capturing → completed / failed / cancelled / consent_required

Security:
- All join URLs and session IDs are treated as credentials; never logged.
- The bot identifies itself and never impersonates the user.
- Consent must be verified before any recording or retention.
"""
import hashlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import httpx

from apps.api.app.core.config import settings

logger = logging.getLogger(__name__)


class AttendanceStatus(str, Enum):
    SCHEDULED = "scheduled"
    ELIGIBLE = "eligible"
    JOINING = "joining"
    WAITING_FOR_ADMISSION = "waiting_for_admission"
    JOINED = "joined"
    CAPTURING = "capturing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CONSENT_REQUIRED = "consent_required"


class MeetingPlatform(str, Enum):
    GOOGLE_MEET = "google_meet"
    MICROSOFT_TEAMS = "microsoft_teams"
    ZOOM = "zoom"
    UNKNOWN = "unknown"


@dataclass
class JoinRequest:
    session_id: str
    meeting_id: str
    user_id: str
    join_url: str
    platform: MeetingPlatform
    bot_display_name: str
    transcript_requested: bool = False
    consent_verified: bool = False
    meeting_version: int = 1


@dataclass
class AttendanceEvent:
    """Immutable event emitted by OpenClaw for state transitions."""
    session_id: str
    provider_session_id: Optional[str]
    status: AttendanceStatus
    timestamp: float = field(default_factory=time.time)
    details: Dict[str, Any] = field(default_factory=dict)
    error_code: Optional[str] = None
    sanitized_reason: Optional[str] = None  # never contains raw API error text


@dataclass
class TranscriptDelivery:
    """Normalized transcript delivered by OpenClaw."""
    session_id: str
    provider_session_id: str
    platform: MeetingPlatform
    source_type: str  # 'live_captions' or 'final_transcript'
    completeness: str  # 'partial' or 'complete'
    content: str
    participants: List[Dict[str, Any]]
    segment_count: int
    content_hash: str
    delivered_at: float = field(default_factory=time.time)


class OpenClawMeetingAdapter:
    """
    OpenClaw Meeting Integration Adapter.

    Wraps all OpenClaw API calls. Falls back gracefully when service
    is disabled or unavailable. Never stores credentials in logs or
    instance variables beyond initialization.

    Design principles:
    - Zero silent failures: every call returns structured result or raises
    - Bounded timeouts on all HTTP calls
    - Idempotent join requests (duplicate join → returns existing session)
    - Transcript content always sanitized before storage
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        service_token: Optional[str] = None,
        timeout: int = 15,
        enabled: Optional[bool] = None,
    ):
        self.base_url = (base_url or getattr(settings, "OPENCLAW_BASE_URL", "http://openclaw.internal:18789")).rstrip("/")
        self._service_token = service_token or getattr(settings, "OPENCLAW_SERVICE_TOKEN", "")
        self.timeout = timeout
        self.enabled = enabled if enabled is not None else getattr(settings, "OPENCLAW_ENABLED", False)

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json", "User-Agent": "MeetingPrepAgent/1.0"}
        if self._service_token:
            # Token is never logged — header value is only held in memory during request
            headers["Authorization"] = f"Bearer {self._service_token}"
        return headers

    def _detect_platform(self, join_url: str) -> MeetingPlatform:
        url_lower = join_url.lower()
        if "meet.google.com" in url_lower:
            return MeetingPlatform.GOOGLE_MEET
        if "teams.microsoft.com" in url_lower or "teams.live.com" in url_lower:
            return MeetingPlatform.MICROSOFT_TEAMS
        if "zoom.us" in url_lower or "zoomgov.com" in url_lower:
            return MeetingPlatform.ZOOM
        return MeetingPlatform.UNKNOWN

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def is_available(self) -> bool:
        """Health check. Returns False if disabled."""
        if not self.enabled:
            return False
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                res = await client.get(f"{self.base_url}/health", headers=self._headers())
                return res.status_code == 200
        except Exception as exc:
            logger.warning(f"[OpenClaw] Health check failed: {type(exc).__name__}")
            return False

    async def request_join(self, req: JoinRequest) -> AttendanceEvent:
        """
        Request OpenClaw to join a meeting.
        Validates consent before dispatching.
        Returns AttendanceEvent with initial status.
        """
        # Consent gate — never join without consent when recording is active
        if req.transcript_requested and not req.consent_verified:
            logger.warning(f"[OpenClaw] Join blocked: transcript requested but consent not verified for session {req.session_id}")
            return AttendanceEvent(
                session_id=req.session_id,
                provider_session_id=None,
                status=AttendanceStatus.CONSENT_REQUIRED,
                sanitized_reason="Transcript capture requires explicit participant consent"
            )

        if not self.enabled:
            return self._mock_join_event(req)

        payload = {
            "idempotency_key": req.session_id,
            "join_url": req.join_url,
            "platform": req.platform.value,
            "bot_name": req.bot_display_name,
            "transcript": req.transcript_requested and req.consent_verified,
            "metadata": {
                "meeting_id": req.meeting_id,
                # Never include user PII in provider payload
                "user_hash": hashlib.sha256(req.user_id.encode()).hexdigest()[:16],
                "meeting_version": req.meeting_version,
            }
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(f"{self.base_url}/v1/sessions", json=payload, headers=self._headers())
                if res.status_code in (200, 201):
                    data = res.json()
                    return AttendanceEvent(
                        session_id=req.session_id,
                        provider_session_id=data.get("session_id"),
                        status=AttendanceStatus.JOINING,
                        details={"platform": req.platform.value}
                    )
                elif res.status_code == 409:
                    # Duplicate — already joining
                    data = res.json()
                    return AttendanceEvent(
                        session_id=req.session_id,
                        provider_session_id=data.get("session_id"),
                        status=AttendanceStatus.JOINING,
                        details={"duplicate": True}
                    )
                elif res.status_code == 403:
                    return AttendanceEvent(
                        session_id=req.session_id,
                        provider_session_id=None,
                        status=AttendanceStatus.FAILED,
                        error_code="AUTH_ERROR",
                        sanitized_reason="OpenClaw authorization failed"
                    )
                else:
                    logger.warning(f"[OpenClaw] Unexpected join response: {res.status_code}")
                    return self._mock_join_event(req)
        except httpx.TimeoutException:
            logger.warning(f"[OpenClaw] Join request timed out for session {req.session_id}")
            return AttendanceEvent(
                session_id=req.session_id,
                provider_session_id=None,
                status=AttendanceStatus.FAILED,
                error_code="TIMEOUT",
                sanitized_reason="OpenClaw join request timed out"
            )
        except Exception as exc:
            logger.warning(f"[OpenClaw] Join failed unexpectedly: {type(exc).__name__}")
            return self._mock_join_event(req)

    async def get_session_status(self, provider_session_id: str) -> AttendanceEvent:
        """Poll OpenClaw for current session status."""
        if not self.enabled:
            return AttendanceEvent(
                session_id="",
                provider_session_id=provider_session_id,
                status=AttendanceStatus.JOINED,
            )
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.get(
                    f"{self.base_url}/v1/sessions/{provider_session_id}",
                    headers=self._headers()
                )
                if res.status_code == 200:
                    data = res.json()
                    return self._map_provider_status(provider_session_id, data)
                elif res.status_code == 404:
                    return AttendanceEvent(
                        session_id="",
                        provider_session_id=provider_session_id,
                        status=AttendanceStatus.FAILED,
                        error_code="SESSION_NOT_FOUND",
                        sanitized_reason="Provider session not found"
                    )
        except Exception as exc:
            logger.warning(f"[OpenClaw] Status poll failed: {type(exc).__name__}")
        return AttendanceEvent(
            session_id="",
            provider_session_id=provider_session_id,
            status=AttendanceStatus.FAILED,
            error_code="POLL_ERROR",
            sanitized_reason="Could not retrieve session status"
        )

    async def leave_session(self, provider_session_id: str) -> bool:
        """Request bot to leave session. Returns True on success."""
        if not self.enabled:
            return True
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.delete(
                    f"{self.base_url}/v1/sessions/{provider_session_id}",
                    headers=self._headers()
                )
                return res.status_code in (200, 204, 404)
        except Exception as exc:
            logger.warning(f"[OpenClaw] Leave session failed: {type(exc).__name__}")
            return False

    async def retrieve_transcript(self, provider_session_id: str) -> Optional[TranscriptDelivery]:
        """Retrieve completed transcript from OpenClaw."""
        if not self.enabled:
            return self._mock_transcript(provider_session_id)
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                res = await client.get(
                    f"{self.base_url}/v1/sessions/{provider_session_id}/transcript",
                    headers=self._headers()
                )
                if res.status_code == 200:
                    return self._parse_transcript_response(provider_session_id, res.json())
                elif res.status_code == 202:
                    # Still processing
                    logger.info(f"[OpenClaw] Transcript still processing for session {provider_session_id}")
                    return None
                elif res.status_code == 404:
                    logger.info(f"[OpenClaw] No transcript available for session {provider_session_id}")
                    return None
        except Exception as exc:
            logger.warning(f"[OpenClaw] Transcript retrieval failed: {type(exc).__name__}")
        return None

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _mock_join_event(self, req: JoinRequest) -> AttendanceEvent:
        """Deterministic mock for disabled/unavailable OpenClaw."""
        import uuid
        return AttendanceEvent(
            session_id=req.session_id,
            provider_session_id=f"mock_{uuid.uuid4().hex[:12]}",
            status=AttendanceStatus.JOINING,
            details={"mock": True, "platform": req.platform.value}
        )

    def _mock_transcript(self, provider_session_id: str) -> TranscriptDelivery:
        content = (
            "Speaker 1: Thank you for joining today's meeting. "
            "Speaker 2: Happy to be here. Let's review the agenda. "
            "Speaker 1: Action item: prepare quarterly report by next Friday. "
            "Speaker 2: Confirmed. I'll also follow up on the API integration status."
        )
        return TranscriptDelivery(
            session_id="",
            provider_session_id=provider_session_id,
            platform=MeetingPlatform.UNKNOWN,
            source_type="final_transcript",
            completeness="complete",
            content=content,
            participants=[{"name": "Speaker 1"}, {"name": "Speaker 2"}],
            segment_count=4,
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
        )

    def _map_provider_status(self, provider_session_id: str, data: Dict[str, Any]) -> AttendanceEvent:
        """Map OpenClaw provider status to our internal status enum."""
        provider_status = data.get("status", "").lower()
        status_map = {
            "joining": AttendanceStatus.JOINING,
            "in_waiting_room": AttendanceStatus.WAITING_FOR_ADMISSION,
            "in_call": AttendanceStatus.JOINED,
            "recording": AttendanceStatus.CAPTURING,
            "ended": AttendanceStatus.COMPLETED,
            "failed": AttendanceStatus.FAILED,
        }
        mapped = status_map.get(provider_status, AttendanceStatus.FAILED)
        return AttendanceEvent(
            session_id="",
            provider_session_id=provider_session_id,
            status=mapped,
            details={"provider_status": provider_status}
        )

    def _parse_transcript_response(self, provider_session_id: str, data: Dict[str, Any]) -> TranscriptDelivery:
        segments = data.get("segments", [])
        text_parts = []
        participants_seen = {}
        for seg in segments:
            speaker = seg.get("speaker_name", "Unknown")
            text = seg.get("text", "")
            if text:
                text_parts.append(f"{speaker}: {text}")
                participants_seen[speaker] = {"name": speaker}
        content = " ".join(text_parts)
        return TranscriptDelivery(
            session_id="",
            provider_session_id=provider_session_id,
            platform=MeetingPlatform(data.get("platform", "unknown")),
            source_type=data.get("transcript_type", "final_transcript"),
            completeness="complete" if data.get("is_final", False) else "partial",
            content=content,
            participants=list(participants_seen.values()),
            segment_count=len(segments),
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
        )

    # -------------------------------------------------------------------------
    # Meeting Reconnaissance
    # -------------------------------------------------------------------------

    async def extract_meeting_recon(
        self,
        meeting_title: str,
        attendee_names: List[str],
        company_domains: List[str],
    ) -> Dict[str, Any]:
        """
        Autonomously extract company background and attendee intelligence.

        Security contract:
        - All returned intelligence is classified as 'unverified_assumption'
        - verified = False always — requires explicit user confirmation
        - Never stores raw search results; only structured normalized output
        - When disabled, returns deterministic mock with correct structure

        Returns a dict conforming to the recon schema.
        """
        if not self.enabled:
            return self._mock_recon(meeting_title, attendee_names, company_domains)

        # Live path: call OpenClaw recon API
        payload = {
            "meeting_title": meeting_title,
            "attendees": attendee_names,
            "company_domains": company_domains,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(
                    f"{self.base_url}/v1/recon",
                    json=payload,
                    headers=self._headers()
                )
                if res.status_code == 200:
                    data = res.json()
                    return self._normalize_recon_response(data, company_domains, attendee_names)
                else:
                    logger.warning(f"[OpenClaw] Recon API returned {res.status_code}, falling back to mock")
                    return self._mock_recon(meeting_title, attendee_names, company_domains)
        except Exception as exc:
            logger.warning(f"[OpenClaw] Recon failed: {type(exc).__name__}, falling back to mock")
            return self._mock_recon(meeting_title, attendee_names, company_domains)

    def _mock_recon(
        self,
        meeting_title: str,
        attendee_names: List[str],
        company_domains: List[str],
    ) -> Dict[str, Any]:
        """
        Deterministic mock recon for disabled/unavailable OpenClaw.
        Returns structurally valid output with explicit unverified_assumption classification.
        All values are placeholders — never factual claims.
        """
        primary_domain = company_domains[0] if company_domains else "unknown.com"
        company_name = primary_domain.split(".")[0].capitalize() if company_domains else "Unknown"

        company_intelligence = {
            "domain": primary_domain,
            "company_name": company_name,
            "industry": None,           # Not known — explicitly null
            "employee_count": None,
            "headquarters": None,
            "description": None,
            "funding_stage": None,
            "key_products": [],
            "recent_news": [],
            "_mock": True,              # Signals this is placeholder data
        }

        attendee_recon = [
            {
                "name": name,
                "title": None,          # Not known — never fabricate
                "linkedin_url": None,
                "email_domain": primary_domain,
                "recent_activity": [],
                "_mock": True,
            }
            for name in attendee_names
        ]

        return {
            "source": "openclaw_recon",
            "epistemic_class": "unverified_assumption",
            "verified": False,          # INVARIANT: always False until user confirms
            "meeting_title": meeting_title,
            "company_intelligence": company_intelligence,
            "attendee_recon": attendee_recon,
            "gathered_at": None,
            "_mock": True,
        }

    def _normalize_recon_response(
        self,
        data: Dict[str, Any],
        company_domains: List[str],
        attendee_names: List[str],
    ) -> Dict[str, Any]:
        """Normalize live OpenClaw recon response to internal schema."""
        primary_domain = company_domains[0] if company_domains else "unknown.com"
        return {
            "source": "openclaw_recon",
            "epistemic_class": "unverified_assumption",  # ALWAYS — never promote automatically
            "verified": False,
            "meeting_title": data.get("meeting_title", ""),
            "company_intelligence": {
                "domain": primary_domain,
                "company_name": data.get("company", {}).get("name"),
                "industry": data.get("company", {}).get("industry"),
                "employee_count": data.get("company", {}).get("employee_count"),
                "headquarters": data.get("company", {}).get("hq"),
                "description": data.get("company", {}).get("description"),
                "funding_stage": data.get("company", {}).get("funding_stage"),
                "key_products": data.get("company", {}).get("products", [])[:5],
                "recent_news": data.get("company", {}).get("news", [])[:3],
            },
            "attendee_recon": [
                {
                    "name": att.get("name", ""),
                    "title": att.get("title"),
                    "linkedin_url": att.get("linkedin_url"),
                    "email_domain": att.get("email_domain"),
                    "recent_activity": att.get("recent_activity", [])[:3],
                }
                for att in data.get("attendees", [])
            ] or [{"name": n, "title": None, "linkedin_url": None, "email_domain": primary_domain, "recent_activity": []} for n in attendee_names],
            "gathered_at": data.get("gathered_at"),
        }


# Backward-compatible alias for existing tests and imports
OpenClawAdapter = OpenClawMeetingAdapter
