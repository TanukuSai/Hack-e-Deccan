from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from apps.api.app.core.security import get_current_user_id
from apps.api.app.core.db import get_tenant_session
from apps.api.app.schemas.contact import ContactCreate, ContactUpdate, ContactResponse

router = APIRouter(prefix="/contacts", tags=["contacts"])

@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def create_contact(
    payload: ContactCreate,
    user_id: str = Depends(get_current_user_id)
):
    async with get_tenant_session(user_id) as session:
        ins_res = await session.execute(
            text("""
            INSERT INTO public.contacts (user_id, name, email, organization, role_title, notes)
            VALUES (:user_id, :name, :email, :organization, :role_title, :notes)
            RETURNING *;
            """),
            {
                "user_id": user_id,
                "name": payload.name,
                "email": payload.email,
                "organization": payload.organization,
                "role_title": payload.role_title,
                "notes": payload.notes
            }
        )
        return dict(ins_res.mappings().first())

@router.get("", response_model=List[ContactResponse])
async def list_contacts(user_id: str = Depends(get_current_user_id)):
    async with get_tenant_session(user_id) as session:
        res = await session.execute(
            text("SELECT * FROM public.contacts WHERE user_id = :user_id ORDER BY name ASC;"),
            {"user_id": user_id}
        )
        return [dict(r) for r in res.mappings().all()]

@router.get("/{contact_id}", response_model=ContactResponse)
async def get_contact(contact_id: UUID, user_id: str = Depends(get_current_user_id)):
    async with get_tenant_session(user_id) as session:
        res = await session.execute(
            text("SELECT * FROM public.contacts WHERE id = :c_id AND user_id = :u_id;"),
            {"c_id": str(contact_id), "u_id": user_id}
        )
        contact = res.mappings().first()
        if not contact:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
        return dict(contact)

@router.patch("/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: UUID,
    payload: ContactUpdate,
    user_id: str = Depends(get_current_user_id)
):
    async with get_tenant_session(user_id) as session:
        updates = []
        params = {"c_id": str(contact_id), "u_id": user_id}

        if payload.name is not None:
            updates.append("name = :name")
            params["name"] = payload.name
        if payload.email is not None:
            updates.append("email = :email")
            params["email"] = payload.email
        if payload.organization is not None:
            updates.append("organization = :organization")
            params["organization"] = payload.organization
        if payload.role_title is not None:
            updates.append("role_title = :role_title")
            params["role_title"] = payload.role_title
        if payload.notes is not None:
            updates.append("notes = :notes")
            params["notes"] = payload.notes

        if not updates:
            res = await session.execute(
                text("SELECT * FROM public.contacts WHERE id = :c_id AND user_id = :u_id;"),
                params
            )
            contact = res.mappings().first()
            if not contact:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
            return dict(contact)

        updates.append("updated_at = NOW()")
        query = f"UPDATE public.contacts SET {', '.join(updates)} WHERE id = :c_id AND user_id = :u_id RETURNING *;"
        res = await session.execute(text(query), params)
        updated = res.mappings().first()
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
        return dict(updated)

@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(contact_id: UUID, user_id: str = Depends(get_current_user_id)):
    async with get_tenant_session(user_id) as session:
        del_res = await session.execute(
            text("DELETE FROM public.contacts WHERE id = :c_id AND user_id = :u_id RETURNING id;"),
            {"c_id": str(contact_id), "u_id": user_id}
        )
        if not del_res.scalar():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")

@router.get("/{contact_id}/enrich/options")
async def get_contact_enrichment_options(
    contact_id: UUID,
    user_id: str = Depends(get_current_user_id)
):
    """
    Presents the two first-time meeting prep options:
    Option A: Upload a background report/dossier.
    Option B: Automated internet research.
    """
    from apps.api.app.services.enrichment_service import EnrichmentService
    enrichment_service = EnrichmentService()
    return await enrichment_service.get_enrichment_options(user_id=user_id, contact_id=contact_id)

@router.post("/{contact_id}/enrich/search")
async def execute_contact_web_enrichment(
    contact_id: UUID,
    meeting_title: Optional[str] = None,
    meeting_purpose: Optional[str] = None,
    user_id: str = Depends(get_current_user_id)
):
    """
    Executes Option B: automated web intelligence gathering for first-time contacts.
    """
    from apps.api.app.services.enrichment_service import EnrichmentService
    enrichment_service = EnrichmentService()
    return await enrichment_service.execute_web_enrichment(
        user_id=user_id,
        contact_id=contact_id,
        meeting_title=meeting_title,
        meeting_purpose=meeting_purpose
    )
