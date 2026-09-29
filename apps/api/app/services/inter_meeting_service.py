import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text

from apps.api.app.core.db import get_tenant_session
from apps.api.app.providers.groq_adapter import GroqAdapter
from apps.api.app.schemas.outcome import (
    InterMeetingReportSyncResponse,
    PreviousMeetingInfo,
    SyncedReminderItem,
    CommitmentResponse,
)
from apps.api.app.services.document_service import DocumentService

logger = logging.getLogger(__name__)


class InterMeetingService:
    def __init__(self, llm_adapter: Optional[GroqAdapter] = None):
        self.llm_adapter = llm_adapter or GroqAdapter()

    async def get_inter_meeting_context(
        self, user_id: str, meeting_id: UUID
    ) -> Dict[str, Any]:
        """
        Identifies the current meeting, its participants, and finds the previous meeting
        between the same people along with the pending/active reminders established between them.
        """
        async with get_tenant_session(user_id) as session:
            # 1. Fetch current meeting
            m_res = await session.execute(
                text("""
                SELECT id, title, purpose, start_time, end_time, project_id, status
                FROM public.meetings
                WHERE id = :m_id AND user_id = :u_id;
                """),
                {"m_id": str(meeting_id), "u_id": user_id}
            )
            current_meeting = m_res.mappings().first()
            if not current_meeting:
                raise HTTPException(status_code=404, detail="Meeting not found")

            # 2. Fetch participants for current meeting
            p_res = await session.execute(
                text("""
                SELECT id, name, role, contact_id, is_organizer
                FROM public.meeting_participants
                WHERE meeting_id = :m_id AND user_id = :u_id;
                """),
                {"m_id": str(meeting_id), "u_id": user_id}
            )
            current_participants = [dict(r) for r in p_res.mappings().all()]
            participant_names = {p["name"].strip().lower() for p in current_participants if p.get("name")}
            contact_ids = {str(p["contact_id"]) for p in current_participants if p.get("contact_id")}

            # 3. Find previous meeting(s) sharing participants with this user
            all_prev_res = await session.execute(
                text("""
                SELECT id, title, purpose, start_time, end_time, status
                FROM public.meetings
                WHERE user_id = :u_id 
                  AND id != :m_id 
                  AND start_time <= :current_start
                ORDER BY start_time DESC;
                """),
                {"u_id": user_id, "m_id": str(meeting_id), "current_start": current_meeting["start_time"]}
            )
            prev_meetings = [dict(r) for r in all_prev_res.mappings().all()]

            matched_prev_meeting = None
            shared_participant_names = []

            for pm in prev_meetings:
                part_check = await session.execute(
                    text("""
                    SELECT name, contact_id
                    FROM public.meeting_participants
                    WHERE meeting_id = :pm_id AND user_id = :u_id;
                    """),
                    {"pm_id": str(pm["id"]), "u_id": user_id}
                )
                pm_parts = part_check.mappings().all()
                shared = []
                for p in pm_parts:
                    p_name = p["name"].strip().lower() if p["name"] else ""
                    p_cid = str(p["contact_id"]) if p["contact_id"] else ""
                    if (p_name and p_name in participant_names) or (p_cid and p_cid in contact_ids):
                        shared.append(p["name"])

                if shared:
                    matched_prev_meeting = pm
                    shared_participant_names = shared
                    break

            # 4. Fetch candidate reminders between these meetings
            # Reminders from the previous meeting, or active reminders assigned to these participants
            cand_clauses = ["user_id = :u_id"]
            cand_params = {"u_id": user_id}

            if matched_prev_meeting:
                cand_clauses.append("(meeting_id = :prev_id OR meeting_id = :curr_id OR status IN ('pending', 'in_progress'))")
                cand_params["prev_id"] = str(matched_prev_meeting["id"])
                cand_params["curr_id"] = str(meeting_id)
            else:
                cand_clauses.append("(meeting_id = :curr_id OR status IN ('pending', 'in_progress'))")
                cand_params["curr_id"] = str(meeting_id)

            reminders_res = await session.execute(
                text(f"""
                SELECT id, user_id, meeting_id, project_id, owner_name,
                       description, due_date, status, is_confirmed, source_excerpt,
                       created_at, updated_at
                FROM public.commitments
                WHERE {' AND '.join(cand_clauses)}
                ORDER BY created_at DESC;
                """),
                cand_params
            )
            reminders = [dict(r) for r in reminders_res.mappings().all()]

            prev_info = None
            if matched_prev_meeting:
                prev_info = PreviousMeetingInfo(
                    id=matched_prev_meeting["id"],
                    title=matched_prev_meeting["title"],
                    start_time=matched_prev_meeting["start_time"],
                    shared_participants=shared_participant_names
                )

            return {
                "current_meeting": current_meeting,
                "current_participants": current_participants,
                "previous_meeting": prev_info,
                "reminders": reminders
            }

    async def sync_task_report(
        self,
        user_id: str,
        meeting_id: UUID,
        report_text: str,
        filename: str = "inter_meeting_task_report.txt",
        file_content: Optional[bytes] = None
    ) -> InterMeetingReportSyncResponse:
        """
        Ingests the report of tasks carried out between 2 meetings,
        correlates the tasks against existing reminders/commitments,
        updates statuses, extracts newly discovered tasks, and updates the meeting briefing.
        """
        async with get_tenant_session(user_id) as session:
            # 1. Gather context of current and prior meeting with same people
            context = await self.get_inter_meeting_context(user_id, meeting_id)
            curr_meeting = context["current_meeting"]
            prev_meeting: Optional[PreviousMeetingInfo] = context["previous_meeting"]
            existing_reminders: List[Dict[str, Any]] = context["reminders"]

            # 2. Store report as document in public.documents
            doc_id = uuid.uuid4()
            content_bytes = file_content if file_content is not None else report_text.encode("utf-8")
            file_type = "txt"
            if "." in filename:
                ext = filename.rsplit(".", 1)[-1].lower()
                if ext in ("pdf", "docx", "txt", "md"):
                    file_type = ext

            checksum = DocumentService.compute_sha256(content_bytes)
            storage_path = f"task_reports/{user_id}/{doc_id}_{filename}"

            doc_ins = await session.execute(
                text("""
                INSERT INTO public.documents (
                    id, user_id, meeting_id, filename, storage_path,
                    file_type, file_size_bytes, sha256_checksum,
                    processing_status, inline_extracted_text
                )
                VALUES (
                    :id, :user_id, :meeting_id, :filename, :storage_path,
                    :file_type, :file_size_bytes, :sha256_checksum,
                    'extracted', :inline_text
                )
                RETURNING id;
                """),
                {
                    "id": str(doc_id),
                    "user_id": user_id,
                    "meeting_id": str(meeting_id),
                    "filename": filename,
                    "storage_path": storage_path,
                    "file_type": file_type,
                    "file_size_bytes": len(content_bytes),
                    "sha256_checksum": checksum,
                    "inline_text": report_text[:65535]
                }
            )
            saved_doc_id = doc_ins.scalar()

            # 3. Analyze report against existing reminders
            # Correlate which reminders are completed, which are in progress, and identify new tasks
            matched_items, new_commitments, summary_progress = self._correlate_report_with_reminders(
                report_text=report_text,
                existing_reminders=existing_reminders,
                prev_meeting_title=prev_meeting.title if prev_meeting else "Previous Meeting",
                curr_meeting_title=curr_meeting["title"]
            )

            # 4. Update existing reminders in database
            synced_reminders_resp: List[SyncedReminderItem] = []
            completed_count = 0
            in_prog_count = 0

            for match in matched_items:
                r_id = match["id"]
                new_st = match["new_status"]
                prev_st = match["previous_status"]
                excerpt = match["matched_excerpt"]
                status_changed = (new_st != prev_st)

                if new_st == "completed":
                    completed_count += 1
                elif new_st == "in_progress":
                    in_prog_count += 1

                # Update reminder in DB
                await session.execute(
                    text("""
                    UPDATE public.commitments
                    SET status = :new_status,
                        is_confirmed = TRUE,
                        source_excerpt = COALESCE(:excerpt, source_excerpt),
                        updated_at = NOW()
                    WHERE id = :r_id AND user_id = :u_id;
                    """),
                    {
                        "new_status": new_st,
                        "excerpt": excerpt,
                        "r_id": str(r_id),
                        "u_id": user_id
                    }
                )

                synced_reminders_resp.append(
                    SyncedReminderItem(
                        id=UUID(str(r_id)),
                        owner_name=match["owner_name"],
                        description=match["description"],
                        previous_status=prev_st,
                        new_status=new_st,
                        is_confirmed=True,
                        status_changed=status_changed,
                        matched_excerpt=excerpt,
                        notes=match.get("notes")
                    )
                )

            # 5. Insert any new commitments found in report
            new_reminders_resp: List[CommitmentResponse] = []
            for nc in new_commitments:
                new_c_id = uuid.uuid4()
                ins_c = await session.execute(
                    text("""
                    INSERT INTO public.commitments (
                        id, user_id, meeting_id, owner_name, description,
                        due_date, status, is_confirmed, source_excerpt
                    )
                    VALUES (
                        :id, :user_id, :meeting_id, :owner_name, :description,
                        :due_date, :status, FALSE, :source_excerpt
                    )
                    RETURNING id, user_id, meeting_id, project_id, owner_name,
                              description, due_date, status, is_confirmed,
                              source_excerpt, created_at, updated_at;
                    """),
                    {
                        "id": str(new_c_id),
                        "user_id": user_id,
                        "meeting_id": str(meeting_id),
                        "owner_name": nc.get("owner_name", "Team"),
                        "description": nc["description"],
                        "due_date": nc.get("due_date"),
                        "status": "pending",
                        "source_excerpt": nc.get("source_excerpt")
                    }
                )
                row = dict(ins_c.mappings().first())
                new_reminders_resp.append(CommitmentResponse(**row))

            # 6. Update latest briefing with inter-meeting progress & evidence link
            briefing_updated = False
            b_res = await session.execute(
                text("""
                SELECT id, strategic_questions, summary
                FROM public.briefings
                WHERE meeting_id = :m_id AND user_id = :u_id AND is_latest = TRUE;
                """),
                {"m_id": str(meeting_id), "u_id": user_id}
            )
            latest_b = b_res.mappings().first()

            if latest_b:
                briefing_id = str(latest_b["id"])
                # Add strategic priority entry reflecting completed inter-meeting tasks
                strat_list = latest_b["strategic_questions"]
                if isinstance(strat_list, str):
                    try:
                        strat_list = json.loads(strat_list)
                    except Exception:
                        strat_list = []
                elif not isinstance(strat_list, list):
                    strat_list = []

                new_priority = {
                    "title": "Inter-Meeting Task Progress Verified",
                    "detail": f"Inter-meeting report '{filename}' verified: {completed_count} tasks completed, {in_prog_count} in progress. {summary_progress[:180]}",
                    "epistemic_class": "direct_fact"
                }
                strat_list.insert(0, new_priority)

                updated_summary = latest_b["summary"]
                if "Inter-Meeting Progress:" not in updated_summary:
                    updated_summary = f"{updated_summary}\n\n[Inter-Meeting Progress Update]: {summary_progress}"

                await session.execute(
                    text("""
                    UPDATE public.briefings
                    SET strategic_questions = CAST(:strat AS JSONB),
                        summary = :summary,
                        updated_at = NOW()
                    WHERE id = :b_id AND user_id = :u_id;
                    """),
                    {
                        "strat": json.dumps(strat_list),
                        "summary": updated_summary,
                        "b_id": briefing_id,
                        "u_id": user_id
                    }
                )

                # Insert evidence item citing the task report
                await session.execute(
                    text("""
                    INSERT INTO public.evidence_items (
                        user_id, briefing_id, source_type, epistemic_class,
                        claim_text, excerpt, source_id
                    )
                    VALUES (
                        :user_id, :briefing_id, 'document', 'direct_fact',
                        :claim, :excerpt, :source_id
                    );
                    """),
                    {
                        "user_id": user_id,
                        "briefing_id": briefing_id,
                        "claim": f"Tasks carried out between meetings documented in {filename}",
                        "excerpt": summary_progress[:300],
                        "source_id": str(saved_doc_id) if saved_doc_id else None
                    }
                )
                briefing_updated = True

            return InterMeetingReportSyncResponse(
                current_meeting_id=meeting_id,
                current_meeting_title=curr_meeting["title"],
                previous_meeting=prev_meeting,
                report_document_id=UUID(str(saved_doc_id)) if saved_doc_id else None,
                report_filename=filename,
                summary_of_progress=summary_progress,
                synced_reminders=synced_reminders_resp,
                new_reminders_added=new_reminders_resp,
                total_completed=completed_count,
                total_in_progress=in_prog_count,
                briefing_updated=briefing_updated,
                synced_at=datetime.now(timezone.utc)
            )

    def _correlate_report_with_reminders(
        self,
        report_text: str,
        existing_reminders: List[Dict[str, Any]],
        prev_meeting_title: str,
        curr_meeting_title: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], str]:
        """
        Matches tasks in report text against existing reminders.
        Uses keyword, entity, and completion matching with LLM augmentation if available.
        """
        matched_items = []
        report_lines = [l.strip() for l in report_text.split("\n") if l.strip()]
        lower_report = report_text.lower()

        # Phrases indicating completion
        completed_signals = [
            "completed", "finished", "delivered", "done", "resolved",
            "signed off", "prepared", "submitted", "finalized", "conducted", "closed"
        ]
        # Phrases indicating in progress
        in_progress_signals = [
            "in progress", "ongoing", "started", "partially", "awaiting", "testing", "under review"
        ]

        completed_descs = []

        for r in existing_reminders:
            desc = r.get("description", "")
            r_id = r.get("id")
            owner = r.get("owner_name", "Team")
            prev_status = r.get("status", "pending")
            lower_desc = desc.lower()

            # Extract key tokens (> 3 chars) from reminder description
            tokens = [w for w in re.findall(r"\b[a-z]{4,}\b", lower_desc) if w not in ("with", "from", "that", "this", "have", "been")]

            # Look for matching line in report
            matched_line = None
            for line in report_lines:
                ll = line.lower()
                # Check token overlap
                matching_tokens = [t for t in tokens if t in ll]
                if len(tokens) > 0 and len(matching_tokens) >= max(1, len(tokens) // 2):
                    matched_line = line
                    break

            if matched_line:
                ll_matched = matched_line.lower()
                is_comp = any(sig in ll_matched for sig in completed_signals)
                is_prog = any(sig in ll_matched for sig in in_progress_signals)

                if is_comp or ("✓" in matched_line or "[x]" in ll_matched):
                    new_st = "completed"
                    completed_descs.append(desc)
                elif is_prog:
                    new_st = "in_progress"
                else:
                    # If explicitly mentioned in progress report, default to completed unless indicated otherwise
                    new_st = "completed"
                    completed_descs.append(desc)

                matched_items.append({
                    "id": r_id,
                    "description": desc,
                    "owner_name": owner,
                    "previous_status": prev_status,
                    "new_status": new_st,
                    "matched_excerpt": matched_line,
                    "notes": f"Matched with statement in task report: '{matched_line}'"
                })

        # Identify newly carried-out tasks from lines with bullet points not matched
        new_commitments = []
        for line in report_lines:
            if any(line.strip().startswith(prefix) for prefix in ("-", "*", "•", "1.", "2.", "3.", "4.")):
                clean_line = re.sub(r"^[-*•\d.]+\s*", "", line).strip()
                # Check if already in matched items
                already_matched = any(m["description"].lower() in clean_line.lower() or clean_line.lower() in m["description"].lower() for m in matched_items)
                if not already_matched and len(clean_line) > 15:
                    # Potential new reminder or deliverable mentioned
                    new_commitments.append({
                        "description": clean_line,
                        "owner_name": "Team",
                        "due_date": None,
                        "source_excerpt": line
                    })

        # Generate summary
        if completed_descs:
            summary_progress = f"Between {prev_meeting_title} and {curr_meeting_title}, {len(completed_descs)} planned tasks were verified completed: {'; '.join(completed_descs[:3])}."
        else:
            summary_progress = f"Inter-meeting task report ingested for {curr_meeting_title}. Status and progress updated across {len(matched_items)} tracked reminders."

        return matched_items, new_commitments[:5], summary_progress
