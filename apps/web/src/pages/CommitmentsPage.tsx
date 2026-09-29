// Commitments page — human confirmation of AI-proposed action items
import { useEffect, useState } from 'react';
import { commitmentsApi } from '../api';
import type { Commitment } from '../api';
import { useToast } from '../store';

const DEMO: Commitment[] = [
  { id: 'c1', description: 'Prepare quarterly security audit report for David Miller', responsible_person: 'You', due_date: new Date(Date.now() + 432_000_000).toISOString(), status: 'pending', is_confirmed: false, epistemic_class: 'model_inference', commitment_type: 'action_item', created_at: '' },
  { id: 'c2', description: 'Follow up on API integration status with engineering team', responsible_person: 'You', due_date: new Date(Date.now() + 259_200_000).toISOString(), status: 'pending', is_confirmed: false, epistemic_class: 'direct_fact', commitment_type: 'action_item', created_at: '' },
  { id: 'c3', description: 'Share updated roadmap slides before EOD Thursday', responsible_person: 'Sarah Chen', due_date: new Date(Date.now() + 172_800_000).toISOString(), status: 'pending', is_confirmed: false, epistemic_class: 'model_inference', commitment_type: 'deliverable', created_at: '' },
  { id: 'c4', description: 'Schedule follow-up call with Sequoia on Series B timeline', responsible_person: 'You', due_date: new Date(Date.now() + 604_800_000).toISOString(), status: 'in_progress', is_confirmed: true, epistemic_class: 'direct_fact', commitment_type: 'action_item', created_at: '' },
  { id: 'c5', description: 'Send SOC2 evidence package to compliance team', responsible_person: 'Raj Mehta', due_date: new Date(Date.now() - 86_400_000).toISOString(), status: 'missed', is_confirmed: true, epistemic_class: 'direct_fact', commitment_type: 'deliverable', created_at: '' },
];

function fmt(iso: string) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString([], { month: 'short', day: 'numeric' });
}
function isOverdue(iso?: string) {
  return iso ? new Date(iso).getTime() < Date.now() : false;
}

const STATUS_BADGE: Record<string, string> = {
  pending: 'badge-pending', in_progress: 'badge-medium', completed: 'badge-healthy',
  missed: 'badge-error', cancelled: 'badge-error', proposed: 'badge-proposed',
};

export default function CommitmentsPage() {
  const toast = useToast();
  const [items, setItems] = useState<Commitment[]>([]);
  const [filter, setFilter] = useState<'unconfirmed' | 'all' | 'completed'>('unconfirmed');

  useEffect(() => {
    const params: Record<string, any> = {};
    if (filter === 'unconfirmed') params.is_confirmed = false;
    if (filter === 'completed') params.status = 'completed';
    commitmentsApi.list(params)
      .then(c => setItems(c ?? []))
      .catch(() => setItems(DEMO.filter(c =>
        filter === 'all' ? true :
        filter === 'unconfirmed' ? !c.is_confirmed :
        c.status === 'completed'
      )));
  }, [filter]);

  const handleConfirm = async (id: string) => {
    try {
      await commitmentsApi.confirm(id);
      setItems(prev => prev.map(c => c.id === id ? { ...c, is_confirmed: true, status: 'in_progress' } : c));
      toast('Commitment confirmed', 'success', '✓');
    } catch (e: any) { toast(e.message ?? 'Failed', 'error'); }
  };

  const handleStatus = async (id: string, status: string) => {
    try {
      await commitmentsApi.update(id, { status } as any);
      setItems(prev => prev.map(c => c.id === id ? { ...c, status } : c));
      toast(`Marked as ${status}`, 'info');
    } catch (e: any) { toast(e.message ?? 'Failed', 'error'); }
  };

  const display = (items.length > 0 ? items : DEMO).filter(c =>
    filter === 'all' ? true :
    filter === 'unconfirmed' ? !c.is_confirmed :
    c.status === 'completed'
  );

  const unconfirmedCount = (items.length > 0 ? items : DEMO).filter(c => !c.is_confirmed).length;

  return (
    <div className="page-body fade-in">
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: -8 }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 20, fontWeight: 800 }}>Commitments</div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
            {unconfirmedCount > 0
              ? <><span style={{ color: 'var(--amber)' }}>⚠ {unconfirmedCount} unconfirmed</span> — AI-proposed, require your review</>
              : 'All commitments confirmed ✓'}
          </div>
        </div>
      </div>

      {/* Invariant banner */}
      <div style={{ padding: '10px 14px', background: 'rgba(139,92,246,0.08)', border: '1px solid rgba(139,92,246,0.2)', borderRadius: 8, fontSize: 11, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ color: 'var(--violet)', fontSize: 14 }}>◈</span>
        <span><strong style={{ color: 'var(--violet)' }}>Design invariant:</strong> All AI-inferred commitments require explicit human confirmation before becoming active. Proposed = AI suggested. Confirmed = you approved.</span>
      </div>

      <div className="tabs">
        {(['unconfirmed', 'all', 'completed'] as const).map(f => (
          <div key={f} className={`tab ${filter === f ? 'active' : ''}`} onClick={() => setFilter(f)}>
            {f === 'unconfirmed' ? `⚠ Needs Review (${unconfirmedCount})` : f === 'all' ? 'All' : '✓ Completed'}
          </div>
        ))}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {display.map(c => (
          <div key={c.id} className={`commitment-item ${c.is_confirmed ? 'confirmed' : ''} ${c.status === 'missed' ? 'missed' : ''}`} style={{ padding: '14px 16px' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6, lineHeight: 1.4 }}>{c.description}</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
                  <span className={`badge ${STATUS_BADGE[c.status] ?? 'badge-pending'}`}>{c.status}</span>
                  {!c.is_confirmed
                    ? <span className="badge badge-proposed">◇ Proposed</span>
                    : <span className="badge badge-healthy">◆ Confirmed</span>}
                  <span className="evidence-chip" title={c.epistemic_class}>
                    {c.epistemic_class === 'direct_fact' ? '◆ Direct fact' : '◇ Inferred'}
                  </span>
                  {c.commitment_type && <span style={{ fontSize: 10, color: 'var(--text-muted)', alignSelf: 'center' }}>{c.commitment_type}</span>}
                </div>
                <div style={{ display: 'flex', gap: 16, fontSize: 11, color: 'var(--text-muted)' }}>
                  {c.responsible_person && <span>👤 {c.responsible_person}</span>}
                  {c.due_date && (
                    <span style={{ color: isOverdue(c.due_date) && c.status !== 'completed' ? 'var(--rose)' : undefined }}>
                      📅 Due {fmt(c.due_date)}{isOverdue(c.due_date) && c.status !== 'completed' ? ' (overdue)' : ''}
                    </span>
                  )}
                </div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, flexShrink: 0 }}>
                {!c.is_confirmed && (
                  <button className="btn btn-success btn-sm" onClick={() => handleConfirm(c.id)}>✓ Confirm</button>
                )}
                {c.is_confirmed && c.status === 'in_progress' && (
                  <button className="btn btn-success btn-sm" onClick={() => handleStatus(c.id, 'completed')}>Mark Done</button>
                )}
                {c.status !== 'cancelled' && c.status !== 'completed' && (
                  <button className="btn btn-ghost btn-sm" onClick={() => handleStatus(c.id, 'cancelled')}>✕ Cancel</button>
                )}
              </div>
            </div>
          </div>
        ))}
        {display.length === 0 && (
          <div className="empty-state"><div className="empty-icon">✓</div>No commitments in this view</div>
        )}
      </div>
    </div>
  );
}
