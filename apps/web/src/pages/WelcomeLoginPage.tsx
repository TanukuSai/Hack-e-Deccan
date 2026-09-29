import { useState } from 'react';
import { authApi } from '../api';
import { useToast } from '../store';

export default function WelcomeLoginPage() {
  const toast = useToast();
  const [includeCalendar, setIncludeCalendar] = useState(true);
  const [loading, setLoading] = useState(false);
  const [showOAuthHelp, setShowOAuthHelp] = useState(false);

  const activeRedirectUri = `${window.location.origin}/auth/google/callback`;
  const defaultClientId = '22523507322-rp2pon0qpqe05o1jgd1fa6hro5ppe4a7.apps.googleusercontent.com';
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID || defaultClientId;

  const handleGoogleSignIn = async () => {
    setLoading(true);
    const redirectUri = activeRedirectUri;
    const state = Math.random().toString(36).substring(2, 15);
    sessionStorage.setItem('oauth_state', state);

    try {
      const res = await authApi.getGoogleAuthUrl(redirectUri, includeCalendar, state);
      if (res.authorization_url) {
        window.location.href = res.authorization_url;
      }
    } catch {
      toast('Opening Google OAuth consent...', 'info', '🔗');
      const scopes = [
        'openid',
        'https://www.googleapis.com/auth/userinfo.email',
        'https://www.googleapis.com/auth/userinfo.profile',
      ];
      if (includeCalendar) {
        scopes.push(
          'https://www.googleapis.com/auth/calendar.readonly',
          'https://www.googleapis.com/auth/documents.readonly'
        );
      }
      const authUrl = `https://accounts.google.com/o/oauth2/auth?client_id=${encodeURIComponent(clientId)}&redirect_uri=${encodeURIComponent(redirectUri)}&response_type=code&scope=${encodeURIComponent(scopes.join(' '))}&access_type=offline&prompt=consent&state=${state}`;
      window.location.href = authUrl;
    } finally {
      setLoading(false);
    }
  };

  const handleCopyUri = () => {
    navigator.clipboard.writeText(activeRedirectUri);
    toast('Copied Redirect URI to clipboard', 'success', '📋');
  };

  return (
    <div style={{
      minHeight: '100vh',
      width: '100%',
      background: 'radial-gradient(ellipse at 50% 10%, rgba(99, 102, 241, 0.12) 0%, #090a0f 70%)',
      display: 'flex',
      flexDirection: 'column',
      color: 'var(--text-primary)',
      fontFamily: 'var(--font-sans)',
    }}>
      {/* Top Header */}
      <header style={{
        padding: '20px 36px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 34,
            height: 34,
            borderRadius: 9,
            background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.3), rgba(139, 92, 246, 0.3))',
            border: '1px solid rgba(99, 102, 241, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 18,
            color: 'var(--indigo)',
          }}>
            ✦
          </div>
          <div>
            <span style={{ fontSize: 16, fontWeight: 700, letterSpacing: -0.3 }}>Executive Prep</span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 8 }}>v2.4 Executive Edition</span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Protected by Supabase RLS</span>
          <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--success)' }} />
        </div>
      </header>

      {/* Main Grid Content */}
      <div style={{
        flex: 1,
        maxWidth: 1180,
        width: '100%',
        margin: '0 auto',
        padding: '40px 24px',
        display: 'grid',
        gridTemplateColumns: 'minmax(320px, 1.15fr) minmax(340px, 0.85fr)',
        gap: 48,
        alignItems: 'center',
      }}>
        {/* Left Column: Value Proposition & Product Architecture */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          <div>
            <div style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '4px 12px',
              borderRadius: 20,
              background: 'rgba(99, 102, 241, 0.1)',
              border: '1px solid rgba(99, 102, 241, 0.3)',
              color: 'var(--indigo)',
              fontSize: 12,
              fontWeight: 600,
              marginBottom: 16,
            }}>
              <span>✦</span> HINDSIGHT MEMORY &amp; OPENCLAW POWERED
            </div>
            <h1 style={{
              fontSize: 40,
              fontWeight: 800,
              lineHeight: 1.15,
              letterSpacing: -1,
              marginBottom: 16,
              background: 'linear-gradient(180deg, #FFFFFF 30%, #A5B4FC 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
            }}>
              The Autonomous Chief of Staff for High-Stakes Meetings
            </h1>
            <p style={{
              fontSize: 16,
              lineHeight: 1.6,
              color: 'var(--text-secondary)',
              maxWidth: 540,
            }}>
              Zero prompt fatigue. Prepares strategic 60-second briefings, verifies direct evidence against model inferences, links inter-meeting task deliverables, and guarantees Two-Party Consent during live attendance.
            </p>
          </div>

          {/* 4 Architectural Highlights */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: 16,
            marginTop: 8,
          }}>
            <div style={{
              background: 'rgba(255, 255, 255, 0.02)',
              border: '1px solid var(--border)',
              borderRadius: 12,
              padding: 16,
            }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
                ⚡ 60-Second Scan
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                Three strategic pillars: guardrails, verified talking points, and counter-arguments.
              </div>
            </div>

            <div style={{
              background: 'rgba(255, 255, 255, 0.02)',
              border: '1px solid var(--border)',
              borderRadius: 12,
              padding: 16,
            }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
                🧠 Hindsight Memory
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                Remembers attendee negotiation history and correlates inter-meeting deliverables.
              </div>
            </div>

            <div style={{
              background: 'rgba(255, 255, 255, 0.02)',
              border: '1px solid var(--border)',
              borderRadius: 12,
              padding: 16,
            }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
                🛡️ Epistemic Truth
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                Direct facts are tagged with clickable citations; model inferences are never faked.
              </div>
            </div>

            <div style={{
              background: 'rgba(255, 255, 255, 0.02)',
              border: '1px solid var(--border)',
              borderRadius: 12,
              padding: 16,
            }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
                🤖 OpenClaw Live
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                Local gateway attendance with strict Two-Party Consent and SHA-256 transcript hashing.
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Sign In Card */}
        <div style={{
          background: 'var(--surface-primary)',
          border: '1px solid rgba(99, 102, 241, 0.3)',
          borderRadius: 20,
          boxShadow: '0 24px 64px rgba(0, 0, 0, 0.6), 0 0 32px rgba(99, 102, 241, 0.1)',
          padding: 36,
          display: 'flex',
          flexDirection: 'column',
          gap: 20,
        }}>
          <div>
            <div style={{ fontSize: 20, fontWeight: 800, color: 'var(--text-primary)', marginBottom: 4 }}>
              Sign in to your Executive Space
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
              Choose your authentication method to access your briefings and schedule.
            </div>
          </div>

          {/* Primary Action: Google OAuth Sign In */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <button
              className="btn btn-primary"
              onClick={handleGoogleSignIn}
              disabled={loading}
              style={{
                padding: '13px 20px',
                fontSize: 14,
                fontWeight: 700,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 12,
                borderRadius: 10,
              }}
            >
              <svg width="18" height="18" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
              </svg>
              {loading ? 'Connecting Google Account...' : 'Sign in with Google'}
            </button>

            <label style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              fontSize: 11,
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              marginTop: 2,
            }}>
              <input
                type="checkbox"
                checked={includeCalendar}
                onChange={e => setIncludeCalendar(e.target.checked)}
                style={{ width: 14, height: 14, accentColor: 'var(--primary)' }}
              />
              <span>Grant Google Calendar &amp; Docs Read Access (Recommended)</span>
            </label>
          </div>

          {/* Security & Compliance Invariant Notice */}
          <div style={{
            background: 'rgba(255, 255, 255, 0.02)',
            border: '1px solid var(--border)',
            borderRadius: 10,
            padding: '12px 14px',
            fontSize: 12,
            color: 'var(--text-secondary)',
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 600, color: 'var(--text-primary)' }}>
              <span>🛡️</span> Enterprise Privacy Guardrails
            </div>
            <div style={{ fontSize: 11, lineHeight: 1.4 }}>
              • <strong>Draft-Only Invariant:</strong> Zero autonomous email dispatch. Follow-ups remain in human review.<br/>
              • <strong>Two-Party Consent Gate:</strong> Recording and transcription strictly blocked without legal consent.<br/>
              • <strong>Tenant Isolation:</strong> Data partitioned at the database engine level via PostgreSQL RLS.
            </div>
          </div>

          {/* Collapsible OAuth & Testing Guidance */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
              <button
                className="btn btn-ghost"
                onClick={() => setShowOAuthHelp(v => !v)}
                style={{ fontSize: 11, color: 'var(--indigo)', padding: '2px 4px' }}
              >
                {showOAuthHelp ? 'Hide Google Cloud Guide ▲' : 'Google OAuth Configuration Guide ▼'}
              </button>
            </div>

            {showOAuthHelp && (
              <div style={{
                background: 'rgba(239, 68, 68, 0.05)',
                border: '1px solid rgba(239, 68, 68, 0.25)',
                borderRadius: 8,
                padding: '12px 14px',
                fontSize: 11,
                marginTop: 8,
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
              }}>
                <div>
                  <strong style={{ color: 'var(--rose)', display: 'block', marginBottom: 2 }}>
                    1. Fix "Error 403: access_denied" (App in Testing Mode)
                  </strong>
                  <span style={{ color: 'var(--text-secondary)' }}>
                    Google Cloud blocks unapproved accounts when the OAuth consent screen is unpublished. To allow <code>saitanuku81@gmail.com</code>:
                  </span>
                  <ol style={{ paddingLeft: 18, margin: '4px 0', color: 'var(--text-muted)' }}>
                    <li>Open <a href="https://console.cloud.google.com/apis/credentials/consent?project=neuro-play-a2c9ny" target="_blank" rel="noreferrer" style={{ color: 'var(--indigo)', textDecoration: 'underline' }}>Google Cloud OAuth Consent Screen</a></li>
                    <li>Scroll down to <strong>Test users</strong> and click <strong>+ ADD USERS</strong></li>
                    <li>Add <code>saitanuku81@gmail.com</code> &amp; <code>saitanuku460@gmail.com</code> and click <strong>Save</strong>.</li>
                  </ol>
                </div>

                <div>
                  <strong style={{ color: 'var(--warning)', display: 'block', marginBottom: 2 }}>
                    2. Fix "Error 400: redirect_uri_mismatch"
                  </strong>
                  <span style={{ color: 'var(--text-secondary)' }}>
                    Ensure your authorized redirect URI in Google Cloud Credentials includes:
                  </span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(0,0,0,0.3)', padding: '5px 8px', borderRadius: 4, fontFamily: 'var(--font-mono)', fontSize: 10, marginTop: 4 }}>
                    <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis' }}>{activeRedirectUri}</span>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={handleCopyUri}
                      style={{ fontSize: 10, padding: '2px 6px', color: 'var(--primary)' }}
                    >
                      Copy
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
