from typing import List, Optional
from uuid import UUID
import uuid
import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy import text
from apps.api.app.core.security import get_current_user_id
from apps.api.app.core.db import get_tenant_session
from apps.api.app.services.document_service import DocumentService
from apps.api.app.schemas.document import DocumentResponse

router = APIRouter(prefix="/documents", tags=["documents"])

@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    meeting_id: Optional[UUID] = Form(None),
    project_id: Optional[UUID] = Form(None),
    user_id: str = Depends(get_current_user_id)
):
    # Read file content
    content = await file.read()

    # 1. Validate magic bytes and format
    file_type = DocumentService.validate_file(content, file.filename or "unknown")

    # 2. Compute SHA-256
    checksum = DocumentService.compute_sha256(content)

    # 3. Extract text
    extraction = DocumentService.extract_text(content, file_type)

    doc_id = uuid.uuid4()
    storage_path = f"documents/{user_id}/{doc_id}_{file.filename}"
    extracted_text_storage_path = None
    inline_text = None

    if extraction.is_inline:
        inline_text = extraction.text
    else:
        # Text exceeds 64KB -> save to external storage path
        extracted_text_storage_path = f"documents/{user_id}/{doc_id}_extracted.txt"
        # In local filesystem mode or Supabase storage, ensure parent directory
        local_extracted_dir = os.path.join("storage", "extracted", user_id)
        os.makedirs(local_extracted_dir, exist_ok=True)
        local_file_path = os.path.join(local_extracted_dir, f"{doc_id}.txt")
        with open(local_file_path, "w", encoding="utf-8") as f:
            f.write(extraction.text)

    # Also persist raw file locally if in local storage mode
    local_raw_dir = os.path.join("storage", "raw", user_id)
    os.makedirs(local_raw_dir, exist_ok=True)
    with open(os.path.join(local_raw_dir, f"{doc_id}_{file.filename}"), "wb") as f:
        f.write(content)

    async with get_tenant_session(user_id) as session:
        # Validate meeting/project composite ownership if specified
        if meeting_id:
            m_check = await session.execute(
                text("SELECT id FROM public.meetings WHERE id = :m_id AND user_id = :u_id;"),
                {"m_id": str(meeting_id), "u_id": user_id}
            )
            if not m_check.scalar():
                raise HTTPException(status_code=400, detail="Meeting does not belong to user")

        if project_id:
            p_check = await session.execute(
                text("SELECT id FROM public.projects WHERE id = :p_id AND user_id = :u_id;"),
                {"p_id": str(project_id), "u_id": user_id}
            )
            if not p_check.scalar():
                raise HTTPException(status_code=400, detail="Project does not belong to user")

        ins_res = await session.execute(
            text("""
            INSERT INTO public.documents (
                id, user_id, meeting_id, project_id, filename, storage_path,
                file_type, file_size_bytes, sha256_checksum, processing_status,
                inline_extracted_text, extracted_text_storage_path
            )
            VALUES (
                :id, :user_id, :meeting_id, :project_id, :filename, :storage_path,
                :file_type, :file_size_bytes, :sha256_checksum, 'extracted',
                :inline_extracted_text, :extracted_text_storage_path
            )
            RETURNING *;
            """),
            {
                "id": str(doc_id),
                "user_id": user_id,
                "meeting_id": str(meeting_id) if meeting_id else None,
                "project_id": str(project_id) if project_id else None,
                "filename": file.filename or "uploaded_document",
                "storage_path": storage_path,
                "file_type": file_type,
                "file_size_bytes": len(content),
                "sha256_checksum": checksum,
                "inline_extracted_text": inline_text,
                "extracted_text_storage_path": extracted_text_storage_path
            }
        )
        return dict(ins_res.mappings().first())

@router.get("", response_model=List[DocumentResponse])
async def list_documents(
    meeting_id: Optional[UUID] = None,
    project_id: Optional[UUID] = None,
    user_id: str = Depends(get_current_user_id)
):
    async with get_tenant_session(user_id) as session:
        query = "SELECT * FROM public.documents WHERE user_id = :user_id"
        params = {"user_id": user_id}
        if meeting_id:
            query += " AND meeting_id = :meeting_id"
            params["meeting_id"] = str(meeting_id)
        if project_id:
            query += " AND project_id = :project_id"
            params["project_id"] = str(project_id)
        query += " ORDER BY created_at DESC;"

        res = await session.execute(text(query), params)
        return [dict(r) for r in res.mappings().all()]

@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: UUID, user_id: str = Depends(get_current_user_id)):
    async with get_tenant_session(user_id) as session:
        res = await session.execute(
            text("SELECT * FROM public.documents WHERE id = :d_id AND user_id = :u_id;"),
            {"d_id": str(document_id), "u_id": user_id}
        )
        doc = res.mappings().first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return dict(doc)

@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: UUID, user_id: str = Depends(get_current_user_id)):
    async with get_tenant_session(user_id) as session:
        del_res = await session.execute(
            text("DELETE FROM public.documents WHERE id = :d_id AND user_id = :u_id RETURNING id;"),
            {"d_id": str(document_id), "u_id": user_id}
        )
        if not del_res.scalar():
            raise HTTPException(status_code=404, detail="Document not found")
