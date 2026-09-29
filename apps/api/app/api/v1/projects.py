from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from apps.api.app.core.security import get_current_user_id
from apps.api.app.core.db import get_tenant_session
from apps.api.app.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse
from apps.api.app.schemas.outcome import ProjectProgressSummary
from apps.api.app.services.outcome_service import OutcomeService

router = APIRouter(prefix="/projects", tags=["projects"])
outcome_service = OutcomeService()

@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    user_id: str = Depends(get_current_user_id)
):
    async with get_tenant_session(user_id) as session:
        ins_res = await session.execute(
            text("""
            INSERT INTO public.projects (user_id, name, description, status)
            VALUES (:user_id, :name, :description, :status)
            RETURNING *;
            """),
            {
                "user_id": user_id,
                "name": payload.name,
                "description": payload.description,
                "status": payload.status
            }
        )
        return dict(ins_res.mappings().first())

@router.get("", response_model=List[ProjectResponse])
async def list_projects(user_id: str = Depends(get_current_user_id)):
    async with get_tenant_session(user_id) as session:
        res = await session.execute(
            text("SELECT * FROM public.projects WHERE user_id = :user_id ORDER BY created_at DESC;"),
            {"user_id": user_id}
        )
        return [dict(r) for r in res.mappings().all()]

@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: UUID, user_id: str = Depends(get_current_user_id)):
    async with get_tenant_session(user_id) as session:
        res = await session.execute(
            text("SELECT * FROM public.projects WHERE id = :p_id AND user_id = :u_id;"),
            {"p_id": str(project_id), "u_id": user_id}
        )
        proj = res.mappings().first()
        if not proj:
            raise HTTPException(status_code=404, detail="Project not found")
        return dict(proj)

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: UUID, user_id: str = Depends(get_current_user_id)):
    async with get_tenant_session(user_id) as session:
        del_res = await session.execute(
            text("DELETE FROM public.projects WHERE id = :p_id AND user_id = :u_id RETURNING id;"),
            {"p_id": str(project_id), "u_id": user_id}
        )
        if not del_res.scalar():
            raise HTTPException(status_code=404, detail="Project not found")

@router.get("/{project_id}/progress", response_model=ProjectProgressSummary)
async def get_project_progress(
    project_id: UUID,
    user_id: str = Depends(get_current_user_id)
):
    """
    Get aggregated progress metrics and detected blockers for a project.
    """
    return await outcome_service.get_project_progress(user_id=user_id, project_id=project_id)
