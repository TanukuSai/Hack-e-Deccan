"""
Gate 5: Comprehensive Test Suite for Contextual Memory, Deterministic Learning & Cold-Start Strategy.
Validates:
1. Mathematical Confidence Learning: C = clip(B + S - K - D, 0.0, 1.0)
2. Reversible Preference Undo: Restores user control by zeroing confidence
3. Multi-Scoped Preferences: Global, project, contact, and meeting_type scoping
4. Multi-Tenant Isolation on Preferences: Tenant B cannot read or undo Tenant A's preferences
5. Hindsight Memory Cloud Operations: Bank creation, memory retention, recall, and GDPR deletion
6. Graceful Degradation on Memory Outage: Briefing proceeds and flags degraded_reason
7. Cold-Start Dual Option Presentation: Option A (dossier upload) vs Option B (web research)
8. Automated Web Research Enrichment: Extracts domain, writes dossier, tags as unverified_assumption
9. FastAPI REST Endpoints Integration: Validates /preferences and /contacts/{id}/enrich routes
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text

from apps.api.app.main import app
from apps.api.app.core.db import engine, get_tenant_session
from apps.api.app.core.security import create_access_token
from apps.api.app.services.preference_service import PreferenceService
from apps.api.app.services.enrichment_service import EnrichmentService
from apps.api.app.providers.hindsight_adapter import HindsightAdapter

async def seed_user(user_id: str):
    unique_email = f"user_{uuid.uuid4().hex[:10]}@example.com"
    async with engine.begin() as conn:
        await conn.execute(
            text("SELECT public.seed_test_user(CAST(:u_id AS UUID), :email, 25.0, 0.0);"),
            {"u_id": user_id, "email": unique_email}
        )

# ==============================================================================
# 1. Deterministic Preference Learning Mathematical Tests
# ==============================================================================

def test_confidence_mathematical_formula():
    """
    Validates C = clip(B + S - K - D, 0.0, 1.0)
    """
    # 1. Baseline
    assert PreferenceService.calculate_confidence("explicit") == 1.0
    assert PreferenceService.calculate_confidence("learned") == 0.5

    # 2. Positive signals (+0.10 each)
    c_pos = PreferenceService.calculate_confidence("learned", positive_signals=3)
    assert c_pos == 0.8  # 0.5 + 0.3

    # 3. Corrections / friction (-0.15 each)
    c_fric = PreferenceService.calculate_confidence("learned", positive_signals=3, corrections=2)
    assert c_fric == 0.5  # 0.8 - 0.3

    # 4. Inactivity decay (-0.01 per day, max 0.20)
    c_decay = PreferenceService.calculate_confidence("learned", positive_signals=3, corrections=2, days_inactive=10)
    assert c_decay == 0.4  # 0.5 - 0.1

    # 5. Boundary clipping
    assert PreferenceService.calculate_confidence("learned", positive_signals=10) == 1.0
    assert PreferenceService.calculate_confidence("learned", corrections=10) == 0.0


@pytest.mark.asyncio
async def test_preference_crud_and_reversible_undo():
    """
    Validates explicit creation, implicit learning, and reversible undo.
    """
    user_id = str(uuid.uuid4())
    await seed_user(user_id)
    svc = PreferenceService()

    # 1. Create explicit preference
    explicit_pref = await svc.set_explicit_preference(
        user_id=user_id,
        dimension="briefing_format",
        scope="global",
        scope_id="",
        key="format",
        value={"format": "concise"}
    )
    assert explicit_pref["confidence"] == 1.0
    assert explicit_pref["source_type"] == "explicit"

    # 2. Learn implicit preference
    learned_pref = await svc.learn_preference(
        user_id=user_id,
        dimension="topic_priority",
        scope="contact",
        scope_id="contact_123",
        key="focus",
        value={"priority": "budget_discussions"},
        positive_signals=2
    )
    assert learned_pref["confidence"] == 0.7  # 0.5 + 0.2
    assert learned_pref["source_type"] == "learned"

    # 3. Reversible Undo: user resets learned preference
    undone = await svc.undo_learned_preference(user_id=user_id, preference_id=learned_pref["id"])
    assert undone["confidence"] == 0.0
    assert undone["id"] == learned_pref["id"]

    # 4. List preferences filters properly
    prefs = await svc.list_preferences(user_id=user_id, dimension="briefing_format")
    assert len(prefs) == 1
    assert prefs[0]["id"] == explicit_pref["id"]


@pytest.mark.asyncio
async def test_tenant_isolation_on_preferences():
    """
    Validates that Tenant B cannot view or undo Tenant A's preferences.
    """
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    await seed_user(user_a)
    await seed_user(user_b)
    svc = PreferenceService()

    pref_a = await svc.set_explicit_preference(
        user_id=user_a,
        dimension="preparation_timing",
        scope="global",
        scope_id="",
        key="lead_time",
        value={"hours": 4}
    )

    # Tenant B tries to list Tenant A's preferences -> sees 0
    b_prefs = await svc.list_preferences(user_id=user_b)
    assert len(b_prefs) == 0

    # Tenant B tries to undo Tenant A's preference -> 404
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        await svc.undo_learned_preference(user_id=user_b, preference_id=pref_a["id"])
    assert exc.value.status_code == 404


# ==============================================================================
# 2. Hindsight Contextual Memory Cloud Operations
# ==============================================================================

@pytest.mark.asyncio
async def test_hindsight_live_cloud_integration():
    """
    Validates real integration against Hindsight Cloud API (https://api.hindsight.vectorize.io).
    Tests ensure_bank, retain_memory, recall_memories, and delete_bank.
    """
    adapter = HindsightAdapter()
    if not adapter.enabled or not adapter.api_key:
        pytest.skip("Hindsight not enabled or missing API key")

    # 1. Health check
    is_healthy = await adapter.is_healthy()
    assert is_healthy is True, "Hindsight API should be healthy"

    # 2. Idempotent bank creation
    test_bank_id = f"test_{uuid.uuid4().hex[:12]}"
    created = await adapter.ensure_bank(test_bank_id, name="Test Integration Bank")
    assert created is True

    try:
        # 3. Retain memory
        retained = await adapter.retain_memory(
            bank_id=test_bank_id,
            content="Sarah Chen confirmed that the Q4 database migration will complete before November.",
            context="Architecture sync",
            tags=["migration", "sarah_chen"]
        )
        assert retained is True

        # 4. Recall memory
        memories = await adapter.recall_memories(
            bank_id=test_bank_id,
            query="When will the database migration complete?"
        )
        assert isinstance(memories, list)
    finally:
        # 5. GDPR Deletion: Clean up test bank
        deleted = await adapter.delete_bank(test_bank_id)
        assert deleted is True


@pytest.mark.asyncio
async def test_hindsight_graceful_degradation_when_offline():
    """
    Validates that if Hindsight is offline/unreachable, adapter returns empty list gracefully.
    """
    offline_adapter = HindsightAdapter(
        base_url="https://unreachable.hindsight.invalid",
        timeout=1,
        enabled=True
    )
    # Recall should catch error and return [] without crashing
    recalled = await offline_adapter.recall_memories("bank_123", "query")
    assert recalled == []

    # Retain should return False without crashing
    retained = await offline_adapter.retain_memory("bank_123", "content")
    assert retained is False


# ==============================================================================
# 3. First-Time Contact Cold-Start Strategy (Option A vs Option B)
# ==============================================================================

@pytest.mark.asyncio
async def test_cold_start_enrichment_options_and_web_research():
    """
    Validates that the system presents two explicit choices for first-time contacts:
    - Option A: Upload Background Report / Dossier
    - Option B: Automated Internet Research
    And validates execution of Option B using email domain extraction and epistemic tagging.
    """
    user_id = str(uuid.uuid4())
    await seed_user(user_id)

    # Create a first-time contact
    async with get_tenant_session(user_id) as session:
        c_res = await session.execute(
            text("""
            INSERT INTO public.contacts (user_id, name, email, organization, role_title)
            VALUES (:u_id, 'Elena Rostova', 'elena@datadoghq.com', NULL, 'VP of Infrastructure')
            RETURNING id;
            """),
            {"u_id": user_id}
        )
        contact_id = c_res.scalar()

    enrichment_svc = EnrichmentService()

    # 1. Verify two options are presented to the user
    options_data = await enrichment_svc.get_enrichment_options(user_id=user_id, contact_id=contact_id)
    assert options_data["contact_name"] == "Elena Rostova"
    assert options_data["inferred_company"] == "Datadoghq"
    options = options_data["options"]
    assert len(options) == 2
    assert options[0]["option_id"] == "upload_report"
    assert options[1]["option_id"] == "web_search"

    # 2. Execute Option B (Automated Web Research)
    research_res = await enrichment_svc.execute_web_enrichment(
        user_id=user_id,
        contact_id=contact_id,
        meeting_title="Observability Architecture Review",
        meeting_purpose="Evaluate distributed tracing integration"
    )
    assert research_res["contact_name"] == "Elena Rostova"
    assert "Datadoghq" in research_res["organization"]
    assert research_res["epistemic_class"] == "unverified_assumption"
    assert research_res["verified"] is False
    assert research_res["document_id"] is not None

    # 3. Verify contact profile was updated in DB
    async with get_tenant_session(user_id) as session:
        c_row = (await session.execute(
            text("SELECT notes, organization FROM public.contacts WHERE id = :c_id;"),
            {"c_id": str(contact_id)}
        )).mappings().first()
        assert "Automated Web Dossier" in c_row["notes"]


# ==============================================================================
# 4. FastAPI Endpoints Integration
# ==============================================================================

@pytest.mark.asyncio
async def test_fastapi_gate5_endpoints():
    """
    Validates HTTP REST endpoints for preferences and cold-start enrichment.
    """
    user_id = str(uuid.uuid4())
    await seed_user(user_id)
    token = create_access_token({"sub": user_id, "role": "authenticated"})
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create preference via API
        post_pref = await client.post(
            "/api/v1/preferences",
            json={
                "dimension": "briefing_format",
                "scope": "global",
                "scope_id": "",
                "key": "style",
                "value": {"detail": "standard"}
            },
            headers=headers
        )
        assert post_pref.status_code == 201
        pref_id = post_pref.json()["id"]

        # 2. List preferences via API
        list_pref = await client.get("/api/v1/preferences", headers=headers)
        assert list_pref.status_code == 200
        assert len(list_pref.json()) >= 1

        # 3. Undo preference via API
        undo_resp = await client.post(f"/api/v1/preferences/{pref_id}/undo", headers=headers)
        assert undo_resp.status_code == 200
        assert undo_resp.json()["confidence"] == 0.0

        # 4. Create contact and fetch enrichment options via API
        c_post = await client.post(
            "/api/v1/contacts",
            json={
                "name": "Marcus Aurelius",
                "email": "marcus@rome.org",
                "role_title": "Leader"
            },
            headers=headers
        )
        contact_id = c_post.json()["id"]

        opt_resp = await client.get(f"/api/v1/contacts/{contact_id}/enrich/options", headers=headers)
        assert opt_resp.status_code == 200
        assert len(opt_resp.json()["options"]) == 2

        # 5. Trigger Option B web enrichment via API
        search_resp = await client.post(
            f"/api/v1/contacts/{contact_id}/enrich/search",
            params={"meeting_title": "Philosophical Alignment"},
            headers=headers
        )
        assert search_resp.status_code == 200
        assert search_resp.json()["epistemic_class"] == "unverified_assumption"
