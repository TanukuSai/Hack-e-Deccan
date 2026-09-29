// Projects page with progress tracking
import { useEffect, useState } from 'react';
import { projectsApi } from '../api';
import type { Project, ProjectProgress } from '../api';
import { useToast } from '../store';

const DEMO_PROJECTS: Project[] = [
  { id: 'p1', name: 'Cloudflare Zero Trust Rollout', description: 'Full mTLS and Zero Trust deployment across all services', status: 'active', created_at: '' },
  { id: 'p2', name: 'Series B Fundraise', description: 'Sequoia-led Series B targeting $40M', status: 'active', created_at: '' },
  { id: 'p3', name: 'SOC2 Type II Compliance', description: 'Annual compliance audit preparation', status: 'active', created_at: '' },
];
const DEMO_PROGRESS: Record<string, ProjectProgress> = {
  p1: { project_id: 'p1', name: 'Cloudflare Zero Trust Rollout', total_commitments: 12, completed_commitments: 8, pending_commitments: 3, missed_commitments: 1, blockers: [{ description: 'mTLS cert rotation blocked by legacy service', severity: 'high' }], completion_pct: 67 },
  p2: { project_id: 'p2', name: 'Series B Fundraise', total_commitments: 7, completed_commitments: 3, pending_commitments: 4, missed_commitments: 0, blockers: [], completion_pct: 43 },
  p3: { project_id: 'p3', name: 'SOC2 Type II Compliance', total_commitments: 18, completed_commitments: 15, pending_commitments: 2, missed_commitments: 1, blockers: [], completion_pct: 83 },
};

const STATUS_COLOR: Record<string, string> = { active: 'badge-pending', completed: 'badge-healthy', on_hold: 'badge-medium', cancelled: 'badge-error' };

export default function ProjectsPage() {
  const toast = useToast();
  const [projects, setProjects] = useState<Project[]>([]);
  const [progress, setProgress] = useState<Record<string, ProjectProgress>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: '', description: '', status: 'active' });

  useEffect(() => {
    projectsApi.list()
      .then(async ps => {
        const projs = ps ?? [];
        setProjects(projs.length > 0 ? projs : DEMO_PROJECTS);
        const prog: Record<string, ProjectProgress> = {};
        await Promise.allSettled((projs.length > 0 ? projs : DEMO_PROJECTS).map(async p => {
          try {
            prog[p.id] = await projectsApi.progress(p.id);
          } catch {
            prog[p.id] = DEMO_PROGRESS[p.id] ?? { project_id: p.id, name: p.name, total_commitments: 0, completed_commitments: 0, pending_commitments: 0, missed_commitments: 0, blockers: [], completion_pct: 0 };
          }
        }));
        setProgress(prog);
      })
      .catch(() => { setProjects(DEMO_PROJECTS); setProgress(DEMO_PROGRESS); });
  }, []);

  const handleCreate = async () => {
    if (!form.name) return;
    try {
      const p = await projectsApi.create(form);
      setProjects(prev => [p, ...prev]);
      setShowCreate(false);
      setForm({ name: '', description: '', status: 'active' });
      toast('Project created', 'success', '✓');
    } catch (e: any) { toast(e.message, 'error'); }
  };

  const display = projects.length > 0 ? projects : DEMO_PROJECTS;

  return (
    <div className="page-body fade-in">
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: -8 }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 20, fontWeight: 800 }}>Projects</div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{display.length} active projects</div>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>＋ New Project</button>
      </div>

      {showCreate && (
        <div className="card" style={{ borderColor: 'var(--border-bright)' }}>
          <div className="card-title" style={{ marginBottom: 16 }}>New Project</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 12 }}>
            <input style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border)', borderRadius: 8, padding: '8px 10px', color: 'var(--text-primary)', fontSize: 13, fontFamily: 'var(--font)' }}
              placeholder="Project name *" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
            <textarea style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border)', borderRadius: 8, padding: '8px 10px', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font)', resize: 'none', height: 60 }}
              placeholder="Description (optional)" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-primary" onClick={handleCreate}>Create</button>
            <button className="btn btn-ghost" onClick={() => setShowCreate(false)}>Cancel</button>
          </div>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {display.map(p => {
          const prog = progress[p.id];
          const pct = prog?.completion_pct ?? 0;
          const isSelected = selected === p.id;
          return (
            <div key={p.id} className="card" style={{ borderColor: isSelected ? 'var(--border-bright)' : undefined }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, cursor: 'pointer' }} onClick={() => setSelected(isSelected ? null : p.id)}>
                <div style={{ width: 40, height: 40, borderRadius: 10, background: 'var(--gradient-main)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, flexShrink: 0 }}>◫</div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <div style={{ fontSize: 14, fontWeight: 700 }}>{p.name}</div>
                    <span className={`badge ${STATUS_COLOR[p.status] ?? 'badge-pending'}`}>{p.status}</span>
                  </div>
                  {p.description && <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 8 }}>{p.description}</div>}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div className="progress-bar-wrap" style={{ flex: 1 }}>
                      <div className={`progress-bar-fill ${pct >= 80 ? 'fill-emerald' : pct >= 40 ? 'fill-indigo' : 'fill-amber'}`} style={{ width: `${pct}%` }} />
                    </div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-secondary)', width: 36, textAlign: 'right' }}>{pct}%</div>
                  </div>
                </div>
                <div style={{ fontSize: 18, color: 'var(--text-muted)', transition: 'transform 0.2s', transform: isSelected ? 'rotate(90deg)' : '' }}>›</div>
              </div>

              {isSelected && prog && (
                <div className="fade-in" style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 14 }}>
                    {[
                      ['Total', prog.total_commitments, 'var(--text-secondary)'],
                      ['Done', prog.completed_commitments, 'var(--emerald)'],
                      ['Pending', prog.pending_commitments, 'var(--amber)'],
                      ['Missed', prog.missed_commitments, 'var(--rose)'],
                    ].map(([label, val, color]) => (
                      <div key={label as string} style={{ textAlign: 'center', padding: '10px', background: 'rgba(255,255,255,0.03)', borderRadius: 8 }}>
                        <div style={{ fontSize: 22, fontWeight: 800, color: color as string }}>{val as number}</div>
                        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2 }}>{label as string}</div>
                      </div>
                    ))}
                  </div>

                  {prog.blockers && prog.blockers.length > 0 && (
                    <div style={{ padding: '10px 14px', background: 'rgba(244,63,94,0.07)', border: '1px solid rgba(244,63,94,0.2)', borderRadius: 8 }}>
                      <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--rose)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 }}>Blockers</div>
                      {prog.blockers.map((b: any, i: number) => (
                        <div key={i} style={{ fontSize: 12, color: 'var(--text-secondary)', display: 'flex', gap: 8, paddingBottom: 4 }}>
                          <span style={{ color: 'var(--rose)' }}>⚠</span> {b.description}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
