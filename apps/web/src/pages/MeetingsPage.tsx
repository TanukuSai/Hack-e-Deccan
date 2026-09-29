// Meetings list page
import { useEffect, useState } from 'react';
import { meetingsApi } from '../api';
import type { Meeting } from '../api';
import { useApp, useToast } from '../store';

function formatDT(iso: string) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}
function priorityClass(imp: number) {
  if (imp >= 4) return 'badge-high';
  if (imp >= 2) return 'badge-medium';
  return 'badge-low';
}
function priorityLabel(imp: number) {
  if (imp >= 4) return 'High' ; if (imp >= 2) return 'Med'; return 'Low';
}

const DEMO: Meeting[] = [
  { id: 'm1', title: 'Enterprise Cloud Security Review', purpose: 'Q4 security posture alignment with Cloudflare team', start_time: new Date(Date.now() + 8_040_000).toISOString(), end_time: new Date(Date.now() + 11_640_000).toISOString(), status: 'upcoming', effective_importance: 5, meeting_version: 1, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), join_url: 'https://meet.google.com/abc', calendar_source: 'google' },
  { id: 'm2', title: 'Q4 Product Roadmap Alignment', purpose: 'Review and align on H1 2027 priorities', start_time: new Date(Date.now() + 86_400_000).toISOString(), end_time: new Date(Date.now() + 90_000_000).toISOString(), status: 'upcoming', effective_importance: 4, meeting_version: 2, created_at: new Date().toISOString(), updated_at: new Date().toISOString() },
  { id: 'm3', title: 'Investor Series B Prep Call', purpose: 'Prep narrative and metrics deck for Sequoia meeting', start_time: new Date(Date.now() + 172_800_000).toISOString(), end_time: new Date(Date.now() + 176_400_000).toISOString(), status: 'upcoming', effective_importance: 5, meeting_version: 1, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), has_transcript: false },
  { id: 'm4', title: 'Sprint Retrospective — Infra', purpose: 'Infra sprint retro', start_time: new Date(Date.now() - 86_400_000).toISOString(), end_time: new Date(Date.now() - 82_800_000).toISOString(), status: 'completed', effective_importance: 2, meeting_version: 3, created_at: new Date().toISOString(), updated_at: new Date().toISOString(), has_transcript: true },
];

export default function MeetingsPage() {
  const { dispatch } = useApp();
  const toast = useToast();
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [filter, setFilter] = useState<'all' | 'upcoming' | 'completed'>('upcoming');
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ title: '', purpose: '', start_time: '', end_time: '' });

  useEffect(() => {
    meetingsApi.list(50, filter === 'all' ? undefined : filter)
      .then(m => setMeetings(m ?? []))
      .catch(() => setMeetings(DEMO.filter(m => filter === 'all' || m.status === filter)))
      .finally(() => setLoading(false));
  }, [filter]);

  const handleCreate = async () => {
    if (!form.title) return;
    try {
      const m = await meetingsApi.create(form);
      setMeetings(prev => [m, ...prev]);
      setShowCreate(false);
      setForm({ title: '', purpose: '', start_time: '', end_time: '' });
      toast('Meeting created', 'success', '✓');
    } catch (e: any) { toast(e.message, 'error', '✗'); }
  };

  const display = meetings.length > 0 ? meetings : DEMO.filter(m => filter === 'all' || m.status === filter);

  return (
    <div className="page-body fade-in">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: -8 }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 20, fontWeight: 800 }}>Meetings</div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{display.length} meetings</div>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>＋ New Meeting</button>
      </div>

      <div className="tabs">
        {(['upcoming', 'all', 'completed'] as const).map(f => (
          <div key={f} className={`tab ${filter === f ? 'active' : ''}`} onClick={() => setFilter(f)}>
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </div>
        ))}
      </div>

      {showCreate && (
        <div className="card" style={{ borderColor: 'var(--border-bright)' }}>
          <div className="card-title" style={{ marginBottom: 16 }}>New Meeting</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>Title *</div>
              <input style={{ width: '100%', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border)', borderRadius: 8, padding: '8px 10px', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font)' }}
                placeholder="Meeting title" value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
            </div>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>Purpose</div>
              <input style={{ width: '100%', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border)', borderRadius: 8, padding: '8px 10px', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font)' }}
                placeholder="Goal of the meeting" value={form.purpose} onChange={e => setForm(f => ({ ...f, purpose: e.target.value }))} />
            </div>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>Start Time</div>
              <input type="datetime-local" style={{ width: '100%', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border)', borderRadius: 8, padding: '8px 10px', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font)', colorScheme: 'dark' }}
                value={form.start_time} onChange={e => setForm(f => ({ ...f, start_time: e.target.value }))} />
            </div>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>End Time</div>
              <input type="datetime-local" style={{ width: '100%', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border)', borderRadius: 8, padding: '8px 10px', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font)', colorScheme: 'dark' }}
                value={form.end_time} onChange={e => setForm(f => ({ ...f, end_time: e.target.value }))} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-primary" onClick={handleCreate}>Create Meeting</button>
            <button className="btn btn-ghost" onClick={() => setShowCreate(false)}>Cancel</button>
          </div>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {loading ? (
          <div className="empty-state"><div className="empty-icon" style={{ animation: 'spin 1s linear infinite' }}>⟳</div>Loading…</div>
        ) : display.map(m => (
          <div key={m.id} className="meeting-item" style={{ padding: '16px 18px' }} onClick={() => dispatch({ type: 'SET_PAGE', page: 'briefing', meetingId: m.id })}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                <div style={{ fontSize: 14, fontWeight: 700, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{m.title}</div>
                <span className={`badge ${priorityClass(m.effective_importance)}`}>{priorityLabel(m.effective_importance)}</span>
                {m.has_transcript && <span className="badge badge-pending">📝 Transcript</span>}
                {m.calendar_source && <span className="badge" style={{ background: 'rgba(99,102,241,0.1)', color: 'var(--indigo)', border: '1px solid rgba(99,102,241,0.2)' }}>📅 {m.calendar_source}</span>}
              </div>
              {m.purpose && <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>{m.purpose}</div>}
              <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                {formatDT(m.start_time)}{m.end_time ? ` → ${formatDT(m.end_time)}` : ''}
              </div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end' }}>
              <span className={`badge ${m.status === 'completed' ? 'badge-healthy' : m.status === 'upcoming' ? 'badge-pending' : 'badge-medium'}`}>
                {m.status}
              </span>
              <button className="btn btn-ghost btn-sm" onClick={e => { e.stopPropagation(); dispatch({ type: 'SET_PAGE', page: 'briefing', meetingId: m.id }); }}>
                View Briefing →
              </button>
            </div>
          </div>
        ))}
        {!loading && display.length === 0 && (
          <div className="empty-state"><div className="empty-icon">📅</div>No {filter} meetings found.<br /><button className="btn btn-primary" style={{ marginTop: 12 }} onClick={() => setShowCreate(true)}>Create your first meeting</button></div>
        )}
      </div>
    </div>
  );
}
