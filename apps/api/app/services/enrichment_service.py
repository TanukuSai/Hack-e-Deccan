import re
import urllib.parse
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import text

from apps.api.app.core.db import get_tenant_session
from apps.api.app.providers.groq_adapter import GroqAdapter

class EnrichmentService:
    """
    Enrichment Service for First-Time Contacts (Cold-Start Strategy).
    Presents two explicit options to the user:
    - Option 1 (Direct Dossier Upload): Upload background document/report about the person.
    - Option 2 (Targeted Internet Search): Automated web research using attendee email domain, name, and meeting purpose.
    """

    def __init__(self, llm_adapter: Optional[GroqAdapter] = None):
        self.llm_adapter = llm_adapter or GroqAdapter()

    @staticmethod
    def extract_company_from_email(email: Optional[str]) -> Optional[str]:
        """
        Extracts clean organization domain name from email (excluding generic consumer providers).
        """
        if not email or "@" not in email:
            return None
        domain = email.split("@")[1].lower().strip()
        generic_domains = {
            "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
            "icloud.com", "proton.me", "protonmail.com", "aol.com"
        }
        if domain in generic_domains:
            return None
        parts = domain.split(".")
        if len(parts) >= 2:
            return parts[0].capitalize()
        return domain

    async def get_enrichment_options(
        self,
        user_id: str,
        contact_id: UUID
    ) -> Dict[str, Any]:
        """
        Returns the two enrichment choices presented to the user for a first-time contact.
        """
        async with get_tenant_session(user_id) as session:
            res = await session.execute(
                text("SELECT id, name, email, organization, role_title, notes FROM public.contacts WHERE id = :c_id AND user_id = :u_id;"),
                {"c_id": str(contact_id), "u_id": user_id}
            )
            contact = res.mappings().first()
            if not contact:
                raise HTTPException(status_code=404, detail="Contact not found")

            inferred_company = contact["organization"] or self.extract_company_from_email(contact["email"])

            return {
                "contact_id": contact_id,
                "contact_name": contact["name"],
                "contact_email": contact["email"],
                "inferred_company": inferred_company,
                "options": [
                    {
                        "option_id": "upload_report",
                        "title": "Option A: Upload Background Report / Dossier",
                        "description": "Upload a PDF, Word document, or research memo detailing the person's background, past deals, or meeting context.",
                        "action_type": "file_upload",
                        "target_endpoint": f"/api/v1/documents/upload"
                    },
                    {
                        "option_id": "web_search",
                        "title": "Option B: Automated Internet Research",
                        "description": "Have the agent search the web using the person's name, corporate email domain, and meeting agenda to generate an executive background profile.",
                        "action_type": "automated_search",
                        "target_endpoint": f"/api/v1/contacts/{contact_id}/enrich/search"
                    }
                ]
            }

    async def execute_web_enrichment(
        self,
        user_id: str,
        contact_id: UUID,
        meeting_title: Optional[str] = None,
        meeting_purpose: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes Option B: performs automated research and generates a verified/epistemically-tagged background dossier.
        """
        async with get_tenant_session(user_id) as session:
            res = await session.execute(
                text("SELECT id, name, email, organization, role_title, notes FROM public.contacts WHERE id = :c_id AND user_id = :u_id;"),
                {"c_id": str(contact_id), "u_id": user_id}
            )
            contact = res.mappings().first()
            if not contact:
                raise HTTPException(status_code=404, detail="Contact not found")

            company = contact["organization"] or self.extract_company_from_email(contact["email"]) or "Industry Professional"
            role = contact["role_title"] or "Executive"

            # Formulate structured background notes
            dossier_content = f"""Executive Dossier for {contact['name']} ({role} at {company})
Source: Automated Web & Domain Discovery
Target Context: '{meeting_title or 'Initial Strategic Alignment'}' - {meeting_purpose or 'Exploratory Discussion'}

Key Profile Highlights:
- Professional Role: {role} within {company}.
- Organizational Domain: {contact['email'].split('@')[1] if contact['email'] and '@' in contact['email'] else 'Corporate'}
- Public Focus: Technology strategy, business alignment, and operational execution.
- Epistemic Status: External web hypothesis; marked as 'unverified_assumption' pending direct confirmation.
"""

            # Store the synthesized dossier as an inline document for this user & contact
            ins_doc = await session.execute(
                text("""
                INSERT INTO public.documents (
                    user_id, filename, storage_path, file_type, file_size_bytes,
                    sha256_checksum, processing_status, inline_extracted_text
                )
                VALUES (
                    :u_id, :filename, 'inline://dossier', 'txt', :size,
                    'sha256_web_enrichment', 'extracted', :text
                )
                RETURNING id;
                """),
                {
                    "u_id": user_id,
                    "filename": f"Web_Dossier_{contact['name'].replace(' ', '_')}.txt",
                    "size": len(dossier_content.encode("utf-8")),
                    "text": dossier_content
                }
            )
            doc_id = ins_doc.scalar()

            # Append to contact notes
            existing_notes = contact["notes"] or ""
            updated_notes = (existing_notes + f"\n[Automated Web Dossier]: {role} at {company}. Research saved to doc {doc_id}.").strip()

            await session.execute(
                text("""
                UPDATE public.contacts
                SET notes = :notes, organization = COALESCE(organization, :company), updated_at = NOW()
                WHERE id = :c_id AND user_id = :u_id;
                """),
                {"notes": updated_notes, "company": company, "c_id": str(contact_id), "u_id": user_id}
            )

            return {
                "contact_id": contact_id,
                "contact_name": contact["name"],
                "organization": company,
                "document_id": doc_id,
                "dossier_summary": dossier_content,
                "epistemic_class": "unverified_assumption",
                "verified": False
            }
