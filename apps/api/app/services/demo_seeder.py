import json
import uuid
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from apps.api.app.core.db import engine

async def ensure_staged_executive_data(user_id: str, email: str, name: str):
    """
    Checks if user has any meetings. If 0, auto-provisions full executive staged data:
    - Key Project (Series A Capital Raise)
    - Key Stakeholder Contacts (Elena Rostova, Marcus Vance, Devon Clark)
    - Upcoming Hero Meeting in 45m with 60-Second Scan Briefing & Epistemic Evidence
    - Meeting in 4h & Past Meeting with Follow-up Draft
    - Commitments / Reminders Ledger (Needing Review, Overdue, Active, Completed)
    """
    async with engine.connect() as conn:
        res = await conn.execute(
            text("SELECT COUNT(*) FROM public.meetings WHERE user_id = CAST(:uid AS UUID) AND title LIKE '%Series A%';"),
            {"uid": user_id}
        )
        count = res.scalar() or 0
        if count > 0:
            return  # Already has showcase meeting data

    now = datetime.now(timezone.utc)
    proj_id = str(uuid.uuid4())
    m1_id = str(uuid.uuid4())
    m2_id = str(uuid.uuid4())
    m3_id = str(uuid.uuid4())
    b1_id = str(uuid.uuid4())
    c1_id = str(uuid.uuid4())
    c2_id = str(uuid.uuid4())
    c3_id = str(uuid.uuid4())

    async with engine.begin() as conn:
        # 1. Project
        await conn.execute(text("""
            INSERT INTO public.projects (id, user_id, name, description)
            VALUES (CAST(:id AS UUID), CAST(:uid AS UUID), :name, :desc)
            ON CONFLICT DO NOTHING;
        """), {
            "id": proj_id,
            "uid": user_id,
            "name": "Series A Growth & AI Platform Expansion",
            "desc": "Key fundraising and strategic architecture roadmap for 2026."
        })

        # 2. Contacts
        contacts = [
            (c1_id, "Elena Rostova", "elena.rostova@horizonventures.com", "Horizon Ventures", "General Partner", "Lead investor. Very focused on gross margins and technical moat. Sensitive to enterprise deployment timelines."),
            (c2_id, "Marcus Vance", "marcus@apextechnologies.io", "Apex Technologies", "VP Engineering", "Technical co-evaluator. Values verifiable system reliability and data isolation."),
            (c3_id, "Devon Clark", "devon@hypercloud.com", "HyperCloud Capital", "Principal", "Focuses on open ecosystem integrations and developer advocacy."),
        ]
        for cid, cname, cmail, comp, role, notes in contacts:
            await conn.execute(text("""
                INSERT INTO public.contacts (id, user_id, name, email, organization, role_title, notes)
                VALUES (CAST(:id AS UUID), CAST(:uid AS UUID), :name, :email, :comp, :role, :notes)
                ON CONFLICT DO NOTHING;
            """), {
                "id": cid, "uid": user_id, "name": cname, "email": cmail,
                "comp": comp, "role": role, "notes": notes
            })

        # 3. Meetings
        # Meeting 1: Upcoming in 45 min (Hero Meeting)
        m1_start = now + timedelta(minutes=45)
        m1_end = now + timedelta(minutes=105)
        await conn.execute(text("""
            INSERT INTO public.meetings (
                id, user_id, project_id, title, purpose, start_time, end_time,
                status, effective_importance, join_url, notes
            ) VALUES (
                CAST(:id AS UUID), CAST(:uid AS UUID), CAST(:pid AS UUID), :title, :purpose,
                :start, :end, 'prepared', 'critical', 'https://meet.google.com/xyz-qwer-zxc',
                :notes
            ) ON CONFLICT (id, user_id) DO UPDATE SET title = EXCLUDED.title;
        """), {
            "id": m1_id, "uid": user_id, "pid": proj_id,
            "title": "Series A Investment Committee & Term Sheet Review",
            "purpose": "Finalize term sheet valuation parameters, governance seats, and Q3 deployment milestones.",
            "start": m1_start, "end": m1_end,
            "notes": "Elena and Marcus attending. Review previous commitments on ARR runway and gross margin validation."
        })

        # Meeting 2: In 4 hours
        m2_start = now + timedelta(hours=4)
        m2_end = now + timedelta(hours=5)
        await conn.execute(text("""
            INSERT INTO public.meetings (
                id, user_id, project_id, title, purpose, start_time, end_time,
                status, effective_importance, join_url, notes
            ) VALUES (
                CAST(:id AS UUID), CAST(:uid AS UUID), CAST(:pid AS UUID), :title, :purpose,
                :start, :end, 'scheduled', 'high', 'https://zoom.us/j/9876543210',
                'Technical roadmap review and team expansion goals.'
            ) ON CONFLICT (id, user_id) DO UPDATE SET title = EXCLUDED.title;
        """), {
            "id": m2_id, "uid": user_id, "pid": proj_id,
            "title": "Executive AI Infrastructure & Security Review",
            "purpose": "Evaluate multi-tenant RLS isolation and OpenClaw autonomous attendance safety.",
            "start": m2_start, "end": m2_end
        })

        # Meeting 3: Past meeting yesterday
        m3_start = now - timedelta(days=1, hours=2)
        m3_end = now - timedelta(days=1, hours=1)
        await conn.execute(text("""
            INSERT INTO public.meetings (
                id, user_id, project_id, title, purpose, start_time, end_time,
                status, effective_importance, join_url, notes
            ) VALUES (
                CAST(:id AS UUID), CAST(:uid AS UUID), CAST(:pid AS UUID), :title, :purpose,
                :start, :end, 'completed', 'high', 'https://meet.google.com/abc-defg-hij',
                'Completed pre-term sync.'
            ) ON CONFLICT (id, user_id) DO UPDATE SET title = EXCLUDED.title;
        """), {
            "id": m3_id, "uid": user_id, "pid": proj_id,
            "title": "Initial Horizon Ventures Partner Alignment",
            "purpose": "Preliminary discussion on platform architecture and revenue traction.",
            "start": m3_start, "end": m3_end
        })

        # Participants for Meeting 1
        await conn.execute(text("""
            INSERT INTO public.meeting_participants (id, user_id, meeting_id, contact_id, name, role, is_organizer)
            VALUES 
                (gen_random_uuid(), CAST(:uid AS UUID), CAST(:mid AS UUID), CAST(:c1 AS UUID), 'Elena Rostova', 'Lead Partner', FALSE),
                (gen_random_uuid(), CAST(:uid AS UUID), CAST(:mid AS UUID), CAST(:c2 AS UUID), 'Marcus Vance', 'VP Engineering', FALSE),
                (gen_random_uuid(), CAST(:uid AS UUID), CAST(:mid AS UUID), NULL, :myname, 'Executive Sponsor', TRUE)
            ON CONFLICT DO NOTHING;
        """), {"uid": user_id, "mid": m1_id, "c1": c1_id, "c2": c2_id, "myname": name})

        # 4. Briefing for Meeting 1 (60-Second Scan)
        talking_points = [
            "Maintain firm $28M pre-money valuation floor based on verified 4.2x YoY ARR growth.",
            "Confirm that OpenClaw attendance requires strict Two-Party Consent and cryptographic transcript hashing.",
            "Highlight that inter-meeting task tracking eliminated 100% of missed deliverables between technical syncs."
        ]
        risks = [
            "Horizon Ventures may push for a second board seat or liquidation preference clauses.",
            "Marcus Vance might request dedicated on-premise deployment timelines."
        ]
        questions = [
            "What specific criteria does the investment committee require to expedite wire execution?",
            "How does Horizon prefer we structure investor update cadences post-close?"
        ]

        await conn.execute(text("""
            INSERT INTO public.briefings (
                id, user_id, meeting_id, meeting_version, version, status,
                summary, talking_points, identified_risks, strategic_questions,
                assumptions_and_gaps, conflicts_detected, model_provider, model_name, is_latest
            ) VALUES (
                CAST(:id AS UUID), CAST(:uid AS UUID), CAST(:mid AS UUID), 1, 1, 'ready',
                :summary, CAST(:tp AS JSONB), CAST(:risks AS JSONB), CAST(:q AS JSONB),
                '[]', '[]', 'groq', 'llama-3.3-70b-versatile', TRUE
            ) ON CONFLICT (id, user_id) DO UPDATE SET summary = EXCLUDED.summary;
        """), {
            "id": b1_id, "uid": user_id, "mid": m1_id,
            "summary": "High-stakes Series A term sheet finalization with Elena Rostova (Horizon Ventures). Objective is securing signed term sheet at $28M valuation with single board seat.",
            "tp": json.dumps(talking_points),
            "risks": json.dumps(risks),
            "q": json.dumps(questions)
        })

        # 5. Evidence Items for Epistemic Classification (Direct Facts & Model Inferences)
        evidence = [
            (
                "Direct Fact: ARR stands at $1.85M with 84% gross margins as verified by Q2 audited financials.",
                "direct_fact",
                "document",
                "storage/docs/q2_audited_financials.pdf",
                "Page 4, Table 2.1: 'Net recurring revenue and margin breakdown for Q2 2026'"
            ),
            (
                "Model Inference: Elena Rostova historically counters valuation requests with milestone-based tranches.",
                "model_inference",
                "previous_meeting",
                None,
                "Inference derived from Hindsight Memory across past 3 investment committee meetings."
            ),
            (
                "Direct Fact: Two-Party Consent verification gate is enforced in PostgreSQL RLS session state.",
                "direct_fact",
                "document",
                "apps/api/app/providers/openclaw_adapter.py",
                "Lines 156-164: Hard block on transcript capture without consent_verified flag."
            )
        ]
        for claim, ep_class, stype, sloc, excerpt in evidence:
            await conn.execute(text("""
                INSERT INTO public.evidence_items (
                    id, briefing_id, user_id, claim_text, epistemic_class,
                    source_type, source_location, excerpt
                ) VALUES (
                    gen_random_uuid(), CAST(:bid AS UUID), CAST(:uid AS UUID), :claim, :ep,
                    :stype, :sloc, :excerpt
                );
            """), {
                "bid": b1_id, "uid": user_id, "claim": claim, "ep": ep_class,
                "stype": stype, "sloc": sloc, "excerpt": excerpt
            })

        # 6. Commitments / Reminders with diverse statuses
        commitments = [
            # Awaiting Review
            ("Elena Rostova", "Review revised governance clauses regarding veto thresholds on capital expenditures.", (now + timedelta(days=2)).date(), "pending", False, "Quote from partner sync: 'I will review Section 4 veto clauses.'"),
            ("Marcus Vance", "Deliver architecture security benchmark showing RLS tenant isolation.", (now + timedelta(days=1)).date(), "pending", False, "Notes: 'Marcus promised benchmark test by tomorrow.'"),
            # Overdue
            ("Devon Clark", "Share syndicate co-investor allocation preference document.", (now - timedelta(days=2)).date(), "in_progress", True, "Mentioned in last Monday's check-in."),
            # Active Confirmed
            (name, "Finalize legal capitalization table model in preparation for definitive agreements.", (now + timedelta(days=3)).date(), "in_progress", True, "CEO commitment to board."),
            ("Elena Rostova", "Provide draft standard investor rights agreement template.", (now + timedelta(days=5)).date(), "in_progress", True, "Term sheet rider."),
            # Completed
            (name, "Deliver Q2 audited financial statements to Elena Rostova.", (now - timedelta(days=4)).date(), "completed", True, "Sent via secure portal."),
        ]
        for owner, desc, due, stat, conf, excerpt in commitments:
            await conn.execute(text("""
                INSERT INTO public.commitments (
                    id, user_id, meeting_id, project_id, owner_name, description,
                    due_date, status, is_confirmed, source_excerpt
                ) VALUES (
                    gen_random_uuid(), CAST(:uid AS UUID), CAST(:mid AS UUID), CAST(:pid AS UUID),
                    :owner, :desc, :due, :stat, :conf, :excerpt
                );
            """), {
                "uid": user_id, "mid": m1_id, "pid": proj_id,
                "owner": owner, "desc": desc, "due": due, "stat": stat,
                "conf": conf, "excerpt": excerpt
            })

        # 7. Follow-up Draft for Meeting 3
        await conn.execute(text("""
            INSERT INTO public.follow_up_drafts (
                id, meeting_id, user_id, subject, body, recipients, status
            ) VALUES (
                gen_random_uuid(), CAST(:m3 AS UUID), CAST(:uid AS UUID),
                'Follow-up: Horizon Ventures & Term Sheet Finalization',
                'Elena,\n\nThank you for the productive discussion yesterday. As agreed, we are anchoring our Series A term sheet on the $28M valuation with single board seat representation.\n\nLooking forward to reviewing the final draft during our upcoming committee review.\n\nBest,\n' || :myname,
                CAST(:recipients AS JSONB),
                'draft'
            );
        """), {
            "m3": m3_id, "uid": user_id, "myname": name,
            "recipients": json.dumps(["elena.rostova@horizonventures.com", "marcus@apextechnologies.io"])
        })
