from datetime import date, datetime
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field

class OutcomeAnalysisRequest(BaseModel):
    notes: str = Field(..., min_length=10, description="Raw notes taken during or after the meeting")
    transcript: Optional[str] = Field(None, description="Optional raw audio/text transcript")

class ProposedCommitmentItem(BaseModel):
    owner_name: str = Field(..., description="Person responsible for the commitment")
    description: str = Field(..., description="Actionable deliverable or task description")
    due_date: Optional[date] = Field(None, description="Inferred due date (YYYY-MM-DD) if mentioned")
    source_excerpt: Optional[str] = Field(None, description="Quote from notes supporting this commitment")
    is_confirmed: bool = Field(default=False, description="Always False until explicitly confirmed by user")

class ProposedFollowUpDraftItem(BaseModel):
    subject: str = Field(..., description="Suggested professional email subject")
    body: str = Field(..., description="Draft email body summarizing meeting and next steps")
    recipients: List[str] = Field(default_factory=list, description="Suggested attendee emails/names")
    status: str = Field(default="draft", description="Always draft; zero client-send capability")

class EpistemicOutcomeLLMOutput(BaseModel):
    meeting_summary: str = Field(..., description="Executive debrief of what happened in the meeting")
    decisions_made: List[str] = Field(default_factory=list, description="Explicit decisions agreed upon")
    proposed_commitments: List[ProposedCommitmentItem] = Field(default_factory=list, description="Inferred commitments")
    follow_up_draft: ProposedFollowUpDraftItem = Field(..., description="Draft-only follow-up message")

class CommitmentResponse(BaseModel):
    id: UUID
    user_id: UUID
    meeting_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    owner_name: str
    description: str
    due_date: Optional[date] = None
    status: str
    is_confirmed: bool
    source_excerpt: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class CommitmentUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern="^(pending|in_progress|completed|missed|cancelled)$")
    description: Optional[str] = None
    due_date: Optional[date] = None
    owner_name: Optional[str] = None

class FollowUpDraftResponse(BaseModel):
    id: UUID
    user_id: UUID
    meeting_id: UUID
    subject: str
    body: str
    recipients: List[str]
    status: str
    created_at: datetime
    updated_at: datetime

class FollowUpDraftUpdate(BaseModel):
    subject: Optional[str] = None
    body: Optional[str] = None
    recipients: Optional[List[str]] = None
    status: Optional[str] = Field(None, pattern="^(draft|reviewed|discarded)$")

class ProjectProgressSummary(BaseModel):
    project_id: UUID
    total_commitments: int = 0
    confirmed_commitments: int = 0
    proposed_commitments: int = 0
    completed_commitments: int = 0
    in_progress_commitments: int = 0
    pending_commitments: int = 0
    overdue_commitments: int = 0
    missed_commitments: int = 0
    completion_rate_pct: float = 0.0
    completion_pct: float = 0.0
    blockers_detected: List[str] = Field(default_factory=list)
    blockers: List[str] = Field(default_factory=list)

class OutcomeAnalysisResponse(BaseModel):
    meeting_id: UUID
    meeting_summary: str
    decisions_made: List[str]
    commitments: List[CommitmentResponse]
    follow_up_draft: FollowUpDraftResponse
