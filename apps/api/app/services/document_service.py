import hashlib
import io
import os
from typing import Tuple, Optional
import pypdf
import docx
from fastapi import HTTPException, status
from apps.api.app.schemas.document import DocumentExtractionResult

MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024 # 25 MB
INLINE_TEXT_LIMIT_BYTES = 64 * 1024     # 64 KB

# Magic byte signatures
PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"

class DocumentService:
    @staticmethod
    def validate_file(content: bytes, filename: str) -> str:
        """
        Validates file size and inspects magic bytes.
        Returns the confirmed file_type ('pdf', 'docx', 'txt', 'md').
        Raises HTTPException on violation.
        """
        if len(content) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds maximum allowed size of 25MB (got {len(content)} bytes)"
            )

        ext = filename.lower().split(".")[-1] if "." in filename else ""

        if ext == "pdf":
            if not content.startswith(PDF_MAGIC):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File header does not match PDF format (invalid magic bytes)"
                )
            return "pdf"

        elif ext == "docx":
            if not content.startswith(ZIP_MAGIC):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File header does not match DOCX format (invalid magic bytes)"
                )
            return "docx"

        elif ext in ("txt", "md"):
            # Text files must not contain binary null characters
            if b"\x00" in content[:4096]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File contains binary characters and cannot be processed as plain text"
                )
            return ext

        else:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported file extension '.{ext}'. Supported formats: pdf, docx, txt, md"
            )

    @staticmethod
    def compute_sha256(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def extract_text(content: bytes, file_type: str) -> DocumentExtractionResult:
        """
        Extracts plain text from validated document bytes.
        Determines whether text fits inline (<= 64KB) or requires external storage.
        """
        extracted_text = ""

        try:
            if file_type == "pdf":
                try:
                    reader = pypdf.PdfReader(io.BytesIO(content))
                    pages = []
                    for i, page in enumerate(reader.pages):
                        page_text = page.extract_text() or ""
                        pages.append(f"--- Page {i+1} ---\n{page_text}")
                    extracted_text = "\n\n".join(pages)
                except Exception:
                    extracted_text = ""

            elif file_type == "docx":
                doc = docx.Document(io.BytesIO(content))
                paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
                extracted_text = "\n\n".join(paragraphs)

            elif file_type in ("txt", "md"):
                extracted_text = content.decode("utf-8", errors="replace")

            else:
                raise ValueError(f"Unknown file type: {file_type}")

        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Failed to extract text from document: {str(e)}"
            )

        text_bytes_len = len(extracted_text.encode("utf-8"))
        is_inline = text_bytes_len <= INLINE_TEXT_LIMIT_BYTES

        return DocumentExtractionResult(
            text=extracted_text,
            is_inline=is_inline,
            char_count=len(extracted_text)
        )
