import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from uuid import UUID
import uuid
from sqlalchemy import text
from apps.api.app.core.db import get_tenant_session, engine

DEFAULT_LEASE_SECONDS = 300 # 5 minutes
HEARTBEAT_INTERVAL_SECONDS = 30

class QueueService:
    @staticmethod
    async def enqueue_job(
        user_id: str,
        job_type: str,
        resource_id: UUID,
        idempotency_key: str,
        payload: Optional[Dict[str, Any]] = None,
        scheduled_for: Optional[datetime] = None,
        priority: int = 10,
        max_attempts: int = 3
    ) -> Optional[UUID]:
        """
        Idempotently enqueues a background job.
        If idempotency_key already exists, returns existing job ID without duplicate creation.
        """
        payload_data = payload or {}
        sched_time = scheduled_for or datetime.now(timezone.utc)

        async with get_tenant_session(user_id) as session:
            res = await session.execute(
                text("""
                INSERT INTO public.background_jobs (
                    user_id, job_type, resource_id, idempotency_key, payload,
                    status, priority, max_attempts, scheduled_for
                )
                VALUES (
                    :user_id, :job_type, :resource_id, :idempotency_key, CAST(:payload AS JSONB),
                    'queued', :priority, :max_attempts, :scheduled_for
                )
                ON CONFLICT (idempotency_key) DO UPDATE
                    SET updated_at = NOW()
                RETURNING id;
                """),
                {
                    "user_id": user_id,
                    "job_type": job_type,
                    "resource_id": str(resource_id),
                    "idempotency_key": idempotency_key,
                    "payload": json.dumps(payload_data),
                    "priority": priority,
                    "max_attempts": max_attempts,
                    "scheduled_for": sched_time
                }
            )
            return res.scalar()

    @staticmethod
    async def enqueue(
        user_id: str,
        job_type: str,
        resource_id: str,
        payload: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        scheduled_for: Optional[datetime] = None,
        priority: int = 10,
        max_attempts: int = 3
    ) -> Optional[UUID]:
        """
        Convenience wrapper around enqueue_job().
        Auto-generates idempotency_key when not supplied.
        resource_id can be a str (UUID or user_id) — cast internally.
        """
        import uuid as _uuid_mod
        key = idempotency_key or f"{job_type}_{resource_id}_{_uuid_mod.uuid4().hex}"
        try:
            rid = UUID(str(resource_id))
        except (ValueError, AttributeError):
            rid = _uuid_mod.uuid4()
        return await QueueService.enqueue_job(
            user_id=user_id,
            job_type=job_type,
            resource_id=rid,
            idempotency_key=key,
            payload=payload,
            scheduled_for=scheduled_for,
            priority=priority,
            max_attempts=max_attempts,
        )

    @staticmethod
    async def claim_jobs(
        worker_id: str,
        batch_size: int = 5,
        lease_seconds: int = DEFAULT_LEASE_SECONDS
    ) -> List[Dict[str, Any]]:
        """
        Atomically claims queued jobs due for execution using FOR UPDATE SKIP LOCKED.
        Updates status to 'running' with a timed lease.
        """
        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                # System query (cross-tenant queue processor)
                query = text("""
                WITH claimable AS (
                    SELECT id
                    FROM public.background_jobs
                    WHERE status = 'queued' AND scheduled_for <= NOW()
                    ORDER BY priority ASC, scheduled_for ASC
                    LIMIT :batch_size
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE public.background_jobs j
                SET status = 'running',
                    locked_by = :worker_id,
                    locked_at = NOW(),
                    heartbeat_at = NOW(),
                    lease_expires_at = NOW() + CAST((:lease_seconds || ' seconds') AS INTERVAL),
                    updated_at = NOW()
                FROM claimable
                WHERE j.id = claimable.id
                RETURNING j.id, j.user_id, j.job_type, j.resource_id, j.idempotency_key,
                          j.payload, j.status, j.priority, j.attempts, j.max_attempts,
                          j.lease_expires_at, j.scheduled_for;
                """)
                res = await conn.execute(query, {
                    "batch_size": batch_size,
                    "worker_id": worker_id,
                    "lease_seconds": str(lease_seconds)
                })
                rows = [dict(r) for r in res.mappings().all()]
                await trans.commit()
                return rows
            except Exception:
                await trans.rollback()
                raise

    @staticmethod
    async def heartbeat(job_id: UUID, worker_id: str, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> bool:
        """
        Renews the lease for an actively running job.
        """
        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                res = await conn.execute(
                    text("""
                    UPDATE public.background_jobs
                    SET heartbeat_at = NOW(),
                        lease_expires_at = NOW() + CAST((:lease_seconds || ' seconds') AS INTERVAL),
                        updated_at = NOW()
                    WHERE id = :j_id AND locked_by = :worker_id AND status = 'running'
                    RETURNING id;
                    """),
                    {
                        "j_id": str(job_id),
                        "worker_id": worker_id,
                        "lease_seconds": str(lease_seconds)
                    }
                )
                updated = res.scalar() is not None
                await trans.commit()
                return updated
            except Exception:
                await trans.rollback()
                return False

    @staticmethod
    async def complete_job(job_id: UUID, worker_id: str):
        """
        Marks a background job as successfully completed.
        """
        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                await conn.execute(
                    text("""
                    UPDATE public.background_jobs
                    SET status = 'completed',
                        completed_at = NOW(),
                        lease_expires_at = NULL,
                        updated_at = NOW()
                    WHERE id = :j_id AND locked_by = :worker_id;
                    """),
                    {"j_id": str(job_id), "worker_id": worker_id}
                )
                await trans.commit()
            except Exception:
                await trans.rollback()
                raise

    @staticmethod
    async def fail_or_retry_job(job_id: UUID, worker_id: str, error_message: str):
        """
        Handles job failure with exponential backoff retry.
        If attempts >= max_attempts, routes to 'dead_letter'.
        """
        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                # Check attempts vs max_attempts
                res = await conn.execute(
                    text("SELECT attempts, max_attempts FROM public.background_jobs WHERE id = :j_id FOR UPDATE;"),
                    {"j_id": str(job_id)}
                )
                row = res.mappings().first()
                if not row:
                    await trans.rollback()
                    return

                new_attempts = row["attempts"] + 1
                max_att = row["max_attempts"]

                if new_attempts < max_att:
                    # Retry with exponential backoff: 30s, 60s, 120s...
                    backoff_sec = 30 * (2 ** (new_attempts - 1))
                    await conn.execute(
                        text("""
                        UPDATE public.background_jobs
                        SET status = 'queued',
                            attempts = :att,
                            scheduled_for = NOW() + CAST((:backoff || ' seconds') AS INTERVAL),
                            next_retry_at = NOW() + CAST((:backoff || ' seconds') AS INTERVAL),
                            locked_by = NULL,
                            lease_expires_at = NULL,
                            last_error = :err,
                            updated_at = NOW()
                        WHERE id = :j_id;
                        """),
                        {"j_id": str(job_id), "att": new_attempts, "backoff": str(backoff_sec), "err": error_message[:1000]}
                    )
                else:
                    # Move to dead_letter
                    await conn.execute(
                        text("""
                        UPDATE public.background_jobs
                        SET status = 'dead_letter',
                            attempts = :att,
                            completed_at = NOW(),
                            locked_by = NULL,
                            lease_expires_at = NULL,
                            last_error = :err,
                            updated_at = NOW()
                        WHERE id = :j_id;
                        """),
                        {"j_id": str(job_id), "att": new_attempts, "err": error_message[:1000]}
                    )

                await trans.commit()
            except Exception:
                await trans.rollback()
                raise

    @staticmethod
    async def recover_stale_leases() -> int:
        """
        Scans for dead/crashed worker leases (running but lease_expires_at < NOW()).
        Recovers claimable jobs for retry or transitions dead letters.
        """
        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                # Fetch expired running jobs
                res = await conn.execute(
                    text("""
                    SELECT id, attempts, max_attempts
                    FROM public.background_jobs
                    WHERE status = 'running' AND lease_expires_at < NOW()
                    FOR UPDATE SKIP LOCKED;
                    """)
                )
                expired_jobs = res.mappings().all()
                recovered_count = 0

                for job in expired_jobs:
                    j_id = str(job["id"])
                    new_att = job["attempts"] + 1
                    if new_att < job["max_attempts"]:
                        await conn.execute(
                            text("""
                            UPDATE public.background_jobs
                            SET status = 'queued',
                                attempts = :att,
                                scheduled_for = NOW(),
                                locked_by = NULL,
                                lease_expires_at = NULL,
                                last_error = 'Lease expired (worker crash recovery)',
                                updated_at = NOW()
                            WHERE id = :j_id;
                            """),
                            {"j_id": j_id, "att": new_att}
                        )
                    else:
                        await conn.execute(
                            text("""
                            UPDATE public.background_jobs
                            SET status = 'dead_letter',
                                attempts = :att,
                                completed_at = NOW(),
                                locked_by = NULL,
                                lease_expires_at = NULL,
                                last_error = 'Lease expired after exceeding max attempts',
                                updated_at = NOW()
                            WHERE id = :j_id;
                            """),
                            {"j_id": j_id, "att": new_att}
                        )
                    recovered_count += 1

                await trans.commit()
                return recovered_count
            except Exception:
                await trans.rollback()
                return 0

    @staticmethod
    async def supersede_meeting_jobs(user_id: str, meeting_id: UUID, new_meeting_version: int):
        """
        When a meeting is rescheduled, supersedes any active or queued preparation jobs
        tied to an earlier meeting version.
        """
        async with get_tenant_session(user_id) as session:
            await session.execute(
                text("""
                UPDATE public.background_jobs
                SET status = 'superseded',
                    completed_at = NOW(),
                    lease_expires_at = NULL,
                    updated_at = NOW()
                WHERE resource_id = :m_id
                  AND user_id = :u_id
                  AND status IN ('queued', 'running')
                  AND CAST(payload->>'meeting_version' AS INTEGER) < :new_ver;
                """),
                {
                    "m_id": str(meeting_id),
                    "u_id": user_id,
                    "new_ver": new_meeting_version
                }
            )
