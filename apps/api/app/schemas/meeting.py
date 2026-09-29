from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Optional, List, Literal
from datetime import datetime
from uuid import UUID

class ParticipantCreate(BaseModel):
    contact_id: Optional[UUID] = None
    name: str = Field(..., min_length=1)
    email: Optional[str] = None
    role: Optional[str] = None
    is_organizer: bool = False

    model_config = ConfigDict(extra="ignore")

class ParticipantResponse(BaseModel):
    id: UUID
    user_id: UUID
    meeting_id: UUID
    contact_id: Optional[UUID] = None
    name: str
    email: Optional[str] = None
    role: Optional[str] = None
    is_organizer: bool

    model_config = ConfigDict(from_attributes=True, extra="ignore")

class MeetingBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    project_id: Optional[UUID] = None
    purpose: Optional[str] = None
    meeting_timezone: str = "UTC"
    start_time: datetime
    end_time: datetime
    user_importance_override: Optional[Literal['low', 'medium', 'high', 'critical']] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_time_window(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be strictly after start_time")
        return self

class MeetingCreate(MeetingBase):
    participants: Optional[List[ParticipantCreate]] = None

class MeetingUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    project_id: Optional[UUID] = None
    purpose: Optional[str] = None
    meeting_timezone: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: Optional[Literal['scheduled', 'preparing', 'prepared', 'completed', 'cancelled']] = None
    user_importance_override: Optional[Literal['low', 'medium', 'high', 'critical']] = None
    notes: Optional[str] = None

class MeetingResponse(MeetingBase):
    id: UUID
    user_id: UUID
    status: Literal['scheduled', 'preparing', 'prepared', 'completed', 'cancelled']
    effective_importance: Literal['low', 'medium', 'high', 'critical']
    meeting_version: int
    active_prep_job_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class MeetingDetailResponse(MeetingResponse):
    participants: List[ParticipantResponse] = []
