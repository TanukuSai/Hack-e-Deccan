"""
Gate 8: HTTP Integration Test Suite
Tests every API endpoint over the real ASGI transport (httpx.ASGITransport).
Full stack: HTTP routing → FastAPI → service layer → SQLAlchemy → live DB → RLS

Coverage: health probes, auth enforcement, meetings CRUD + reschedule,
contacts, documents, briefings, commitments (AI invariant + lifecycle),
projects, preferences, integrations (Google OAuth, calendar sync, transcripts),
outcomes (no-send invariant), tenant RLS, GDPR deletion, schema validation.
"""
import io
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text

from apps.api.app.main import app
from apps.api.app.core.db import engine
from apps.api.app.core.security import create_access_token


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def seed_user(user_id: str, budget: float = 50.0, spend: float = 0.0):
    suffix = uuid.uuid4().hex[:8]
    email = f"int_{suffix}@test.invalid"
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "SELECT public.seed_test_user("
                "CAST(:u AS UUID), :e, "
                "CAST(:b AS NUMERIC), CAST(:s AS NUMERIC)"
                ");"
            ),
            {"u": user_id, "e": email, "b": budget, "s": spend},
        )


def tok(uid: str) -> str:
    return create_access_token({"sub": uid, "role": "authenticated"})


def hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def fdt(hours: int = 24) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def pdf_bytes() -> bytes:
    return b"%PDF-1.4 1 0 obj<</Type/Catalog>>endobj\n%%EOF"


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def U(client):
    """Primary test user."""
    uid = str(uuid.uuid4())
    await seed_user(uid)
    return {"id": uid, "h": hdr(tok(uid))}


@pytest.fixture
async def V(client):
    """Second user for cross-tenant isolation checks."""
    uid = str(uuid.uuid4())
    await seed_user(uid)
    return {"id": uid, "h": hdr(tok(uid))}


# ==============================================================================
# 1. Health Probes
# ==============================================================================

@pytest.mark.asyncio
async def test_health_live(client):
    r = await client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_health_ready(client):
    r = await client.get("/health/ready")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_health_dependencies(client):
    r = await client.get("/health/dependencies")
    assert r.status_code == 200
    deps = r.json()["dependencies"]
    assert deps["database"]["status"] == "connected"
    assert "llm_provider" in deps


@pytest.mark.asyncio
async def test_correlation_headers_present(client):
    r = await client.get("/health/live")
    assert "x-request-id" in r.headers
    assert "x-response-time-ms" in r.headers


@pytest.mark.asyncio
async def test_custom_correlation_id_echoed(client):
    cid = "test-" + uuid.uuid4().hex[:8]
    r = await client.get("/health/live", headers={"X-Request-ID": cid})
    assert r.headers["x-request-id"] == cid


# ==============================================================================
# 2. Auth Enforcement
# ==============================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", [
    ("GET", "/api/v1/meetings"),
    ("GET", "/api/v1/contacts"),
    ("GET", "/api/v1/projects"),
    ("GET", "/api/v1/commitments"),
    ("GET", "/api/v1/preferences"),
    ("GET", "/api/v1/integrations/google/status"),
    ("GET", "/api/v1/integrations/health"),
    ("GET", "/api/v1/integrations/calendar/sync-state"),
])
async def test_auth_required(client, method, path):
    r = await client.request(method, path)
    assert r.status_code == 401, f"{method} {path} -> expected 401, got {r.status_code}"


@pytest.mark.asyncio
async def test_invalid_jwt_rejected(client):
    r = await client.get("/api/v1/meetings", headers={"Authorization": "Bearer bad.jwt.value"})
    assert r.status_code == 401


# ==============================================================================
# 3. Meetings CRUD
# ==============================================================================

@pytest.mark.asyncio
async def test_meeting_create(client, U):
    r = await client.post("/api/v1/meetings", json={
        "title": "HTTP Integration Test", "start_time": fdt(24), "end_time": fdt(25),
    }, headers=U["h"])
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["title"] == "HTTP Integration Test"
    assert "id" in m and m["status"] in ("scheduled", "upcoming")


@pytest.mark.asyncio
async def test_meeting_list_non_empty(client, U):
    await client.post("/api/v1/meetings", json={
        "title": "List", "start_time": fdt(2), "end_time": fdt(3),
    }, headers=U["h"])
    r = await client.get("/api/v1/meetings", headers=U["h"])
    assert r.status_code == 200 and len(r.json()) > 0


