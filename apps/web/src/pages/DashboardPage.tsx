import { useEffect, useState, useCallback } from 'react';
import {
  meetingsApi, commitmentsApi, integrationsApi,
} from '../api';
import type { Meeting, Commitment, IntegrationHealth } from '../api';
import { useApp, useToast } from '../store';

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString([], { month: 'short', day: 'numeric' });
}
function timeUntil(iso: string) {
  const diff = new Date(iso).getTime() - Date.now();
  if (diff < 0) return 'Now';
  const h = Math.floor(diff / 3_600_000);
  const m = Math.floor((diff % 3_600_000) / 60_000);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}
function priorityClass(imp: number) {
  if (imp >= 4) return 'badge-high';
  if (imp >= 2) return 'badge-medium';
  return 'badge-low';
}
function priorityLabel(imp: number) {
  if (imp >= 4) return 'High';
  if (imp >= 2) return 'Med';
  return 'Low';
}

export default function DashboardPage() {
  const { dispatch } = useApp();
  const toast = useToast();

  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [commitments, setCommitments] = useState<Commitment[]>([]);
  const [integrations, setIntegrations] = useState<IntegrationHealth[]>([]);
  const [syncing, setSyncing] = useState(false);

  const load = useCallback(async () => {
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
      // silently degrade — API may not be running yet
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSync = async () => {
    setSyncing(true);
    try {
      await integrationsApi.calendarSync();
      toast('Calendar sync queued', 'success', '✓');
      setTimeout(load, 2000);
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
      toast('Commitment confirmed', 'success', '✓');
    } catch (e: any) {
      toast(e.message ?? 'Failed', 'error', '✗');
    }
  };

  const handleDismiss = async (id: string) => {
    try {
      await commitmentsApi.update(id, { status: 'cancelled' });
      setCommitments(c => c.filter(x => x.id !== id));
      toast('Commitment dismissed', 'info', '—');
    } catch (e: any) {
      toast(e.message ?? 'Failed', 'error', '✗');
    }
  };

  // ── MOCK data when API is offline ──
  const DEMO_MEETINGS: Meeting[] = [
    { id: 'm1', title: 'Enterprise Cloud Security Review', start_time: new Date(Date.now() + 8_040_000).toISOString(), end_time: '', status: 'upcoming', effective_importance: 5, meeting_version: 1, created_at: '', updated_at: '', join_url: 'https://meet.google.com/abc' },
    { id: 'm2', title: 'Q4 Product Roadmap Alignment', start_time: new Date(Date.now() + 86_400_000).toISOString(), end_time: '', status: 'upcoming', effective_importance: 4, meeting_version: 1, created_at: '', updated_at: '' },
    { id: 'm3', title: 'Investor Series B Prep Call', start_time: new Date(Date.now() + 172_800_000).toISOString(), end_time: '', status: 'upcoming', effective_importance: 5, meeting_version: 1, created_at: '', updated_at: '' },
    { id: 'm4', title: 'Sprint Retrospective — Infra', start_time: new Date(Date.now() + 259_200_000).toISOString(), end_time: '', status: 'upcoming', effective_importance: 2, meeting_version: 1, created_at: '', updated_at: '' },
  ];
  const DEMO_COMMITMENTS: Commitment[] = [
    { id: 'c1', description: 'Prepare quarterly security audit report for David Miller', responsible_person: 'You', due_date: new Date(Date.now() + 432_000_000).toISOString(), status: 'pending', is_confirmed: false, epistemic_class: 'model_inference', created_at: '' },
    { id: 'c2', description: 'Follow up on API integration status with engineering team', responsible_person: 'You', due_date: new Date(Date.now() + 259_200_000).toISOString(), status: 'pending', is_confirmed: false, epistemic_class: 'direct_fact', created_at: '' },
    { id: 'c3', description: 'Share updated roadmap slides before EOD Thursday', responsible_person: 'Sarah Chen', due_date: new Date(Date.now() + 172_800_000).toISOString(), status: 'pending', is_confirmed: false, epistemic_class: 'model_inference', created_at: '' },
  ];
  const DEMO_INTEGRATIONS: IntegrationHealth[] = [
    { integration_type: 'google_meet', is_enabled: true, attendance_mode: 'manual', health_status: 'healthy', last_sync_at: new Date(Date.now() - 3_600_000).toISOString() },
    { integration_type: 'openclaw', is_enabled: true, attendance_mode: 'automatic', health_status: 'healthy', last_sync_at: new Date(Date.now() - 900_000).toISOString() },
  ];

  const displayMeetings = meetings.length > 0 ? meetings : DEMO_MEETINGS;
  const displayCommitments = commitments.length > 0 ? commitments : DEMO_COMMITMENTS;
  const displayIntegrations = integrations.length > 0 ? integrations : DEMO_INTEGRATIONS;
  const displayNext = displayMeetings[0];

  return (
    <div className="page-body fade-in">
      {/* ── Topbar ── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: -8 }}>
        <div>
          <div style={{ fontSize: 20, fontWeight: 800 }}>Good morning ✦</div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
            {new Date().toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })}
            {meetings.length === 0 && <span style={{ marginLeft: 12, color: 'var(--amber)', fontSize: 11 }}>⚠ Demo mode — API offline</span>}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-ghost" onClick={load}>↺ Refresh</button>
          <button className={`btn btn-primary ${syncing ? 'pulse' : ''}`} onClick={handleSync} disabled={syncing}>
            {syncing ? '⟳ Syncing…' : '⟳ Sync Calendar'}
          </button>
        </div>
      </div>

      {/* ── Stat Cards ── */}
      <div className="stats-grid">
        <div className="stat-card indigo" onClick={() => dispatch({ type: 'SET_PAGE', page: 'meetings' })} style={{ cursor: 'pointer' }}>
          <div className="stat-icon indigo">📅</div>
          <div className="countdown">{displayNext ? timeUntil(displayNext.start_time) : '—'}</div>
          <div className="stat-label">Next Meeting</div>
          <div className="stat-sub">{displayNext?.title?.slice(0, 32) ?? 'No upcoming meetings'}</div>
        </div>
        <div className="stat-card violet" onClick={() => dispatch({ type: 'SET_PAGE', page: 'briefing' })} style={{ cursor: 'pointer' }}>
          <div className="stat-icon violet">✦</div>
          <div className="stat-value">{displayMeetings.length}</div>
          <div className="stat-label">Active Briefings</div>
          <div className="stat-sub">Ready to review</div>
        </div>
        <div className="stat-card amber" onClick={() => dispatch({ type: 'SET_PAGE', page: 'commitments' })} style={{ cursor: 'pointer' }}>
          <div className="stat-icon amber">✓</div>
          <div className="stat-value">{displayCommitments.length}</div>
          <div className="stat-label">Action Required</div>
          <div className="stat-sub">Commitments needing confirmation</div>
        </div>
        <div className="stat-card emerald" onClick={() => dispatch({ type: 'SET_PAGE', page: 'integrations' })} style={{ cursor: 'pointer' }}>
          <div className="stat-icon emerald">⟳</div>
          <div className="stat-value">{displayIntegrations.filter(i => i.health_status === 'healthy').length}/{displayIntegrations.length || '—'}</div>
          <div className="stat-label">Integrations Healthy</div>
          <div className="stat-sub">Calendar, OpenClaw, Memory</div>
        </div>
      </div>

      {/* ── Main Two-col ── */}
      <div className="two-col">
        {/* Upcoming Meetings */}
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Upcoming Meetings</div>
              <div className="card-sub">Next {displayMeetings.length} on your calendar</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => dispatch({ type: 'SET_PAGE', page: 'meetings' })}>
              All →
            </button>
          </div>
          <div className="meeting-list scroll-panel">
            {displayMeetings.map(m => (
              <div key={m.id} className="meeting-item" onClick={() => { dispatch({ type: 'SET_PAGE', page: 'briefing', meetingId: m.id }); }}>
                <div className="meeting-time">{formatTime(m.start_time)}<br /><span style={{ fontSize: 9, color: 'var(--text-muted)' }}>{formatDate(m.start_time)}</span></div>
                <div className="meeting-info">
                  <div className="meeting-title">{m.title}</div>
                  <div className="meeting-sub">{m.join_url ? '🔗 Has join link' : '📌 No link yet'}{m.has_transcript ? ' · 📝 Transcript' : ''}</div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                  <span className={`badge ${priorityClass(m.effective_importance)}`}>{priorityLabel(m.effective_importance)}</span>
                  <span className="btn btn-ghost btn-sm" style={{ fontSize: 10 }}>Briefing →</span>
                </div>
              </div>
            ))}
            {displayMeetings.length === 0 && (
              <div className="empty-state"><div className="empty-icon">📅</div>No upcoming meetings</div>
            )}
          </div>
        </div>

        {/* Action Required */}
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">Action Required</div>
              <div className="card-sub">AI-proposed commitments needing confirmation</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => dispatch({ type: 'SET_PAGE', page: 'commitments' })}>All →</button>
          </div>
          <div className="commitment-list scroll-panel">
            {displayCommitments.map(c => (
              <div key={c.id} className="commitment-item">
                <div className="commitment-desc">{c.description}</div>
                <div className="commitment-meta">
                  <span className="badge badge-proposed">Proposed</span>
                  <span className={`evidence-chip`} title="Epistemic class">
                    {c.epistemic_class === 'direct_fact' ? '◆ Direct' : '◇ Inferred'}
                  </span>
                  {c.due_date && <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>Due {formatDate(c.due_date)}</span>}
                </div>
                <div className="commitment-actions">
                  <button className="btn btn-success btn-sm" onClick={() => handleConfirm(c.id)}>✓ Confirm</button>
                  <button className="btn btn-ghost btn-sm" onClick={() => handleDismiss(c.id)}>✕ Dismiss</button>
                </div>
              </div>
            ))}
            {displayCommitments.length === 0 && (
              <div className="empty-state"><div className="empty-icon">✓</div>All clear — no pending confirmations</div>
            )}
          </div>
        </div>
      </div>

      {/* ── Bottom Row ── */}
      <div className="two-col">
        {/* Integration Health */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">Integration Health</div>
            <button className="btn btn-ghost btn-sm" onClick={() => dispatch({ type: 'SET_PAGE', page: 'integrations' })}>Manage →</button>
          </div>
          <div className="integration-list">
            {/* Always show these core integrations */}
            {[
              { key: 'google_calendar', icon: '📅', label: 'Google Calendar', type: 'calendar' },
              { key: 'openclaw',        icon: '◈',  label: 'OpenClaw Bot',    type: 'attendance' },
              { key: 'hindsight',       icon: '◉',  label: 'Hindsight Memory',type: 'memory' },
            ].map(({ key, icon, label, type }) => {
              const live = displayIntegrations.find(i => i.integration_type === key || i.integration_type.includes(key.split('_')[0]));
              const isHealthy = live?.health_status === 'healthy';
              return (
                <div key={key} className="integration-item">
                  <div className="integration-icon" style={{ background: 'rgba(99,102,241,0.1)' }}>{icon}</div>
                  <div>
                    <div className="integration-name">{label}</div>
                    <div className="integration-sub">
                      {live?.last_sync_at ? `Synced ${Math.round((Date.now() - new Date(live.last_sync_at).getTime()) / 60_000)}m ago` : type}
                    </div>
                  </div>
                  <span className={`badge ${isHealthy || !live ? 'badge-healthy' : 'badge-error'} `} style={{ marginLeft: 'auto' }}>
                    {isHealthy || !live ? 'Healthy' : live.health_status}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Recent Activity Timeline */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">Recent Activity</div>
          </div>
          <div className="timeline">
            {[
              { title: 'Calendar synced — 4 events imported', time: '2 min ago', dot: '⟳' },
              { title: 'Briefing generated: Enterprise Security Review', time: '18 min ago', dot: '✦' },
              { title: 'Commitment confirmed: API integration status', time: '1h ago', dot: '✓' },
              { title: 'OpenClaw joined Q3 Strategy Call', time: '3h ago', dot: '◈' },
              { title: 'Transcript analyzed — 3 action items extracted', time: '3h ago', dot: '◉' },
            ].map((item, i) => (
              <div key={i} className="timeline-item">
                <div className="timeline-dot">{item.dot}</div>
                <div className="timeline-content">
                  <div className="timeline-title">{item.title}</div>
                  <div className="timeline-time">{item.time}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
