"""
Calendar Sync Provider
=======================
Abstracts calendar synchronization across supported providers.
Currently implements Google Calendar via OAuth.
Designed for incremental sync using provider sync tokens.

Design:
- Provider abstraction: CalendarProvider protocol → GoogleCalendarProvider
- Sync tokens stored in integration_sync_state table
- Meeting changes → enqueue prep jobs (never generate briefings inline)
- Attendees are extracted but never stored without consent
"""
import hashlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CalendarEvent:
    """Normalized calendar event from any provider."""
    provider_event_id: str
    provider: str  # 'google', 'microsoft', 'ical'
    title: str
    start_time: datetime
    end_time: datetime
    organizer_email: Optional[str]
    attendee_emails: List[str]
    join_url: Optional[str]
    description: Optional[str]
    status: str  # 'confirmed', 'tentative', 'cancelled'
    is_recurring: bool = False
    recurrence_id: Optional[str] = None
    linked_document_urls: List[str] = field(default_factory=list)
    raw_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SyncResult:
    """Result of an incremental calendar sync."""
    provider: str
    events_created: List[CalendarEvent] = field(default_factory=list)
    events_updated: List[CalendarEvent] = field(default_factory=list)
    events_cancelled: List[str] = field(default_factory=list)  # provider_event_ids
    next_sync_token: Optional[str] = None
    sync_anchor: Optional[datetime] = None
    error: Optional[str] = None
    is_partial: bool = False


# ---------------------------------------------------------------------------
# Abstract provider
# ---------------------------------------------------------------------------

class CalendarProvider(ABC):
    """Abstract interface for calendar providers."""

    @abstractmethod
    async def get_sync_result(
        self,
        access_token: str,
        sync_token: Optional[str] = None,
        sync_anchor: Optional[datetime] = None,
        max_results: int = 250
    ) -> SyncResult:
        """Perform incremental (or full) sync. Returns normalized SyncResult."""
        ...

    @abstractmethod
    async def get_event(self, access_token: str, event_id: str) -> Optional[CalendarEvent]:
        """Fetch a single event by provider ID."""
        ...


# ---------------------------------------------------------------------------
# Google Calendar Provider
# ---------------------------------------------------------------------------

