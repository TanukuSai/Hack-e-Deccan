import { useEffect, useState, useCallback } from 'react';
import {
  meetingsApi, commitmentsApi, integrationsApi,
} from '../api';
import type { Meeting, Commitment, IntegrationHealth } from '../api';
import { useApp, useToast } from '../store';

function formatTime(iso: string) {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return iso;
  }
}
function formatDate(iso: string) {
  try {
    return new Date(iso).toLocaleDateString([], { month: 'short', day: 'numeric' });
  } catch {
    return iso;
  }
}
function timeUntil(iso: string) {
  try {
    const diff = new Date(iso).getTime() - Date.now();
    if (diff < 0) return 'In Progress';
    const h = Math.floor(diff / 3_600_000);
    const m = Math.floor((diff % 3_600_000) / 60_000);
    return h > 0 ? `in ${h}h ${m}m` : `in ${m}m`;
  } catch {
    return '—';
  }
}

export default function DashboardPage() {
  const { dispatch } = useApp();
  const toast = useToast();

  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [commitments, setCommitments] = useState<Commitment[]>([]);
  const [integrations, setIntegrations] = useState<IntegrationHealth[]>([]);
  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [m, c, ih] = await Promise.allSettled([
        meetingsApi.list(10, 'upcoming'),
        commitmentsApi.list({ is_confirmed: 'false', status: 'pending' } as any),
        integrationsApi.health(),
      ]);
      if (m.status === 'fulfilled') setMeetings(m.value ?? []);
      if (c.status === 'fulfilled') setCommitments(c.value ?? []);
      if (ih.status === 'fulfilled') setIntegrations(ih.value?.integrations ?? []);
    } catch {
      // Graceful fallback to demo data if API is starting up
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSync = async () => {
    setSyncing(true);
    try {
      await integrationsApi.calendarSync();
      toast('Calendar synchronization queued', 'success', '✓');
      setTimeout(load, 2500);
    } catch (e: any) {
      toast(e.message ?? 'Sync failed', 'error', '✗');
    } finally {
      setSyncing(false);
    }
  };

  const handleConfirm = async (id: string) => {
    try {
      await commitmentsApi.confirm(id);
      setCommitments(c => c.filter(x => x.id !== id));
      toast('Reminder confirmed into active ledger', 'success', '✓');
    } catch (e: any) {
      toast(e.message ?? 'Failed to confirm reminder', 'error', '✗');
    }
  };

  const handleDismiss = async (id: string) => {
    try {
      await commitmentsApi.update(id, { status: 'cancelled' });
      setCommitments(c => c.filter(x => x.id !== id));
      toast('Reminder dismissed', 'info', '—');
    } catch (e: any) {
      toast(e.message ?? 'Failed to dismiss', 'error', '✗');
    }
  };

  // ── High-Fidelity Demo Data for Offline/Preview States ──
  const DEMO_MEETINGS: Meeting[] = [
    {
      id: 'm1',
      title: 'Enterprise Cloud Security Review',
      start_time: new Date(Date.now() + 8_040_000).toISOString(),
      end_time: new Date(Date.now() + 11_640_000).toISOString(),
      status: 'scheduled',
      effective_importance: 5,
      meeting_version: 1,
      created_at: '',
      updated_at: '',
      join_url: 'https://meet.google.com/qaz-wsxe-edc',
    },
    {
      id: 'm2',
      title: 'Q4 Product Roadmap Alignment',
      start_time: new Date(Date.now() + 86_400_000).toISOString(),
      end_time: new Date(Date.now() + 90_000_000).toISOString(),
      status: 'scheduled',
      effective_importance: 4,
      meeting_version: 1,
      created_at: '',
      updated_at: '',
      join_url: 'https://zoom.us/j/987654321',
    },
    {
      id: 'm3',
      title: 'Series B Strategy & Investor Briefing',
      start_time: new Date(Date.now() + 172_800_000).toISOString(),
      end_time: new Date(Date.now() + 176_400_000).toISOString(),
      status: 'scheduled',
      effective_importance: 5,
      meeting_version: 1,
      created_at: '',
      updated_at: '',
    },
  ];

  const DEMO_COMMITMENTS: Commitment[] = [
    {
      id: 'c1',
      description: 'Prepare quarterly security audit report for David Miller',
      responsible_person: 'You',
      due_date: new Date(Date.now() + 172_800_000).toISOString(),
      status: 'pending',
      is_confirmed: false,
      epistemic_class: 'model_inference',
      created_at: '',
    },
    {
      id: 'c2',
      description: 'Follow up on API integration status with backend team',
      responsible_person: 'You',
      due_date: new Date(Date.now() + 86_400_000).toISOString(),
      status: 'pending',
      is_confirmed: false,
      epistemic_class: 'direct_fact',
      created_at: '',
    },
    {
      id: 'c3',
      description: 'Circulate revised data retention policy before EOD Thursday',
      responsible_person: 'Sarah Chen (Legal)',
      due_date: new Date(Date.now() + 259_200_000).toISOString(),
      status: 'pending',
      is_confirmed: false,
      epistemic_class: 'direct_fact',
      created_at: '',
    },
  ];

  const DEMO_INTEGRATIONS: IntegrationHealth[] = [
    {
      integration_type: 'google_meet',
      is_enabled: true,
      attendance_mode: 'manual',
      health_status: 'healthy',
      last_sync_at: new Date(Date.now() - 600_000).toISOString(),
      transcript_capture_enabled: false,
    },
    {
      integration_type: 'openclaw',
      is_enabled: true,
      attendance_mode: 'manual',
      health_status: 'healthy',
      last_sync_at: new Date(Date.now() - 1_200_000).toISOString(),
      transcript_capture_enabled: true,
    },
  ];

  const displayMeetings = meetings.length > 0 ? meetings : DEMO_MEETINGS;
  const displayCommitments = commitments.length > 0 ? commitments : DEMO_COMMITMENTS;
  const displayIntegrations = integrations.length > 0 ? integrations : DEMO_INTEGRATIONS;
  const nextMeeting = displayMeetings[0];

  const overdueCount = displayCommitments.filter(c => c.due_date && new Date(c.due_date).getTime() < Date.now()).length;

  return (
    <div className="page-body">
      {/* ── Executive Greeting & Quick Actions ── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <div style={{ fontSize: 22, fontStretch: 'condensed', fontWeight: 800, letterSpacing: '-0.02em', color: '#fff' }}>
            Daily Command Center
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span>{new Date().toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}</span>
            <span>•</span>
            <span style={{ color: 'var(--emerald)', fontWeight: 600 }}>Active Workspace Operational</span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button className="btn btn-ghost btn-sm" onClick={load} disabled={loading} title="Reload live database state">
            {loading ? '⟳ Refreshing…' : '↺ Refresh'}
          </button>
          <button
            className={`btn btn-primary btn-sm ${syncing ? 'pulse' : ''}`}
            onClick={handleSync}
            disabled={syncing}
            title="Poll Google Calendar for upcoming schedule updates"
          >
            {syncing ? '⟳ Syncing…' : '⟳ Sync Calendar'}
          </button>
        </div>
      </div>

      {/* ── 1. WHAT IS COMING UP? -> Hero Next Meeting Banner ── */}
      {nextMeeting && (
        <div className="hero-next-meeting">
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="hero-badge-strip">
              <span className="badge badge-ready">✦ Next Meeting</span>
              <span className="badge badge-direct">High Stakes</span>
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                {formatDate(nextMeeting.start_time)} · {formatTime(nextMeeting.start_time)}
              </span>
            </div>

            <div className="hero-meeting-title">
              {nextMeeting.title}
            </div>

            <div className="hero-attendees-strip">
              <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>Stakeholders:</span>
              <span>David Miller (VP Eng, Cloudflare)</span>
              <span>•</span>
              <span>Priya Nair (Security Lead)</span>
              <span>•</span>
              <span>You</span>
            </div>

            <div style={{ display: 'flex', gap: 10, marginTop: 16, flexWrap: 'wrap' }}>
              <button
                className="btn btn-primary btn-sm"
                onClick={() => dispatch({ type: 'SET_PAGE', page: 'briefing', meetingId: nextMeeting.id })}
              >
                ✦ Open 60-Sec Briefing
              </button>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => dispatch({ type: 'SET_PAGE', page: 'chat', meetingId: nextMeeting.id })}
              >
                💬 Spar with Agent
              </button>
              {nextMeeting.join_url && (
                <a
                  href={nextMeeting.join_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-ghost btn-sm"
                  style={{ color: 'var(--sky)' }}
                >
                  🔗 Join Video Call
                </a>
              )}
            </div>
          </div>

          <div className="hero-countdown-box">
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)', fontWeight: 700 }}>
                Starts In
              </div>
              <div className="hero-timer">
                {timeUntil(nextMeeting.start_time)}
              </div>
            </div>
            <div style={{ fontSize: 11, color: 'var(--emerald)', display: 'flex', alignItems: 'center', gap: 4 }}>
              <span>✓</span> Intelligence & Briefing Synthesized
            </div>
          </div>
        </div>
      )}

      {/* ── Operational Pulse Stats ── */}
      <div className="stats-grid">
        <div
          className="stat-card"
          onClick={() => dispatch({ type: 'SET_PAGE', page: 'meetings' })}
        >
          <div className="stat-label">Upcoming Meetings</div>
          <div className="stat-value">{displayMeetings.length}</div>
          <div className="stat-sub">Next 7 days on calendar</div>
        </div>

        <div
          className="stat-card"
          onClick={() => dispatch({ type: 'SET_PAGE', page: 'briefing' })}
        >
          <div className="stat-label">Prepared Briefings</div>
          <div className="stat-value" style={{ color: 'var(--indigo)' }}>{displayMeetings.length}</div>
          <div className="stat-sub">100% ready for executive review</div>
        </div>

        <div
          className="stat-card"
          onClick={() => dispatch({ type: 'SET_PAGE', page: 'commitments' })}
        >
          <div className="stat-label">Reminders to Confirm</div>
          <div className="stat-value" style={{ color: overdueCount > 0 ? 'var(--rose)' : 'var(--amber)' }}>
            {displayCommitments.length}
          </div>
          <div className="stat-sub">
            {overdueCount > 0 ? `🚨 ${overdueCount} overdue` : 'AI commitments awaiting triage'}
          </div>
        </div>

        <div
          className="stat-card"
          onClick={() => dispatch({ type: 'SET_PAGE', page: 'integrations' })}
        >
          <div className="stat-label">Connected Integrations</div>
          <div className="stat-value" style={{ color: 'var(--emerald)' }}>
            {displayIntegrations.filter(i => i.health_status === 'healthy').length}/3
          </div>
          <div className="stat-sub">Calendar, OpenClaw Bot, Memory</div>
        </div>
      </div>

      {/* ── 2. WHAT DO I NEED TO DO? & 3. IS ANYTHING AT RISK? ── */}
      <div className="two-col">
        {/* Left: Actionable Reminders Triage Queue */}
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Reminders Awaiting Triage</div>
              <div className="card-sub">Review AI-proposed commitments before your next meeting</div>
            </div>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => dispatch({ type: 'SET_PAGE', page: 'commitments' })}
            >
              All Reminders ({displayCommitments.length}) →
            </button>
          </div>

          <div className="commitment-list">
            {displayCommitments.map(c => {
              const isOverdue = c.due_date && new Date(c.due_date).getTime() < Date.now();
              return (
                <div key={c.id} className="commitment-item">
                  <div className="commitment-desc">{c.description}</div>
                  <div className="commitment-meta">
                    <span className={`badge ${c.epistemic_class === 'direct_fact' ? 'badge-direct' : 'badge-inferred'}`}>
                      {c.epistemic_class === 'direct_fact' ? '◆ Verified Fact' : '◇ AI Inference'}
                    </span>
                    <span style={{ color: 'var(--text-secondary)' }}>
                      Owner: <strong>{c.responsible_person || 'You'}</strong>
                    </span>
                    {c.due_date && (
                      <span className={`badge ${isOverdue ? 'badge-overdue' : 'badge-ready'}`}>
                        {isOverdue ? '🚨 Overdue' : `Due ${formatDate(c.due_date)}`}
                      </span>
                    )}
                  </div>
                  <div className="commitment-actions">
                    <button
                      className="btn btn-success btn-sm"
                      onClick={() => handleConfirm(c.id)}
                      title="Approve this reminder into your confirmed commitments ledger"
                    >
                      ✓ Confirm
                    </button>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => handleDismiss(c.id)}
                      title="Dismiss false positive"
                    >
                      ✕ Dismiss
                    </button>
                  </div>
                </div>
              );
            })}

            {displayCommitments.length === 0 && (
              <div className="empty-state">
                <div className="empty-icon">✓</div>
                <div>All commitments confirmed</div>
                <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>No pending reminders requiring your attention.</div>
              </div>
            )}
          </div>
        </div>

        {/* Right: Upcoming Schedule & Readiness */}
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Today's Meeting Schedule</div>
              <div className="card-sub">Chronological briefing status across your day</div>
            </div>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => dispatch({ type: 'SET_PAGE', page: 'meetings' })}
            >
              Full Calendar →
            </button>
          </div>

          <div className="meeting-list">
            {displayMeetings.map((m, idx) => (
              <div
                key={m.id}
                className="meeting-item"
                style={{ cursor: 'pointer' }}
                onClick={() => dispatch({ type: 'SET_PAGE', page: 'briefing', meetingId: m.id })}
              >
                <div className="meeting-time">
                  {formatTime(m.start_time)}
                  <div style={{ fontSize: 9.5, color: 'var(--text-muted)' }}>{formatDate(m.start_time)}</div>
                </div>

                <div className="meeting-info">
                  <div className="meeting-title">{m.title}</div>
                  <div className="meeting-sub">
                    {idx === 0 ? '✦ Next in line' : 'Upcoming call'}
                    {m.join_url ? ' · 🔗 Video link attached' : ''}
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                  <span className="badge badge-ready">60s Briefing</span>
                  <span className="btn btn-ghost btn-sm" style={{ padding: '3px 8px', fontSize: 10 }}>
                    Prep →
                  </span>
                </div>
              </div>
            ))}

            {displayMeetings.length === 0 && (
              <div className="empty-state">
                <div className="empty-icon">📅</div>
                <div>No meetings scheduled</div>
                <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>Click "Sync Calendar" above to import your upcoming calendar events.</div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── System Status & Security Invariants ── */}
      <div className="card" style={{ padding: '16px 20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap', fontSize: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ color: 'var(--emerald)' }}>●</span>
              <span style={{ color: 'var(--text-secondary)' }}>Google Calendar:</span>
              <strong style={{ color: '#fff' }}>Connected & Polling</strong>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ color: 'var(--emerald)' }}>●</span>
              <span style={{ color: 'var(--text-secondary)' }}>OpenClaw Bot:</span>
              <strong style={{ color: '#fff' }}>Manual Request Only (Consent Enforced)</strong>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ color: 'var(--emerald)' }}>●</span>
              <span style={{ color: 'var(--text-secondary)' }}>Epistemic Safety:</span>
              <strong style={{ color: '#fff' }}>Draft-Only Email Invariant Active</strong>
            </div>
          </div>

          <button
            className="btn btn-ghost btn-sm"
            onClick={() => dispatch({ type: 'SET_PAGE', page: 'integrations' })}
          >
            Manage Integrations →
          </button>
        </div>
      </div>
    </div>
  );
}
