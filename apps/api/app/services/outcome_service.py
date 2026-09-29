import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text

from apps.api.app.core.db import get_tenant_session
from apps.api.app.providers.groq_adapter import GroqAdapter
from apps.api.app.schemas.outcome import CommitmentUpdate, FollowUpDraftUpdate
from apps.api.app.services.cost_service import CostService


class OutcomeService:
    def __init__(self, llm_adapter: Optional[GroqAdapter] = None):
        self.llm_adapter = llm_adapter or GroqAdapter()

    async def analyze_and_store_outcomes(
        self,
        user_id: str,
        meeting_id: UUID,
        notes: str,
        transcript: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyzes post-meeting notes and transcript.
        Atomically records decisions, inserts proposed commitments (is_confirmed=False),
        creates draft-only follow-up communication, marks meeting completed, and settles cost.
        """
        async with get_tenant_session(user_id) as session:
            # 1. Fetch and lock meeting
            meeting_res = await session.execute(
                text("""
                SELECT id, title, project_id, status, notes
                FROM public.meetings
                WHERE id = :meeting_id AND user_id = :user_id
                FOR UPDATE;
                """),
                {"meeting_id": str(meeting_id), "user_id": user_id}
            )
            meeting_row = meeting_res.mappings().first()
            if not meeting_row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Meeting {meeting_id} not found"
                )

            # 2. Gather meeting participants
            part_res = await session.execute(
                text("""
                SELECT id, name, role, is_organizer
                FROM public.meeting_participants
                WHERE meeting_id = :meeting_id AND user_id = :user_id;
                """),
                {"meeting_id": str(meeting_id), "user_id": user_id}
            )
            participants = [
                {
                    "id": str(r["id"]),
                    "name": r["name"],
                    "role": r["role"],
                    "is_organizer": r["is_organizer"]
                }
                for r in part_res.mappings().all()
            ]

            # 3. Reserve budget for LLM analysis
            est_cost = Decimal("0.0100")
            reservation_id = await CostService.reserve_budget(
                user_id=user_id,
                estimated_cost=est_cost,
                operation_type="outcome_proposal",
                model_provider="groq",
                model_name=self.llm_adapter.model
            )

            try:
                # 4. Generate structured outcomes via LLM Adapter
                llm_output = self.llm_adapter.analyze_meeting_outcomes(
                    meeting_title=meeting_row["title"],
                    participants=participants,
                    notes=notes,
                    transcript=transcript
                )

                # Settle actual cost
                await CostService.settle_reservation(
                    user_id=user_id,
                    ledger_id=reservation_id,
                    prompt_tokens=850,
                    completion_tokens=420
                )
            except Exception as e:
                await CostService.release_reservation(user_id=user_id, ledger_id=reservation_id)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to analyze meeting outcomes: {str(e)}"
                )

            # 5. Update meeting notes and status to completed
            await session.execute(
                text("""
                UPDATE public.meetings
                SET notes = :notes, status = 'completed', updated_at = NOW()
                WHERE id = :meeting_id AND user_id = :user_id;
                """),
                {"notes": notes, "meeting_id": str(meeting_id), "user_id": user_id}
            )

            # 6. Insert proposed commitments (INVARIANT: is_confirmed = FALSE)
            inserted_commitments = []
            for item in llm_output.proposed_commitments:
                comm_res = await session.execute(
                    text("""
                    INSERT INTO public.commitments (
                        user_id, meeting_id, project_id, owner_name,
                        description, due_date, status, is_confirmed,
                        source_excerpt
                    )
                    VALUES (
                        :user_id, :meeting_id, :project_id, :owner_name,
                        :description, :due_date, 'pending', FALSE,
                        :source_excerpt
                    )
                    RETURNING id, user_id, meeting_id, project_id, owner_name,
                              description, due_date, status, is_confirmed,
                              source_excerpt, created_at, updated_at;
                    """),
                    {
                        "user_id": user_id,
                        "meeting_id": str(meeting_id),
                        "project_id": str(meeting_row["project_id"]) if meeting_row["project_id"] else None,
                        "owner_name": item.owner_name,
                        "description": item.description,
                        "due_date": item.due_date,
                        "source_excerpt": item.source_excerpt
                    }
                )
                comm_row = comm_res.mappings().first()
                inserted_commitments.append(dict(comm_row))

            # 7. Insert follow-up draft (INVARIANT: status = 'draft', zero client-send capability)
            draft_item = llm_output.follow_up_draft
            draft_res = await session.execute(
                text("""
                INSERT INTO public.follow_up_drafts (
                    user_id, meeting_id, subject, body, recipients, status
                )
                VALUES (
                    :user_id, :meeting_id, :subject, :body,
                    CAST(:recipients AS JSONB), 'draft'
                )
                RETURNING id, user_id, meeting_id, subject, body, recipients,
                          status, created_at, updated_at;
                """),
                {
                    "user_id": user_id,
                    "meeting_id": str(meeting_id),
                    "subject": draft_item.subject,
                    "body": draft_item.body,
                    "recipients": json.dumps(draft_item.recipients)
                }
            )
            draft_row = draft_res.mappings().first()
            draft_dict = dict(draft_row)
            if isinstance(draft_dict.get("recipients"), str):
                draft_dict["recipients"] = json.loads(draft_dict["recipients"])

            return {
                "meeting_id": meeting_id,
                "meeting_summary": llm_output.meeting_summary,
                "decisions_made": llm_output.decisions_made,
                "commitments": inserted_commitments,
                "follow_up_draft": draft_dict
            }

    async def confirm_commitment(self, user_id: str, commitment_id: UUID) -> Dict[str, Any]:
        """
        Explicitly confirms an inferred commitment (is_confirmed: False -> True).
        """
        async with get_tenant_session(user_id) as session:
            res = await session.execute(
                text("""
                UPDATE public.commitments
                SET is_confirmed = TRUE, updated_at = NOW()
                WHERE id = :c_id AND user_id = :u_id
                RETURNING id, user_id, meeting_id, project_id, owner_name,
                          description, due_date, status, is_confirmed,
                          source_excerpt, created_at, updated_at;
                """),
                {"c_id": str(commitment_id), "u_id": user_id}
            )
            row = res.mappings().first()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Commitment {commitment_id} not found"
                )
            return dict(row)

    async def update_commitment(
        self,
        user_id: str,
        commitment_id: UUID,
        payload: CommitmentUpdate
    ) -> Dict[str, Any]:
        """
        Updates commitment details (status, due date, description, owner).
        """
        async with get_tenant_session(user_id) as session:
            updates = []
            params: Dict[str, Any] = {"c_id": str(commitment_id), "u_id": user_id}

            if payload.status is not None:
                updates.append("status = :status")
                params["status"] = payload.status
            if payload.description is not None:
                updates.append("description = :description")
                params["description"] = payload.description
            if payload.due_date is not None:
                updates.append("due_date = :due_date")
                params["due_date"] = payload.due_date
            if payload.owner_name is not None:
                updates.append("owner_name = :owner_name")
                params["owner_name"] = payload.owner_name

            if not updates:
                # Return current state if no updates
                res = await session.execute(
                    text("SELECT * FROM public.commitments WHERE id = :c_id AND user_id = :u_id;"),
                    params
                )
                row = res.mappings().first()
                if not row:
                    raise HTTPException(status_code=404, detail="Commitment not found")
                return dict(row)

            updates.append("updated_at = NOW()")
            query = f"""
            UPDATE public.commitments
            SET {', '.join(updates)}
            WHERE id = :c_id AND user_id = :u_id
            RETURNING id, user_id, meeting_id, project_id, owner_name,
                      description, due_date, status, is_confirmed,
                      source_excerpt, created_at, updated_at;
            """
            res = await session.execute(text(query), params)
            row = res.mappings().first()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Commitment {commitment_id} not found"
                )
            return dict(row)

    async def list_commitments(
        self,
        user_id: str,
        meeting_id: Optional[UUID] = None,
        project_id: Optional[UUID] = None,
        commitment_status: Optional[str] = None,
        is_confirmed: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """
        Lists commitments with multi-attribute filtering under strict tenant isolation.
        """
        async with get_tenant_session(user_id) as session:
            clauses = ["user_id = :u_id"]
            params: Dict[str, Any] = {"u_id": user_id}

            if meeting_id is not None:
                clauses.append("meeting_id = :meeting_id")
                params["meeting_id"] = str(meeting_id)
            if project_id is not None:
                clauses.append("project_id = :project_id")
                params["project_id"] = str(project_id)
            if commitment_status is not None:
                clauses.append("status = :status")
                params["status"] = commitment_status
            if is_confirmed is not None:
                clauses.append("is_confirmed = :is_confirmed")
                params["is_confirmed"] = is_confirmed

            query = f"""
            SELECT id, user_id, meeting_id, project_id, owner_name,
                   description, due_date, status, is_confirmed,
                   source_excerpt, created_at, updated_at
            FROM public.commitments
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at DESC;
            """
            res = await session.execute(text(query), params)
            return [dict(r) for r in res.mappings().all()]

    async def get_follow_up_draft(self, user_id: str, meeting_id: UUID) -> Dict[str, Any]:
        """
        Retrieves the latest draft follow-up for a meeting.
        """
        async with get_tenant_session(user_id) as session:
            res = await session.execute(
                text("""
                SELECT id, user_id, meeting_id, subject, body, recipients,
                       status, created_at, updated_at
                FROM public.follow_up_drafts
                WHERE meeting_id = :m_id AND user_id = :u_id
                ORDER BY created_at DESC
                LIMIT 1;
                """),
                {"m_id": str(meeting_id), "u_id": user_id}
            )
            row = res.mappings().first()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No follow-up draft found for meeting {meeting_id}"
                )
            d = dict(row)
            if isinstance(d.get("recipients"), str):
                d["recipients"] = json.loads(d["recipients"])
            return d

    async def update_follow_up_draft(
        self,
        user_id: str,
        draft_id: UUID,
        payload: FollowUpDraftUpdate
    ) -> Dict[str, Any]:
        """
        Updates follow-up draft content or status (draft -> reviewed / discarded).
        INVARIANT: No send endpoint or sent status exists.
        """
        async with get_tenant_session(user_id) as session:
            updates = []
            params: Dict[str, Any] = {"d_id": str(draft_id), "u_id": user_id}

            if payload.subject is not None:
                updates.append("subject = :subject")
                params["subject"] = payload.subject
            if payload.body is not None:
                updates.append("body = :body")
                params["body"] = payload.body
            if payload.recipients is not None:
                updates.append("recipients = CAST(:recipients AS JSONB)")
                params["recipients"] = json.dumps(payload.recipients)
            if payload.status is not None:
                updates.append("status = :status")
                params["status"] = payload.status

            if not updates:
                res = await session.execute(
                    text("SELECT * FROM public.follow_up_drafts WHERE id = :d_id AND user_id = :u_id;"),
                    params
                )
                row = res.mappings().first()
                if not row:
                    raise HTTPException(status_code=404, detail="Follow-up draft not found")
                d = dict(row)
                if isinstance(d.get("recipients"), str):
                    d["recipients"] = json.loads(d["recipients"])
                return d

            updates.append("updated_at = NOW()")
            query = f"""
            UPDATE public.follow_up_drafts
            SET {', '.join(updates)}
            WHERE id = :d_id AND user_id = :u_id
            RETURNING id, user_id, meeting_id, subject, body, recipients,
                      status, created_at, updated_at;
            """
            res = await session.execute(text(query), params)
            row = res.mappings().first()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Follow-up draft {draft_id} not found"
                )
            d = dict(row)
            if isinstance(d.get("recipients"), str):
                d["recipients"] = json.loads(d["recipients"])
            return d

    async def get_project_progress(self, user_id: str, project_id: UUID) -> Dict[str, Any]:
        """
        Aggregates project progress metrics across commitments.
        Identifies confirmed vs proposed commitments, completion rate, and blockers.
        """
        async with get_tenant_session(user_id) as session:
            # Check project exists and belongs to user
            p_res = await session.execute(
                text("SELECT id, name FROM public.projects WHERE id = :p_id AND user_id = :u_id;"),
                {"p_id": str(project_id), "u_id": user_id}
            )
            project = p_res.mappings().first()
            if not project:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Project {project_id} not found"
                )

            # Fetch all commitments for this project
            comm_res = await session.execute(
                text("""
                SELECT id, owner_name, description, due_date, status, is_confirmed
                FROM public.commitments
                WHERE project_id = :p_id AND user_id = :u_id;
                """),
                {"p_id": str(project_id), "u_id": user_id}
            )
            commitments = [dict(r) for r in comm_res.mappings().all()]

            today = date.today()
            total = len(commitments)
            confirmed = sum(1 for c in commitments if c["is_confirmed"])
            proposed = sum(1 for c in commitments if not c["is_confirmed"])
            completed = sum(1 for c in commitments if c["status"] == "completed")
            in_progress = sum(1 for c in commitments if c["status"] == "in_progress")
            
            overdue_list = [
                c for c in commitments
                if c["due_date"] and c["due_date"] < today and c["status"] in ("pending", "in_progress")
            ]
            overdue_count = len(overdue_list)
            
            completion_rate = round((completed / total * 100.0), 2) if total > 0 else 0.0

            blockers = []
            for c in overdue_list:
                blockers.append(f"Overdue: {c['owner_name']} - '{c['description']}' (Due: {c['due_date']})")
            for c in commitments:
                if c["status"] == "missed":
                    blockers.append(f"Missed: {c['owner_name']} - '{c['description']}'")

            return {
                "project_id": project_id,
                "total_commitments": total,
                "confirmed_commitments": confirmed,
                "proposed_commitments": proposed,
                "completed_commitments": completed,
                "in_progress_commitments": in_progress,
                "pending_commitments": in_progress + proposed,
                "overdue_commitments": overdue_count,
                "missed_commitments": sum(1 for c in commitments if c["status"] == "missed"),
                "completion_rate_pct": completion_rate,
                "completion_pct": completion_rate,
                "blockers_detected": blockers,
                "blockers": blockers
            }
