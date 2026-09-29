import { useEffect, useState } from 'react';
import { remindersApi } from '../api';
import type { Reminder } from '../api';
import { useToast, useApp } from '../store';

const DEMO: Reminder[] = [
  {
    id: 'c1',
    description: 'Prepare quarterly security audit report for David Miller',
    responsible_person: 'You',
    due_date: new Date(Date.now() + 345_600_000).toISOString(),
    status: 'pending',
    is_confirmed: false,
    epistemic_class: 'model_inference',
    commitment_type: 'reminder',
    created_at: '',
  },
  {
    id: 'c2',
    description: 'Follow up on API integration status with backend engineering team',
    responsible_person: 'You',
    due_date: new Date(Date.now() + 172_800_000).toISOString(),
    status: 'pending',
    is_confirmed: false,
    epistemic_class: 'direct_fact',
    commitment_type: 'reminder',
    created_at: '',
  },
  {
    id: 'c3',
    description: 'Share updated roadmap slides before EOD Thursday',
    responsible_person: 'Sarah Chen (Legal)',
    due_date: new Date(Date.now() + 86_400_000).toISOString(),
    status: 'pending',
    is_confirmed: false,
    epistemic_class: 'model_inference',
    commitment_type: 'deliverable',
    created_at: '',
  },
  {
    id: 'c4',
    description: 'Schedule follow-up call on cross-team deployment rollback rules',
    responsible_person: 'You',
    due_date: new Date(Date.now() + 518_400_000).toISOString(),
    status: 'in_progress',
    is_confirmed: true,
    epistemic_class: 'direct_fact',
    commitment_type: 'reminder',
    created_at: '',
  },
  {
    id: 'c5',
    description: 'Send SOC2 compliance evidence package to David Miller',
    responsible_person: 'Priya Nair',
    due_date: new Date(Date.now() - 43_200_000).toISOString(),
    status: 'missed',
    is_confirmed: true,
    epistemic_class: 'direct_fact',
    commitment_type: 'deliverable',
    created_at: '',
  },
];

function fmt(iso?: string) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleDateString([], { month: 'short', day: 'numeric' });
  } catch {
    return iso;
  }
}

function isOverdue(iso?: string) {
  return iso ? new Date(iso).getTime() < Date.now() : false;
}

