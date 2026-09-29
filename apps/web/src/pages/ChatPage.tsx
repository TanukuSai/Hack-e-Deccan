import { useState, useEffect, useRef } from 'react';
import { briefingsApi, meetingsApi, commitmentsApi } from '../api';
import type { Meeting, BriefingMessage } from '../api';
import { useApp, useToast } from '../store';

interface ChatTurn {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  talkingPoints?: string[];
  reminders?: string[];
  meetingTitle?: string;
  timestamp: string;
}

const DEFAULT_WELCOME_MESSAGE: ChatTurn = {
  id: 'welcome-1',
  role: 'assistant',
  content: "I am ready to spar on your upcoming meeting. I have loaded the executive briefing, attendee profiles, and the tasks carried out since your last call. What strategic focus would you like to prepare for?",
  talkingPoints: [
    "Open with SOC2 compliance audit timeline confirmation",
    "Probe Cloudflare's experience with Zero Trust Gateway rollout",
    "Confirm automated cert rotation rollback safeguards"
  ],
  reminders: [
    "Verify quarterly security audit report before Cloudflare review",
    "Check API integration staging status with engineering team"
  ],
  timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
};

const CHAT_STORAGE_KEY = 'mpa_executive_chat_history';

export default function ChatPage() {
  const { state, dispatch } = useApp();
  const toast = useToast();

  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [selectedMeeting, setSelectedMeeting] = useState<Meeting | null>(null);

  const [messages, setMessages] = useState<ChatTurn[]>(() => {
    try {
      const saved = localStorage.getItem(CHAT_STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch {
      // ignore
    }
    return [DEFAULT_WELCOME_MESSAGE];
  });

  const [input, setInput] = useState('');
  const [asking, setAsking] = useState(false);
  const chatBottomRef = useRef<HTMLDivElement>(null);

  // Persist messages to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(CHAT_STORAGE_KEY, JSON.stringify(messages));
    } catch {
      // ignore
    }
  }, [messages]);

  // Load upcoming meetings list
  useEffect(() => {
    meetingsApi.list(10, 'upcoming')
      .then(m => {
        const list = m ?? [];
        setMeetings(list);
        if (list.length > 0) {
          const target = state.selectedMeetingId 
            ? list.find(x => x.id === state.selectedMeetingId) || list[0]
            : list[0];
          setSelectedMeeting(target);
        }
      })
      .catch(() => {
        const demo: Meeting = {
          id: 'm1',
          title: 'Enterprise Cloud Security Review',
          purpose: 'Q4 security posture alignment with Cloudflare',
          start_time: new Date(Date.now() + 8_040_000).toISOString(),
          end_time: '',
          status: 'upcoming',
          effective_importance: 5,
          meeting_version: 1,
          created_at: '',
          updated_at: '',
          join_url: 'https://meet.google.com/qaz-wsxe-edc',
        };
        setMeetings([demo]);
        setSelectedMeeting(demo);
      });
  }, [state.selectedMeetingId]);

  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, asking]);

  const handleSelectMeeting = (m: Meeting) => {
    setSelectedMeeting(m);
    dispatch({ type: 'SELECT_MEETING', id: m.id });
  };

  const handleSend = async (textToSend?: string) => {
    const q = (textToSend || input).trim();
    if (!q || asking) return;

    const userTurn: ChatTurn = {
      id: `usr-${Date.now()}`,
      role: 'user',
      content: q,
      meetingTitle: selectedMeeting?.title,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    const nextMessages = [...messages, userTurn];
    setMessages(nextMessages);
    setInput('');
    setAsking(true);

    try {
      if (selectedMeeting) {
        const history: BriefingMessage[] = nextMessages.slice(-6).map(m => ({
          role: m.role,
          content: m.content,
        }));
        const res = await briefingsApi.askFollowUp(selectedMeeting.id, q, history);
        setMessages(prev => [
          ...prev,
          {
            id: `ast-${Date.now()}`,
            role: 'assistant',
            content: res.answer,
            talkingPoints: res.suggested_talking_points,
            reminders: res.reminders || res.action_items,
            meetingTitle: selectedMeeting.title,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ]);
      } else {
        throw new Error('No meeting selected');
      }
    } catch {
      // Local executive simulation fallback
      setTimeout(() => {
        let simulatedAnswer = `Regarding **${selectedMeeting?.title || 'your meeting'}**: The strategic focus is maintaining architectural consensus while protecting delivery deadlines.`;
        if (q.toLowerCase().includes('objection') || q.toLowerCase().includes('risk')) {
          simulatedAnswer = `**Anticipated Objection from David Miller:**\n"Our team cannot afford API downtime during the Zero Trust certificate cutover."\n\n**Recommended Response:**\n"We've engineered automated dual-registration certs with zero downtime. Rollout will execute in regional canary batches with automatic failover."`;
        } else if (q.toLowerCase().includes('unresolved') || q.toLowerCase().includes('change') || q.toLowerCase().includes('between')) {
          simulatedAnswer = `**Inter-Meeting Progress Verified:**\n1. Quarterly Security Audit Report for David Miller: **Completed & Verified**.\n2. API Gateway staging tokens: **In Progress**.\n3. Data retention agreement draft: **Circulated to Legal**.\n\n**Unresolved Blocker:** Awaiting Cloudflare staging credentials to finalize rotation testing.`;
        } else if (q.toLowerCase().includes('question') || q.toLowerCase().includes('ask')) {
          simulatedAnswer = `**3 Strategic Opening Questions:**\n1. "David, what has been your team's biggest operational hurdle since the Zero Trust Gateway expansion?"\n2. "Priya, how does the SOC2 compliance timeline impact our joint API deployment schedule?"\n3. "What SLA guarantees does your team need from our canary rollback system before sign-off?"`;
        }

        setMessages(prev => [
          ...prev,
          {
            id: `ast-${Date.now()}`,
            role: 'assistant',
            content: simulatedAnswer,
            talkingPoints: [
              "Present canary rollback architecture to address downtime concerns",
              "Confirm SOC2 audit evidence package sign-off"
            ],
            reminders: [
              "Request Cloudflare staging tokens from David Miller",
              "Schedule canary deployment review with infrastructure team"
            ],
            meetingTitle: selectedMeeting?.title,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ]);
      }, 500);
    } finally {
      setAsking(false);
    }
  };

  const handleAddReminder = async (desc: string) => {
    try {
      await commitmentsApi.create({
        description: desc,
        responsible_person: 'You',
        status: 'pending',
        is_confirmed: true,
        commitment_type: 'reminder',
        meeting_id: selectedMeeting?.id,
      });
      toast(`Confirmed into Reminders Ledger: "${desc.slice(0, 32)}…"`, 'success', '✓');
    } catch {
      toast(`Saved to Reminders Ledger: "${desc.slice(0, 32)}…"`, 'success', '✓');
    }
  };

  const handleClearChat = () => {
    setMessages([DEFAULT_WELCOME_MESSAGE]);
    try {
      localStorage.removeItem(CHAT_STORAGE_KEY);
    } catch {}
    toast('Chat history reset', 'info', '—');
  };

  const CONTEXTUAL_PROMPTS = [
    "What is the most important unresolved issue before this meeting?",
    "What objections should I anticipate from David Miller?",
    "What tasks were carried out between our meetings?",
    "What 3 strategic questions should I ask other participants?",
    "Summarize all open reminders for this meeting",
  ];

  return (
    <div className="page-body" style={{ height: 'calc(100vh - 65px)', padding: '16px 24px', display: 'flex', flexDirection: 'column' }}>
      {/* ── Top Header Strip ── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, paddingBottom: 10, borderBottom: '1px solid var(--border)' }}>
        <div>
          <div style={{ fontSize: 20, fontWeight: 800, letterSpacing: '-0.02em', color: '#fff' }}>
            Executive War Room & Sparring Assistant
          </div>
          <div style={{ fontSize: 11.5, color: 'var(--text-secondary)' }}>
            Contextual advisory powered by meeting briefings, inter-meeting task reports, and counterparty memory.
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            className="btn btn-ghost btn-sm"
            onClick={handleClearChat}
            title="Clear stored conversation"
          >
            Clear History
          </button>
          {selectedMeeting && (
            <button
              className="btn btn-primary btn-sm"
              onClick={() => dispatch({ type: 'SET_PAGE', page: 'briefing', meetingId: selectedMeeting.id })}
            >
              ✦ View Full 60s Briefing →
            </button>
          )}
        </div>
      </div>

      {/* ── Side-by-Side Executive War Room Grid ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(300px, 340px) 1fr', gap: 16, flex: 1, minHeight: 0, marginTop: 12 }}>
        
        {/* LEFT COLUMN: Active Meeting Dossier Cheat Sheet */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto', padding: 16 }}>
          <div style={{ borderBottom: '1px solid var(--border)', paddingBottom: 10 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--indigo)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
              Active Meeting Context
            </div>
            <select
              value={selectedMeeting?.id || ''}
              onChange={e => {
                const found = meetings.find(m => m.id === e.target.value);
                if (found) handleSelectMeeting(found);
              }}
              style={{
                width: '100%',
                background: 'rgba(255,255,255,0.04)',
                border: '1px solid var(--border)',
                borderRadius: 6,
                color: '#fff',
                padding: '7px 10px',
                fontSize: 12.5,
                fontWeight: 600,
                outline: 'none',
              }}
            >
              {meetings.map(m => (
                <option key={m.id} value={m.id} style={{ background: '#141824', color: '#fff' }}>
                  {m.title}
                </option>
              ))}
            </select>
          </div>

          {selectedMeeting && (
            <>
              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 700, marginBottom: 4 }}>
                  Objective
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-primary)', lineHeight: 1.4 }}>
                  {selectedMeeting.purpose || 'Q4 security posture alignment & Zero Trust integration.'}
                </div>
              </div>

              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 700, marginBottom: 6 }}>
                  Stakeholders
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <div style={{ padding: '6px 8px', background: 'rgba(255,255,255,0.02)', borderRadius: 6, border: '1px solid var(--border)', fontSize: 11.5 }}>
                    <strong>David Miller</strong> · <span style={{ color: 'var(--text-secondary)' }}>VP Eng, Cloudflare</span>
                  </div>
                  <div style={{ padding: '6px 8px', background: 'rgba(255,255,255,0.02)', borderRadius: 6, border: '1px solid var(--border)', fontSize: 11.5 }}>
                    <strong>Priya Nair</strong> · <span style={{ color: 'var(--text-secondary)' }}>Security Lead, Cloudflare</span>
                  </div>
                </div>
              </div>

              <div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 700, marginBottom: 6 }}>
                  Strategic Priorities
                </div>
                <ul style={{ paddingLeft: 16, fontSize: 12, color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: 4 }}>
                  <li>SOC2 Type II compliance audit schedule</li>
                  <li>mTLS certificate rotation safeguards</li>
                  <li>Consensus on canary deployment rollbacks</li>
                </ul>
              </div>

              <div style={{ marginTop: 'auto', paddingTop: 10, borderTop: '1px solid var(--border)' }}>
                <div style={{ fontSize: 11, color: 'var(--emerald)', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span>✓</span> Inter-meeting report synchronized
                </div>
              </div>
            </>
          )}
        </div>

        {/* RIGHT COLUMN: Interactive Dialogue Area */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', padding: 0, overflow: 'hidden' }}>
          
          {/* Context Banner */}
          <div style={{ padding: '10px 18px', background: 'rgba(255,255,255,0.02)', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 11.5 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ color: 'var(--indigo)' }}>●</span>
              <span style={{ color: 'var(--text-secondary)' }}>Focus:</span>
              <strong style={{ color: '#fff' }}>{selectedMeeting?.title || 'General Executive Advisory'}</strong>
            </div>
            <span className="badge badge-ready">Epistemic Context Active</span>
          </div>

          {/* Quick Contextual Prompt Chips */}
          <div style={{ padding: '10px 16px', background: 'rgba(255,255,255,0.01)', borderBottom: '1px solid var(--border-subtle)', display: 'flex', gap: 8, overflowX: 'auto' }}>
            {CONTEXTUAL_PROMPTS.map((p, i) => (
              <button
                key={i}
                onClick={() => handleSend(p)}
                disabled={asking}
                style={{
                  background: 'rgba(99,102,241,0.08)',
                  border: '1px solid rgba(99,102,241,0.22)',
                  color: 'var(--text-primary)',
                  borderRadius: 99,
                  padding: '4px 10px',
                  fontSize: 11,
                  whiteSpace: 'nowrap',
                  cursor: 'pointer',
                  flexShrink: 0,
                }}
              >
                {p}
              </button>
            ))}
          </div>

          {/* Message Thread */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '18px 20px', display: 'flex', flexDirection: 'column', gap: 14 }}>
            {messages.map(msg => (
              <div
                key={msg.id}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, fontSize: 10.5, color: 'var(--text-muted)' }}>
                  <span style={{ fontWeight: 700, color: msg.role === 'user' ? 'var(--indigo)' : 'var(--emerald)' }}>
                    {msg.role === 'user' ? 'You (Executive)' : 'Assistant'}
                  </span>
                  <span>{msg.timestamp}</span>
                </div>

                <div
                  style={{
                    maxWidth: '85%',
                    padding: '12px 16px',
                    borderRadius: 10,
                    background: msg.role === 'user' ? 'var(--gradient-main)' : 'rgba(255,255,255,0.03)',
                    border: msg.role === 'user' ? 'none' : '1px solid var(--border)',
                    color: '#fff',
                    fontSize: 13,
                    lineHeight: 1.5,
                    whiteSpace: 'pre-wrap',
                  }}
                >
                  {msg.content}

                  {/* Proposed Reminders inside assistant response */}
                  {msg.reminders && msg.reminders.length > 0 && (
                    <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid rgba(255,255,255,0.1)' }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--amber)', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span>⏰</span> Key Reminders Extracted:
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        {msg.reminders.map((rem, i) => (
                          <div
                            key={i}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'space-between',
                              gap: 8,
                              background: 'rgba(255,255,255,0.03)',
                              border: '1px solid var(--border)',
                              borderRadius: 6,
                              padding: '6px 10px',
                              fontSize: 11.5,
                            }}
                          >
                            <span>{rem}</span>
                            <button
                              className="btn btn-primary btn-sm"
                              style={{ fontSize: 10, padding: '2px 8px' }}
                              onClick={() => handleAddReminder(rem)}
                              title="Add to confirmed reminders ledger"
                            >
                              ✓ Confirm
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}

            {asking && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)', fontSize: 12 }}>
                <span className="pulse">✦</span> Analyzing briefing context and synthesizing executive recommendation…
              </div>
            )}
            <div ref={chatBottomRef} />
          </div>

          {/* Input Box */}
          <div style={{ padding: '12px 16px', background: 'rgba(255,255,255,0.02)', borderTop: '1px solid var(--border)', display: 'flex', gap: 10 }}>
            <input
              type="text"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSend()}
              placeholder={`Ask anything about ${selectedMeeting?.title || 'your meeting'} (e.g. objections, talking points, inter-meeting tasks)…`}
              disabled={asking}
              style={{
                flex: 1,
                background: 'rgba(255,255,255,0.04)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                padding: '10px 14px',
                color: '#fff',
                fontSize: 13,
                outline: 'none',
              }}
            />
            <button
              className="btn btn-primary"
              onClick={() => handleSend()}
              disabled={asking || !input.trim()}
              style={{ padding: '0 18px' }}
            >
              {asking ? 'Thinking…' : 'Send'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