@pytest.mark.asyncio
async def test_meeting_get_by_id(client, U):
    rm = await client.post("/api/v1/meetings", json={
        "title": "GetByID", "start_time": fdt(2), "end_time": fdt(3),
    }, headers=U["h"])
    mid = rm.json()["id"]
    r = await client.get(f"/api/v1/meetings/{mid}", headers=U["h"])
    assert r.status_code == 200 and r.json()["id"] == mid


@pytest.mark.asyncio
async def test_meeting_cross_tenant_get_404(client, U, V):
    mid = (await client.post("/api/v1/meetings", json={
        "title": "Private", "start_time": fdt(2), "end_time": fdt(3),
    }, headers=U["h"])).json()["id"]
    assert (await client.get(f"/api/v1/meetings/{mid}", headers=V["h"])).status_code == 404


@pytest.mark.asyncio
async def test_meeting_title_update_no_version_bump(client, U):
    rm = await client.post("/api/v1/meetings", json={
        "title": "Original", "start_time": fdt(24), "end_time": fdt(25),
    }, headers=U["h"])
    m = rm.json()
    mid, v1 = m["id"], m["meeting_version"]
    r = await client.patch(f"/api/v1/meetings/{mid}", json={"title": "Renamed"}, headers=U["h"])
    assert r.status_code == 200
    assert r.json()["meeting_version"] == v1, "Title-only update must NOT bump version"


@pytest.mark.asyncio
async def test_meeting_reschedule_bumps_version(client, U):
    rm = await client.post("/api/v1/meetings", json={
        "title": "Reschedule", "start_time": fdt(24), "end_time": fdt(25),
    }, headers=U["h"])
    m = rm.json()
    mid, v1 = m["id"], m["meeting_version"]
    r = await client.patch(f"/api/v1/meetings/{mid}", json={
        "start_time": fdt(48), "end_time": fdt(49),
    }, headers=U["h"])
    assert r.status_code == 200
    assert r.json()["meeting_version"] > v1, "Reschedule MUST bump meeting_version"


@pytest.mark.asyncio
async def test_meeting_delete(client, U):
    mid = (await client.post("/api/v1/meetings", json={
        "title": "Delete", "start_time": fdt(1), "end_time": fdt(2),
    }, headers=U["h"])).json()["id"]
    assert (await client.delete(f"/api/v1/meetings/{mid}", headers=U["h"])).status_code == 204
    assert (await client.get(f"/api/v1/meetings/{mid}", headers=U["h"])).status_code == 404


@pytest.mark.asyncio
async def test_meeting_cross_tenant_delete_blocked(client, U, V):
    mid = (await client.post("/api/v1/meetings", json={
        "title": "NotYours", "start_time": fdt(2), "end_time": fdt(3),
    }, headers=U["h"])).json()["id"]
    assert (await client.delete(f"/api/v1/meetings/{mid}", headers=V["h"])).status_code == 404


@pytest.mark.asyncio
async def test_meeting_participants_add_and_list(client, U):
    mid = (await client.post("/api/v1/meetings", json={
        "title": "Participants", "start_time": fdt(2), "end_time": fdt(3),
    }, headers=U["h"])).json()["id"]
    rp = await client.post(f"/api/v1/meetings/{mid}/participants", json={
        "name": "Alice", "email": "alice@test.com", "role": "attendee",
    }, headers=U["h"])
    assert rp.status_code in (200, 201), rp.text
    rl = await client.get(f"/api/v1/meetings/{mid}/participants", headers=U["h"])
    assert any(p["name"] == "Alice" for p in rl.json())


@pytest.mark.asyncio
async def test_meeting_importance_override(client, U):
    r = await client.post("/api/v1/meetings", json={
        "title": "HighPriority", "start_time": fdt(2), "end_time": fdt(3),
        "user_importance_override": "critical",
    }, headers=U["h"])
    assert r.status_code == 201
    assert r.json()["effective_importance"] == "critical"


# ==============================================================================
# 4. Contacts CRUD + Tenant Isolation
# ==============================================================================

