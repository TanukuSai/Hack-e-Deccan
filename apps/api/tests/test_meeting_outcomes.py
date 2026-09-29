"""
Gate 4: Comprehensive Test Suite for Meeting Outcomes, Commitments & Progress.
Validates:
1. Notes/Transcript Analysis: Extracts decisions, proposes commitments, creates follow-up draft
2. Proposed Commitments Invariant: Inferred commitments MUST be created with is_confirmed=False
3. Human Confirmation: Explicit confirmation flips is_confirmed to True
4. Commitment Lifecycle: Status updates (pending, in_progress, completed, missed)
5. Draft-Only External Communications: Draft status only, zero client-send capability
6. Multi-Tenant RLS Isolation: Tenant B cannot access or modify Tenant A's commitments or drafts
7. Project Progress Summary: Aggregation of confirmed, proposed, completed, overdue, and blockers
8. Cost Ledger Accounting: LLM budget reservation and settlement recorded
9. FastAPI HTTP Endpoints: Full request/response cycle verification
"""
import uuid
import json
import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import text
from httpx import AsyncClient, ASGITransport

from apps.api.app.main import app
from apps.api.app.core.db import engine, get_tenant_session
from apps.api.app.core.security import create_access_token
from apps.api.app.services.outcome_service import OutcomeService
from apps.api.app.schemas.outcome import CommitmentUpdate, FollowUpDraftUpdate

async def seed_user(user_id: str, budget: float = 25.0, spend: float = 0.0):
    unique_email = f"user_{uuid.uuid4().hex[:10]}@example.com"
    async with engine.begin() as conn:
        await conn.execute(
            text("SELECT public.seed_test_user(CAST(:u_id AS UUID), :email, CAST(:budget AS NUMERIC), CAST(:spend AS NUMERIC));"),
            {"u_id": user_id, "email": unique_email, "budget": budget, "spend": spend}
        )

async def create_test_project_and_meeting(user_id: str):
    async with get_tenant_session(user_id) as session:
        # Create Project
        p_res = await session.execute(
            text("""
            INSERT INTO public.projects (user_id, name, description)
            VALUES (:u_id, 'Q3 Migration Project', 'Core platform overhaul')
            RETURNING id;
            """),
            {"u_id": user_id}
        )
        project_id = p_res.scalar()

        # Create Meeting
        m_res = await session.execute(
            text("""
            INSERT INTO public.meetings (
                user_id, project_id, title, purpose,
                start_time, end_time, status
            )
            VALUES (
                :u_id, :p_id, 'Architecture Review & Gate 4 Alignment', 'Finalize milestones and commitments',
                NOW(), NOW() + INTERVAL '1 hour', 'scheduled'
            )
            RETURNING id;
            """),
            {"u_id": user_id, "p_id": str(project_id)}
        )
        meeting_id = m_res.scalar()

        # Add Participants
        await session.execute(
            text("""
            INSERT INTO public.meeting_participants (user_id, meeting_id, name, role)
            VALUES
                (:u_id, :m_id, 'Sarah Chen', 'Lead Architect'),
                (:u_id, :m_id, 'Marcus Vance', 'Engineering Director');
            """),
            {"u_id": user_id, "m_id": str(meeting_id)}
        )

        return project_id, meeting_id


@pytest.mark.asyncio
async def test_outcome_analysis_and_proposed_commitments_invariant():
    """
    Validates notes analysis extracts decisions, proposed commitments with is_confirmed=False,
    follow-up draft with status='draft', and updates meeting status to completed.
    """
    user_id = str(uuid.uuid4())
    await seed_user(user_id)
    project_id, meeting_id = await create_test_project_and_meeting(user_id)

    outcome_service = OutcomeService()

    sample_notes = """
    Architecture Review Meeting Notes:
    - Decided to adopt PostgreSQL RLS and strict composite foreign keys for multi-tenancy.
    - Agreed on the leased job queue design for asynchronous background processing.
    - Sarah Chen will deliver the final migration scripts by Friday.
    - Marcus Vance to review the cost enforcement policy before deployment.
    """

    res = await outcome_service.analyze_and_store_outcomes(
        user_id=user_id,
        meeting_id=meeting_id,
        notes=sample_notes
    )

    # 1. Verify meeting summary and decisions
    assert "meeting_summary" in res
    assert len(res["decisions_made"]) >= 1

    # 2. Strict Invariant: All inferred commitments MUST be is_confirmed=False
    assert len(res["commitments"]) >= 1
    for comm in res["commitments"]:
        assert comm["is_confirmed"] is False, "CRITICAL: Inferred commitment must NOT be auto-confirmed"
        assert comm["status"] == "pending"
        assert comm["user_id"] == uuid.UUID(user_id)
        assert comm["meeting_id"] == meeting_id

    # 3. Draft-only external communication: status must be 'draft'
    assert res["follow_up_draft"]["status"] == "draft"
    assert "Sarah Chen" in str(res["follow_up_draft"]["recipients"]) or len(res["follow_up_draft"]["recipients"]) > 0

    # 4. Verify DB state: meeting marked completed
    async with get_tenant_session(user_id) as session:
        m_row = (await session.execute(
            text("SELECT status, notes FROM public.meetings WHERE id = :m_id;"),
            {"m_id": str(meeting_id)}
        )).mappings().first()
        assert m_row["status"] == "completed"
        assert sample_notes in m_row["notes"]


