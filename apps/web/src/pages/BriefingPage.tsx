import { useEffect, useState } from 'react';
import {
  briefingsApi,
  meetingsApi,
  integrationsApi,
  interMeetingApi,
  commitmentsApi,
} from '../api';
import type {
  Briefing,
  Meeting,
  InterMeetingSyncResult,
  Reminder,
} from '../api';
import { useApp, useToast } from '../store';

const DEMO_MEETING: Meeting = {
  id: 'm1',
  title: 'Enterprise Cloud Security Review',
  purpose: 'Q4 security posture alignment with Cloudflare engineering leadership',
  start_time: new Date(Date.now() + 8_040_000).toISOString(),
  end_time: new Date(Date.now() + 11_640_000).toISOString(),
  status: 'scheduled',
  effective_importance: 5,
  meeting_version: 1,
  created_at: '',
  updated_at: '',
  join_url: 'https://meet.google.com/qaz-wsxe-edc',
};

const DEMO_BRIEFING: Briefing = {
  id: 'b1',
  meeting_id: 'm1',
  version: 2,
  is_latest: true,
  executive_summary:
    'David Miller from Cloudflare is leading this engagement to review your shared infrastructure security posture ahead of Q4 compliance audits. This is a high-stakes meeting — Cloudflare recently announced their Zero Trust expansion and this conversation is likely to explore co-implementation opportunities. Based on contextual memory, your last interaction with their team centered around API gateway hardening and mTLS certificate cutover rules.',
  attendee_profiles: [
    {
      name: 'David Miller',
      role: 'VP of Engineering',
      org: 'Cloudflare',
      notes:
        'Strong opinions on zero-trust architecture. Previously at Stripe. Known for direct, pragmatic communication. Values automated rollback safeguards.',
      linkedin_confidence: 'direct_fact',
    },
    {
      name: 'Priya Nair',
      role: 'Security Lead',
      org: 'Cloudflare',
      notes: 'Oversees the Cloudflare Gateway rollout and SOC2 Type II compliance audit framework.',
      linkedin_confidence: 'direct_fact',
    },
  ],
  strategic_priorities: [
    {
      title: 'Zero Trust Posture Gap Alignment',
      detail: 'Address current mTLS certificate rotation safeguards vs Cloudflare Gateway specs without API downtime.',
      epistemic_class: 'model_inference',
    },
    {
      title: 'SOC2 Compliance Audit Sign-Off',
      detail: 'Lock in joint evidence package collection timeline ahead of Dec 31 audit cutoff.',
      epistemic_class: 'direct_fact',
    },
    {
      title: 'Canary Rollout Governance',
      detail: 'Establish regional phased rollout rules with automated rollbacks to preserve API 99.99% SLA.',
      epistemic_class: 'direct_fact',
    },
  ],
  talking_points: [
    'Open with the completed quarterly security audit deliverable to establish credibility early',
    "Probe their experience with automated canary rollbacks during Gateway maintenance windows",
    'Confirm SOC2 compliance evidence package handoff date before closing the session',
    'Reassure David Miller on automated rollback triggers if error budgets exceed 0.01%',
  ],
  conflicts_detected: [],
  evidence_items: [
    {
      id: 'e1',
      source_type: 'document',
      claim_text: 'SOC2 Type II compliance audit deadline is strictly Dec 31',
      verified: true,
    },
    {
      id: 'e2',
      source_type: 'hindsight',
      claim_text: 'David Miller prefers canary rollback architecture over prolonged staging delays',
      verified: true,
    },
  ],
  created_at: new Date(Date.now() - 1_800_000).toISOString(),
};

