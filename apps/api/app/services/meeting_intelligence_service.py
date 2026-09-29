"""
Meeting Intelligence Service
==============================
Extracts actionable intelligence from meeting transcripts using the existing
Groq adapter and established epistemic classification system.

Extracts:
- Summary
- Decisions
- Commitments / Action items (with responsible person + due date)
- Blockers / Risks
- Unresolved questions
- Follow-up requirements
- Project status changes
- Contact context updates

All extracted items:
- Reference their source transcript segment
- Are classified under the existing epistemic system
- Proposed (not confirmed) unless explicit authorization exists
- Never auto-sent to participants

Integrates with the Gate 4 commitment lifecycle via OutcomeService.
Budget checked before any LLM call.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import text

from apps.api.app.core.db import get_tenant_session
from apps.api.app.providers.groq_adapter import GroqAdapter
from apps.api.app.services.cost_service import BudgetExceededException, CostService
from apps.api.app.services.queue_service import QueueService

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = """You are an expert meeting analyst. Your role is to extract structured intelligence from meeting transcripts.

STRICT RULES:
1. Only extract information that is EXPLICITLY present in the transcript. Never infer or fabricate.
2. If a speaker is unknown, mark responsible_person as null.
3. If a due date is not stated, mark due_date as null.
4. Every commitment must reference the speaker who made it.
5. Mark all proposed commitments as "proposed" status — NEVER "confirmed".
6. Classify your confidence: direct_fact (clearly stated), model_inference (implied but not stated), unverified_assumption (uncertain).
7. Never suggest sending emails or messages automatically.

