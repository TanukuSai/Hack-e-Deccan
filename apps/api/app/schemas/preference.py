from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field

class PreferenceCreate(BaseModel):
    dimension: str = Field(..., pattern="^(briefing_format|topic_priority|preparation_timing)$")
    scope: str = Field(default="global", pattern="^(global|meeting_type|project|contact)$")
    scope_id: str = Field(default="")
    key: str = Field(..., min_length=1)
    value: Any = Field(...)

class PreferenceResponse(BaseModel):
    id: UUID
    user_id: UUID
    dimension: str
    scope: str
    scope_id: str
    key: str
    value: Any
    source_type: str
    confidence: float
    created_at: datetime
    updated_at: datetime

class PreferenceUndoResponse(BaseModel):
    id: UUID
    confidence: float
    message: str