@pytest.mark.asyncio
async def test_explicit_human_confirmation_of_commitment():
    """
    Validates that proposed commitments require human confirmation to flip is_confirmed: False -> True.
    """
    user_id = str(uuid.uuid4())
    await seed_user(user_id)
    project_id, meeting_id = await create_test_project_and_meeting(user_id)

    outcome_service = OutcomeService()
    notes = "Agreed to proceed. Sarah Chen will finalize the schema docs."
    res = await outcome_service.analyze_and_store_outcomes(user_id, meeting_id, notes)

    commitment = res["commitments"][0]
    comm_id = commitment["id"]
    assert commitment["is_confirmed"] is False

    # Perform explicit confirmation
    confirmed = await outcome_service.confirm_commitment(user_id, comm_id)
    assert confirmed["id"] == comm_id
    assert confirmed["is_confirmed"] is True

    # Check persistence
    commitments = await outcome_service.list_commitments(user_id, meeting_id=meeting_id, is_confirmed=True)
    assert len(commitments) == 1
    assert commitments[0]["id"] == comm_id


@pytest.mark.asyncio
async def test_commitment_lifecycle_and_updates():
    """
    Validates updating commitment status, due dates, descriptions, and filtering.
    """
    user_id = str(uuid.uuid4())
    await seed_user(user_id)
    project_id, meeting_id = await create_test_project_and_meeting(user_id)

    outcome_service = OutcomeService()
    notes = "Marcus Vance will configure production monitoring alerts by next week."
    res = await outcome_service.analyze_and_store_outcomes(user_id, meeting_id, notes)
    comm_id = res["commitments"][0]["id"]

    # Update commitment to in_progress with a due date
    target_date = date.today() + timedelta(days=5)
    updated = await outcome_service.update_commitment(
        user_id=user_id,
        commitment_id=comm_id,
        payload=CommitmentUpdate(
            status="in_progress",
            due_date=target_date,
            description="Marcus Vance will configure Datadog & Supabase metrics alerts"
        )
    )
    assert updated["status"] == "in_progress"
    assert updated["due_date"] == target_date
    assert "Datadog" in updated["description"]

    # Filter commitments by status
    in_prog_list = await outcome_service.list_commitments(user_id, commitment_status="in_progress")
    assert len(in_prog_list) == 1
    assert in_prog_list[0]["id"] == comm_id

    # Complete the commitment
    completed = await outcome_service.update_commitment(
        user_id=user_id,
        commitment_id=comm_id,
        payload=CommitmentUpdate(status="completed")
    )
    assert completed["status"] == "completed"


@pytest.mark.asyncio
async def test_draft_only_external_communication():
    """
    Validates draft-only follow-ups (draft -> reviewed / discarded).
    Enforces that 'sent' status is strictly disallowed by check constraints.
    """
    user_id = str(uuid.uuid4())
    await seed_user(user_id)
    project_id, meeting_id = await create_test_project_and_meeting(user_id)

    outcome_service = OutcomeService()
    notes = "Reviewed Sprint goals. Marcus Vance to deploy release candidate."
    res = await outcome_service.analyze_and_store_outcomes(user_id, meeting_id, notes)

    draft = res["follow_up_draft"]
    draft_id = draft["id"]
    assert draft["status"] == "draft"

    # User reviews and updates draft text
    updated_draft = await outcome_service.update_follow_up_draft(
        user_id=user_id,
        draft_id=draft_id,
        payload=FollowUpDraftUpdate(
            subject="Updated Subject: Sprint Architecture Review",
            body="Team, thank you for your active participation today. Here are the approved items...",
            status="reviewed"
        )
    )
    assert updated_draft["status"] == "reviewed"
    assert "Updated Subject" in updated_draft["subject"]

    # Verify attempt to set status to 'sent' is rejected by DB check constraint
    async with get_tenant_session(user_id) as session:
        with pytest.raises(Exception):
            await session.execute(
                text("UPDATE public.follow_up_drafts SET status = 'sent' WHERE id = :d_id;"),
                {"d_id": str(draft_id)}
            )


