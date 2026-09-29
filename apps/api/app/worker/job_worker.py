import asyncio
import os
import uuid
import socket
import logging
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from apps.api.app.services.queue_service import QueueService
from apps.api.app.services.cost_service import CostService
from apps.api.app.services.briefing_service import BriefingService
from apps.api.app.services.calendar_sync_service import CalendarSyncService
from apps.api.app.services.meeting_intelligence_service import MeetingIntelligenceService
from apps.api.app.core.db import get_tenant_session
from sqlalchemy import text

logger = logging.getLogger("JobWorker")
logging.basicConfig(level=logging.INFO)

class JobWorker:
    def __init__(self, worker_id: Optional[str] = None):
        hostname = socket.gethostname()
        pid = os.getpid()
        self.worker_id = worker_id or f"worker_{hostname}_{pid}_{uuid.uuid4().hex[:6]}"
        self.briefing_service = BriefingService()
        self.calendar_sync_service = CalendarSyncService()
        self.intelligence_service = MeetingIntelligenceService()
        self._running = False

    async def execute_job(self, job: Dict[str, Any]):
        job_id = job["id"]
        user_id = str(job["user_id"])
        job_type = job["job_type"]
        payload = job.get("payload") or {}
        resource_id = job["resource_id"]

        logger.info(f"[{self.worker_id}] Executing job {job_id} ({job_type}) for user {user_id}")

        # Start periodic heartbeat task
        stop_heartbeat = asyncio.Event()

        async def heartbeat_loop():
            while not stop_heartbeat.is_set():
                await asyncio.sleep(30)
                if stop_heartbeat.is_set():
                    break
                await QueueService.heartbeat(job_id, self.worker_id)

        heartbeat_task = asyncio.create_task(heartbeat_loop())
        ledger_id = None

        try:
            if job_type == "prep_meeting":
                meeting_id = resource_id
                target_version = payload.get("meeting_version")

                # Verify meeting version before doing heavy work
                async with get_tenant_session(user_id) as session:
                    res = await session.execute(
                        text("SELECT meeting_version, status FROM public.meetings WHERE id = :m_id;"),
                        {"m_id": str(meeting_id)}
                    )
                    meeting = res.mappings().first()
                    if not meeting:
                        raise ValueError(f"Meeting {meeting_id} no longer exists")

                    if target_version is not None and meeting["meeting_version"] != target_version:
                        logger.info(f"Job {job_id} target version {target_version} superseded by meeting version {meeting['meeting_version']}")
                        await session.execute(
                            text("UPDATE public.background_jobs SET status = 'superseded', completed_at = NOW() WHERE id = :j_id;"),
                            {"j_id": str(job_id)}
                        )
                        return

                # 1. Atomically reserve budget
                ledger_id = await CostService.reserve_budget(
                    user_id=user_id,
                    operation_type="briefing",
                    job_id=job_id
                )

                # 2. Synthesize and promote briefing atomically
                briefing_res = await self.briefing_service.generate_and_promote_briefing(
                    user_id=user_id,
                    meeting_id=meeting_id,
                    force_refresh=True
                )

                # 3. Settle budget (estimate token usage based on briefing size)
                # In production, Groq provider returns actual prompt_tokens & completion_tokens
                prompt_est = 2500
                completion_est = 800
                await CostService.settle_reservation(
                    user_id=user_id,
                    ledger_id=ledger_id,
                    prompt_tokens=prompt_est,
                    completion_tokens=completion_est
                )
                ledger_id = None # Successfully settled

                # 4. Mark job completed
                await QueueService.complete_job(job_id, self.worker_id)
                logger.info(f"[{self.worker_id}] Job {job_id} completed successfully.")

            elif job_type == "calendar_sync":
                # Sync calendar events for a user
                force_full = payload.get("force_full_sync", False)
                summary = await self.calendar_sync_service.sync_for_user(
                    user_id=user_id,
                    force_full_sync=force_full
                )
                logger.info(f"[{self.worker_id}] Calendar sync result: {summary}")
                await QueueService.complete_job(job_id, self.worker_id)

            elif job_type == "transcript_analysis":
                # Analyze a transcript and extract intelligence
                transcript_source_id = payload.get("transcript_source_id")
                meeting_id = resource_id
                if not transcript_source_id:
                    raise ValueError("transcript_source_id required in payload for transcript_analysis job")

                ledger_id = await CostService.reserve_budget(
                    user_id=user_id,
                    operation_type="transcript_analysis",
                    job_id=job_id
                )
                result = await self.intelligence_service.analyze_transcript(
                    user_id=user_id,
                    meeting_id=str(meeting_id),
                    transcript_source_id=transcript_source_id,
                    job_id=job_id
                )
                prompt_est = 3500
                completion_est = 700
                await CostService.settle_reservation(
                    user_id=user_id,
                    ledger_id=ledger_id,
                    prompt_tokens=prompt_est,
                    completion_tokens=completion_est
                )
                ledger_id = None
                logger.info(f"[{self.worker_id}] Transcript analysis complete: {result.get('items_extracted')}")
                await QueueService.complete_job(job_id, self.worker_id)

            elif job_type == "information_gather":
                # Orchestrated multi-step information gathering for a meeting
                meeting_id = resource_id
                run_types = payload.get("run_types", ["hindsight_recall", "contact_research"])

                # Log the gathering run (no LLM budget needed for routing)
                logger.info(f"[{self.worker_id}] Information gathering for meeting {meeting_id}: {run_types}")

                # Calendar sync if requested
                if "calendar_sync" in run_types:
                    await self.calendar_sync_service.sync_for_user(user_id)

                # For now, enqueue a prep_meeting job to refresh the briefing after gathering
                await QueueService.enqueue(
                    user_id=user_id,
                    job_type="prep_meeting",
                    resource_id=str(meeting_id),
                    payload={"triggered_by": "information_gather"},
                    idempotency_key=f"prep_after_gather_{meeting_id}",
                )
                await QueueService.complete_job(job_id, self.worker_id)

            else:
                logger.warning(f"Unsupported job type: {job_type}")
                await QueueService.complete_job(job_id, self.worker_id)

        except Exception as e:
            logger.error(f"[{self.worker_id}] Job {job_id} failed: {str(e)}", exc_info=True)
            if ledger_id:
                # Release reserved funds on failure
                try:
                    await CostService.release_reservation(user_id, ledger_id)
                except Exception as rel_err:
                    logger.error(f"Failed to release reservation {ledger_id}: {rel_err}")

            await QueueService.fail_or_retry_job(job_id, self.worker_id, str(e))

        finally:
            stop_heartbeat.set()
            heartbeat_task.cancel()

    async def run_once(self, batch_size: int = 5) -> int:
        """
        Executes a single polling iteration. Returns number of processed jobs.
        Useful for unit/integration testing and scheduled cron invocations.
        """
        # 1. Recover any stale leases from crashed workers
        recovered = await QueueService.recover_stale_leases()
        if recovered > 0:
            logger.info(f"[{self.worker_id}] Recovered {recovered} stale worker leases.")

        # 2. Claim due jobs
        jobs = await QueueService.claim_jobs(self.worker_id, batch_size=batch_size)
        if not jobs:
            return 0

        # 3. Execute claimed jobs concurrently
        tasks = [self.execute_job(j) for j in jobs]
        await asyncio.gather(*tasks)
        return len(jobs)

    async def run_forever(self, poll_interval_seconds: float = 3.0, batch_size: int = 5):
        """
        Continuous daemon worker polling loop with graceful shutdown support.
        """
        self._running = True
        logger.info(f"Worker {self.worker_id} started. Polling every {poll_interval_seconds}s...")
        try:
            while self._running:
                processed = await self.run_once(batch_size=batch_size)
                if processed == 0:
                    await asyncio.sleep(poll_interval_seconds)
        except asyncio.CancelledError:
            logger.info(f"Worker {self.worker_id} shutting down gracefully...")
        finally:
            self._running = False
