"""
Transcript Ingestion Service
==============================
Unified ingestion pipeline for all transcript sources:
  1. OpenClaw live captions / final transcript
  2. Platform API transcripts (Google Meet, Zoom, Teams)
  3. Manually uploaded transcript files
  4. Integration push (webhook delivery)

Guarantees:
- Idempotent: duplicate content_hash per (user, meeting) is rejected
- Retryable: processing failures don't create duplicate records
- Epistemic: all transcript content is classified as 'direct_fact'
- Partial: partial transcripts are explicitly marked
- No fabrication: missing speakers, timestamps are stored as NULL, not guessed

Integration with existing document service:
- Transcripts backed by the documents table for storage provenance
- transcript_sources references document_id from existing documents table
"""
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from apps.api.app.core.db import get_tenant_session
from apps.api.app.providers.openclaw_adapter import TranscriptDelivery

logger = logging.getLogger(__name__)


@dataclass
class TranscriptIngestRequest:
    """
    Normalized ingestion request from any source.
    All text content must be treated as untrusted input.
    """
    user_id: str
    meeting_id: str
    meeting_version: int
    source_type: str   # 'openclaw_live', 'platform_api', 'manual_upload', 'integration_push'
    source_platform: Optional[str]  # 'google_meet', 'zoom', 'teams', 'openclaw'
    normalized_text: str
    completeness: str  # 'partial', 'complete', 'unknown'
    participants: List[Dict[str, Any]] = field(default_factory=list)
    segments: List[Dict[str, Any]] = field(default_factory=list)
    source_url: Optional[str] = None
    attendance_session_id: Optional[str] = None
    document_id: Optional[str] = None
    consent_verified: bool = False
    retention_policy: str = "standard"
    meeting_started_at: Optional[datetime] = None
    meeting_ended_at: Optional[datetime] = None
    transcript_start_at: Optional[datetime] = None
    transcript_end_at: Optional[datetime] = None


@dataclass
class IngestResult:
    success: bool
    transcript_source_id: Optional[str] = None
    duplicate: bool = False
    segments_ingested: int = 0
    error: Optional[str] = None


