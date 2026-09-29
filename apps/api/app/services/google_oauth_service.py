import base64
import hashlib
import json
import logging
import os
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from cryptography.fernet import Fernet
from fastapi import HTTPException, status
from sqlalchemy import text

from apps.api.app.core.config import settings
from apps.api.app.core.db import get_tenant_session, engine

logger = logging.getLogger(__name__)

CLIENT_SECRET_FILE = Path(os.getenv("GOOGLE_CLIENT_SECRET_FILE", "client_secret.json"))


def _get_fernet() -> Fernet:
    """Derive a deterministic 32-byte URL-safe base64 Fernet key from SUPABASE_JWT_SECRET."""
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SUPABASE_JWT_SECRET.encode()).digest())
    return Fernet(key)


def encrypt_token(plain_token: Optional[str]) -> Optional[str]:
    if not plain_token:
        return None
    try:
        f = _get_fernet()
        return f.encrypt(plain_token.encode()).decode()
    except Exception as e:
        logger.warning(f"Failed to encrypt token: {e}")
        return plain_token


def decrypt_token(cipher_token: Optional[str]) -> Optional[str]:
    if not cipher_token:
        return None
    try:
        f = _get_fernet()
        return f.decrypt(cipher_token.encode()).decode()
    except Exception:
        # Fallback in case token was stored unencrypted in earlier migration
        return cipher_token


