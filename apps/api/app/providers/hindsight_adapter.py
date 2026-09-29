import logging
from typing import Any, Dict, List, Optional
import httpx

from apps.api.app.core.config import settings

logger = logging.getLogger(__name__)

class HindsightAdapter:
    """
    Adapter for Hindsight Contextual Memory Cloud Service (https://api.hindsight.vectorize.io).
    Provides resilient, asynchronous bank creation, memory retention, recall, and GDPR deletion.
    Gracefully degrades when offline or disabled without blocking core meeting operations.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: Optional[int] = None,
        enabled: Optional[bool] = None
    ):
        self.base_url = (base_url or settings.HINDSIGHT_BASE_URL).rstrip("/")
        self.api_key = api_key or settings.HINDSIGHT_API_KEY
        self.timeout = timeout or settings.HINDSIGHT_TIMEOUT_SECONDS
        self.enabled = settings.HINDSIGHT_ENABLED if enabled is None else enabled

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def is_healthy(self) -> bool:
        if not self.enabled:
            return False
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.get(f"{self.base_url}/health", headers=self._headers())
                return res.status_code == 200
        except Exception as e:
            logger.warning(f"Hindsight health check failed: {e}")
            return False

    async def ensure_bank(self, bank_id: str, name: Optional[str] = None) -> bool:
        """
        Idempotently creates or verifies a dedicated memory bank for the tenant.
        """
        if not self.enabled or not self.api_key:
            return False

        url = f"{self.base_url}/v1/default/banks/{bank_id}"
        payload = {
            "name": name or f"tenant_{bank_id}",
            "retain_mission": "Retain key meeting decisions, commitments, attendee roles, and personal preferences."
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.put(url, json=payload, headers=self._headers())
                if res.status_code in (200, 201):
                    return True
                logger.warning(f"Hindsight PUT bank {bank_id} returned {res.status_code}: {res.text}")
                return False
        except Exception as e:
            logger.warning(f"Failed to ensure Hindsight bank {bank_id}: {e}")
            return False

    async def retain_memory(
        self,
        bank_id: str,
        content: str,
        context: Optional[str] = None,
        document_id: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> bool:
        """
        Retains a structured memory item in the user's Hindsight bank.
        """
        if not self.enabled or not self.api_key:
            return False

        url = f"{self.base_url}/v1/default/banks/{bank_id}/memories"
        item = {
            "content": content,
            "context": context or "Meeting outcome",
            "document_id": document_id,
            "tags": tags or []
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(url, json={"items": [item]}, headers=self._headers())
                if res.status_code in (200, 201, 202):
                    return True
                logger.warning(f"Hindsight retain memories returned {res.status_code}: {res.text}")
                return False
        except Exception as e:
            logger.warning(f"Failed to retain memory in Hindsight bank {bank_id}: {e}")
            return False

    async def recall_memories(
        self,
        bank_id: str,
        query: str,
        tags: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Queries relevant contextual memories from the bank.
        Returns list of memories or empty list on timeout/error.
        """
        if not self.enabled or not self.api_key:
            return []

        url = f"{self.base_url}/v1/default/banks/{bank_id}/memories/recall"
        payload: Dict[str, Any] = {"query": query}
        if tags:
            payload["tags"] = tags

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(url, json=payload, headers=self._headers())
                if res.status_code == 200:
                    data = res.json()
                    # Return memory hits list
                    if isinstance(data, dict):
                        return data.get("memories") or data.get("items") or []
                    if isinstance(data, list):
                        return data
                    return []
                logger.warning(f"Hindsight recall returned {res.status_code}: {res.text}")
                return []
        except Exception as e:
            logger.warning(f"Failed to recall memories from Hindsight bank {bank_id}: {e}")
            return []

    async def delete_bank(self, bank_id: str) -> bool:
        """
        GDPR account deletion: permanently purges the entire memory bank.
        """
        if not self.enabled or not self.api_key:
            return False

        url = f"{self.base_url}/v1/default/banks/{bank_id}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.delete(url, headers=self._headers())
                return res.status_code in (200, 204, 404)
        except Exception as e:
            logger.warning(f"Failed to delete Hindsight bank {bank_id}: {e}")
            return False
