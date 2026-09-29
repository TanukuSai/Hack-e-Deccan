import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from apps.api.app.core.security import get_current_user_id
from apps.api.app.services.auth_service import AuthService
from apps.api.app.services.google_oauth_service import GoogleOAuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
auth_service = AuthService()
google_oauth = GoogleOAuthService()


class GoogleLoginCallbackPayload(BaseModel):
    code: str = Field(..., description="Authorization code from Google OAuth redirect")
    redirect_uri: str = Field(..., description="Redirect URI registered in Google Console")
    state: Optional[str] = Field(None, description="Optional CSRF state parameter")


class DevLoginPayload(BaseModel):
    email: Optional[str] = Field(None, description="Test user email")
    name: Optional[str] = Field(None, description="Test user display name")


class AuthUrlResponse(BaseModel):
    authorization_url: str
    scopes: List[str]


@router.get("/google/url", response_model=AuthUrlResponse, summary="Get Google OAuth login URL")
async def get_google_login_url(
    redirect_uri: str = Query(..., description="Redirect URI for Google callback"),
    include_calendar: bool = Query(False, description="Whether to also request Calendar and Docs scopes"),
    state: Optional[str] = Query(None, description="Optional CSRF state parameter")
):
    """
    Generates the Google OAuth 2.0 authorization URL for app sign-in.
    If include_calendar is True, requests Calendar and Docs read permissions upfront.
    """
    url = google_oauth.get_authorization_url(
        redirect_uri=redirect_uri,
        state=state,
        include_workspace=include_calendar
    )
    scopes = google_oauth.DEFAULT_SCOPES if include_calendar else google_oauth.IDENTITY_SCOPES
    return {"authorization_url": url, "scopes": scopes}


@router.post("/google/callback", summary="Exchange Google code for session JWT")
async def google_login_callback(payload: GoogleLoginCallbackPayload):
    """
    Exchanges Google authorization code for tokens, retrieves profile,
    auto-provisions user in auth.users & public.user_profiles, and issues JWT.
    """
    return await auth_service.sign_in_with_google(
        code=payload.code,
        redirect_uri=payload.redirect_uri
    )


@router.post("/dev-login", summary="One-click developer/demo login")
async def dev_login(payload: Optional[DevLoginPayload] = None):
    """
    Instant sign-in for development, demonstrations, and test suites.
    Provisions a demo user and issues a valid JWT without Google redirects.
    """
    email = payload.email if payload else None
    name = payload.name if payload else None
    return await auth_service.dev_login(email=email, name=name)


@router.get("/me", summary="Get authenticated user profile")
async def get_current_user_profile(user_id: str = Depends(get_current_user_id)):
    """
    Returns the authenticated user's profile and budget metrics.
    """
    profile = await auth_service.get_user_profile(user_id)
    integration = await google_oauth.get_integration_status(user_id)
    profile["google_integration"] = integration
    return profile


@router.post("/logout", summary="Logout current session")
async def logout(user_id: str = Depends(get_current_user_id)):
    """
    Invalidates client session.
    """
    return {"status": "logged_out", "user_id": user_id}