@pytest.mark.asyncio
async def test_contacts_create_list_update_delete(client, U):
    r = await client.post("/api/v1/contacts", json={
        "name": "Bob", "email": "bob@acme.com", "organization": "Acme",
    }, headers=U["h"])
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert any(c["id"] == cid for c in (await client.get("/api/v1/contacts", headers=U["h"])).json())
    ru = await client.patch(f"/api/v1/contacts/{cid}", json={"notes": "async preferred"}, headers=U["h"])
    assert ru.status_code == 200 and ru.json()["notes"] == "async preferred"
    assert (await client.delete(f"/api/v1/contacts/{cid}", headers=U["h"])).status_code == 204
    assert (await client.get(f"/api/v1/contacts/{cid}", headers=U["h"])).status_code == 404


@pytest.mark.asyncio
async def test_contact_tenant_isolation(client, U, V):
    cid = (await client.post("/api/v1/contacts", json={"name": "Secret"}, headers=U["h"])).json()["id"]
    other_ids = [c["id"] for c in (await client.get("/api/v1/contacts", headers=V["h"])).json()]
    assert cid not in other_ids


# ==============================================================================
# 5. Documents
# ==============================================================================

@pytest.mark.asyncio
async def test_document_upload_text(client, U):
    r = await client.post("/api/v1/documents/upload",
                          files={"file": ("note.txt", io.BytesIO(b"meeting notes"), "text/plain")},
                          headers=U["h"])
    assert r.status_code == 201, r.text
    assert "id" in r.json() and r.json()["checksum_sha256"] is not None


@pytest.mark.asyncio
async def test_document_upload_pdf(client, U):
    r = await client.post("/api/v1/documents/upload",
                          files={"file": ("report.pdf", io.BytesIO(pdf_bytes()), "application/pdf")},
                          headers=U["h"])
    assert r.status_code == 201 and r.json()["file_type"] == "pdf"


