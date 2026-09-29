import json
import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import HTTPException, status
from sqlalchemy import text

from apps.api.app.core.config import settings
from apps.api.app.core.db import engine, get_tenant_session
from apps.api.app.core.security import create_access_token
from apps.api.app.services.google_oauth_service import GoogleOAuthService

logger = logging.getLogger(__name__)


class AuthService:
    """
    Central Authentication and User Provisioning Service.
    Integrates Google OAuth 2.0 with Supabase auth.users and public.user_profiles.
    """

    def __init__(self):
        self.google_service = GoogleOAuthService()

    async def get_or_create_user(
        self,
        email: str,
        full_name: Optional[str] = None,
        google_sub: Optional[str] = None
    ) -> str:
        """
        Idempotently gets or creates a user in auth.users and public.user_profiles.
        Returns the user UUID as a string.
        """
        async with engine.connect() as conn:
            # Check if user already exists with this email
            res = await conn.execute(
                text("SELECT id FROM public.user_profiles WHERE email = :e LIMIT 1;"),
                {"e": email}
            )
            existing = res.mappings().first()
            if existing:
                user_id = str(existing["id"])
                # Update full_name if provided
                if full_name:
                    async with engine.begin() as bconn:
                        await bconn.execute(
                            text("UPDATE public.user_profiles SET full_name = :fn WHERE id = CAST(:uid AS UUID);"),
                            {"fn": full_name, "uid": user_id}
                        )
                return user_id

        # Generate deterministic UUID from Google sub or random UUID
        if google_sub:
            user_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"google:{google_sub}"))
        else:
            user_id = str(uuid.uuid4())

        # Seed into auth.users and public.user_profiles
        async with engine.begin() as bconn:
            await bconn.execute(
                text("SELECT public.seed_test_user(CAST(:u AS UUID), :e, 25.0, 0.0);"),
                {"u": user_id, "e": email}
            )
            if full_name:
                await bconn.execute(
                    text("UPDATE public.user_profiles SET full_name = :fn WHERE id = CAST(:uid AS UUID);"),
                    {"fn": full_name, "uid": user_id}
                )

        return user_id

    async def sign_in_with_google(
        self,
        code: str,
        redirect_uri: str
    ) -> Dict[str, Any]:
        """
        Exchanges Google auth code, provisions user profile, saves integration tokens,
        and returns access token + user details.
        """
        tokens, user_info = await self.google_service.exchange_code_for_user_info(
            code=code, redirect_uri=redirect_uri
        )

        email = user_info.get("email")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google OAuth response did not contain an email address",
            )
        name = user_info.get("name") or email.split("@")[0]
        google_sub = user_info.get("sub")

        # Provision user
        user_id = await self.get_or_create_user(email=email, full_name=name, google_sub=google_sub)

        # Check if workspace scopes were granted (calendar, docs)
        granted_scopes = tokens.get("scope", "").split(" ")
        has_calendar = any("calendar" in s for s in granted_scopes)
        if has_calendar:
            try:
                await self.google_service.save_tokens(
                    user_id=user_id,
                    access_token=tokens.get("access_token", ""),
                    refresh_token=tokens.get("refresh_token", ""),
                    expires_in=tokens.get("expires_in", 3600),
                    scopes=granted_scopes,
                    metadata={"email": email, "name": name, "google_sub": google_sub},
                )
            except Exception as e:
                logger.warning(f"Could not save tenant integration tokens: {e}")

        # Issue Supabase JWT
        jwt_token = create_access_token({
            "sub": user_id,
            "email": email,
            "role": "authenticated"
        })

        user_profile = await self.get_user_profile(user_id)

        return {
            "access_token": jwt_token,
            "token_type": "bearer",
            "expires_in": 86400 * 7,
            "user": user_profile,
            "has_calendar_access": has_calendar,
        }

    async def dev_login(
        self,
        email: Optional[str] = None,
        name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Quick developer/demo sign-in. Seeds test user and returns signed JWT.
        """
        target_email = email or "demo_executive@example.com"
        target_name = name or "Demo Executive"
        user_id = await self.get_or_create_user(email=target_email, full_name=target_name)

        jwt_token = create_access_token({
            "sub": user_id,
            "email": target_email,
            "role": "authenticated"
        })
        user_profile = await self.get_user_profile(user_id)

        return {
            "access_token": jwt_token,
            "token_type": "bearer",
            "expires_in": 86400 * 7,
            "user": user_profile,
            "has_calendar_access": True,
        }

    async def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """
        Fetches user profile details with tenant isolation.
        """
        async with get_tenant_session(user_id) as session:
            res = await session.execute(
                text("""
                SELECT id, email, full_name, timezone, briefing_format_preference,
                       prep_lead_time_hours, monthly_budget_usd, current_month_spend_usd,
                       account_status, created_at, updated_at
                FROM public.user_profiles
                WHERE id = CAST(:uid AS UUID);
                """),
                {"uid": user_id}
            )
            row = res.mappings().first()
            if not row:
                raise HTTPException(status_code=404, detail="User profile not found")
            d = dict(row)
            d["id"] = str(d["id"])
            d["monthly_budget_usd"] = float(d["monthly_budget_usd"]) if d["monthly_budget_usd"] else 25.0
            d["current_month_spend_usd"] = float(d["current_month_spend_usd"]) if d["current_month_spend_usd"] else 0.0
            return d
