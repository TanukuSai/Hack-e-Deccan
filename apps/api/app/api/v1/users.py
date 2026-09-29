import hashlib
import logging
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from apps.api.app.core.security import get_current_user_id
from apps.api.app.core.db import get_tenant_session
from apps.api.app.providers.hindsight_adapter import HindsightAdapter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])
hindsight_adapter = HindsightAdapter()


class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    timezone: Optional[str] = None
    briefing_format_preference: Optional[str] = Field(None, pattern="^(standard|concise|detailed)$")
    prep_lead_time_hours: Optional[int] = Field(None, ge=1, le=72)
    monthly_budget_usd: Optional[float] = Field(None, ge=5.0)


@router.get("/me", summary="Get user profile details")
async def get_user_profile(user_id: str = Depends(get_current_user_id)):
    async with get_tenant_session(user_id) as session:
        prof_res = await session.execute(
            text("""
            SELECT id, email, full_name, timezone, briefing_format_preference,
                   prep_lead_time_hours, monthly_budget_usd, current_month_spend_usd,
                   account_status, created_at, updated_at
            FROM public.user_profiles WHERE id = CAST(:u_id AS UUID);
            """),
            {"u_id": user_id}
        )
        profile = prof_res.mappings().first()
        if not profile:
            raise HTTPException(status_code=404, detail="User profile not found")
        d = dict(profile)
        d["id"] = str(d["id"])
        d["monthly_budget_usd"] = float(d["monthly_budget_usd"]) if d["monthly_budget_usd"] else 25.0
        d["current_month_spend_usd"] = float(d["current_month_spend_usd"]) if d["current_month_spend_usd"] else 0.0
        return d


@router.patch("/me", summary="Update user profile settings")
async def update_user_profile(
    payload: UserProfileUpdate,
    user_id: str = Depends(get_current_user_id)
):
    updates = []
    params = {"u_id": user_id}
    if payload.full_name is not None:
        updates.append("full_name = :full_name")
        params["full_name"] = payload.full_name
    if payload.timezone is not None:
        updates.append("timezone = :timezone")
        params["timezone"] = payload.timezone
    if payload.briefing_format_preference is not None:
        updates.append("briefing_format_preference = :pref")
        params["pref"] = payload.briefing_format_preference
    if payload.prep_lead_time_hours is not None:
        updates.append("prep_lead_time_hours = :lead")
        params["lead"] = payload.prep_lead_time_hours
    if payload.monthly_budget_usd is not None:
        updates.append("monthly_budget_usd = :budget")
        params["budget"] = payload.monthly_budget_usd

    if not updates:
        return await get_user_profile(user_id)

    updates.append("updated_at = NOW()")
    sql = f"UPDATE public.user_profiles SET {', '.join(updates)} WHERE id = CAST(:u_id AS UUID) RETURNING id;"

    async with get_tenant_session(user_id) as session:
        await session.execute(text(sql), params)

    return await get_user_profile(user_id)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_account(
    user_id: str = Depends(get_current_user_id)
):
    """
    GDPR Account Deletion Workflow (Gate 6):
    1. Mark account status as 'deleting'
    2. Cancel all active background jobs
    3. Purge tenant Hindsight memory bank
    4. Anonymize audit events (user_id = NULL, preserve original_user_hash)
    5. Delete user_profiles record (cascades to all tenant tables under composite FKs)
    """
    async with get_tenant_session(user_id) as session:
        # 1. Fetch profile & bank ID
        prof_res = await session.execute(
            text("SELECT id, email, hindsight_bank_id FROM public.user_profiles WHERE id = :u_id;"),
            {"u_id": user_id}
        )
        profile = prof_res.mappings().first()
        if not profile:
            raise HTTPException(status_code=404, detail="User profile not found")

        bank_id = profile["hindsight_bank_id"]

        # 2. Purge external Hindsight Memory Bank first
        if bank_id and hindsight_adapter.enabled:
            try:
                await hindsight_adapter.delete_bank(bank_id)
            except Exception as e:
                logger.warning(f"Failed to delete Hindsight bank during GDPR deletion: {e}")

        # 3. Execute atomic GDPR database deletion & anonymization (security definer)
        user_hash = hashlib.sha256(f"{user_id}_gdpr_pepper".encode()).hexdigest()
        await session.execute(
            text("SELECT public.execute_gdpr_account_deletion(CAST(:u_id AS UUID), :u_hash);"),
            {"u_id": user_id, "u_hash": user_hash}
        )