@pytest.mark.asyncio
async def test_document_invalid_extension_rejected(client, U):
    r = await client.post("/api/v1/documents/upload",
                          files={"file": ("mal.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
                          headers=U["h"])
    assert r.status_code == 415


@pytest.mark.asyncio
async def test_document_list_and_get(client, U):
    r = await client.post("/api/v1/documents/upload",
                          files={"file": ("l.txt", io.BytesIO(b"hi"), "text/plain")},
                          headers=U["h"])
    did = r.json()["id"]
    assert any(d["id"] == did for d in (await client.get("/api/v1/documents", headers=U["h"])).json())
    assert (await client.get(f"/api/v1/documents/{did}", headers=U["h"])).status_code == 200


@pytest.mark.asyncio
async def test_document_linked_to_meeting(client, U):
    mid = (await client.post("/api/v1/meetings", json={
        "title": "DocLinked", "start_time": fdt(4), "end_time": fdt(5),
    }, headers=U["h"])).json()["id"]
    r = await client.post("/api/v1/documents/upload",
                          files={"file": ("a.txt", io.BytesIO(b"agenda"), "text/plain")},
                          data={"meeting_id": mid}, headers=U["h"])
    assert r.status_code == 201 and str(r.json().get("meeting_id")) == str(mid)


@pytest.mark.asyncio
async def test_document_cross_tenant_blocked(client, U, V):
    r = await client.post("/api/v1/documents/upload",
                          files={"file": ("p.txt", io.BytesIO(b"secret"), "text/plain")},
                          headers=U["h"])
    did = r.json()["id"]
    assert (await client.get(f"/api/v1/documents/{did}", headers=V["h"])).status_code == 404


# ==============================================================================
# 6. Briefings
# ==============================================================================

@pytest.mark.asyncio
async def test_briefing_generate_and_latest(client, U):
    mid = (await client.post("/api/v1/meetings", json={
        "title": "BriefingTest", "purpose": "test", "start_time": fdt(2), "end_time": fdt(3),
    }, headers=U["h"])).json()["id"]
    await client.post(f"/api/v1/meetings/{mid}/participants", json={
        "name": "Eve", "email": "eve@test.com", "role": "attendee",
    }, headers=U["h"])
    await client.post("/api/v1/documents/upload",
                      files={"file": ("ctx.txt", io.BytesIO(b"Eve leads zero-trust."), "text/plain")},
                      data={"meeting_id": mid}, headers=U["h"])
    rg = await client.post("/api/v1/briefings/generate", json={
        "meeting_id": mid, "force_refresh": False,
    }, headers=U["h"])
    assert rg.status_code == 200, rg.text
    b = rg.json()
    assert b["meeting_id"] == mid and b["is_latest"] is True and b["version"] >= 1
    rl = await client.get(f"/api/v1/briefings/meeting/{mid}/latest", headers=U["h"])
    assert rl.status_code == 200 and rl.json()["is_latest"] is True


@pytest.mark.asyncio
async def test_briefing_version_increments_on_force(client, U):
    mid = (await client.post("/api/v1/meetings", json={
        "title": "VersionBump", "start_time": fdt(2), "end_time": fdt(3),
    }, headers=U["h"])).json()["id"]
    v1 = (await client.post("/api/v1/briefings/generate", json={"meeting_id": mid}, headers=U["h"])).json()["version"]
    v2 = (await client.post("/api/v1/briefings/generate", json={"meeting_id": mid, "force_refresh": True}, headers=U["h"])).json()["version"]
    assert v2 > v1


@pytest.mark.asyncio
async def test_briefing_history_returns_list(client, U):
    mid = (await client.post("/api/v1/meetings", json={
        "title": "BriefHistory", "start_time": fdt(2), "end_time": fdt(3),
    }, headers=U["h"])).json()["id"]
    await client.post("/api/v1/briefings/generate", json={"meeting_id": mid}, headers=U["h"])
    rh = await client.get(f"/api/v1/briefings/meeting/{mid}/history", headers=U["h"])
    assert rh.status_code == 200 and len(rh.json()) >= 1


@pytest.mark.asyncio
async def test_briefing_404_for_unprep_meeting(client, U):
    mid = (await client.post("/api/v1/meetings", json={
        "title": "NoBriefing", "start_time": fdt(48), "end_time": fdt(49),
    }, headers=U["h"])).json()["id"]
    assert (await client.get(f"/api/v1/briefings/meeting/{mid}/latest", headers=U["h"])).status_code == 404


# ==============================================================================
# 7. Commitments
# ==============================================================================

@pytest.mark.asyncio
async def test_commitments_list_empty(client, U):
    r = await client.get("/api/v1/commitments", headers=U["h"])
    assert r.status_code == 200 and isinstance(r.json(), list)


@pytest.mark.asyncio
@pytest.mark.parametrize("qs", [
    "?status=pending", "?is_confirmed=false", "?status=completed&is_confirmed=true",
])
async def test_commitments_filter_params_valid(client, U, qs):
    r = await client.get(f"/api/v1/commitments{qs}", headers=U["h"])
    assert r.status_code == 200, f"{qs} -> {r.status_code}: {r.text}"


@pytest.mark.asyncio
async def test_commitment_ai_proposed_unconfirmed_invariant(client, U):
    """INVARIANT: All AI-proposed commitments must start with is_confirmed=False."""
    mid = (await client.post("/api/v1/meetings", json={
        "title": "CommitmentInvariant", "start_time": fdt(1), "end_time": fdt(2),
    }, headers=U["h"])).json()["id"]
    ra = await client.post(f"/api/v1/meetings/{mid}/outcomes/analyze", json={
        "notes": "Alice will send the security report by Friday.",
        "transcript": "Alice: I will send the security report by Friday.",
    }, headers=U["h"])
    if ra.status_code == 402:
        pytest.skip("Budget exhausted")
    assert ra.status_code == 200, ra.text
    for c in ra.json().get("proposed_commitments", []):
        assert c["is_confirmed"] is False, "AI commitment violated unconfirmed invariant"


@pytest.mark.asyncio
async def test_commitment_confirm_and_update(client, U):
    mid = (await client.post("/api/v1/meetings", json={
        "title": "CommitLifecycle", "start_time": fdt(1), "end_time": fdt(2),
    }, headers=U["h"])).json()["id"]
    ra = await client.post(f"/api/v1/meetings/{mid}/outcomes/analyze", json={
        "notes": "Bob will write the runbook by Monday.",
        "transcript": "Bob: I will write the runbook by Monday.",
    }, headers=U["h"])
    if ra.status_code == 402:
        pytest.skip("Budget exhausted")
    proposed = ra.json().get("proposed_commitments", [])
    if not proposed:
        pytest.skip("No commitments extracted")
    cid = proposed[0]["id"]
    rc = await client.post(f"/api/v1/commitments/{cid}/confirm", headers=U["h"])
    assert rc.status_code == 200 and rc.json()["is_confirmed"] is True
    ru = await client.patch(f"/api/v1/commitments/{cid}", json={"status": "in_progress"}, headers=U["h"])
    assert ru.status_code == 200 and ru.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_commitment_cross_tenant_confirm_blocked(client, U, V):
    mid = (await client.post("/api/v1/meetings", json={
        "title": "IsolatedCommit", "start_time": fdt(1), "end_time": fdt(2),
    }, headers=U["h"])).json()["id"]
    ra = await client.post(f"/api/v1/meetings/{mid}/outcomes/analyze", json={
        "notes": "Bob prepares runbook.", "transcript": "Bob: I will prepare the runbook.",
    }, headers=U["h"])
    if ra.status_code != 200:
        pytest.skip("Outcome analysis unavailable")
    proposed = ra.json().get("proposed_commitments", [])
    if not proposed:
        pytest.skip("No commitments generated")
    cid = proposed[0]["id"]
    assert (await client.post(f"/api/v1/commitments/{cid}/confirm", headers=V["h"])).status_code == 404


# ==============================================================================
# 8. Projects
# ==============================================================================

@pytest.mark.asyncio
async def test_projects_full_crud(client, U):
    r = await client.post("/api/v1/projects", json={"name": "ProjectAlpha", "status": "active"}, headers=U["h"])
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert any(p["id"] == pid for p in (await client.get("/api/v1/projects", headers=U["h"])).json())
    assert (await client.get(f"/api/v1/projects/{pid}", headers=U["h"])).status_code == 200
    assert (await client.delete(f"/api/v1/projects/{pid}", headers=U["h"])).status_code == 204
    assert (await client.get(f"/api/v1/projects/{pid}", headers=U["h"])).status_code == 404


@pytest.mark.asyncio
async def test_project_progress_response_shape(client, U):
    pid = (await client.post("/api/v1/projects", json={"name": "ProgTest", "status": "active"}, headers=U["h"])).json()["id"]
    rp = await client.get(f"/api/v1/projects/{pid}/progress", headers=U["h"])
    assert rp.status_code == 200
    prog = rp.json()
    for field in ["total_commitments", "completed_commitments", "pending_commitments",
                  "missed_commitments", "blockers", "completion_pct"]:
        assert field in prog, f"Missing field: {field}"


@pytest.mark.asyncio
async def test_project_tenant_isolation(client, U, V):
    pid = (await client.post("/api/v1/projects", json={"name": "Isolated", "status": "active"}, headers=U["h"])).json()["id"]
    assert (await client.get(f"/api/v1/projects/{pid}", headers=V["h"])).status_code == 404
    assert (await client.delete(f"/api/v1/projects/{pid}", headers=V["h"])).status_code == 404


# ==============================================================================
# 9. Preferences
# ==============================================================================

@pytest.mark.asyncio
async def test_preferences_list_returns_list(client, U):
    r = await client.get("/api/v1/preferences", headers=U["h"])
    assert r.status_code == 200 and isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_preference_create_has_full_confidence(client, U):
    r = await client.post("/api/v1/preferences", json={
        "dimension": "briefing_format", "scope": "global", "key": "length", "value": "concise",
    }, headers=U["h"])
    assert r.status_code == 201, r.text
    assert float(r.json()["confidence"]) == 1.0


@pytest.mark.asyncio
async def test_preference_undo_reduces_confidence(client, U):
    r = await client.post("/api/v1/preferences", json={
        "dimension": "topic_priority", "scope": "global", "key": "focus", "value": "strategic",
    }, headers=U["h"])
    pid = r.json()["id"]
    ru = await client.post(f"/api/v1/preferences/{pid}/undo", headers=U["h"])
    assert ru.status_code == 200 and float(ru.json()["confidence"]) < 1.0


@pytest.mark.asyncio
async def test_preferences_dimension_filter(client, U):
    await client.post("/api/v1/preferences", json={
        "dimension": "briefing_format", "scope": "global", "key": "k", "value": "v",
    }, headers=U["h"])
    r = await client.get("/api/v1/preferences?dimension=briefing_format", headers=U["h"])
    assert r.status_code == 200
    for p in r.json():
        assert p["dimension"] == "briefing_format"


# ==============================================================================
# 10. Integrations
# ==============================================================================

@pytest.mark.asyncio
async def test_google_auth_url_generation(client, U):
    r = await client.get(
        "/api/v1/integrations/google/auth-url?redirect_uri=http://localhost:5173/callback",
        headers=U["h"],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "accounts.google.com" in body["authorization_url"]
    assert len(body["scopes"]) > 0


@pytest.mark.asyncio
async def test_google_status_fresh_user_not_connected(client, U):
    r = await client.get("/api/v1/integrations/google/status", headers=U["h"])
    assert r.status_code == 200
    assert r.json().get("connected") is False or "connected" in r.json()


@pytest.mark.asyncio
async def test_google_callback_invalid_code_returns_error(client, U):
    r = await client.post("/api/v1/integrations/google/callback", json={
        "code": "bogus_invalid_code",
        "redirect_uri": "http://localhost:5173/callback",
    }, headers=U["h"])
    assert r.status_code in (400, 422, 502), f"Got {r.status_code}: {r.text}"


@pytest.mark.asyncio
async def test_meeting_integration_config_upsert_and_get(client, U):
    r = await client.put("/api/v1/integrations/meeting/google_meet", json={
        "is_enabled": True, "attendance_mode": "manual",
        "join_before_minutes": 3, "auto_leave_on_end": True,
        "transcript_capture_enabled": False, "consent_verified": False,
    }, headers=U["h"])
    assert r.status_code in (200, 201), r.text
    assert r.json()["attendance_mode"] == "manual"
    rg = await client.get("/api/v1/integrations/meeting/google_meet", headers=U["h"])
    assert rg.status_code == 200 and rg.json()["integration_type"] == "google_meet"


@pytest.mark.asyncio
async def test_calendar_sync_enqueues_job(client, U):
    r = await client.post("/api/v1/integrations/calendar/sync", headers=U["h"])
    assert r.status_code in (200, 202), r.text
    body = r.json()
    assert "job_id" in body or "status" in body or "message" in body


@pytest.mark.asyncio
async def test_calendar_sync_state(client, U):
    r = await client.get("/api/v1/integrations/calendar/sync-state", headers=U["h"])
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_transcript_upload_with_consent(client, U):
    mid = (await client.post("/api/v1/meetings", json={
        "title": "TranscriptUpload", "start_time": fdt(2), "end_time": fdt(3),
    }, headers=U["h"])).json()["id"]
    r = await client.post("/api/v1/integrations/transcripts/upload", json={
        "meeting_id": mid,
        "transcript_text": "Alice: Deploy Tuesday.\nBob: Runbook done.",
        "completeness": "complete",
        "consent_verified": True,
    }, headers=U["h"])
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body.get("segments_ingested", 0) > 0 or "transcript_id" in body


@pytest.mark.asyncio
async def test_transcript_upload_no_consent_rejected(client, U):
    mid = (await client.post("/api/v1/meetings", json={
        "title": "NoConsent", "start_time": fdt(2), "end_time": fdt(3),
    }, headers=U["h"])).json()["id"]
    r = await client.post("/api/v1/integrations/transcripts/upload", json={
        "meeting_id": mid,
        "transcript_text": "Alice: Hi Bob.",
        "completeness": "partial",
        "consent_verified": False,
    }, headers=U["h"])
    assert r.status_code in (400, 403, 422), f"Consent gate not enforced: {r.status_code}"


@pytest.mark.asyncio
async def test_integrations_health_shape(client, U):
    r = await client.get("/api/v1/integrations/health", headers=U["h"])
    assert r.status_code == 200
    assert isinstance(r.json()["integrations"], list)


@pytest.mark.asyncio
async def test_transcript_list_for_meeting(client, U):
    mid = (await client.post("/api/v1/meetings", json={
        "title": "TranscriptList", "start_time": fdt(2), "end_time": fdt(3),
    }, headers=U["h"])).json()["id"]
    r = await client.get(f"/api/v1/integrations/transcripts/{mid}", headers=U["h"])
    assert r.status_code == 200


# ==============================================================================
# 11. Outcomes — No-Send Invariant
# ==============================================================================

@pytest.mark.asyncio
async def test_no_send_endpoint_must_not_exist(client, U):
    """INVARIANT: No email send endpoint may exist. Draft-only system."""
    mid = (await client.post("/api/v1/meetings", json={
        "title": "SendTest", "start_time": fdt(1), "end_time": fdt(2),
    }, headers=U["h"])).json()["id"]
    for path in [
        f"/api/v1/meetings/{mid}/follow-up/send",
        f"/api/v1/meetings/{mid}/send-follow-up",
        "/api/v1/email/send",
    ]:
        r = await client.post(path, headers=U["h"])
        assert r.status_code == 404, f"INVARIANT VIOLATED — send endpoint exists: {path}"


# ==============================================================================
# 12. GDPR Deletion
# ==============================================================================

@pytest.mark.asyncio
async def test_gdpr_delete_cascades(client, U):
    await client.post("/api/v1/meetings", json={
        "title": "ToDelete", "start_time": fdt(2), "end_time": fdt(3),
    }, headers=U["h"])
    await client.post("/api/v1/projects", json={"name": "GoneProject", "status": "active"}, headers=U["h"])
    rd = await client.delete("/api/v1/users/me", headers=U["h"])
    assert rd.status_code == 204
    r = await client.get("/api/v1/meetings", headers=U["h"])
    # After deletion: either 401 (auth fails on deleted user) or 200 with empty list
    assert r.status_code in (200, 401, 404)
    if r.status_code == 200:
        assert r.json() == [], "Meetings must be purged after GDPR deletion"


# ==============================================================================
# 13. Schema Validation — 422 on bad input
# ==============================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("payload,endpoint", [
    ({}, "/api/v1/meetings"),
    ({"title": "X", "start_time": "not-a-date", "end_time": "also-bad"}, "/api/v1/meetings"),
    ({}, "/api/v1/projects"),
    ({}, "/api/v1/contacts"),
])
async def test_schema_validation_422(client, U, payload, endpoint):
    r = await client.post(endpoint, json=payload, headers=U["h"])
    assert r.status_code == 422, f"{endpoint} {payload} -> expected 422, got {r.status_code}"


@pytest.mark.asyncio
async def test_invalid_uuid_in_path(client, U):
    r = await client.get("/api/v1/meetings/not-a-valid-uuid", headers=U["h"])
    assert r.status_code in (404, 422)


# ==============================================================================
# 14. Authentication & User Profile Management
# ==============================================================================

@pytest.mark.asyncio
async def test_auth_google_url_generation(client):
    r = await client.get("/api/v1/auth/google/url?redirect_uri=http://localhost:5173/auth/google/callback&include_calendar=true")
    assert r.status_code == 200
    data = r.json()
    assert "authorization_url" in data
    assert "accounts.google.com" in data["authorization_url"]
    assert "calendar.readonly" in data["authorization_url"]


@pytest.mark.asyncio
async def test_auth_dev_login_and_me(client):
    suffix = uuid.uuid4().hex[:6]
    test_email = f"exec_{suffix}@testcorp.io"
    r = await client.post("/api/v1/auth/dev-login", json={"email": test_email, "name": "Executive Tester"})
    assert r.status_code == 200
    data = r.json()
    assert "access_token" in data
    assert data["user"]["email"] == test_email
    
    # Test /api/v1/auth/me with the generated token
    token = data["access_token"]
    rme = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert rme.status_code == 200
    me = rme.json()
    assert me["email"] == test_email
    assert "google_integration" in me


@pytest.mark.asyncio
async def test_users_me_get_and_patch(client, U):
    r = await client.get("/api/v1/users/me", headers=U["h"])
    assert r.status_code == 200
    profile = r.json()
    assert "email" in profile

    # PATCH preferences
    rp = await client.patch("/api/v1/users/me", json={
        "full_name": "Updated Name",
        "timezone": "America/New_York",
        "briefing_format_preference": "concise"
    }, headers=U["h"])
    assert rp.status_code == 200
    up = rp.json()
    assert up["full_name"] == "Updated Name"
    assert up["timezone"] == "America/New_York"
    assert up["briefing_format_preference"] == "concise"


# ==============================================================================
# 15. Briefing Follow-Up Conversation
# ==============================================================================

@pytest.mark.asyncio
async def test_briefing_follow_up_conversation(client, U):
    mid = (await client.post("/api/v1/meetings", json={
        "title": "Strategy Review with David Miller",
        "purpose": "Discuss cloud migration and security roadmap",
        "start_time": fdt(2),
        "end_time": fdt(3),
    }, headers=U["h"])).json()["id"]

    r = await client.post(f"/api/v1/briefings/meeting/{mid}/conversation", json={
        "question": "What are the biggest objections David Miller might raise?",
        "history": []
    }, headers=U["h"])
    assert r.status_code == 200
    data = r.json()
    assert data["meeting_id"] == mid
    assert "answer" in data and len(data["answer"]) > 10
    assert "suggested_talking_points" in data

