from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from uuid import UUID

EpistemicSourceType = Literal['direct_fact', 'user_confirmed', 'model_inference', 'unverified_assumption']

class EvidenceItemBase(BaseModel):
    source_type: EpistemicSourceType
    claim_text: str
    quote_or_content: Optional[str] = None
    source_document_id: Optional[UUID] = None
    verified: bool = False

class EvidenceItemResponse(EvidenceItemBase):
    id: UUID
    user_id: UUID
    briefing_id: UUID
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class ConflictItem(BaseModel):
    topic: str
    description: str
    source_a: str
    source_b: str
    severity: Literal['low', 'medium', 'high'] = 'medium'

class EpistemicBriefingLLMOutput(BaseModel):
    """
    Strict Pydantic schema enforced for Groq/LLM output generation.
    Any non-conforming field or instruction is automatically rejected.
    """
    executive_summary: str = Field(..., description="High-level synthesis of meeting purpose and stakes.")
    attendee_profiles: List[Dict[str, Any]] = Field(default_factory=list, description="Synthesized profile per participant.")
    strategic_priorities: List[str] = Field(default_factory=list, description="Key strategic goals for this meeting.")
    talking_points: List[str] = Field(default_factory=list, description="Targeted discussion topics and suggested questions.")
    conflicts_detected: List[ConflictItem] = Field(default_factory=list, description="Contradictions detected between documents/notes.")
    evidence_items: List[EvidenceItemBase] = Field(default_factory=list, description="Epistemic claims supporting the briefing.")

class BriefingResponse(BaseModel):
    id: UUID
    user_id: UUID
    meeting_id: UUID
    version: int
    is_latest: bool
    executive_summary: str
    attendee_profiles: List[Dict[str, Any]] = []
    strategic_priorities: List[str] = []
    talking_points: List[str] = []
    conflicts_detected: List[Dict[str, Any]] = []
    degraded_reason: Optional[str] = None
    created_at: datetime
    evidence_items: List[EvidenceItemResponse] = []

    model_config = ConfigDict(from_attributes=True)

class BriefingGenerationRequest(BaseModel):
    meeting_id: UUID
    force_refresh: bool = False

class BriefingFollowUpRequest(BaseModel):
    question: str = Field(..., description="Follow-up question or instruction for the briefing agent")
    history: List[Dict[str, str]] = Field(default_factory=list, description="Recent conversation turns")

class BriefingFollowUpResponse(BaseModel):
    meeting_id: str
    question: str
    answer: str
    suggested_talking_points: List[str] = Field(default_factory=list)
    action_items: List[str] = Field(default_factory=list)

BriefingFollowUpRequest.model_rebuild()
BriefingFollowUpResponse.model_rebuild()