export default function CommitmentsPage() {
  const { dispatch } = useApp();
  const toast = useToast();
  const [items, setItems] = useState<Reminder[]>([]);
  const [filter, setFilter] = useState<'unconfirmed' | 'overdue' | 'all' | 'completed'>('unconfirmed');
  const [loading, setLoading] = useState(false);

  const loadData = () => {
    setLoading(true);
    remindersApi.list()
      .then(c => setItems(c ?? []))
      .catch(() => setItems(DEMO))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleConfirm = async (id: string) => {
    try {
      await remindersApi.confirm(id);
      setItems(prev => prev.map(c => c.id === id ? { ...c, is_confirmed: true, status: 'in_progress' } : c));
      toast('Reminder confirmed into active operational backlog', 'success', '✓');
    } catch (e: any) {
      toast(e.message ?? 'Failed to confirm reminder', 'error', '✗');
    }
  };

  const handleMarkCompleted = async (id: string) => {
    try {
      await remindersApi.update(id, { status: 'completed' } as any);
      setItems(prev => prev.map(c => c.id === id ? { ...c, status: 'completed' } : c));
      toast('Reminder marked completed', 'success', '✓');
    } catch (e: any) {
      toast(e.message ?? 'Failed to update', 'error', '✗');
    }
  };

  const handleDismiss = async (id: string) => {
    try {
      await remindersApi.update(id, { status: 'cancelled' } as any);
      setItems(prev => prev.filter(c => c.id !== id));
      toast('Reminder dismissed', 'info', '—');
    } catch (e: any) {
      toast(e.message ?? 'Failed', 'error', '✗');
    }
  };

  const displayPool = items.length > 0 ? items : DEMO;

  const unconfirmedItems = displayPool.filter(c => !c.is_confirmed);
  const overdueItems = displayPool.filter(c => isOverdue(c.due_date) && c.status !== 'completed');
  const completedItems = displayPool.filter(c => c.status === 'completed');

  const filteredItems = displayPool.filter(c => {
    if (filter === 'unconfirmed') return !c.is_confirmed;
    if (filter === 'overdue') return isOverdue(c.due_date) && c.status !== 'completed';
    if (filter === 'completed') return c.status === 'completed';
    return true;
  });

  return (
    <div className="page-body">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-0.02em', color: '#fff' }}>
            Reminders & Commitments Ledger
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>
            Track commitments made during meetings, verify inter-meeting task execution, and confirm AI-extracted deliverables.
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            className="btn btn-ghost btn-sm"
            onClick={loadData}
            disabled={loading}
          >
            {loading ? '⟳ Loading…' : '↺ Refresh'}
          </button>
          <button
            className="btn btn-primary btn-sm"
            onClick={() => dispatch({ type: 'SET_PAGE', page: 'briefing' })}
          >
            📋 Sync Inter-Meeting Tasks →
          </button>
        </div>
      </div>

      {/* ── Operational Status Metrics ── */}
      <div className="stats-grid">
        <div className="stat-card" onClick={() => setFilter('unconfirmed')}>
          <div className="stat-label">Needs Confirmation</div>
          <div className="stat-value" style={{ color: unconfirmedItems.length > 0 ? 'var(--amber)' : '#fff' }}>
            {unconfirmedItems.length}
          </div>
          <div className="stat-sub">AI-proposed commitments</div>
        </div>

        <div className="stat-card" onClick={() => setFilter('overdue')}>
          <div className="stat-label">Overdue Commitments</div>
          <div className="stat-value" style={{ color: overdueItems.length > 0 ? 'var(--rose)' : 'var(--emerald)' }}>
            {overdueItems.length}
          </div>
          <div className="stat-sub">Past stated due date</div>
        </div>

        <div className="stat-card" onClick={() => setFilter('all')}>
          <div className="stat-label">Active Backlog</div>
          <div className="stat-value" style={{ color: 'var(--indigo)' }}>
            {displayPool.filter(c => c.status !== 'completed').length}
          </div>
          <div className="stat-sub">Across all meetings & projects</div>
        </div>

        <div className="stat-card" onClick={() => setFilter('completed')}>
          <div className="stat-label">Completed & Verified</div>
          <div className="stat-value" style={{ color: 'var(--emerald)' }}>
            {completedItems.length}
          </div>
          <div className="stat-sub">Fulfilled with proof</div>
        </div>
      </div>

      {/* ── Strict Human-in-the-Loop Invariant Notice ── */}
      <div style={{ padding: '10px 14px', background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.2)', borderRadius: 8, fontSize: 11.5, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ color: 'var(--indigo)', fontSize: 14 }}>✦</span>
        <span>
          <strong style={{ color: '#fff' }}>Human-in-the-Loop Invariant:</strong> Proposed reminders are inferred from conversation transcripts. They remain inactive until you click <strong>✓ Confirm</strong>.
        </span>
      </div>

      {/* ── Filter Tabs ── */}
      <div className="tabs">
        {[
          { key: 'unconfirmed', label: `⚠ Needs Review (${unconfirmedItems.length})` },
          { key: 'overdue', label: `🚨 Overdue (${overdueItems.length})` },
          { key: 'all', label: `All Active (${displayPool.length})` },
          { key: 'completed', label: `✓ Completed (${completedItems.length})` },
        ].map(t => (
          <div
            key={t.key}
            className={`tab ${filter === t.key ? 'active' : ''}`}
            onClick={() => setFilter(t.key as any)}
          >
            {t.label}
          </div>
        ))}
      </div>

      {/* ── Reminders List ── */}
      <div className="card">
        <div className="commitment-list">
          {filteredItems.map(c => {
            const overdue = isOverdue(c.due_date) && c.status !== 'completed';
            const isDone = c.status === 'completed';

            return (
              <div
                key={c.id}
                className="commitment-item"
                style={{
                  borderLeft: `3px solid ${overdue ? 'var(--rose)' : isDone ? 'var(--emerald)' : c.is_confirmed ? 'var(--indigo)' : 'var(--amber)'}`,
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                  <div style={{ flex: 1 }}>
                    <div className="commitment-desc">{c.description}</div>
                    <div className="commitment-meta">
                      <span className={`badge ${c.epistemic_class === 'direct_fact' ? 'badge-direct' : 'badge-inferred'}`}>
                        {c.epistemic_class === 'direct_fact' ? '◆ Verified Fact' : '◇ AI Inference'}
                      </span>

                      <span style={{ color: 'var(--text-secondary)' }}>
                        Assignee: <strong>{c.responsible_person || 'You'}</strong>
                      </span>

                      {c.due_date && (
                        <span className={`badge ${overdue ? 'badge-overdue' : 'badge-ready'}`}>
                          {overdue ? `🚨 Overdue: ${fmt(c.due_date)}` : `Due: ${fmt(c.due_date)}`}
                        </span>
                      )}

                      <span className={`badge ${c.is_confirmed ? 'badge-completed' : 'badge-inferred'}`}>
                        {c.is_confirmed ? 'Confirmed' : 'Needs Review'}
                      </span>
                    </div>

                    {c.source_excerpt && (
                      <div style={{ marginTop: 6, padding: '6px 10px', background: 'rgba(255,255,255,0.03)', borderLeft: '2px solid var(--border)', fontSize: 11, color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                        "{c.source_excerpt}"
                      </div>
                    )}
                  </div>

                  <div className="commitment-actions">
                    {!c.is_confirmed ? (
                      <>
                        <button
                          className="btn btn-success btn-sm"
                          onClick={() => handleConfirm(c.id)}
                          title="Confirm this commitment into your active backlog"
                        >
                          ✓ Confirm
                        </button>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => handleDismiss(c.id)}
                          title="Dismiss this suggested item"
                        >
                          ✕ Dismiss
                        </button>
                      </>
                    ) : !isDone ? (
                      <>
                        <button
                          className="btn btn-success btn-sm"
                          onClick={() => handleMarkCompleted(c.id)}
                          title="Mark this deliverable as completed"
                        >
                          ✓ Mark Done
                        </button>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={() => handleDismiss(c.id)}
                          title="Cancel commitment"
                        >
                          Cancel
                        </button>
                      </>
                    ) : (
                      <span style={{ fontSize: 11, color: 'var(--emerald)', fontWeight: 600 }}>
                        ✓ Completed
                      </span>
                    )}
                  </div>
                </div>
              </div>
            );
          })}

          {filteredItems.length === 0 && (
            <div className="empty-state">
              <div className="empty-icon">✓</div>
              <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>No reminders in this filter</div>
              <div style={{ color: 'var(--text-muted)' }}>All caught up! No items pending action.</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
