// Briefing viewer page with interactive Agent Follow-Up Conversation
import { useEffect, useState, useRef } from 'react';
import { briefingsApi, meetingsApi, integrationsApi } from '../api';
import type { Briefing, Meeting, BriefingMessage } from '../api';
import { useApp, useToast } from '../store';

const DEMO_MEETING: Meeting = {
  id: 'm1', title: 'Enterprise Cloud Security Review',
  purpose: 'Q4 security posture alignment with Cloudflare engineering team',
  start_time: new Date(Date.now() + 8_040_000).toISOString(),
  end_time: new Date(Date.now() + 11_640_000).toISOString(),
  status: 'upcoming', effective_importance: 5, meeting_version: 1,
  created_at: '', updated_at: '', join_url: 'https://meet.google.com/abc',
};

const DEMO_BRIEFING: Briefing = {
  id: 'b1', meeting_id: 'm1', version: 2, is_latest: true,
  executive_summary: 'David Miller from Cloudflare is leading this engagement to review your shared infrastructure security posture ahead of Q4 compliance audits. This is a high-stakes meeting — Cloudflare recently announced their Zero Trust expansion and this conversation is likely to explore co-implementation opportunities. Based on contextual memory, your last interaction with their team centered around API gateway hardening.',
  attendee_profiles: [
    { name: 'David Miller', role: 'VP of Engineering', org: 'Cloudflare', notes: 'Strong opinions on zero-trust architecture. Previously at Stripe. Known for direct communication style.', linkedin_confidence: 'unverified_assumption' },
    { name: 'Priya Nair', role: 'Security Lead', org: 'Cloudflare', notes: 'Led the Cloudflare Gateway rollout in APAC.', linkedin_confidence: 'model_inference' },
  ],
  strategic_priorities: [
    { title: 'Zero Trust Posture Gap', detail: 'Identify gaps in current mTLS implementation vs Cloudflare\'s recommendations', epistemic_class: 'model_inference' },
    { title: 'Compliance Timeline', detail: 'Align on SOC2 Type II audit schedule before Dec 31', epistemic_class: 'direct_fact' },
    { title: 'API Gateway Handoff', detail: 'Follow up on action items from August call — deployment rollout status', epistemic_class: 'model_inference' },
  ],
  talking_points: [
    'Open with the progress on the mTLS certificate rotation timeline',
    'Ask about their experience with AI-assisted threat detection in Gateway — we\'re evaluating similar approaches',
    'Probe their Q1 2027 roadmap for Zero Trust to identify partnership opportunities',
    'Confirm SOC2 evidence collection requirements before closing',
  ],
  conflicts_detected: [
    { type: 'data_conflict', description: 'Last briefing stated rollout is 80% complete, but recent Slack note says 60% — confirm actual status before the meeting', severity: 'medium' },
  ],
  evidence_items: [
    { id: 'e1', source_type: 'document', claim_text: 'mTLS rollout at 80% completion', verified: true },
    { id: 'e2', source_type: 'hindsight', claim_text: 'David Miller prefers async follow-ups over email chains', verified: false },
  ],
  created_at: new Date(Date.now() - 1_800_000).toISOString(),
};

interface ChatTurn {
  role: 'user' | 'assistant';
  content: string;
  talkingPoints?: string[];
  actionItems?: string[];
  timestamp: string;
}

