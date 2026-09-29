"""
Gate 3: Comprehensive Test Suite for Transactional Leased Background Job Queue & Cost Ledger.
Validates:
1. Enqueue & Claim Lifecycle with FOR UPDATE SKIP LOCKED
2. Concurrency Safety: Disjoint claims across multiple workers with zero contention
3. Idempotency Key Deduplication: No duplicate jobs enqueued
4. Heartbeat Renewal: Active leases extended
5. Crash Simulation & Stale Lease Recovery: Expired leases reset to queued
6. Dead Letter Routing: Jobs exceeding max_attempts routed to dead_letter
7. Meeting Reschedule Supersession: Outdated meeting version jobs superseded
8. Atomic Budget Reservation & Ceiling Enforcement: BudgetExceededException raised
9. Budget Release on Failure: Zero spend added on error
"""
import uuid
import asyncio
from decimal import Decimal
from datetime import datetime, timedelta, timezone
import pytest
from apps.api.app.services.queue_service import QueueService
from apps.api.app.services.cost_service import CostService, BudgetExceededException
from apps.api.app.core.db import get_tenant_session, engine
from sqlalchemy import text

@pytest.fixture(autouse=True)
async def cleanup_queue():
    """Ensures each queue test executes against a clean background_jobs queue."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        await conn.execute(text("DELETE FROM public.background_jobs;"))
        await trans.commit()
    yield

async def seed_user(user_id: str, email: str = "test@example.com", budget: float = 25.0, spend: float = 0.0):
    unique_email = f"user_{uuid.uuid4().hex[:10]}@example.com"
    async with engine.begin() as conn:
        await conn.execute(
            text("SELECT public.seed_test_user(CAST(:u_id AS UUID), :email, CAST(:budget AS NUMERIC), CAST(:spend AS NUMERIC));"),
            {"u_id": user_id, "email": unique_email, "budget": budget, "spend": spend}
        )

@pytest.mark.asyncio
async def test_job_enqueue_and_claim():
    user_id = str(uuid.uuid4())
    meeting_id = uuid.uuid4()
    worker_id = f"test_worker_{uuid.uuid4().hex[:6]}"

    await seed_user(user_id)

    # 1. Enqueue job
    idemp_key = f"test_prep_{meeting_id}_v1"
    job_id = await QueueService.enqueue_job(
        user_id=user_id,
        job_type="prep_meeting",
        resource_id=meeting_id,
        idempotency_key=idemp_key,
        payload={"meeting_version": 1},
        priority=5
    )
    assert job_id is not None

    # 2. Claim job
    claimed = await QueueService.claim_jobs(worker_id=worker_id, batch_size=10)
    matching = [j for j in claimed if str(j["id"]) == str(job_id)]
    assert len(matching) == 1
    job = matching[0]
    assert job["status"] == "running"
    assert job["lease_expires_at"] is not None

    # 3. Complete job
    await QueueService.complete_job(job_id=job_id, worker_id=worker_id)
    async with get_tenant_session(user_id) as session:
        res = await session.execute(
            text("SELECT status, completed_at FROM public.background_jobs WHERE id = :j_id;"),
            {"j_id": str(job_id)}
        )
        row = res.mappings().first()
        assert row["status"] == "completed"
        assert row["completed_at"] is not None

@pytest.mark.asyncio
async def test_concurrency_disjoint_claims():
    """
    Validates that FOR UPDATE SKIP LOCKED guarantees disjoint claims
    across multiple concurrent workers with zero race conditions or collisions.
    """
    user_id = str(uuid.uuid4())
    await seed_user(user_id)

    # Enqueue 10 distinct jobs
    job_ids = []
    for i in range(10):
        jid = await QueueService.enqueue_job(
            user_id=user_id,
            job_type="prep_meeting",
            resource_id=uuid.uuid4(),
            idempotency_key=f"concurrent_test_{uuid.uuid4()}",
            priority=10 - i
        )
        job_ids.append(str(jid))

    # Launch 3 workers concurrently claiming batches of 4
    w1_task = QueueService.claim_jobs(worker_id=f"worker_alpha_{uuid.uuid4().hex[:4]}", batch_size=4)
    w2_task = QueueService.claim_jobs(worker_id=f"worker_beta_{uuid.uuid4().hex[:4]}", batch_size=4)
    w3_task = QueueService.claim_jobs(worker_id=f"worker_gamma_{uuid.uuid4().hex[:4]}", batch_size=4)

    results = await asyncio.gather(w1_task, w2_task, w3_task)

    claimed_alpha = [str(j["id"]) for j in results[0] if str(j["id"]) in job_ids]
    claimed_beta = [str(j["id"]) for j in results[1] if str(j["id"]) in job_ids]
    claimed_gamma = [str(j["id"]) for j in results[2] if str(j["id"]) in job_ids]

    all_claimed = claimed_alpha + claimed_beta + claimed_gamma
    # Verify no worker claimed the same job (disjoint partition)
    assert len(all_claimed) == len(set(all_claimed))
    assert len(all_claimed) == 10

@pytest.mark.asyncio
async def test_idempotency_key_deduplication():
    user_id = str(uuid.uuid4())
    meeting_id = uuid.uuid4()
    idemp_key = f"idemp_test_{uuid.uuid4()}"

    await seed_user(user_id)

    # Enqueue first time
    id1 = await QueueService.enqueue_job(
        user_id=user_id,
        job_type="prep_meeting",
        resource_id=meeting_id,
        idempotency_key=idemp_key
    )

    # Enqueue second time with identical key
    id2 = await QueueService.enqueue_job(
        user_id=user_id,
        job_type="prep_meeting",
        resource_id=meeting_id,
        idempotency_key=idemp_key
    )

    assert id1 == id2 # Same job ID returned, zero duplicates

@pytest.mark.asyncio
async def test_heartbeat_lease_extension():
    user_id = str(uuid.uuid4())
    meeting_id = uuid.uuid4()
    worker_id = f"heartbeat_worker_{uuid.uuid4().hex[:6]}"

    await seed_user(user_id)

    job_id = await QueueService.enqueue_job(
        user_id=user_id,
        job_type="prep_meeting",
        resource_id=meeting_id,
        idempotency_key=f"hb_test_{uuid.uuid4()}"
    )

    claimed = await QueueService.claim_jobs(worker_id=worker_id, batch_size=10)
    job = [j for j in claimed if str(j["id"]) == str(job_id)][0]
    initial_lease = job["lease_expires_at"]

    # Sleep brief tick and trigger heartbeat with new lease duration
    await asyncio.sleep(0.1)
    renewed = await QueueService.heartbeat(job_id=job_id, worker_id=worker_id, lease_seconds=600)
    assert renewed is True

    async with get_tenant_session(user_id) as session:
        res = await session.execute(
            text("SELECT lease_expires_at, heartbeat_at FROM public.background_jobs WHERE id = :j_id;"),
            {"j_id": str(job_id)}
        )
        row = res.mappings().first()
        assert row["lease_expires_at"] > initial_lease
        assert row["heartbeat_at"] is not None

@pytest.mark.asyncio
async def test_crash_simulation_and_stale_lease_recovery():
    user_id = str(uuid.uuid4())
    meeting_id = uuid.uuid4()
    dead_worker = "crashed_worker_99"

    await seed_user(user_id)

    job_id = await QueueService.enqueue_job(
        user_id=user_id,
        job_type="prep_meeting",
        resource_id=meeting_id,
        idempotency_key=f"crash_test_{uuid.uuid4()}"
    )

    # Claim job
    await QueueService.claim_jobs(worker_id=dead_worker, batch_size=10)

    # Manually backdate lease_expires_at to simulate worker crash
    async with engine.connect() as conn:
        trans = await conn.begin()
        await conn.execute(
            text("UPDATE public.background_jobs SET lease_expires_at = NOW() - INTERVAL '10 seconds' WHERE id = :j_id;"),
            {"j_id": str(job_id)}
        )
        await trans.commit()

    # Run recovery
    recovered_count = await QueueService.recover_stale_leases()
    assert recovered_count >= 1

    # Verify job is recovered back to queued status with attempts incremented
    async with get_tenant_session(user_id) as session:
        res = await session.execute(
            text("SELECT status, attempts, locked_by FROM public.background_jobs WHERE id = :j_id;"),
            {"j_id": str(job_id)}
        )
        row = res.mappings().first()
        assert row["status"] == "queued"
        assert row["attempts"] == 1
        assert row["locked_by"] is None

@pytest.mark.asyncio
async def test_dead_letter_on_exceeded_attempts():
    user_id = str(uuid.uuid4())
    meeting_id = uuid.uuid4()
    worker_id = "failing_worker"

    await seed_user(user_id)

    # Enqueue job with max_attempts = 2
    job_id = await QueueService.enqueue_job(
        user_id=user_id,
        job_type="prep_meeting",
        resource_id=meeting_id,
        idempotency_key=f"dl_test_{uuid.uuid4()}",
        max_attempts=2
    )

    # First failure -> retried
    await QueueService.claim_jobs(worker_id=worker_id, batch_size=10)
    await QueueService.fail_or_retry_job(job_id, worker_id, "Transient network timeout")

    async with get_tenant_session(user_id) as session:
        r1 = await session.execute(text("SELECT status, attempts FROM public.background_jobs WHERE id = :j_id;"), {"j_id": str(job_id)})
        row1 = r1.mappings().first()
        assert row1["status"] == "queued"
        assert row1["attempts"] == 1

        # Fast forward schedule
        await session.execute(text("UPDATE public.background_jobs SET scheduled_for = NOW() WHERE id = :j_id;"), {"j_id": str(job_id)})

    # Second failure -> routes to dead_letter
    await QueueService.claim_jobs(worker_id=worker_id, batch_size=10)
    await QueueService.fail_or_retry_job(job_id, worker_id, "Fatal out of memory error")

    async with get_tenant_session(user_id) as session:
        r2 = await session.execute(text("SELECT status, attempts, last_error FROM public.background_jobs WHERE id = :j_id;"), {"j_id": str(job_id)})
        row = r2.mappings().first()
        assert row["status"] == "dead_letter"
        assert row["attempts"] == 2
        assert "Fatal out of memory" in row["last_error"]

@pytest.mark.asyncio
async def test_meeting_reschedule_supersedes_jobs():
    user_id = str(uuid.uuid4())
    meeting_id = uuid.uuid4()

    await seed_user(user_id)

    # Job for version 1
    j1 = await QueueService.enqueue_job(
        user_id=user_id,
        job_type="prep_meeting",
        resource_id=meeting_id,
        idempotency_key=f"super_v1_{uuid.uuid4()}",
        payload={"meeting_version": 1}
    )

    # Meeting rescheduled to version 2 -> supersede prior version jobs
    await QueueService.supersede_meeting_jobs(user_id, meeting_id, new_meeting_version=2)

    async with get_tenant_session(user_id) as session:
        res = await session.execute(
            text("SELECT status FROM public.background_jobs WHERE id = :j_id;"),
            {"j_id": str(j1)}
        )
        assert res.scalar() == "superseded"

@pytest.mark.asyncio
async def test_atomic_budget_reservation_and_enforcement():
    user_id = str(uuid.uuid4())

    # User with $10 budget, currently spent $9.995 (only $0.005 remaining)
    await seed_user(user_id, budget=10.00, spend=9.9950)

    # Attempting to reserve $0.0100 must fail with BudgetExceededException
    with pytest.raises(BudgetExceededException):
        await CostService.reserve_budget(
            user_id=user_id,
            estimated_cost=Decimal("0.0100")
        )

@pytest.mark.asyncio
async def test_budget_settlement_and_release():
    user_id = str(uuid.uuid4())

    await seed_user(user_id, budget=50.00, spend=0.0000)

    # 1. Successful cycle: Reserve -> Settle
    ledger_id = await CostService.reserve_budget(user_id=user_id, estimated_cost=Decimal("0.0100"))
    actual_cost = await CostService.settle_reservation(
        user_id=user_id,
        ledger_id=ledger_id,
        prompt_tokens=2000,
        completion_tokens=500
    )
    assert actual_cost > 0

    async with get_tenant_session(user_id) as session:
        res = await session.execute(text("SELECT current_month_spend_usd FROM public.user_profiles WHERE id = :u_id;"), {"u_id": user_id})
        new_spend = res.scalar()
        assert float(new_spend) == float(actual_cost)

    # 2. Failed cycle: Reserve -> Release (zero spend added)
    ledger_id_fail = await CostService.reserve_budget(user_id=user_id, estimated_cost=Decimal("0.0100"))
    await CostService.release_reservation(user_id=user_id, ledger_id=ledger_id_fail)

    async with get_tenant_session(user_id) as session:
        res2 = await session.execute(text("SELECT current_month_spend_usd FROM public.user_profiles WHERE id = :u_id;"), {"u_id": user_id})
        assert float(res2.scalar()) == float(new_spend) # Unchanged!
