"""
Comprehensive OpenClaw Integration Test Suite
=============================================
Validates:
1. OpenClawMeetingAdapter platform detection (Google Meet, Teams, Zoom, Unknown)
2. Consent verification gate: join blocked if transcript requested without participant consent
3. Deterministic containment and mock handling when OpenClaw service is disabled
4. Reconnaissance extraction: epistemic contract (always unverified_assumption, verified=False)
5. Transcript delivery normalization, speaker attribution, and SHA256 hashing
6. Meeting integration configuration endpoints (GET / PUT / DELETE)
7. Attendance session lifecycle: request join, consent enforcement, and cancellation
8. Integration health reporting endpoint
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text

from apps.api.app.main import app
from apps.api.app.core.db import engine, get_tenant_session
from apps.api.app.core.security import create_access_token
from apps.api.app.providers.openclaw_adapter import (
    OpenClawMeetingAdapter,
    JoinRequest,
    AttendanceStatus,
    MeetingPlatform,
)

async def seed_test_tenant(user_id: str):
    email = f"openclaw_test_{uuid.uuid4().hex[:8]}@example.com"
    async with engine.begin() as conn:
        await conn.execute(
            text("SELECT public.seed_test_user(CAST(:u_id AS UUID), :email, 25.0, 0.0);"),
            {"u_id": user_id, "email": email}
        )

# ==============================================================================
# 1. OpenClaw Adapter Unit & Protocol Tests
# ==============================================================================

def test_openclaw_platform_detection():
    adapter = OpenClawMeetingAdapter(enabled=False)
    assert adapter._detect_platform("https://meet.google.com/abc-defg-hij") == MeetingPlatform.GOOGLE_MEET
    assert adapter._detect_platform("https://teams.microsoft.com/l/meetup-join/19%3ameeting") == MeetingPlatform.MICROSOFT_TEAMS
    assert adapter._detect_platform("https://zoom.us/j/1234567890") == MeetingPlatform.ZOOM
    assert adapter._detect_platform("https://other-service.com/room/123") == MeetingPlatform.UNKNOWN


@pytest.mark.asyncio
async def test_openclaw_consent_gate_blocks_unauthorized_recording():
    """Consent gate must strictly block transcript capture if consent is unverified."""
    adapter = OpenClawMeetingAdapter(enabled=False)
    req = JoinRequest(
        session_id=str(uuid.uuid4()),
        meeting_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        join_url="https://meet.google.com/xyz-uvwx-rst",
        platform=MeetingPlatform.GOOGLE_MEET,
        bot_display_name="Executive Assistant Bot",
        transcript_requested=True,
        consent_verified=False,  # NOT VERIFIED!
    )
    event = await adapter.request_join(req)
    assert event.status == AttendanceStatus.CONSENT_REQUIRED
    assert "consent" in (event.sanitized_reason or "").lower()


@pytest.mark.asyncio
async def test_openclaw_mock_join_when_contained():
    """When disabled/contained, adapter produces deterministic mock join event."""
    adapter = OpenClawMeetingAdapter(enabled=False)
    req = JoinRequest(
        session_id=str(uuid.uuid4()),
        meeting_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        join_url="https://meet.google.com/xyz-uvwx-rst",
        platform=MeetingPlatform.GOOGLE_MEET,
        bot_display_name="Executive Assistant Bot",
        transcript_requested=False,
        consent_verified=True,
    )
    event = await adapter.request_join(req)
    assert event.status == AttendanceStatus.JOINING
    assert event.provider_session_id is not None
    assert event.provider_session_id.startswith("mock_")
    assert event.details.get("mock") is True


@pytest.mark.asyncio
async def test_openclaw_reconnaissance_epistemic_invariants():
    """Reconnaissance must strictly return unverified_assumption and verified=False."""
    adapter = OpenClawMeetingAdapter(enabled=False)
    recon = await adapter.extract_meeting_recon(
        meeting_title="Security Review with David Miller",
        attendee_names=["David Miller", "Priya Nair"],
        company_domains=["cloudflare.com"]
    )
    assert recon["source"] == "openclaw_recon"
    assert recon["epistemic_class"] == "unverified_assumption"
    assert recon["verified"] is False
    assert recon["company_intelligence"]["company_name"] == "Cloudflare"
    assert len(recon["attendee_recon"]) == 2


@pytest.mark.asyncio
async def test_openclaw_mock_transcript_normalization():
    """Mock transcript generation parses speaker attribution and creates deterministic content hash."""
    adapter = OpenClawMeetingAdapter(enabled=False)
    delivery = await adapter.retrieve_transcript("mock_session_123")
    assert delivery is not None
    assert delivery.source_type == "final_transcript"
    assert delivery.completeness == "complete"
    assert len(delivery.content) > 20
    assert len(delivery.content_hash) == 64  # SHA-256
    assert len(delivery.participants) >= 2

# ==============================================================================
# 2. Integration HTTP API & Attendance Session Lifecycle Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_openclaw_meeting_integration_config_crud():
    """Test full CRUD on meeting integration configuration for OpenClaw."""
    user_id = str(uuid.uuid4())
    await seed_test_tenant(user_id)
    token = create_access_token({"sub": user_id})
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Configure OpenClaw
        cfg_payload = {
            "attendance_mode": "manual",
            "is_enabled": True,
            "join_before_minutes": 5,
            "auto_leave_on_end": True,
            "transcript_capture_enabled": True,
            "allowed_meeting_types": ["client", "board"],
            "eligible_platforms": ["google_meet", "zoom"],
            "attendance_rules": {"max_duration_minutes": 60}
        }
        put_res = await client.put(
            "/api/v1/integrations/meeting/openclaw",
            json=cfg_payload,
            headers=headers
        )
        assert put_res.status_code == 200
        data = put_res.json()
        assert data["status"] == "configured"
        assert data["attendance_mode"] == "manual"
        assert data["is_enabled"] is True

        # 2. Get OpenClaw config
        get_res = await client.get("/api/v1/integrations/meeting/openclaw", headers=headers)
        assert get_res.status_code == 200
        config_data = get_res.json()
        assert config_data["integration_type"] == "openclaw"
        assert config_data["attendance_mode"] == "manual"
        assert config_data["join_before_minutes"] == 5

        # 3. Health overview should include configured openclaw
        health_res = await client.get("/api/v1/integrations/health", headers=headers)
        assert health_res.status_code == 200
        health_data = health_res.json()
        types = [i["integration_type"] for i in health_data["integrations"]]
        assert "openclaw" in types


@pytest.mark.asyncio
async def test_openclaw_attendance_session_and_consent_enforcement():
    """Test manual attendance request, consent verification, and session cancellation."""
    user_id = str(uuid.uuid4())
    await seed_test_tenant(user_id)
    token = create_access_token({"sub": user_id})
    headers = {"Authorization": f"Bearer {token}"}

    # Create meeting with join URL in tenant DB
    meeting_id = str(uuid.uuid4())
    async with get_tenant_session(user_id) as session:
        await session.execute(
            text("""
                INSERT INTO public.meetings (
                    id, user_id, title, purpose, start_time, end_time,
                    join_url, status, meeting_version
                ) VALUES (
                    :m_id, :u_id, 'Executive Cloud Sync', 'Quarterly Review',
                    NOW(), NOW() + INTERVAL '1 hour',
                    'https://meet.google.com/test-claw-room', 'scheduled', 1
                );
            """),
            {"m_id": meeting_id, "u_id": user_id}
        )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # A. Attempt attendance with transcript capture but WITHOUT consent -> HTTP 422
        bad_req = await client.post(
            f"/api/v1/integrations/attendance/{meeting_id}/request",
            json={"transcript_capture": True, "consent_verified": False},
            headers=headers
        )
        assert bad_req.status_code == 422
        assert "consent verification" in bad_req.json()["detail"].lower()

        # B. Request attendance with consent verified -> HTTP 200
        good_req = await client.post(
            f"/api/v1/integrations/attendance/{meeting_id}/request",
            json={"transcript_capture": True, "consent_verified": True},
            headers=headers
        )
        assert good_req.status_code == 200
        session_info = good_req.json()
        assert session_info["status"] == "eligible"
        assert session_info["transcript_requested"] is True

        # C. Query attendance session
        sess_get = await client.get(f"/api/v1/integrations/attendance/{meeting_id}", headers=headers)
        assert sess_get.status_code == 200
        assert sess_get.json()["status"] == "eligible"
        assert sess_get.json()["provider"] == "openclaw"

        # D. Cancel attendance session
        cancel_res = await client.delete(f"/api/v1/integrations/attendance/{meeting_id}/cancel", headers=headers)
        assert cancel_res.status_code == 200
        assert cancel_res.json()["status"] == "cancelled"

        # E. Query attendance session after cancel -> status should be cancelled
        sess_cancelled = await client.get(f"/api/v1/integrations/attendance/{meeting_id}", headers=headers)
        assert sess_cancelled.status_code == 200
        assert sess_cancelled.json()["status"] == "cancelled"
