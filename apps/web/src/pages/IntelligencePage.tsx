// Intelligence page — OpenClaw recon + Hindsight memory overview
import { useState } from 'react';
import { useToast } from '../store';

const DEMO_RECON = {
  source: 'openclaw_recon',
  epistemic_class: 'unverified_assumption',
  verified: false,
  meeting_title: 'Enterprise Cloud Security Review',
  company_intelligence: {
    domain: 'cloudflare.com',
    company_name: 'Cloudflare',
    industry: 'Cybersecurity / CDN',
    employee_count: '4,000+',
    headquarters: 'San Francisco, CA',
    description: 'Cloud connectivity company focused on security, performance, and reliability for internet properties.',
    funding_stage: 'Public (NET)',
    key_products: ['Zero Trust Gateway', 'Workers', 'R2 Storage', 'Magic WAN'],
    recent_news: ['Cloudflare expands AI Gateway to 50+ regions', 'Zero Trust Platform adds ML-based threat scoring'],
  },
  attendee_recon: [
    { name: 'David Miller', title: 'VP of Engineering', linkedin_url: null, email_domain: 'cloudflare.com', recent_activity: ['Spoke at CloudNative Con 2026', 'Published blog on zero-trust architecture'] },
  ],
};

export default function IntelligencePage() {
  const toast = useToast();
  const [recon, setRecon] = useState<typeof DEMO_RECON | null>(null);
  const [domains, setDomains] = useState('cloudflare.com');
  const [attendees, setAttendees] = useState('David Miller');
  const [meetingTitle, setMeetingTitle] = useState('Enterprise Cloud Security Review');
  const [running, setRunning] = useState(false);
  const [confirmed, setConfirmed] = useState<Set<string>>(new Set());

  const handleRunRecon = async () => {
    setRunning(true);
    // Simulate API call to OpenClaw adapter
    await new Promise(r => setTimeout(r, 1400));
    setRecon(DEMO_RECON);
    setRunning(false);
    toast('Reconnaissance complete — review and confirm before use', 'info', '◈');
  };

  const handleConfirmField = (key: string) => {
    setConfirmed(prev => new Set([...prev, key]));
    toast(`Field confirmed as verified`, 'success', '◆');
  };

  return (
    <div className="page-body fade-in">
      <div style={{ marginBottom: -8 }}>
        <div style={{ fontSize: 20, fontWeight: 800 }}>Intelligence</div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>OpenClaw reconnaissance · Hindsight memory · Research provenance</div>
      </div>

      {/* Epistemic invariant */}
      <div style={{ padding: '12px 16px', background: 'rgba(139,92,246,0.08)', border: '1px solid rgba(139,92,246,0.2)', borderRadius: 10, display: 'flex', gap: 10 }}>
        <span style={{ fontSize: 20 }}>◈</span>
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--violet)', marginBottom: 4 }}>Epistemic Boundary Enforced</div>
          <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            All research gathered here is classified as <span className="badge badge-proposed" style={{ verticalAlign: 'middle' }}>unverified_assumption</span> until you explicitly confirm it. 
            Confirmed fields are marked <span className="evidence-chip" style={{ verticalAlign: 'middle' }}>◆ direct_fact</span> and used in briefings. 
            Unconfirmed data is never auto-promoted.
          </div>
        </div>
      </div>

      <div className="two-col">
        {/* Recon trigger */}
        <div className="card">
          <div className="card-title" style={{ marginBottom: 14 }}>◈ OpenClaw Reconnaissance</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 14 }}>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>Meeting Title</div>
              <input style={{ width: '100%', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border)', borderRadius: 8, padding: '8px 10px', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font)' }}
                value={meetingTitle} onChange={e => setMeetingTitle(e.target.value)} />
            </div>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>Attendee Names (comma-separated)</div>
              <input style={{ width: '100%', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border)', borderRadius: 8, padding: '8px 10px', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font)' }}
                value={attendees} onChange={e => setAttendees(e.target.value)} placeholder="John Smith, Jane Doe" />
            </div>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>Company Domains</div>
              <input style={{ width: '100%', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border)', borderRadius: 8, padding: '8px 10px', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font)' }}
                value={domains} onChange={e => setDomains(e.target.value)} placeholder="company.com" />
            </div>
          </div>
          <button className={`btn btn-primary ${running ? 'pulse' : ''}`} onClick={handleRunRecon} disabled={running} style={{ width: '100%', justifyContent: 'center' }}>
            {running ? '◈ Running reconnaissance…' : '◈ Run OpenClaw Recon'}
          </button>
        </div>

        {/* Hindsight Memory */}
        <div className="card">
          <div className="card-title" style={{ marginBottom: 14 }}>◉ Hindsight Memory</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[
              { claim: 'David Miller prefers async follow-ups over email chains', source: 'meeting_notes', date: '2026-08-15', verified: true },
              { claim: 'Cloudflare team uses internal review process taking 2 weeks for new integrations', source: 'briefing_v3', date: '2026-07-22', verified: true },
              { claim: 'Previous engagement stalled due to procurement process delays', source: 'transcript', date: '2026-06-10', verified: false },
            ].map((item, i) => (
              <div key={i} style={{ padding: '10px 12px', background: 'rgba(6,182,212,0.06)', border: '1px solid rgba(6,182,212,0.15)', borderRadius: 8 }}>
                <div style={{ fontSize: 12, marginBottom: 6, lineHeight: 1.5 }}>{item.claim}</div>
                <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                  <span className={`evidence-chip`}>{item.verified ? '◆ Verified' : '◇ Unverified'}</span>
                  <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{item.source} · {item.date}</span>
                </div>
              </div>
            ))}
            <button className="btn btn-ghost btn-sm" style={{ marginTop: 4 }} onClick={() => toast('Full Hindsight query requires API connection', 'info', '◉')}>
              Query Hindsight Memory →
            </button>
          </div>
        </div>
      </div>

      {/* Recon results */}
      {recon && (
        <div className="card fade-in" style={{ borderColor: 'rgba(139,92,246,0.25)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
            <div className="card-title">Reconnaissance Results</div>
            <span className="badge badge-proposed">unverified_assumption</span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 'auto' }}>Review and confirm before use in briefings</span>
          </div>

          <div className="two-col" style={{ gap: 14 }}>
            {/* Company */}
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--violet)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 10 }}>Company Intelligence</div>
              {Object.entries(recon.company_intelligence).filter(([k]) => !['key_products', 'recent_news'].includes(k)).map(([key, val]) => {
                const fkey = `company_${key}`;
                const isConf = confirmed.has(fkey);
                return (
                  <div key={key} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '7px 0', borderBottom: '1px solid var(--border)' }}>
                    <div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'capitalize' }}>{key.replace(/_/g, ' ')}</div>
                      <div style={{ fontSize: 12, fontWeight: 500 }}>{String(val)}</div>
                    </div>
                    {isConf
                      ? <span className="evidence-chip">◆ Confirmed</span>
                      : <button className="btn btn-ghost btn-sm" style={{ fontSize: 10 }} onClick={() => handleConfirmField(fkey)}>Confirm</button>}
                  </div>
                );
              })}
              <div style={{ marginTop: 10 }}>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 6 }}>Key Products</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {recon.company_intelligence.key_products.map((p: string) => (
                    <span key={p} style={{ fontSize: 10, padding: '2px 8px', background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.2)', borderRadius: 99, color: 'var(--indigo)' }}>{p}</span>
                  ))}
                </div>
              </div>
            </div>

            {/* Attendees */}
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--violet)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 10 }}>Attendee Intelligence</div>
              {recon.attendee_recon.map((a: any, i: number) => (
                <div key={i} style={{ padding: '10px 12px', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)', borderRadius: 8, marginBottom: 8 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, marginBottom: 2 }}>{a.name}</div>
                  {a.title && <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6 }}>{a.title}</div>}
                  {a.recent_activity.length > 0 && (
                    <div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>Recent Activity</div>
                      {a.recent_activity.map((act: string, j: number) => (
                        <div key={j} style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'flex', gap: 6, marginBottom: 2 }}>
                          <span style={{ color: 'var(--violet)' }}>›</span> {act}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              <div style={{ marginTop: 10 }}>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>Recent News</div>
                {recon.company_intelligence.recent_news.map((n: string, i: number) => (
                  <div key={i} style={{ fontSize: 11, color: 'var(--text-secondary)', padding: '5px 0', borderBottom: '1px solid var(--border)', display: 'flex', gap: 6 }}>
                    <span style={{ color: 'var(--amber)' }}>◆</span> {n}
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
            <button className="btn btn-success" onClick={() => { setConfirmed(new Set(['company_domain', 'company_company_name', 'company_industry'])); toast('Core company data confirmed', 'success', '◆'); }}>
              ◆ Confirm Key Fields
            </button>
            <button className="btn btn-ghost" onClick={() => { setRecon(null); toast('Recon data discarded', 'info'); }}>
              Discard
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