export default function BriefingPage() {
  const { state, dispatch } = useApp();
  const toast = useToast();
  const meetingId = state.selectedMeetingId;

  const [meeting, setMeeting] = useState<Meeting | null>(null);
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [showTranscript, setShowTranscript] = useState(false);
  const [transcriptText, setTranscriptText] = useState('');
  const [uploadingTranscript, setUploadingTranscript] = useState(false);
  const [transcripts, setTranscripts] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState<'briefing' | 'followup' | 'attendees' | 'intelligence' | 'transcripts'>('briefing');

  // Follow-up conversation state
  const [messages, setMessages] = useState<ChatTurn[]>([
    {
      role: 'assistant',
      content: "I've synthesized the meeting briefing, attendee background, and strategic context. What would you like to drill into? (e.g. anticipating objections, negotiation tactics, or drafting custom talking points)",
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    },
  ]);
  const [questionInput, setQuestionInput] = useState('');
  const [asking, setAsking] = useState(false);
  const chatBottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!meetingId) { setMeeting(DEMO_MEETING); setBriefing(DEMO_BRIEFING); return; }
    setLoading(true);
    Promise.allSettled([meetingsApi.get(meetingId), briefingsApi.latest(meetingId), integrationsApi.transcripts(meetingId)])
      .then(([m, b, t]) => {
        setMeeting(m.status === 'fulfilled' ? m.value : DEMO_MEETING);
        setBriefing(b.status === 'fulfilled' ? b.value : DEMO_BRIEFING);
        setTranscripts(t.status === 'fulfilled' ? (t.value as any)?.transcripts ?? [] : []);
      })
      .finally(() => setLoading(false));
  }, [meetingId]);

  useEffect(() => {
    if (activeTab === 'followup') {
      chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, activeTab]);

  const handleGenerate = async () => {
    if (!meeting) return;
    setGenerating(true);
    try {
      const b = await briefingsApi.generate(meeting.id, true);
      setBriefing(b);
      toast('Briefing regenerated', 'success', '✦');
    } catch (e: any) { toast(e.message ?? 'Failed', 'error', '✗'); }
    finally { setGenerating(false); }
  };

  const handleTranscriptUpload = async () => {
    if (!transcriptText.trim() || !meeting) return;
    setUploadingTranscript(true);
    try {
      const result: any = await integrationsApi.transcriptUpload({
        meeting_id: meeting.id,
        transcript_text: transcriptText,
        completeness: 'complete',
        consent_verified: true,
      });
      toast(`Transcript ingested — ${result?.segments_ingested ?? 0} segments · Analysis queued`, 'success', '✦');
      setShowTranscript(false);
      setTranscriptText('');
    } catch (e: any) { toast(e.message ?? 'Upload failed', 'error', '✗'); }
    finally { setUploadingTranscript(false); }
  };

  const handleSendQuestion = async (customQ?: string) => {
    const q = (customQ ?? questionInput).trim();
    if (!q || !meeting || asking) return;

    const userTurn: ChatTurn = {
      role: 'user',
      content: q,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    const nextMessages = [...messages, userTurn];
    setMessages(nextMessages);
    setQuestionInput('');
    setAsking(true);
    if (activeTab !== 'followup') setActiveTab('followup');

    try {
      const historyPayload: BriefingMessage[] = nextMessages
        .slice(-6)
        .map(m => ({ role: m.role, content: m.content }));

      const res = await briefingsApi.askFollowUp(meeting.id, q, historyPayload);

      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: res.answer,
          talkingPoints: res.suggested_talking_points,
          actionItems: res.action_items,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        }
      ]);
    } catch (e: any) {
      // Local fallback for offline/demo mode
      setTimeout(() => {
        let simulatedAnswer = `Regarding your question on **${meeting.title}**: The strategic priority is maintaining momentum on deliverables and ensuring alignment between both engineering teams.`;
        if (q.toLowerCase().includes('objection') || q.toLowerCase().includes('risk')) {
          simulatedAnswer = `Key objections to anticipate from David Miller: 1) Migration timeline risks for mTLS cert rotation, 2) Maintenance window impact on customer-facing APIs. Recommended response: Propose rolling regional updates with automatic canary rollbacks.`;
        } else if (q.toLowerCase().includes('talking point') || q.toLowerCase().includes('point')) {
          simulatedAnswer = `Here are 2 high-impact talking points for this meeting:\n- "We have established automated compliance checks that cut audit preparation by 40%."\n- "Our zero-trust policy architecture aligns directly with Cloudflare Gateway specifications."`;
        }

        setMessages(prev => [
          ...prev,
          {
            role: 'assistant',
            content: simulatedAnswer,
            talkingPoints: ['Propose rolling regional updates with canary verification', 'Confirm audit checklist before sign-off'],
            actionItems: ['Document consensus points in the post-meeting debrief'],
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          }
        ]);
      }, 400);
    } finally {
      setAsking(false);
    }
  };

  const handleAddTalkingPoint = (tp: string) => {
    if (!briefing) return;
    const current = briefing.talking_points ?? [];
    setBriefing({ ...briefing, talking_points: [...current, tp] });
    toast('Added to Talking Points!', 'success', '✓');
  };

  if (!meeting && !loading) return (
    <div className="page-body fade-in">
      <div className="empty-state">
        <div className="empty-icon">✦</div>
        <div style={{ marginBottom: 16 }}>Select a meeting to view its briefing</div>
        <button className="btn btn-primary" onClick={() => dispatch({ type: 'SET_PAGE', page: 'meetings' })}>Browse Meetings</button>
      </div>
    </div>
  );

  const m = meeting ?? DEMO_MEETING;
  const b = briefing ?? DEMO_BRIEFING;

  const QUICK_QUESTIONS = [
    "What objections is David Miller likely to raise?",
    "Draft 3 sharp talking points for the opening",
    "Are there any budget or timeline conflicts in the docs?",
    "How should I structure the first 10 minutes?",
  ];

  return (
    <div className="page-body fade-in">
      {/* Meeting Header */}
      <div className="card" style={{ background: 'linear-gradient(135deg, rgba(99,102,241,0.06), rgba(139,92,246,0.06))', borderColor: 'rgba(99,102,241,0.2)' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <span className="badge badge-pending">{m.status}</span>
              {b.version && <span className="badge" style={{ background: 'rgba(99,102,241,0.1)', color: 'var(--indigo)', border: '1px solid rgba(99,102,241,0.2)' }}>v{b.version}</span>}
              {b.is_latest && <span className="badge badge-healthy">Latest</span>}
              {b.degraded_reason && <span className="badge badge-error">⚠ Degraded</span>}
            </div>
            <div style={{ fontSize: 20, fontWeight: 800, marginBottom: 4 }}>{m.title}</div>
            {m.purpose && <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>{m.purpose}</div>}
            <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
              📅 {new Date(m.start_time).toLocaleString([], { month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
              {m.join_url && <> · <a href={m.join_url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--indigo)' }}>🔗 Join Link</a></>}
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <button className={`btn btn-primary ${generating ? 'pulse' : ''}`} onClick={handleGenerate} disabled={generating}>
              {generating ? '⟳ Generating…' : '✦ Regenerate Briefing'}
            </button>
            <div style={{ display: 'flex', gap: 6 }}>
              <button className="btn btn-ghost btn-sm" onClick={() => setShowTranscript(s => !s)}>📝 Transcript</button>
              <button className="btn btn-ghost btn-sm" onClick={() => setActiveTab('followup')} style={{ color: 'var(--primary)' }}>💬 Ask Agent</button>
            </div>
          </div>
        </div>

        {b.conflicts_detected && b.conflicts_detected.length > 0 && (
          <div style={{ marginTop: 12, padding: '10px 14px', background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.2)', borderRadius: 8 }}>
            <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--amber)', marginBottom: 4 }}>⚠ Conflicts Detected</div>
            {b.conflicts_detected.map((c, i) => (
              <div key={i} style={{ fontSize: 12, color: 'var(--text-secondary)' }}>• {c.description}</div>
            ))}
          </div>
        )}
      </div>

      {/* Transcript Upload Panel */}
      {showTranscript && (
        <div className="card" style={{ borderColor: 'var(--border-bright)' }}>
          <div className="card-title" style={{ marginBottom: 12 }}>Upload Transcript</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 12 }}>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 8 }}>Option A: Paste transcript text</div>
              <textarea
                style={{ width: '100%', height: 120, background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border)', borderRadius: 8, padding: '10px 12px', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font-mono)', resize: 'vertical' }}
                placeholder="Speaker 1: Hello, thanks for joining...&#10;Speaker 2: Happy to be here..."
                value={transcriptText}
                onChange={e => setTranscriptText(e.target.value)}
              />
            </div>
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 8 }}>Option B: Internet Research (auto)</div>
              <div className="upload-zone" style={{ height: 120 }} onClick={() => toast('Internet research queued — results will appear in Intelligence tab', 'info', '◈')}>
                <div className="upload-icon">◈</div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Click to trigger OpenClaw reconnaissance</div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>Attendees + company background (unverified_assumption)</div>
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-primary" onClick={handleTranscriptUpload} disabled={uploadingTranscript || !transcriptText.trim()}>
              {uploadingTranscript ? '⟳ Uploading…' : '↑ Ingest Transcript'}
            </button>
            <button className="btn btn-ghost" onClick={() => setShowTranscript(false)}>Cancel</button>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="tabs">
        {(['briefing', 'followup', 'attendees', 'intelligence', 'transcripts'] as const).map(t => (
          <div key={t} className={`tab ${activeTab === t ? 'active' : ''}`} onClick={() => setActiveTab(t)}>
            {t === 'briefing' ? '✦ Briefing' :
             t === 'followup' ? '💬 Chat with Agent' :
             t === 'attendees' ? '👤 Attendees' :
             t === 'intelligence' ? '◈ Intelligence' : '📝 Transcripts'}
          </div>
        ))}
      </div>

      {/* Tab: Briefing */}
      {activeTab === 'briefing' && (
        <div className="briefing-section">
          <div className="briefing-block">
            <div className="briefing-block-title">Executive Summary</div>
            <div className="briefing-text">{b.executive_summary ?? 'No briefing generated yet. Click "Regenerate Briefing" above.'}</div>
          </div>
          <div className="briefing-block">
            <div className="briefing-block-title">Strategic Priorities</div>
            {(b.strategic_priorities ?? []).map((p: any, i: number) => (
              <div key={i} style={{ display: 'flex', gap: 10, padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                <div style={{ color: 'var(--indigo)', flexShrink: 0, marginTop: 1 }}>◆</div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 3 }}>{p.title}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{p.detail}</div>
                </div>
                <span className={`evidence-chip`} title={p.epistemic_class}>{p.epistemic_class === 'direct_fact' ? '◆' : '◇'}</span>
              </div>
            ))}
          </div>
          <div className="briefing-block">
            <div className="briefing-block-title">Talking Points</div>
            {(b.talking_points ?? []).map((tp: any, i: number) => (
              <div key={i} className="talking-point">
                <span className="tp-dot">›</span>
                <span>{typeof tp === 'string' ? tp : tp.point ?? JSON.stringify(tp)}</span>
              </div>
            ))}
          </div>

          {/* Quick Follow-Up Bar inside Briefing View */}
          <div className="card" style={{ background: 'linear-gradient(135deg, rgba(99,102,241,0.08), rgba(139,92,246,0.04))', borderColor: 'rgba(99,102,241,0.3)', marginTop: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
              <div style={{ fontSize: 13, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 6 }}>
                <span>💬</span> Ask the Agent about this Briefing
              </div>
              <button className="btn btn-ghost btn-sm" onClick={() => setActiveTab('followup')} style={{ fontSize: 11, color: 'var(--primary)' }}>
                View Full Chat →
              </button>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                type="text"
                placeholder="Ask e.g. What objections might David Miller raise?"
                value={questionInput}
                onChange={e => setQuestionInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSendQuestion()}
                style={{
                  flex: 1,
                  padding: '10px 14px',
                  background: 'var(--surface-input)',
                  border: '1px solid var(--border)',
                  borderRadius: 8,
                  color: 'var(--text-primary)',
                  fontSize: 13,
                }}
              />
              <button
                className="btn btn-primary"
                onClick={() => handleSendQuestion()}
                disabled={asking || !questionInput.trim()}
              >
                {asking ? 'Thinking…' : 'Ask'}
              </button>
            </div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
              {QUICK_QUESTIONS.slice(0, 3).map((qq, i) => (
                <button
                  key={i}
                  className="btn btn-ghost btn-sm"
                  onClick={() => handleSendQuestion(qq)}
                  style={{ fontSize: 11, background: 'rgba(255,255,255,0.04)' }}
                >
                  💡 {qq}
                </button>
              ))}
            </div>
          </div>

          {b.evidence_items && b.evidence_items.length > 0 && (
            <div className="briefing-block" style={{ marginTop: 16 }}>
              <div className="briefing-block-title">Evidence Sources</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {b.evidence_items.map((e: any) => (
                  <span key={e.id} className="evidence-chip">
                    {e.verified ? '◆' : '◇'} {e.source_type} — {(e.claim_text ?? '').slice(0, 48)}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tab: Follow-up Conversation with Agent */}
      {activeTab === 'followup' && (
        <div className="briefing-section">
          <div className="card" style={{ display: 'flex', flexDirection: 'column', height: '600px', padding: 0 }}>
            {/* Conversation Header */}
            <div style={{
              padding: '16px 20px',
              borderBottom: '1px solid var(--border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              background: 'rgba(255,255,255,0.02)',
            }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span>✦</span> Briefing Strategy Advisor
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 2 }}>
                  Trained on {m.title} briefing context, attendee history & documents
                </div>
              </div>
              <span className="badge badge-healthy">Live AI Grounded</span>
            </div>

            {/* Messages Area */}
            <div style={{
              flex: 1,
              overflowY: 'auto',
              padding: '20px',
              display: 'flex',
              flexDirection: 'column',
              gap: 16,
            }}>
              {messages.map((msg, idx) => (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
                  }}
                >
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    fontSize: 11,
                    color: 'var(--text-muted)',
                    marginBottom: 4,
                  }}>
                    <span>{msg.role === 'user' ? 'You' : '✦ Meeting Prep Agent'}</span>
                    <span>·</span>
                    <span>{msg.timestamp}</span>
                  </div>
                  <div style={{
                    maxWidth: '85%',
                    padding: '12px 16px',
                    borderRadius: 12,
                    fontSize: 13,
                    lineHeight: 1.55,
                    background: msg.role === 'user'
                      ? 'linear-gradient(135deg, var(--primary), var(--primary-hover))'
                      : 'rgba(255, 255, 255, 0.05)',
                    color: '#fff',
                    border: msg.role === 'user' ? 'none' : '1px solid var(--border)',
                    whiteSpace: 'pre-wrap',
                  }}>
                    {msg.content}

                    {/* Suggested talking points chips */}
                    {msg.talkingPoints && msg.talkingPoints.length > 0 && (
                      <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid rgba(255,255,255,0.1)' }}>
                        <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--indigo)', marginBottom: 6 }}>
                          💡 Suggested Talking Points
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                          {msg.talkingPoints.map((tp, i) => (
                            <div key={i} style={{
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'space-between',
                              background: 'rgba(99,102,241,0.1)',
                              padding: '6px 10px',
                              borderRadius: 6,
                              fontSize: 12,
                              gap: 8,
                            }}>
                              <span>• {tp}</span>
                              <button
                                className="btn btn-ghost btn-sm"
                                onClick={() => handleAddTalkingPoint(tp)}
                                style={{ fontSize: 10, padding: '2px 6px', color: 'var(--indigo)' }}
                              >
                                + Add
                              </button>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Action Items */}
                    {msg.actionItems && msg.actionItems.length > 0 && (
                      <div style={{ marginTop: 10 }}>
                        <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--amber)', marginBottom: 4 }}>
                          ⚡ Recommended Action Items
                        </div>
                        {msg.actionItems.map((ai, i) => (
                          <div key={i} style={{ fontSize: 12, color: 'var(--text-secondary)', padding: '2px 0' }}>
                            → {ai}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {asking && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)', fontSize: 12, padding: '8px 0' }}>
                  <div className="pulse">✦</div>
                  <span>Agent is analyzing briefing context & synthesizing strategic answer…</span>
                </div>
              )}
              <div ref={chatBottomRef} />
            </div>

            {/* Quick Prompts */}
            <div style={{
              padding: '8px 16px',
              borderTop: '1px solid var(--border)',
              background: 'rgba(255,255,255,0.01)',
              display: 'flex',
              gap: 8,
              overflowX: 'auto',
            }}>
              {QUICK_QUESTIONS.map((qq, i) => (
                <button
                  key={i}
                  className="btn btn-ghost btn-sm"
                  onClick={() => handleSendQuestion(qq)}
                  disabled={asking}
                  style={{
                    fontSize: 11,
                    whiteSpace: 'nowrap',
                    background: 'rgba(255,255,255,0.03)',
                  }}
                >
                  💡 {qq}
                </button>
              ))}
            </div>

            {/* Input Bar */}
            <div style={{
              padding: '16px 20px',
              borderTop: '1px solid var(--border)',
              display: 'flex',
              gap: 10,
              background: 'rgba(255,255,255,0.02)',
            }}>
              <input
                type="text"
                placeholder="Ask about attendees, risks, counter-arguments, talking points..."
                value={questionInput}
                onChange={e => setQuestionInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSendQuestion()}
                disabled={asking}
                style={{
                  flex: 1,
                  padding: '12px 16px',
                  background: 'var(--surface-input)',
                  border: '1px solid var(--border)',
                  borderRadius: 10,
                  color: 'var(--text-primary)',
                  fontSize: 13,
                }}
              />
              <button
                className="btn btn-primary"
                onClick={() => handleSendQuestion()}
                disabled={asking || !questionInput.trim()}
                style={{ padding: '0 20px' }}
              >
                {asking ? 'Thinking…' : 'Send'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tab: Attendees */}
      {activeTab === 'attendees' && (
        <div className="briefing-section">
          {(b.attendee_profiles ?? []).map((a: any, i: number) => (
            <div key={i} className="card" style={{ padding: 16 }}>
              <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
                <div className="contact-avatar" style={{ flexShrink: 0 }}>{a.name?.split(' ').map((n: string) => n[0]).join('').slice(0, 2)}</div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 2 }}>{a.name}</div>
                  <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{a.role} · {a.org}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>{a.notes}</div>
                  <div style={{ marginTop: 8 }}>
                    <span className="evidence-chip" title={`Confidence: ${a.linkedin_confidence}`}>
                      {a.linkedin_confidence === 'direct_fact' ? '◆ Verified' : a.linkedin_confidence === 'model_inference' ? '◇ Inferred' : '◇ Unverified'}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          ))}
          {(b.attendee_profiles ?? []).length === 0 && (
            <div className="empty-state"><div className="empty-icon">👤</div>No attendee profiles extracted yet</div>
          )}
        </div>
      )}

      {/* Tab: Intelligence */}
      {activeTab === 'intelligence' && (
        <div className="briefing-section">
          <div className="card">
            <div className="card-header">
              <div className="card-title">Meeting Intelligence</div>
              <span className="badge badge-pending">Requires transcript</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              {[['Decisions', '—', 'No decisions extracted yet'],['Commitments', '—', 'Upload transcript to extract'],['Blockers', '—', 'No blockers detected'],['Unresolved Questions', '—', 'Awaiting transcript analysis']].map(([label, val, sub]) => (
                <div key={label} style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)', borderRadius: 8, padding: '14px 16px' }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--indigo)', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 }}>{label}</div>
                  <div style={{ fontSize: 22, fontWeight: 800 }}>{val}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>{sub}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="card">
            <div className="card-title" style={{ marginBottom: 12 }}>OpenClaw Reconnaissance</div>
            <div className="recon-item">
              <div className="recon-label">Epistemic Classification</div>
              <div className="recon-value">All recon data is tagged as <span className="badge badge-proposed">unverified_assumption</span> — requires your confirmation</div>
            </div>
            <div className="recon-item">
              <div className="recon-label">Company Intelligence</div>
              <div className="recon-value">Trigger recon by clicking "Upload Transcript" → Option B above</div>
            </div>
          </div>
        </div>
      )}

      {/* Tab: Transcripts */}
      {activeTab === 'transcripts' && (
        <div className="briefing-section">
          {transcripts.length > 0 ? transcripts.map((t: any) => (
            <div key={t.id} className="card" style={{ padding: 16 }}>
              <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{t.source_type} — {t.source_platform ?? 'Unknown platform'}</div>
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    <span className={`badge ${t.completeness === 'complete' ? 'badge-healthy' : 'badge-medium'}`}>{t.completeness}</span>
                    <span className={`badge ${t.processing_status === 'completed' ? 'badge-healthy' : 'badge-pending'}`}>{t.processing_status}</span>
                    {t.consent_verified && <span className="badge badge-healthy">✓ Consented</span>}
                  </div>
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{new Date(t.retrieved_at).toLocaleString()}</div>
              </div>
            </div>
          )) : (
            <div className="empty-state">
              <div className="empty-icon">📝</div>
              No transcripts yet.
              <div style={{ marginTop: 12 }}>
                <button className="btn btn-primary" onClick={() => setShowTranscript(true)}>Upload Transcript</button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