class TranscriptIngestionService:
    """
    Handles ingestion, deduplication, and segmentation of meeting transcripts.
    All content stored under tenant RLS context.
    Existing document service is used for raw storage when applicable.
    """

    async def ingest(self, req: TranscriptIngestRequest) -> IngestResult:
        """
        Primary ingest entry point. Idempotent.
        Returns IngestResult with transcript_source_id on success.
        """
        if not req.normalized_text or not req.normalized_text.strip():
            return IngestResult(success=False, error="Empty transcript content rejected")

        content_hash = hashlib.sha256(req.normalized_text.encode("utf-8")).hexdigest()

        async with get_tenant_session(req.user_id) as session:
            # 1. Deduplication check
            existing = await session.execute(
                text("""
                    SELECT id FROM public.transcript_sources
                    WHERE user_id = :u_id AND meeting_id = :m_id AND content_hash = :hash;
                """),
                {"u_id": req.user_id, "m_id": req.meeting_id, "hash": content_hash}
            )
            existing_row = existing.mappings().first()
            if existing_row:
                logger.info(f"[TranscriptIngestion] Duplicate detected for meeting {req.meeting_id}, hash={content_hash[:12]}")
                return IngestResult(
                    success=True,
                    transcript_source_id=str(existing_row["id"]),
                    duplicate=True
                )

            # 2. Insert transcript_source record
            import json
            try:
                ins = await session.execute(
                    text("""
                        INSERT INTO public.transcript_sources (
                            user_id, meeting_id, meeting_version, attendance_session_id,
                            source_type, source_platform, normalized_text, completeness,
                            processing_status, source_url, content_hash, consent_verified,
                            retention_policy, participants, meeting_started_at, meeting_ended_at,
                            transcript_start_at, transcript_end_at, document_id
                        ) VALUES (
                            :u_id, :m_id, :m_ver, :sess_id,
                            :source_type, :platform, :text, :completeness,
                            'pending', :src_url, :hash, :consent,
                            :retention, CAST(:participants AS JSONB),
                            :meet_start, :meet_end, :tr_start, :tr_end, :doc_id
                        )
                        RETURNING id;
                    """),
                    {
                        "u_id": req.user_id,
                        "m_id": req.meeting_id,
                        "m_ver": req.meeting_version,
                        "sess_id": req.attendance_session_id,
                        "source_type": req.source_type,
                        "platform": req.source_platform,
                        "text": req.normalized_text,
                        "completeness": req.completeness,
                        "src_url": req.source_url,
                        "hash": content_hash,
                        "consent": req.consent_verified,
                        "retention": req.retention_policy,
                        "participants": json.dumps(req.participants),
                        "meet_start": req.meeting_started_at,
                        "meet_end": req.meeting_ended_at,
                        "tr_start": req.transcript_start_at,
                        "tr_end": req.transcript_end_at,
                        "doc_id": req.document_id,
                    }
                )
                source_id = str(ins.scalar())
            except IntegrityError:
                # Race condition — another worker won the dedup race
                return IngestResult(success=True, duplicate=True)

            # 3. Insert segments
            segments_inserted = 0
            if req.segments:
                for seq, seg in enumerate(req.segments):
                    await session.execute(
                        text("""
                            INSERT INTO public.transcript_segments (
                                user_id, transcript_source_id, sequence_number,
                                speaker_name, speaker_id, text,
                                start_offset_ms, end_offset_ms, epistemic_class
                            ) VALUES (
                                :u_id, :src_id, :seq,
                                :speaker, :speaker_id, :text,
                                :start_ms, :end_ms, 'direct_fact'
                            );
                        """),
                        {
                            "u_id": req.user_id,
                            "src_id": source_id,
                            "seq": seq,
                            "speaker": seg.get("speaker_name"),
                            "speaker_id": seg.get("speaker_id"),
                            "text": seg.get("text", ""),
                            "start_ms": seg.get("start_offset_ms"),
                            "end_ms": seg.get("end_offset_ms"),
                        }
                    )
                    segments_inserted += 1
            else:
                # Auto-segment by speaker turn from normalized text
                segments_inserted = await self._auto_segment(session, req.user_id, source_id, req.normalized_text)

            # 4. Mark processing as completed and update meeting.has_transcript
            await session.execute(
                text("""
                    UPDATE public.transcript_sources
                    SET processing_status = 'completed', updated_at = NOW()
                    WHERE id = :src_id AND user_id = :u_id;
                """),
                {"src_id": source_id, "u_id": req.user_id}
            )
            await session.execute(
                text("""
                    UPDATE public.meetings
                    SET has_transcript = true, transcript_source_id = :src_id, updated_at = NOW()
                    WHERE id = :m_id AND user_id = :u_id;
                """),
                {"src_id": source_id, "m_id": req.meeting_id, "u_id": req.user_id}
            )

            logger.info(f"[TranscriptIngestion] Ingested transcript {source_id} for meeting {req.meeting_id} ({segments_inserted} segments)")
            return IngestResult(
                success=True,
                transcript_source_id=source_id,
                segments_ingested=segments_inserted
            )

    async def _auto_segment(self, session: Any, user_id: str, source_id: str, raw_text: str) -> int:
        """
        Auto-parse speaker turns from 'Speaker: text' format.
        Returns number of segments inserted.
        """
        lines = raw_text.split("\n")
        count = 0
        for seq, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            if ": " in line:
                speaker, content = line.split(": ", 1)
                speaker = speaker.strip()
                content = content.strip()
            else:
                speaker = None
                content = line
            if content:
                await session.execute(
                    text("""
                        INSERT INTO public.transcript_segments (
                            user_id, transcript_source_id, sequence_number,
                            speaker_name, text, epistemic_class
                        ) VALUES (:u_id, :src_id, :seq, :speaker, :text, 'direct_fact');
                    """),
                    {"u_id": user_id, "src_id": source_id, "seq": seq, "speaker": speaker, "text": content}
                )
                count += 1
        return count

    @classmethod
    def from_openclaw_delivery(
        cls,
        delivery: TranscriptDelivery,
        user_id: str,
        meeting_id: str,
        meeting_version: int,
        attendance_session_id: Optional[str] = None,
        consent_verified: bool = False,
    ) -> "TranscriptIngestRequest":
        """Factory: build IngestRequest from OpenClaw TranscriptDelivery."""
        return TranscriptIngestRequest(
            user_id=user_id,
            meeting_id=meeting_id,
            meeting_version=meeting_version,
            source_type="openclaw_live" if delivery.source_type == "live_captions" else "openclaw_live",
            source_platform=delivery.platform.value if delivery.platform else "openclaw",
            normalized_text=delivery.content,
            completeness=delivery.completeness,
            participants=delivery.participants,
            attendance_session_id=attendance_session_id,
            consent_verified=consent_verified,
        )
