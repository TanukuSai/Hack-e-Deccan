import json
from uuid import UUID
from typing import Optional, Dict, Any, List
from sqlalchemy import text
from fastapi import HTTPException, status
from apps.api.app.core.db import get_tenant_session
from apps.api.app.providers.groq_adapter import GroqAdapter
from apps.api.app.schemas.briefing import BriefingResponse, EvidenceItemResponse

class BriefingService:
    def __init__(self, llm_adapter: Optional[GroqAdapter] = None):
        self.llm_adapter = llm_adapter or GroqAdapter()

    async def generate_and_promote_briefing(
        self,
        user_id: str,
        meeting_id: UUID,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Synthesizes meeting context, generates an epistemic briefing,
        and atomically promotes it using a PostgreSQL transaction with pessimistic locking.
        """
        async with get_tenant_session(user_id) as session:
            # 1. Fetch meeting and lock row
            res = await session.execute(
                text("""
                SELECT id, title, purpose, meeting_version, status, start_time, end_time, project_id
                FROM public.meetings
                WHERE id = :meeting_id AND user_id = :user_id
                FOR UPDATE;
                """),
                {"meeting_id": str(meeting_id), "user_id": user_id}
            )
            meeting_row = res.mappings().first()
            if not meeting_row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Meeting {meeting_id} not found"
                )

            current_meeting_version = meeting_row["meeting_version"]

            # 2. Check if latest briefing already exists for this meeting version (unless force_refresh is True)
            if not force_refresh:
                briefing_res = await session.execute(
                    text("""
                    SELECT id, user_id, meeting_id, version, is_latest, 
                           summary AS executive_summary,
                           assumptions_and_gaps AS attendee_profiles,
                           strategic_questions AS strategic_priorities,
                           talking_points, conflicts_detected, created_at
                    FROM public.briefings
                    WHERE meeting_id = :meeting_id AND user_id = :user_id AND is_latest = TRUE;
                    """),
                    {"meeting_id": str(meeting_id), "user_id": user_id}
                )
                existing = briefing_res.mappings().first()
                if existing:
                    res_dict = dict(existing)
                    ev_res = await session.execute(
                        text("""
                        SELECT id, user_id, briefing_id, epistemic_class AS source_type, claim_text,
                               excerpt AS quote_or_content, source_id AS source_document_id,
                               (verified_at IS NOT NULL) AS verified
                        FROM public.evidence_items
                        WHERE briefing_id = :b_id AND user_id = :u_id;
                        """),
                        {"b_id": str(existing["id"]), "u_id": user_id}
                    )
                    res_dict["evidence_items"] = [dict(r) for r in ev_res.mappings().all()]
                    return res_dict

            # 3. Gather participants
            part_res = await session.execute(
                text("""
                SELECT id, name, role, is_organizer, contact_id
                FROM public.meeting_participants
                WHERE meeting_id = :meeting_id AND user_id = :user_id;
                """),
                {"meeting_id": str(meeting_id), "user_id": user_id}
            )
            participants = [dict(r) for r in part_res.mappings().all()]

            # 4. Gather associated documents and extracted text
            doc_res = await session.execute(
                text("""
                SELECT id, filename, file_type, inline_extracted_text, processing_status
                FROM public.documents
                WHERE (meeting_id = :meeting_id OR (project_id = :project_id AND :project_id IS NOT NULL))
                  AND user_id = :user_id;
                """),
                {"meeting_id": str(meeting_id), "project_id": str(meeting_row["project_id"]) if meeting_row["project_id"] else None, "user_id": user_id}
            )
            sources = []
            for doc in doc_res.mappings().all():
                if doc["inline_extracted_text"]:
                    sources.append({
                        "id": str(doc["id"]),
                        "type": f"document_{doc['file_type']}",
                        "name": doc["filename"],
                        "text": doc["inline_extracted_text"]
                    })

            # 5. Generate structured epistemic briefing using LLM adapter
            llm_output = self.llm_adapter.generate_briefing(
                meeting_title=meeting_row["title"],
                purpose=meeting_row["purpose"],
                participants=participants,
                sources=sources
            )

            # 6. Determine next briefing version sequence
            ver_res = await session.execute(
                text("SELECT COALESCE(MAX(version), 0) + 1 AS next_ver FROM public.briefings WHERE meeting_id = :meeting_id;"),
                {"meeting_id": str(meeting_id)}
            )
            next_version = ver_res.scalar() or 1

            # 7. Atomic Briefing Promotion:
            # Demote any current latest briefing
            await session.execute(
                text("UPDATE public.briefings SET is_latest = FALSE WHERE meeting_id = :meeting_id AND is_latest = TRUE;"),
                {"meeting_id": str(meeting_id)}
            )

            # Insert new briefing as latest
            insert_briefing_res = await session.execute(
                text("""
                INSERT INTO public.briefings (
                    user_id, meeting_id, meeting_version, version, is_latest, status,
                    summary, talking_points, identified_risks, strategic_questions,
                    assumptions_and_gaps, conflicts_detected, model_provider, model_name
                )
                VALUES (
                    :user_id, :meeting_id, :meeting_version, :version, TRUE, 'ready',
                    :summary, CAST(:talking_points AS JSONB), CAST('[]' AS JSONB), CAST(:strategic_questions AS JSONB),
                    CAST(:assumptions_and_gaps AS JSONB), CAST(:conflicts_detected AS JSONB), :model_provider, :model_name
                )
                RETURNING id, created_at;
                """),
                {
                    "user_id": user_id,
                    "meeting_id": str(meeting_id),
                    "meeting_version": current_meeting_version or 1,
                    "version": next_version,
                    "summary": llm_output.executive_summary,
                    "talking_points": json.dumps(llm_output.talking_points),
                    "strategic_questions": json.dumps(llm_output.strategic_priorities),
                    "assumptions_and_gaps": json.dumps(llm_output.attendee_profiles),
                    "conflicts_detected": json.dumps([c.model_dump() for c in llm_output.conflicts_detected]),
                    "model_provider": "groq",
                    "model_name": "openai/gpt-oss-120b"
                }
            )
            new_briefing = insert_briefing_res.mappings().first()
            new_briefing_id = str(new_briefing["id"])

            # Insert associated evidence items
            evidence_responses = []
            for ev in llm_output.evidence_items:
                ep_class = ev.source_type if ev.source_type in ('direct_fact', 'user_confirmed', 'model_inference', 'unverified_assumption') else 'model_inference'
                st = 'document' if ev.source_document_id else 'user_profile'

                ev_res = await session.execute(
                    text("""
                    INSERT INTO public.evidence_items (
                        user_id, briefing_id, source_type, epistemic_class, claim_text, excerpt, source_id
                    )
                    VALUES (
                        :user_id, :briefing_id, :source_type, :epistemic_class, :claim_text, :excerpt, :source_id
                    )
                    RETURNING id;
                    """),
                    {
                        "user_id": user_id,
                        "briefing_id": new_briefing_id,
                        "source_type": st,
                        "epistemic_class": ep_class,
                        "claim_text": ev.claim_text,
                        "excerpt": ev.quote_or_content or ev.claim_text or "Verified context",
                        "source_id": str(ev.source_document_id) if ev.source_document_id else None
                    }
                )
                inserted_ev = ev_res.mappings().first()
                evidence_responses.append({
                    "id": inserted_ev["id"],
                    "user_id": user_id,
                    "briefing_id": new_briefing_id,
                    "source_type": ep_class,
                    "claim_text": ev.claim_text,
                    "quote_or_content": ev.quote_or_content,
                    "source_document_id": ev.source_document_id,
                    "verified": ev.verified,
                    "created_at": None
                })

            # Update meeting status to 'prepared'
            await session.execute(
                text("UPDATE public.meetings SET status = 'prepared', updated_at = NOW() WHERE id = :meeting_id;"),
                {"meeting_id": str(meeting_id)}
            )

            return {
                "id": new_briefing_id,
                "user_id": user_id,
                "meeting_id": meeting_id,
                "version": next_version,
                "is_latest": True,
                "executive_summary": llm_output.executive_summary,
                "attendee_profiles": llm_output.attendee_profiles,
                "strategic_priorities": llm_output.strategic_priorities,
                "talking_points": llm_output.talking_points,
                "conflicts_detected": [c.model_dump() for c in llm_output.conflicts_detected],
                "created_at": new_briefing["created_at"],
                "evidence_items": evidence_responses
            }