@pytest.mark.asyncio
async def test_tenant_rls_isolation_on_commitments_and_drafts():
    """
    Validates that Tenant B CANNOT read, confirm, or modify Tenant A's commitments or drafts.
    """
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    await seed_user(user_a)
    await seed_user(user_b)

    _, meeting_a = await create_test_project_and_meeting(user_a)
    outcome_service = OutcomeService()
    res_a = await outcome_service.analyze_and_store_outcomes(user_a, meeting_a, "Sarah will submit budget.")
    comm_a_id = res_a["commitments"][0]["id"]
    draft_a_id = res_a["follow_up_draft"]["id"]

    # 1. Tenant B attempts to confirm Tenant A's commitment -> 404
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await outcome_service.confirm_commitment(user_id=user_b, commitment_id=comm_a_id)
    assert exc.value.status_code == 404

    # 2. Tenant B attempts to update Tenant A's commitment -> 404
    with pytest.raises(HTTPException) as exc:
        await outcome_service.update_commitment(
            user_id=user_b,
            commitment_id=comm_a_id,
            payload=CommitmentUpdate(status="completed")
        )
    assert exc.value.status_code == 404

    # 3. Tenant B lists commitments -> sees 0 commitments
    b_commitments = await outcome_service.list_commitments(user_id=user_b)
    assert len(b_commitments) == 0

    # 4. Tenant B attempts to read Tenant A's follow-up draft -> 404
    with pytest.raises(HTTPException) as exc:
        await outcome_service.get_follow_up_draft(user_id=user_b, meeting_id=meeting_a)
    assert exc.value.status_code == 404

    # 5. Tenant B attempts to update Tenant A's follow-up draft -> 404
    with pytest.raises(HTTPException) as exc:
        await outcome_service.update_follow_up_draft(
            user_id=user_b,
            draft_id=draft_a_id,
            payload=FollowUpDraftUpdate(subject="Malicious Hack")
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_project_progress_aggregation_and_blockers():
    """
    Validates calculation of project progress metrics:
    total, confirmed, proposed, completed, in_progress, overdue, completion_rate, and blockers.
    """
    user_id = str(uuid.uuid4())
    await seed_user(user_id)
    project_id, meeting_id = await create_test_project_and_meeting(user_id)

    yesterday = date.today() - timedelta(days=1)
    tomorrow = date.today() + timedelta(days=1)

    # Insert a diverse set of commitments for this project
    async with get_tenant_session(user_id) as session:
        await session.execute(
            text("""
            INSERT INTO public.commitments (
                user_id, project_id, meeting_id, owner_name, description, due_date, status, is_confirmed
            )
            VALUES
                -- 1. Confirmed & Completed
                (:u_id, :p_id, :m_id, 'Sarah', 'Architecture Diagram', :yesterday, 'completed', TRUE),
                -- 2. Confirmed & In Progress
                (:u_id, :p_id, :m_id, 'Marcus', 'Database Migration', :tomorrow, 'in_progress', TRUE),
                -- 3. Confirmed & Overdue (Blocker 1)
                (:u_id, :p_id, :m_id, 'Alex', 'Security Audit Report', :yesterday, 'pending', TRUE),
                -- 4. Confirmed & Missed (Blocker 2)
                (:u_id, :p_id, :m_id, 'Jordan', 'Client Demo Deck', :yesterday, 'missed', TRUE),
                -- 5. Proposed & Unconfirmed
                (:u_id, :p_id, :m_id, 'Taylor', 'Draft API Spec', :tomorrow, 'pending', FALSE);
            """),
            {
                "u_id": user_id,
                "p_id": str(project_id),
                "m_id": str(meeting_id),
                "yesterday": yesterday,
                "tomorrow": tomorrow
            }
        )

    outcome_service = OutcomeService()
    progress = await outcome_service.get_project_progress(user_id=user_id, project_id=project_id)

    assert progress["total_commitments"] == 5
    assert progress["confirmed_commitments"] == 4
    assert progress["proposed_commitments"] == 1
    assert progress["completed_commitments"] == 1
    assert progress["in_progress_commitments"] == 1
    assert progress["overdue_commitments"] == 1
    assert progress["completion_rate_pct"] == 20.0  # 1 completed out of 5 total = 20%

    # Blocker detection
    assert len(progress["blockers_detected"]) == 2
    blocker_str = " ".join(progress["blockers_detected"])
    assert "Security Audit Report" in blocker_str
    assert "Client Demo Deck" in blocker_str


@pytest.mark.asyncio
async def test_cost_ledger_settlement_on_outcome_analysis():
    """
    Validates that analyzing meeting outcomes reserves and settles LLM cost in llm_usage_ledger.
    """
    user_id = str(uuid.uuid4())
    await seed_user(user_id, budget=25.0, spend=0.0)
    project_id, meeting_id = await create_test_project_and_meeting(user_id)

    outcome_service = OutcomeService()
    notes = "Reviewed deliverables. Sarah will deploy the hotfix today."
    await outcome_service.analyze_and_store_outcomes(user_id, meeting_id, notes)

    # Check ledger
    async with get_tenant_session(user_id) as session:
        ledger_res = await session.execute(
            text("""
            SELECT operation_type, actual_cost_usd, status
            FROM public.llm_usage_ledger
            WHERE user_id = :u_id;
            """),
            {"u_id": user_id}
        )
        entries = [dict(r) for r in ledger_res.mappings().all()]
        assert len(entries) >= 1
        assert any(e["operation_type"] == "outcome_proposal" and e["status"] == "settled" for e in entries)

        # Spend updated on user_profile
        profile = (await session.execute(
            text("SELECT current_month_spend_usd FROM public.user_profiles WHERE id = :u_id;"),
            {"u_id": user_id}
        )).mappings().first()
        assert profile["current_month_spend_usd"] > Decimal("0.0000")


@pytest.mark.asyncio
async def test_fastapi_endpoints_integration():
    """
    Validates the end-to-end HTTP REST endpoints using FastAPI TestClient:
    - POST /api/v1/meetings/{id}/outcomes/analyze
    - GET /api/v1/commitments
    - POST /api/v1/commitments/{id}/confirm
    - GET /api/v1/projects/{id}/progress
    - GET /api/v1/meetings/{id}/follow-up
    - PATCH /api/v1/meetings/{id}/follow-up/{draft_id}
    """
    user_id = str(uuid.uuid4())
    await seed_user(user_id)
    project_id, meeting_id = await create_test_project_and_meeting(user_id)

    # Generate valid Supabase JWT for this tenant
    token = create_access_token({"sub": user_id, "role": "authenticated"})
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Analyze outcomes
        resp = await client.post(
            f"/api/v1/meetings/{meeting_id}/outcomes/analyze",
            json={
                "notes": "Decided on micro-commitments. Sarah Chen will prepare QA checklist. Jordan to review."
            },
            headers=headers
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "meeting_summary" in data
        assert len(data["commitments"]) >= 1
        comm_id = data["commitments"][0]["id"]
        draft_id = data["follow_up_draft"]["id"]

        # 2. List commitments via API
        list_resp = await client.get("/api/v1/commitments", headers=headers)
        assert list_resp.status_code == 200
        assert len(list_resp.json()) >= 1

        # 3. Confirm commitment via API
        confirm_resp = await client.post(f"/api/v1/commitments/{comm_id}/confirm", headers=headers)
        assert confirm_resp.status_code == 200
        assert confirm_resp.json()["is_confirmed"] is True

        # 4. Check project progress via API
        prog_resp = await client.get(f"/api/v1/projects/{project_id}/progress", headers=headers)
        assert prog_resp.status_code == 200
        prog_data = prog_resp.json()
        assert prog_data["total_commitments"] >= 1
        assert prog_data["confirmed_commitments"] >= 1

        # 5. Fetch follow-up draft via API
        draft_resp = await client.get(f"/api/v1/meetings/{meeting_id}/follow-up", headers=headers)
        assert draft_resp.status_code == 200
        assert draft_resp.json()["status"] == "draft"

        # 6. Update follow-up draft via API
        patch_draft_resp = await client.patch(
            f"/api/v1/meetings/{meeting_id}/follow-up/{draft_id}",
            json={"status": "reviewed", "subject": "Final Follow-up from Meeting"},
            headers=headers
        )
        assert patch_draft_resp.status_code == 200
        assert patch_draft_resp.json()["status"] == "reviewed"