class GoogleOAuthService:
    """
    Enterprise Google OAuth 2.0 Service.
    Handles:
    - Identity & Workspace Scopes separation
    - Authorization consent URL generation with CSRF state
    - Authorization code exchange
    - UserInfo profile retrieval
    - Fernet token encryption at rest
    - Token refresh before expiration
    - Integration status & revoking
    """

    IDENTITY_SCOPES = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ]

    WORKSPACE_SCOPES = [
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/documents.readonly",
    ]

    DEFAULT_SCOPES = IDENTITY_SCOPES + WORKSPACE_SCOPES

    USERINFO_URI = "https://www.googleapis.com/oauth2/v3/userinfo"

    def __init__(self, client_file: Optional[Path] = None):
        self.client_file = client_file or CLIENT_SECRET_FILE
        self.client_id: str = ""
        self.client_secret: str = ""
        self.auth_uri: str = "https://accounts.google.com/o/oauth2/auth"
        self.token_uri: str = "https://oauth2.googleapis.com/token"

        self._load_client_credentials()

    def _load_client_credentials(self):
        if self.client_file.exists():
            try:
                with open(self.client_file, "r") as f:
                    data = json.load(f)
                    web = data.get("web", {})
                    self.client_id = web.get("client_id", "")
                    self.client_secret = web.get("client_secret", "")
                    self.auth_uri = web.get("auth_uri", self.auth_uri)
                    self.token_uri = web.get("token_uri", self.token_uri)
                    return
            except Exception as e:
                logger.warning(f"Failed to read client credentials file: {e}")

        self.client_id = os.getenv("GOOGLE_CLIENT_ID", "")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")

    def get_authorization_url(
        self,
        redirect_uri: str,
        state: Optional[str] = None,
        include_workspace: bool = False
    ) -> str:
        """
        Generates Google OAuth 2.0 consent URL.
        If include_workspace=True, includes Calendar & Docs scopes.
        Uses access_type=offline & prompt=consent to ensure refresh token is returned.
        """
        scopes = self.DEFAULT_SCOPES if include_workspace else self.IDENTITY_SCOPES
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
        }
        if state:
            params["state"] = state
        return f"{self.auth_uri}?{urllib.parse.urlencode(params)}"

    async def exchange_code_for_user_info(
        self,
        code: str,
        redirect_uri: str
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Exchanges authorization code for tokens and calls Google UserInfo endpoint.
        Returns: (tokens_dict, user_info_dict)
        """
        token_data = {
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(self.token_uri, data=token_data)
            if resp.status_code != 200:
                logger.error(f"Google token exchange failed: {resp.text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Google OAuth token exchange failed: {resp.text}",
                )
            tokens = resp.json()

            access_token = tokens.get("access_token")
            user_resp = await client.get(
                self.USERINFO_URI,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if user_resp.status_code != 200:
                logger.error(f"Google userinfo request failed: {user_resp.text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to retrieve Google user profile info",
                )
            user_info = user_resp.json()

        return tokens, user_info

    async def save_tokens(
        self,
        user_id: str,
        access_token: str,
        refresh_token: str,
        expires_in: int,
        scopes: List[str],
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Encrypts and stores OAuth tokens in tenant_integrations under tenant session.
        Preserves existing refresh token if Google didn't return a new one.
        """
        enc_access = encrypt_token(access_token)
        enc_refresh = encrypt_token(refresh_token) if refresh_token else None
        meta = metadata or {"connected_at": datetime.now(timezone.utc).isoformat()}

        async with get_tenant_session(user_id) as session:
            await session.execute(
                text("""
                INSERT INTO public.tenant_integrations (
                    user_id, provider, status, access_token_encrypted,
                    refresh_token_encrypted, token_expires_at, scopes, metadata
                )
                VALUES (
                    :u_id, 'google', 'connected', :access_tok,
                    :refresh_tok, NOW() + CAST((:exp || ' seconds') AS INTERVAL),
                    CAST(:scopes AS JSONB), CAST(:meta AS JSONB)
                )
                ON CONFLICT (user_id, provider) DO UPDATE SET
                    status = 'connected',
                    access_token_encrypted = EXCLUDED.access_token_encrypted,
                    refresh_token_encrypted = CASE 
                        WHEN EXCLUDED.refresh_token_encrypted IS NOT NULL AND EXCLUDED.refresh_token_encrypted != ''
                        THEN EXCLUDED.refresh_token_encrypted 
                        ELSE public.tenant_integrations.refresh_token_encrypted 
                    END,
                    token_expires_at = EXCLUDED.token_expires_at,
                    scopes = EXCLUDED.scopes,
                    updated_at = NOW();
                """),
                {
                    "u_id": user_id,
                    "access_tok": enc_access,
                    "refresh_tok": enc_refresh,
                    "exp": expires_in,
                    "scopes": json.dumps(scopes),
                    "meta": json.dumps(meta),
                }
            )

    async def handle_oauth_callback(
        self,
        user_id: str,
        code: str,
        redirect_uri: str
    ) -> Dict[str, Any]:
        """
        Callback handler when user is already logged in and connecting Google Workspace.
        """
        tokens, user_info = await self.exchange_code_for_user_info(code, redirect_uri)
        access_token = tokens.get("access_token", "")
        refresh_token = tokens.get("refresh_token", "")
        expires_in = tokens.get("expires_in", 3600)
        scopes = tokens.get("scope", "").split(" ")

        await self.save_tokens(
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            scopes=scopes,
            metadata={"email": user_info.get("email"), "name": user_info.get("name")},
        )

        return {
            "provider": "google",
            "status": "connected",
            "email": user_info.get("email"),
            "scopes": scopes,
            "has_refresh_token": bool(refresh_token),
        }

    async def get_valid_access_token(self, user_id: str) -> Optional[str]:
        """
        Retrieves a valid, decrypted Google access token for the tenant.
        If current token is expired or within 5 minutes of expiring, automatically
        refreshes using refresh_token and updates database.
        """
        async with get_tenant_session(user_id) as session:
            res = await session.execute(
                text("""
                SELECT access_token_encrypted, refresh_token_encrypted, token_expires_at
                FROM public.tenant_integrations
                WHERE user_id = :u_id AND provider = 'google' AND status = 'connected';
                """),
                {"u_id": user_id}
            )
            row = res.mappings().first()
            if not row:
                return None

            enc_access = row["access_token_encrypted"]
            enc_refresh = row["refresh_token_encrypted"]
            expires_at = row["token_expires_at"]

            # Check if token is still valid (buffer of 300s)
            now = datetime.now(timezone.utc)
            if expires_at and expires_at > (now + timedelta(seconds=300)):
                return decrypt_token(enc_access)

            # Needs refresh
            refresh_tok = decrypt_token(enc_refresh)
            if not refresh_tok:
                logger.warning(f"Google access token expired for user {user_id} and no refresh token available")
                return decrypt_token(enc_access)

            # Refresh token with Google
            refresh_data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh_tok,
                "grant_type": "refresh_token",
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(self.token_uri, data=refresh_data)
                if resp.status_code != 200:
                    logger.error(f"Google token refresh failed: {resp.text}")
                    return decrypt_token(enc_access)
                refreshed = resp.json()

            new_access = refreshed.get("access_token")
            new_exp = refreshed.get("expires_in", 3600)
            enc_new_access = encrypt_token(new_access)

            await session.execute(
                text("""
                UPDATE public.tenant_integrations
                SET access_token_encrypted = :tok,
                    token_expires_at = NOW() + CAST((:exp || ' seconds') AS INTERVAL),
                    updated_at = NOW()
                WHERE user_id = :u_id AND provider = 'google';
                """),
                {"u_id": user_id, "tok": enc_new_access, "exp": new_exp}
            )
            return new_access

    async def get_integration_status(self, user_id: str) -> Dict[str, Any]:
        async with get_tenant_session(user_id) as session:
            res = await session.execute(
                text("""
                SELECT provider, status, token_expires_at, scopes, metadata, updated_at
                FROM public.tenant_integrations
                WHERE user_id = :u_id AND provider = 'google';
                """),
                {"u_id": user_id}
            )
            row = res.mappings().first()
            if not row:
                return {
                    "provider": "google",
                    "status": "disconnected",
                    "connected": False,
                    "scopes": [],
                }
            d = dict(row)
            d["connected"] = d.get("status") == "connected"
            if isinstance(d.get("scopes"), str):
                d["scopes"] = json.loads(d["scopes"])
            if isinstance(d.get("metadata"), str):
                d["metadata"] = json.loads(d["metadata"])
            if d.get("metadata") and "email" in d["metadata"]:
                d["email"] = d["metadata"]["email"]
            return d

    async def disconnect(self, user_id: str) -> bool:
        async with get_tenant_session(user_id) as session:
            res = await session.execute(
                text("""
                UPDATE public.tenant_integrations
                SET status = 'disconnected',
                    access_token_encrypted = NULL,
                    refresh_token_encrypted = NULL,
                    updated_at = NOW()
                WHERE user_id = :u_id AND provider = 'google'
                RETURNING id;
                """),
                {"u_id": user_id}
            )
            return res.scalar() is not None