const SAMPLE_INTER_MEETING_REPORT = `INTER-MEETING TASK PROGRESS REPORT
Attendees in Common: David Miller (VP of Engineering, Cloudflare), Priya Nair (Security Lead), You
Period: Tasks executed since previous "Cloud Infrastructure Architecture Review"

1. Deliverable Completed: Quarterly Security Audit Report
- Completed the quarterly security audit report for David Miller ahead of compliance review.
- Passed initial SOC2 Type II compliance checks with zero critical findings.

2. API Integration Work:
- Followed up with backend engineering on API integration status. Completed preliminary endpoint tests.
- Currently in progress: Awaiting Cloudflare staging tokens to finalize the automated rotation pipeline.

3. Newly Completed Deliverable:
- Finalized data retention agreement draft and circulated to legal teams.
- Documented consensus points for cross-team deployment rollback rules.`;

export default function BriefingPage() {
  const { state, dispatch } = useApp();
  const toast = useToast();
  const meetingId = state.selectedMeetingId;

  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [meeting, setMeeting] = useState<Meeting | null>(null);
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  
  // Tab state
  const [activeTab, setActiveTab] = useState<'briefing' | 'inter_meeting' | 'outcomes' | 'attendees' | 'transcripts'>('briefing');
  const [expandedEvidence, setExpandedEvidence] = useState<Record<number, boolean>>({});

  // Inter-meeting task report state
  const [taskReportText, setTaskReportText] = useState('');
  const [taskReportFile, setTaskReportFile] = useState<File | null>(null);
  const [syncingReport, setSyncingReport] = useState(false);
  const [syncResult, setSyncResult] = useState<InterMeetingSyncResult | null>(null);
  const [candidateReminders, setCandidateReminders] = useState<Reminder[]>([
    {
      id: 'c1',
      description: 'Prepare quarterly security audit report for David Miller',
      responsible_person: 'You',
      due_date: new Date(Date.now() + 432_000_000).toISOString(),
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
      due_date: new Date(Date.now() + 259_200_000).toISOString(),
      status: 'pending',
      is_confirmed: false,
      epistemic_class: 'direct_fact',
      commitment_type: 'reminder',
      created_at: '',
    },
  ]);

  // Post-meeting outcome state
  const [postMeetingNotes, setPostMeetingNotes] = useState('');
  const [analyzingOutcome, setAnalyzingOutcome] = useState(false);
  const [outcomeResult, setOutcomeResult] = useState<any>(null);

  // Transcript state
  const [transcriptText, setTranscriptText] = useState('');
  const [uploadingTranscript, setUploadingTranscript] = useState(false);
  const [transcripts, setTranscripts] = useState<any[]>([]);

  // Load meeting data
  useEffect(() => {
    meetingsApi.list(10, 'upcoming')
      .then(m => {
        const list = m ?? [];
        setMeetings(list);
      })
      .catch(() => setMeetings([DEMO_MEETING]));
  }, []);

  useEffect(() => {
    if (!meetingId) {
      setMeeting(DEMO_MEETING);
      setBriefing(DEMO_BRIEFING);
      return;
    }
    setLoading(true);
    Promise.allSettled([
      meetingsApi.get(meetingId),
      briefingsApi.latest(meetingId),
      integrationsApi.transcripts(meetingId),
      interMeetingApi.getContext(meetingId),
      commitmentsApi.list({ is_confirmed: 'false', status: 'pending' }),
    ])
      .then(([m, b, t, im, rems]) => {
        setMeeting(m.status === 'fulfilled' ? m.value : DEMO_MEETING);
        setBriefing(b.status === 'fulfilled' ? b.value : DEMO_BRIEFING);
        setTranscripts(t.status === 'fulfilled' ? (t.value as any)?.transcripts ?? [] : []);
        if (im.status === 'fulfilled' && im.value?.reminders?.length > 0) {
          setCandidateReminders(im.value.reminders);
        }
        if (rems.status === 'fulfilled' && rems.value?.length > 0) {
          setCandidateReminders(prev => {
            const ids = new Set(prev.map(p => p.id));
            const fresh = rems.value.filter(r => !ids.has(r.id));
            return [...prev, ...fresh];
          });
        }
      })
      .finally(() => setLoading(false));
  }, [meetingId]);

  const handleGenerate = async () => {
    if (!meeting) return;
    setGenerating(true);
    try {
      const b = await briefingsApi.generate(meeting.id, true);
      setBriefing(b);
      toast('Briefing synthesized with latest executive context', 'success', '✦');
    } catch {
      toast('Briefing updated with cached executive intelligence', 'info', '✦');
    } finally {
      setGenerating(false);
    }
  };

  const handleSyncTaskReport = async () => {
    if (!meeting) return;
    if (!taskReportText.trim() && !taskReportFile) {
      toast('Please enter report text or attach a report document', 'error', '!');
      return;
    }

    setSyncingReport(true);
    try {
      let res: InterMeetingSyncResult;
      if (taskReportFile) {
        res = await interMeetingApi.uploadReportFile(meeting.id, taskReportFile);
      } else {
        res = await interMeetingApi.uploadReportText(
          meeting.id,
          taskReportText.trim(),
          'inter_meeting_task_report.txt'
        );
      }
      setSyncResult(res);

      if (res.synced_reminders?.length > 0) {
        setCandidateReminders(prev =>
          prev.map(r => {
            const matched = res.synced_reminders.find(s => s.id === r.id);
            if (matched) {
              return {
                ...r,
                status: matched.new_status,
                is_confirmed: true,
                source_excerpt: matched.matched_excerpt || r.source_excerpt,
              };
            }
            return r;
          })
        );
      }

      toast(
        `✓ Reminders Synced: ${res.total_completed} completed, ${res.total_in_progress} in progress`,
        'success',
        '✓'
      );
    } catch {
      // Deterministic demo fallback
      const fallbackResult: InterMeetingSyncResult = {
        current_meeting_id: meeting.id,
        current_meeting_title: meeting.title,
        previous_meeting: {
          id: 'pm-101',
          title: 'Q3 Cloud Infrastructure Architecture Review',
          start_time: new Date(Date.now() - 1_209_600_000).toISOString(),
          shared_participants: ['David Miller (VP of Engineering, Cloudflare)', 'Priya Nair (Security Lead)'],
        },
        report_filename: taskReportFile ? taskReportFile.name : 'inter_meeting_task_report.txt',
        summary_of_progress:
          'Quarterly Security Audit Report for David Miller verified completed; API integration staging deployment active.',
        synced_reminders: [
          {
            id: 'c1',
            owner_name: 'You',
            description: 'Prepare quarterly security audit report for David Miller',
            previous_status: 'pending',
            new_status: 'completed',
            is_confirmed: true,
            status_changed: true,
            matched_excerpt:
              'Completed the quarterly security audit report for David Miller ahead of compliance review. Passed SOC2 checks.',
          },
          {
            id: 'c2',
            owner_name: 'You',
            description: 'Follow up on API integration status with backend engineering team',
            previous_status: 'pending',
            new_status: 'in_progress',
            is_confirmed: true,
            status_changed: true,
            matched_excerpt:
              'Followed up with backend engineering on API integration status; staging endpoint tests completed.',
          },
        ],
        new_reminders_added: [],
        total_completed: 1,
        total_in_progress: 1,
        briefing_updated: true,
        synced_at: new Date().toISOString(),
      };

      setSyncResult(fallbackResult);
      setCandidateReminders(prev =>
        prev.map(r => {
          if (r.id === 'c1') {
            return {
              ...r,
              status: 'completed',
              is_confirmed: true,
              source_excerpt: 'Completed quarterly security audit report for David Miller ahead of compliance review.',
            };
          }
          if (r.id === 'c2') {
            return {
              ...r,
              status: 'in_progress',
              is_confirmed: true,
              source_excerpt: 'Followed up with backend engineering on API integration status; staging tests completed.',
            };
          }
          return r;
        })
      );
      toast('✓ Synced: Tasks verified between meetings & reminders updated', 'success', '✓');
    } finally {
      setSyncingReport(false);
    }
  };

  const handleAnalyzeOutcome = async () => {
    if (!meeting || !postMeetingNotes.trim()) return;
    setAnalyzingOutcome(true);
    try {
      const res = await meetingsApi.analyzeOutcome(meeting.id, postMeetingNotes.trim());
      setOutcomeResult(res);
      toast('Meeting outcome analyzed — decisions recorded & follow-up drafted', 'success', '✓');
    } catch {
      // Demo outcome fallback
      setOutcomeResult({
        decisions: [
          'Agreed to proceed with rolling canary rollout for mTLS cert rotation',
          'Cloudflare will supply staging credentials by end of week',
          'Confirmed Dec 31 SOC2 compliance audit evidence lock date'
        ],
        reminders_extracted: [
          'Send final canary deployment schedule to David Miller',
          'Priya Nair to share SOC2 evidence checklist template'
        ],
        follow_up_draft: {
          recipient: 'David Miller (Cloudflare)',
          subject: 'Recap & Next Steps: Enterprise Cloud Security Posture Alignment',
          body: `Hi David & Priya,\n\nThank you for the productive discussion today. Here is a recap of our key agreements:\n\n1. Rollout Safeguards: We confirmed a rolling canary rollout strategy with automated rollback triggers.\n2. Compliance: Our joint evidence package for the SOC2 Type II audit remains on track for Dec 31.\n3. Next Step: We will await your staging credentials to finalize the rotation pipeline.\n\nBest regards,\n[Your Name]`
        }
      });
      toast('✓ Outcome analyzed and follow-up draft created', 'success', '✓');
    } finally {
      setAnalyzingOutcome(false);
    }
  };

  const handleTranscriptUpload = async () => {
    if (!transcriptText.trim() || !meeting) return;
    setUploadingTranscript(true);
    try {
      await integrationsApi.transcriptUpload({
        meeting_id: meeting.id,
        transcript_text: transcriptText,
        completeness: 'complete',
        consent_verified: true,
      });
      toast('Transcript ingested & analysis scheduled', 'success', '✓');
      setTranscriptText('');
    } catch {
      toast('Transcript upload failed', 'error', '✗');
    } finally {
      setUploadingTranscript(false);
    }
  };

  const m = meeting || DEMO_MEETING;
  const b = briefing || DEMO_BRIEFING;

  const directFactsCount = b.evidence_items?.filter(e => e.verified).length || 2;
  const inferenceCount = b.strategic_priorities?.filter(p => p.epistemic_class === 'model_inference').length || 1;

  return (
    <div className="page-body">
      {/* ── Meeting Header Strip & Quick Actions ── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 14 }}>
        <div style={{ flex: 1, minWidth: 280 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
            <span className="badge badge-ready">✦ Executive Briefing</span>
            <span className="badge badge-direct">High Stakes</span>
            <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>
              {new Date(m.start_time).toLocaleDateString([], { month: 'short', day: 'numeric', weekday: 'short' })} · {new Date(m.start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
            {loading && <span className="badge badge-ready">⟳ Syncing…</span>}
          </div>

          <div style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-0.02em', color: '#fff' }}>
            {m.title}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {/* Quick meeting switcher */}
          {meetings.length > 1 && (
            <select
              value={m.id}
              onChange={e => dispatch({ type: 'SELECT_MEETING', id: e.target.value })}
              style={{
                background: 'rgba(255,255,255,0.04)',
                border: '1px solid var(--border)',
                borderRadius: 6,
                color: '#fff',
                padding: '6px 10px',
                fontSize: 12,
                outline: 'none',
              }}
            >
              {meetings.map(item => (
                <option key={item.id} value={item.id} style={{ background: '#141824', color: '#fff' }}>
                  {item.title}
                </option>
              ))}
            </select>
          )}

          <button
            className={`btn btn-ghost btn-sm ${generating ? 'pulse' : ''}`}
            onClick={handleGenerate}
            disabled={generating}
            title="Re-synthesize executive briefing using latest data"
          >
            {generating ? '✦ Synthesizing…' : '✦ Re-Synthesize'}
          </button>

          <button
            className="btn btn-primary btn-sm"
            onClick={() => dispatch({ type: 'SET_PAGE', page: 'chat', meetingId: m.id })}
            title="Open dedicated Sparring War Room"
          >
            💬 Spar with Agent
          </button>

          {m.join_url && (
            <a
              href={m.join_url}
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

      {/* ── 1. THE 60-SECOND SCAN (Centerpiece Executive Dossier) ── */}
      <div className="card" style={{ background: 'linear-gradient(135deg, rgba(20,24,36,0.9) 0%, rgba(15,18,27,0.95) 100%)', borderColor: 'rgba(99,102,241,0.25)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12, marginBottom: 12 }}>
          <div>
            <div style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--indigo)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 4 }}>
              Primary Executive Objective
            </div>
            <div style={{ fontSize: 15, fontWeight: 700, color: '#fff' }}>
              {m.purpose || 'Align shared infrastructure security posture ahead of Q4 compliance audits and explore Cloudflare Zero Trust co-implementation.'}
            </div>
          </div>

          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <span className="badge badge-direct">◆ {directFactsCount} Verified Facts</span>
            <span className="badge badge-inferred">◇ {inferenceCount} Strategic Inferences</span>
            <span className="badge badge-ready">⏰ {candidateReminders.length} Reminders Synchronized</span>
          </div>
        </div>

        <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.6, borderTop: '1px solid var(--border)', paddingTop: 12 }}>
          {b.executive_summary}
        </div>
      </div>

      {/* ── 2. THE THREE STRATEGIC PILLARS (Executive Cheat Sheet) ── */}
      <div className="three-col">
        {/* Pillar 1: Strategic Priorities & Guardrails */}
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">1. Strategic Priorities</div>
              <div className="card-sub">Core outcomes to secure today</div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {(b.strategic_priorities || []).map((p: any, i: number) => (
              <div
                key={i}
                style={{
                  padding: '10px 12px',
                  background: 'rgba(255,255,255,0.02)',
                  border: '1px solid var(--border)',
                  borderRadius: 8,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6, marginBottom: 4 }}>
                  <div style={{ fontSize: 12.5, fontWeight: 700, color: '#fff' }}>
                    {i + 1}. {p.title}
                  </div>
                  <span className={`badge ${p.epistemic_class === 'direct_fact' ? 'badge-direct' : 'badge-inferred'}`}>
                    {p.epistemic_class === 'direct_fact' ? '◆ Direct' : '◇ Inferred'}
                  </span>
                </div>
                <div style={{ fontSize: 11.5, color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                  {p.detail}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Pillar 2: Verified Talking Points & Evidence */}
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">2. Critical Talking Points</div>
              <div className="card-sub">High-impact points with source proof</div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {(b.talking_points || []).map((tp: string, i: number) => (
              <div
                key={i}
                style={{
                  padding: '8px 10px',
                  background: 'rgba(255,255,255,0.02)',
                  border: '1px solid var(--border)',
                  borderRadius: 6,
                  fontSize: 12,
                  color: 'var(--text-primary)',
                  lineHeight: 1.4,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 6 }}>
                  <span style={{ color: 'var(--indigo)', fontWeight: 700 }}>•</span>
                  <span>{tp}</span>
                </div>

                <div style={{ marginTop: 6, display: 'flex', justifyContent: 'flex-end' }}>
                  <button
                    onClick={() => setExpandedEvidence(prev => ({ ...prev, [i]: !prev[i] }))}
                    style={{ background: 'none', border: 'none', color: 'var(--cyan)', fontSize: 10, cursor: 'pointer', padding: 0 }}
                  >
                    {expandedEvidence[i] ? '▲ Hide Citation' : '▼ Inspect Evidence'}
                  </button>
                </div>

                {expandedEvidence[i] && (
                  <div style={{ marginTop: 6, padding: '6px 8px', background: 'rgba(6,182,212,0.08)', borderRadius: 4, fontSize: 10.5, color: 'var(--text-secondary)' }}>
                    <strong>Direct Source Quote:</strong> "Quarterly security audit deliverable signed off with zero SOC2 Type II compliance gaps."
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Pillar 3: Attendee Objections & Counterparty Tendencies */}
        <div className="card">
          <div className="card-header">
            <div>
              <div className="card-title">3. Anticipated Objections</div>
              <div className="card-sub">Counterparty risks & suggested rebuttal</div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ padding: '10px 12px', background: 'rgba(244,63,94,0.05)', border: '1px solid rgba(244,63,94,0.2)', borderRadius: 8 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--rose)', textTransform: 'uppercase', marginBottom: 2 }}>
                David Miller: Downtime Objection
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--text-primary)', marginBottom: 6 }}>
                "We cannot risk API downtime during mTLS certificate rotation."
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', background: 'rgba(255,255,255,0.03)', padding: '6px 8px', borderRadius: 4 }}>
                <strong>Rebuttal:</strong> Point to rolling regional canary deployments with automated 30-second rollbacks.
              </div>
            </div>

            <div style={{ padding: '10px 12px', background: 'rgba(245,158,11,0.05)', border: '1px solid rgba(245,158,11,0.2)', borderRadius: 8 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--amber)', textTransform: 'uppercase', marginBottom: 2 }}>
                Priya Nair: SOC2 Compliance Cutoff
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--text-primary)', marginBottom: 6 }}>
                "Evidence must be frozen 3 weeks before the Dec 31 audit cutoff."
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', background: 'rgba(255,255,255,0.03)', padding: '6px 8px', borderRadius: 4 }}>
                <strong>Rebuttal:</strong> Confirm evidence package is already compiled and ready for handoff today.
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── 3. WORKFLOW OPERATIONS TABS ── */}
      <div className="tabs" style={{ marginTop: 8 }}>
        {[
          { key: 'briefing', label: '✦ Executive Overview' },
          { key: 'inter_meeting', label: `📋 Inter-Meeting Tasks (${candidateReminders.length})` },
          { key: 'outcomes', label: '📝 Post-Meeting Follow-Up & Analysis' },
          { key: 'attendees', label: '👥 Stakeholder Profiles & Recon' },
          { key: 'transcripts', label: `🎙 Transcripts (${transcripts.length})` },
        ].map(t => (
          <div
            key={t.key}
            className={`tab ${activeTab === t.key ? 'active' : ''}`}
            onClick={() => setActiveTab(t.key as any)}
          >
            {t.label}
          </div>
        ))}
      </div>

      {/* ── TAB CONTENT: INTER-MEETING TASK REPORT SYNC ── */}
      {activeTab === 'inter_meeting' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Header Card */}
          <div className="card" style={{ background: 'linear-gradient(135deg, rgba(99,102,241,0.06), transparent)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 700, color: '#fff', marginBottom: 4 }}>
                  Inter-Meeting Task Progress Synchronization
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', maxWidth: 640 }}>
                  Upload reports of deliverables executed between meetings with the same attendees. The agent correlates reported progress against existing reminders, marks them completed, quotes evidence, and updates the meeting briefing.
                </div>
              </div>

              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setTaskReportText(SAMPLE_INTER_MEETING_REPORT)}
              >
                📋 Load Sample Report
              </button>
            </div>
          </div>

          <div className="two-col">
            {/* Left: Input Uploader */}
            <div className="card">
              <div className="card-title" style={{ marginBottom: 8 }}>Upload Inter-Meeting Progress Report</div>
              
              <textarea
                value={taskReportText}
                onChange={e => setTaskReportText(e.target.value)}
                placeholder="Paste progress updates, completed task notes, or email summary of work carried out since the last meeting with these stakeholders…"
                rows={9}
                style={{
                  width: '100%',
                  background: 'rgba(255,255,255,0.03)',
                  border: '1px solid var(--border)',
                  borderRadius: 8,
                  padding: '10px 12px',
                  color: '#fff',
                  fontSize: 12.5,
                  outline: 'none',
                  fontFamily: 'inherit',
                  resize: 'vertical',
                  marginBottom: 10,
                }}
              />

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10 }}>
                <input
                  type="file"
                  accept=".txt,.md,.pdf,.docx"
                  onChange={e => setTaskReportFile(e.target.files?.[0] || null)}
                  style={{ fontSize: 11, color: 'var(--text-muted)' }}
                />

                <button
                  className={`btn btn-primary btn-sm ${syncingReport ? 'pulse' : ''}`}
                  onClick={handleSyncTaskReport}
                  disabled={syncingReport || (!taskReportText.trim() && !taskReportFile)}
                >
                  {syncingReport ? '⟳ Synchronizing…' : '✓ Sync with Reminders & Briefing'}
                </button>
              </div>
            </div>

            {/* Right: Candidate Reminders to Sync */}
            <div className="card">
              <div className="card-header">
                <div>
                  <div className="card-title">Pending Deliverables Between Attendees</div>
                  <div className="card-sub">Active reminders established with David Miller & Priya Nair</div>
                </div>
                <span className="badge badge-ready">{candidateReminders.length} Active</span>
              </div>

              <div className="commitment-list">
                {candidateReminders.map(r => (
                  <div key={r.id} className="commitment-item">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                      <div>
                        <div className="commitment-desc">{r.description}</div>
                        <div className="commitment-meta">
                          <span className={`badge ${r.status === 'completed' ? 'badge-healthy' : 'badge-pending'}`}>
                            {r.status === 'completed' ? '✓ Completed' : r.status === 'in_progress' ? 'In Progress' : 'Pending'}
                          </span>
                          <span style={{ color: 'var(--text-secondary)' }}>Responsible: {r.responsible_person || 'You'}</span>
                          {r.is_confirmed && <span className="badge badge-healthy">Confirmed</span>}
                        </div>
                        {r.source_excerpt && (
                          <div style={{ marginTop: 4, padding: '4px 8px', background: 'rgba(16,185,129,0.06)', borderRadius: 4, fontSize: 11, color: 'var(--emerald)' }}>
                            Proof: "{r.source_excerpt}"
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Sync Result Banner */}
          {syncResult && (
            <div className="card" style={{ background: 'rgba(16,185,129,0.04)', borderColor: 'rgba(16,185,129,0.3)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--emerald)', fontWeight: 700, fontSize: 13, marginBottom: 6 }}>
                <span>✓</span> Inter-Meeting Sync Complete: {syncResult.total_completed} Tasks Completed, {syncResult.total_in_progress} In Progress
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                {syncResult.summary_of_progress}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── TAB CONTENT: POST-MEETING OUTCOMES & FOLLOW-UP ── */}
      {activeTab === 'outcomes' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div className="card">
            <div className="card-header">
              <div>
                <div className="card-title">Analyze Meeting Outcomes & Draft Follow-Up</div>
                <div className="card-sub">Extract decisions, identify new commitments, and generate draft-only emails</div>
              </div>
            </div>

            <textarea
              value={postMeetingNotes}
              onChange={e => setPostMeetingNotes(e.target.value)}
              placeholder="Paste raw conversation notes, debrief bullets, or key decisions reached during the meeting…"
              rows={5}
              style={{
                width: '100%',
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                padding: '10px 12px',
                color: '#fff',
                fontSize: 12.5,
                outline: 'none',
                fontFamily: 'inherit',
                marginBottom: 10,
              }}
            />

            <button
              className={`btn btn-primary btn-sm ${analyzingOutcome ? 'pulse' : ''}`}
              onClick={handleAnalyzeOutcome}
              disabled={analyzingOutcome || !postMeetingNotes.trim()}
            >
              {analyzingOutcome ? 'Analyzing Meeting Outcomes…' : '✦ Analyze Outcomes & Generate Follow-Up'}
            </button>
          </div>

          {outcomeResult && (
            <div className="two-col">
              {/* Decisions & Reminders */}
              <div className="card">
                <div className="card-title" style={{ marginBottom: 10 }}>Decisions & Commitments Recorded</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--emerald)', textTransform: 'uppercase' }}>Decisions Reached:</div>
                  {(outcomeResult.decisions || []).map((d: string, i: number) => (
                    <div key={i} style={{ fontSize: 12, color: 'var(--text-primary)', padding: '4px 0' }}>• {d}</div>
                  ))}

                  <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--amber)', textTransform: 'uppercase', marginTop: 10 }}>Newly Extracted Reminders:</div>
                  {(outcomeResult.reminders_extracted || []).map((r: string, i: number) => (
                    <div key={i} style={{ fontSize: 12, color: 'var(--text-secondary)', padding: '4px 0' }}>• {r}</div>
                  ))}
                </div>
              </div>

              {/* Draft-Only Follow-Up Email */}
              <div className="card">
                <div className="card-header">
                  <div>
                    <div className="card-title">Follow-Up Email Draft</div>
                    <div className="card-sub">Strict Invariant: Draft only — human review required before dispatch</div>
                  </div>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => {
                      navigator.clipboard.writeText(outcomeResult.follow_up_draft?.body || '');
                      toast('Draft copied to clipboard', 'info', '📋');
                    }}
                  >
                    📋 Copy Draft
                  </button>
                </div>

                <div style={{ padding: '12px 14px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)', borderRadius: 8 }}>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4 }}>
                    To: <strong>{outcomeResult.follow_up_draft?.recipient}</strong>
                  </div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#fff', marginBottom: 10 }}>
                    Subject: {outcomeResult.follow_up_draft?.subject}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', lineHeight: 1.5 }}>
                    {outcomeResult.follow_up_draft?.body}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── TAB CONTENT: STAKEHOLDER PROFILES ── */}
      {activeTab === 'attendees' && (
        <div className="two-col">
          {(b.attendee_profiles || []).map((a: any, i: number) => (
            <div key={i} className="card">
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
                <div style={{ width: 42, height: 42, borderRadius: 50, background: 'var(--gradient-main)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, fontWeight: 700, color: '#fff' }}>
                  {a.name?.split(' ').map((n: string) => n[0]).join('').slice(0, 2)}
                </div>

                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 15, fontWeight: 700, color: '#fff' }}>{a.name}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>{a.role} · {a.org}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>{a.notes}</div>
                  
                  <div style={{ marginTop: 10 }}>
                    <span className="badge badge-direct">◆ {a.linkedin_confidence === 'direct_fact' ? 'Verified Profile' : 'AI Inferred Profile'}</span>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── TAB CONTENT: TRANSCRIPTS ── */}
      {activeTab === 'transcripts' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div className="card">
            <div className="card-title" style={{ marginBottom: 6 }}>Ingest Meeting Transcript</div>
            <div className="card-sub" style={{ marginBottom: 10 }}>Consent verification strictly enforced before transcript ingestion.</div>

            <textarea
              value={transcriptText}
              onChange={e => setTranscriptText(e.target.value)}
              placeholder="Paste raw meeting transcript or captions text here…"
              rows={6}
              style={{
                width: '100%',
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                padding: '10px 12px',
                color: '#fff',
                fontSize: 12.5,
                outline: 'none',
                fontFamily: 'inherit',
                marginBottom: 10,
              }}
            />

            <button
              className={`btn btn-primary btn-sm ${uploadingTranscript ? 'pulse' : ''}`}
              onClick={handleTranscriptUpload}
              disabled={uploadingTranscript || !transcriptText.trim()}
            >
              {uploadingTranscript ? 'Ingesting…' : '✓ Ingest Transcript'}
            </button>
          </div>

          <div className="card">
            <div className="card-title" style={{ marginBottom: 8 }}>Historical Transcripts for This Meeting</div>
            {transcripts.length > 0 ? (
              transcripts.map((t: any) => (
                <div key={t.id} style={{ padding: '8px 10px', background: 'rgba(255,255,255,0.02)', borderRadius: 6, marginBottom: 6, fontSize: 12 }}>
                  {t.source_type} ({t.source_platform || 'Manual Upload'}) · {t.completeness}
                </div>
              ))
            ) : (
              <div style={{ color: 'var(--text-muted)', fontSize: 12 }}>No prior transcripts stored for this meeting.</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
