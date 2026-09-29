from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Optional, Literal, Any
from datetime import datetime
from uuid import UUID

class DocumentBase(BaseModel):
    meeting_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    filename: str
    file_type: Literal['pdf', 'docx', 'txt', 'md']
    file_size_bytes: int = Field(..., le=26214400) # 25 MB max

class DocumentResponse(DocumentBase):
    id: UUID
    user_id: UUID
    storage_path: str
    sha256_checksum: str
    checksum_sha256: Optional[str] = None
    source_version: int
    processing_status: Literal['pending', 'extracted', 'failed']
    inline_extracted_text: Optional[str] = None
    extracted_text_storage_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def populate_checksum(self):
        if not self.checksum_sha256 and self.sha256_checksum:
            self.checksum_sha256 = self.sha256_checksum
        return self

    model_config = ConfigDict(from_attributes=True)

class DocumentExtractionResult(BaseModel):
    text: str
    is_inline: bool
    char_count: int
    truncated: bool = False