Return a valid JSON object with this exact schema:
{
  "summary": "2-4 sentence executive summary",
  "decisions": [{"description": "...", "made_by": "...", "epistemic_class": "direct_fact|model_inference"}],
  "commitments": [{"description": "...", "responsible_person": "...", "due_date": "YYYY-MM-DD or null", "epistemic_class": "direct_fact|model_inference"}],
  "blockers": [{"description": "...", "raised_by": "...", "epistemic_class": "direct_fact|model_inference"}],
  "risks": [{"description": "...", "epistemic_class": "model_inference"}],
  "unresolved_questions": [{"question": "...", "epistemic_class": "direct_fact|model_inference"}],
  "follow_ups": [{"action": "...", "for_whom": "...", "epistemic_class": "model_inference"}],
  "project_status_changes": [],
  "contact_context_updates": []
}"""


class MeetingIntelligenceService:
    """
    Extracts structured intelligence from meeting transcripts.
    All output is epistemically classified and proposed, not confirmed.
    Budget is checked before any LLM call.
    """

    def __init__(self, llm_adapter: Optional[GroqAdapter] = None):
        self.llm = llm_adapter or GroqAdapter()

    async def analyze_transcript(
        self,
        user_id: str,
        meeting_id: str,
        transcript_source_id: str,
        job_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyze a transcript and extract meeting intelligence.
        Returns structured dict with all extracted items.
        Budget is reserved and settled.
        """
        # 1. Load transcript
        async with get_tenant_session(user_id) as session:
            ts_res = await session.execute(
                text("""
                    SELECT ts.normalized_text, ts.participants, ts.completeness,
                           ts.source_type, ts.source_platform,
                           m.title, m.start_time
                    FROM public.transcript_sources ts
                    JOIN public.meetings m ON m.id = ts.meeting_id AND m.user_id = ts.user_id
                    WHERE ts.id = :ts_id AND ts.user_id = :u_id;
                """),
                {"ts_id": transcript_source_id, "u_id": user_id}
            )
            ts_row = ts_res.mappings().first()
            if not ts_row:
                return {"error": f"Transcript source {transcript_source_id} not found"}

        transcript_text = ts_row["normalized_text"]
        meeting_title = ts_row["title"]
        completeness = ts_row["completeness"]

        # 2. Check budget
        ledger_id = None
        try:
            ledger_id = await CostService.reserve_budget(
                user_id=user_id,
                operation_type="transcript_analysis",
                job_id=job_id
            )
        except BudgetExceededException:
            return {"error": "Monthly LLM budget exhausted — transcript analysis skipped"}

        # 3. Call Groq with prompt injection containment
        user_message = f"""Meeting: {meeting_title}

<untrusted_source_content>
TRANSCRIPT ({completeness} transcript):
{transcript_text[:8000]}
</untrusted_source_content>

Extract structured intelligence from the above transcript. Follow all rules precisely."""

        try:
            result_text = await self.llm.complete(
                system_prompt=EXTRACTION_SYSTEM_PROMPT,
                user_message=user_message,
                max_tokens=2000,
                temperature=0.1,
            )
        except Exception as exc:
            if ledger_id:
                await CostService.release_reservation(user_id, ledger_id)
            logger.error(f"[MeetingIntelligence] LLM call failed for meeting {meeting_id}: {exc}")
            return {"error": f"LLM extraction failed: {type(exc).__name__}"}

        # 4. Parse extracted JSON
        try:
            # Strip markdown code blocks if present
            clean = result_text.strip()
            if clean.startswith("```"):
                clean = "\n".join(clean.split("\n")[1:])
            if clean.endswith("```"):
                clean = "\n".join(clean.split("\n")[:-1])
            intelligence = json.loads(clean)
        except json.JSONDecodeError:
            if ledger_id:
                await CostService.release_reservation(user_id, ledger_id)
            return {"error": "Failed to parse intelligence JSON from LLM response", "raw": result_text[:500]}

        # 5. Settle budget
        if ledger_id:
            await CostService.settle_reservation(
                user_id=user_id,
                ledger_id=ledger_id,
                prompt_tokens=3000,
                completion_tokens=600
            )

        # 6. Persist extracted intelligence as evidence items + proposed commitments
        await self._persist_intelligence(
            user_id=user_id,
            meeting_id=meeting_id,
            transcript_source_id=transcript_source_id,
            intelligence=intelligence,
        )

        # 7. Add completeness warning if partial transcript
        if completeness == "partial":
            intelligence["_warning"] = "Analysis based on partial transcript. Some items may be incomplete."

        return {
            "transcript_source_id": transcript_source_id,
            "meeting_id": meeting_id,
            "intelligence": intelligence,
            "items_extracted": {
                "decisions": len(intelligence.get("decisions", [])),
                "commitments": len(intelligence.get("commitments", [])),
                "blockers": len(intelligence.get("blockers", [])),
                "unresolved_questions": len(intelligence.get("unresolved_questions", [])),
            }
        }

    async def _persist_intelligence(
        self,
        user_id: str,
        meeting_id: str,
        transcript_source_id: str,
        intelligence: Dict[str, Any],
    ) -> None:
        """Persist extracted intelligence items to evidence_items and commitments tables."""
        async with get_tenant_session(user_id) as session:
            # Persist decisions and commitments as evidence items
            all_items = []
            for decision in intelligence.get("decisions", []):
                all_items.append({
                    "category": "decision",
                    "content": decision.get("description", ""),
                    "epistemic_class": decision.get("epistemic_class", "model_inference"),
                    "source": f"transcript:{transcript_source_id}",
                })

            for commitment in intelligence.get("commitments", []):
                # Store as proposed commitment
                try:
                    await session.execute(
                        text("""
                            INSERT INTO public.commitments (
                                user_id, meeting_id, description, responsible_person,
                                due_date, status, source_type, source_id, epistemic_class,
                                commitment_type, requires_confirmation
                            ) VALUES (
                                :u_id, :m_id, :desc, :person,
                                CAST(:due AS DATE), 'proposed', 'transcript', :src_id,
                                :epi, 'action_item', true
                            )
                            ON CONFLICT DO NOTHING;
                        """),
                        {
                            "u_id": user_id,
                            "m_id": meeting_id,
                            "desc": commitment.get("description", ""),
                            "person": commitment.get("responsible_person"),
                            "due": commitment.get("due_date"),
                            "src_id": transcript_source_id,
                            "epi": commitment.get("epistemic_class", "model_inference"),
                        }
                    )
                except Exception as exc:
                    logger.debug(f"[MeetingIntelligence] Commitment insert skipped: {exc}")

            # Persist blockers and questions as evidence items
            for blocker in intelligence.get("blockers", []):
                all_items.append({
                    "category": "blocker",
                    "content": blocker.get("description", ""),
                    "epistemic_class": blocker.get("epistemic_class", "model_inference"),
                    "source": f"transcript:{transcript_source_id}",
                })

            for question in intelligence.get("unresolved_questions", []):
                all_items.append({
                    "category": "unresolved_question",
                    "content": question.get("question", ""),
                    "epistemic_class": question.get("epistemic_class", "model_inference"),
                    "source": f"transcript:{transcript_source_id}",
                })

            for item in all_items:
                if item["content"]:
                    try:
                        await session.execute(
                            text("""
                                INSERT INTO public.evidence_items (
                                    user_id, meeting_id, category, content,
                                    epistemic_class, source_ref, verified
                                ) VALUES (
                                    :u_id, :m_id, :cat, :content,
                                    :epi, :src, false
                                );
                            """),
                            {
                                "u_id": user_id,
                                "m_id": meeting_id,
                                "cat": item["category"],
                                "content": item["content"][:2000],
                                "epi": item["epistemic_class"],
                                "src": item["source"],
                            }
                        )
                    except Exception as exc:
                        logger.debug(f"[MeetingIntelligence] Evidence insert skipped: {exc}")

            # Update briefing summary if one exists
            summary = intelligence.get("summary", "")
            if summary:
                await session.execute(
                    text("""
                        UPDATE public.briefings
                        SET post_meeting_summary = :summary, updated_at = NOW()
                        WHERE meeting_id = :m_id AND user_id = :u_id;
                    """),
                    {"summary": summary[:5000], "m_id": meeting_id, "u_id": user_id}
                )
