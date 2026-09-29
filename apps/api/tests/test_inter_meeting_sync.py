import pytest
import uuid
from datetime import datetime, timezone, timedelta
from apps.api.app.services.inter_meeting_service import InterMeetingService
from apps.api.app.services.google_oauth_service import GoogleOAuthService

@pytest.mark.asyncio
async def test_google_oauth_service_loads_client_credentials():
    svc = GoogleOAuthService()
    # Ensure client credentials were discovered and loaded
    assert svc.client_id != ""
    assert "22523507322" in svc.client_id
    assert svc.client_secret != ""
    auth_url = svc.get_authorization_url(redirect_uri="http://localhost:3000/auth/google/callback")
    assert "client_id=" in auth_url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A3000%2Fauth%2Fgoogle%2Fcallback" in auth_url

def test_inter_meeting_correlation_logic():
    service = InterMeetingService()
    
    existing_reminders = [
        {
            "id": uuid.uuid4(),
            "owner_name": "You",
            "description": "Prepare quarterly security audit report for David Miller",
            "status": "pending",
        },
        {
            "id": uuid.uuid4(),
            "owner_name": "You",
            "description": "Follow up on API integration status with engineering team",
            "status": "pending",
        },
        {
            "id": uuid.uuid4(),
            "owner_name": "Sarah Chen",
            "description": "Share updated roadmap slides before EOD Thursday",
            "status": "pending",
        }
    ]

    report_text = """INTER-MEETING PROGRESS UPDATE
- Completed the quarterly security audit report for David Miller and team; verified with compliance.
- API integration status: currently in progress, backend endpoint testing underway with engineering.
- Newly established deliverable: Prepare deployment canary rollback rules for next quarter."""

    matched, new_items, summary = service._correlate_report_with_reminders(
        report_text=report_text,
        existing_reminders=existing_reminders,
        prev_meeting_title="Q3 Security Alignment",
        curr_meeting_title="Q4 Cloud Security Review"
    )

    # Verify matching
    assert len(matched) >= 2
    
    # Audit report should be completed
    audit_match = next((m for m in matched if "security audit" in m["description"].lower()), None)
    assert audit_match is not None
    assert audit_match["new_status"] == "completed"
    assert "quarterly security audit report" in audit_match["matched_excerpt"].lower()

    # API integration should be in_progress
    api_match = next((m for m in matched if "api integration" in m["description"].lower()), None)
    assert api_match is not None
    assert api_match["new_status"] == "in_progress"

    # New deliverable detected
    assert len(new_items) >= 1
    assert any("canary rollback" in item["description"].lower() for item in new_items)

    # Summary generated
    assert "Q3 Security Alignment" in summary or "Q4 Cloud Security Review" in summary
    assert "completed" in summary.lower()