class GoogleCalendarProvider(CalendarProvider):
    """
    Google Calendar v3 API provider.
    Uses incremental sync via syncToken.
    Falls back to time-based anchor when syncToken is invalidated (410 Gone).
    """

    BASE_URL = "https://www.googleapis.com/calendar/v3"

    async def get_sync_result(
        self,
        access_token: str,
        sync_token: Optional[str] = None,
        sync_anchor: Optional[datetime] = None,
        max_results: int = 250
    ) -> SyncResult:
        params = {
            "maxResults": max_results,
            "singleEvents": "true",
            "orderBy": "updated",
        }

        if sync_token:
            params["syncToken"] = sync_token
        else:
            # Full or anchor-based sync
            anchor = sync_anchor or (datetime.now(timezone.utc) - timedelta(days=14))
            params["timeMin"] = anchor.isoformat()

        headers = {"Authorization": f"Bearer {access_token}"}
        all_created, all_updated, all_cancelled = [], [], []
        page_token = None

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                while True:
                    if page_token:
                        params["pageToken"] = page_token
                    res = await client.get(f"{self.BASE_URL}/calendars/primary/events", params=params, headers=headers)

                    if res.status_code == 410:
                        # syncToken invalidated — do full resync
                        logger.info("[GoogleCalendar] Sync token invalidated, initiating full resync")
                        return await self.get_sync_result(access_token, sync_token=None, sync_anchor=sync_anchor, max_results=max_results)

                    if res.status_code == 401:
                        return SyncResult(provider="google", error="UNAUTHORIZED: OAuth token expired or revoked")

                    if res.status_code != 200:
                        return SyncResult(provider="google", error=f"PROVIDER_ERROR: status {res.status_code}")

                    data = res.json()
                    for item in data.get("items", []):
                        if item.get("status") == "cancelled":
                            all_cancelled.append(item["id"])
                        else:
                            event = self._parse_event(item)
                            if event:
                                # We can't easily distinguish created vs updated without DB comparison
                                # Worker layer does that comparison
                                all_updated.append(event)

                    page_token = data.get("nextPageToken")
                    if not page_token:
                        return SyncResult(
                            provider="google",
                            events_created=[],  # resolved by worker
                            events_updated=all_updated,
                            events_cancelled=all_cancelled,
                            next_sync_token=data.get("nextSyncToken"),
                        )
        except httpx.TimeoutException:
            return SyncResult(provider="google", error="TIMEOUT")
        except Exception as exc:
            logger.warning(f"[GoogleCalendar] Sync error: {type(exc).__name__}: {exc}")
            return SyncResult(provider="google", error=f"UNEXPECTED_ERROR: {type(exc).__name__}")

    async def get_event(self, access_token: str, event_id: str) -> Optional[CalendarEvent]:
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.get(
                    f"{self.BASE_URL}/calendars/primary/events/{event_id}",
                    headers=headers
                )
                if res.status_code == 200:
                    return self._parse_event(res.json())
                return None
        except Exception as exc:
            logger.warning(f"[GoogleCalendar] Get event failed: {type(exc).__name__}")
            return None

    def _parse_event(self, item: Dict[str, Any]) -> Optional[CalendarEvent]:
        """Parse raw Google Calendar event item into CalendarEvent."""
        try:
            start_raw = item.get("start", {})
            end_raw = item.get("end", {})

            start_time = self._parse_dt(start_raw)
            end_time = self._parse_dt(end_raw)
            if not start_time or not end_time:
                return None

            # Extract join URL from conferenceData or location
            join_url = None
            conf = item.get("conferenceData", {})
            for ep in conf.get("entryPoints", []):
                if ep.get("entryPointType") == "video":
                    join_url = ep.get("uri")
                    break
            if not join_url:
                location = item.get("location", "")
                if location.startswith("http") and ("meet.google.com" in location or "zoom.us" in location or "teams.microsoft" in location):
                    join_url = location

            # Extract attendees (emails only, no names stored)
            attendee_emails = [
                a["email"] for a in item.get("attendees", [])
                if "email" in a and not a.get("resource", False)
            ]

            # Extract linked Google Docs from description
            desc = item.get("description", "") or ""
            doc_urls = [
                word for word in desc.split()
                if "docs.google.com" in word or "drive.google.com" in word
            ]

            return CalendarEvent(
                provider_event_id=item["id"],
                provider="google",
                title=item.get("summary", "(No Title)"),
                start_time=start_time,
                end_time=end_time,
                organizer_email=item.get("organizer", {}).get("email"),
                attendee_emails=attendee_emails,
                join_url=join_url,
                description=desc[:2000] if desc else None,  # truncate
                status=item.get("status", "confirmed"),
                is_recurring="recurringEventId" in item,
                recurrence_id=item.get("recurringEventId"),
                linked_document_urls=doc_urls[:10],
                raw_metadata={
                    "etag": item.get("etag"),
                    "updated": item.get("updated"),
                    "htmlLink": item.get("htmlLink"),
                }
            )
        except (KeyError, ValueError) as exc:
            logger.debug(f"[GoogleCalendar] Failed to parse event: {exc}")
            return None

    def _parse_dt(self, dt_obj: Dict[str, Any]) -> Optional[datetime]:
        """Parse Google's dateTime or date field."""
        if "dateTime" in dt_obj:
            try:
                return datetime.fromisoformat(dt_obj["dateTime"].replace("Z", "+00:00"))
            except ValueError:
                return None
        if "date" in dt_obj:
            try:
                d = datetime.strptime(dt_obj["date"], "%Y-%m-%d")
                return d.replace(tzinfo=timezone.utc)
            except ValueError:
                return None
        return None


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

CALENDAR_PROVIDERS: Dict[str, CalendarProvider] = {
    "google": GoogleCalendarProvider(),
}


def get_calendar_provider(provider_name: str) -> Optional[CalendarProvider]:
    return CALENDAR_PROVIDERS.get(provider_name)
