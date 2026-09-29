import { useState } from 'react';
import { authApi } from './api';
import { useToast } from './store';

export default function AuthModal({ onDismiss }: { onDismiss?: () => void }) {
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
      // Direct fallback to Google OAuth endpoint if backend route is slow
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
      position: 'fixed',
      top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(9, 11, 17, 0.88)',
      backdropFilter: 'blur(10px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 9999,
      padding: 16
    }}>
      <div className="card fade-in" style={{
        maxWidth: 540,
        width: '100%',
        background: 'var(--surface-primary)',
        borderColor: 'rgba(99, 102, 241, 0.35)',
        boxShadow: '0 24px 64px rgba(0, 0, 0, 0.6), 0 0 32px rgba(99, 102, 241, 0.15)',
        padding: 32,
        borderRadius: 16,
        position: 'relative',
      }}>
        {/* Close Button */}
        {onDismiss && (
          <button
            onClick={onDismiss}
            style={{
              position: 'absolute',
              top: 18,
              right: 18,
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              fontSize: 18,
              cursor: 'pointer',
              padding: '4px 8px',
              borderRadius: 6,
            }}
            title="Close"
          >
            ✕
          </button>
        )}

        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: 20 }}>
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 52,
            height: 52,
            borderRadius: 14,
            background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(139, 92, 246, 0.2))',
            border: '1px solid rgba(99, 102, 241, 0.4)',
            fontSize: 26,
            marginBottom: 12,
          }}>
            ✦
          </div>
          <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-primary)' }}>
            Meeting Prep Agent
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
            Autonomous intelligence briefings, reminder tracking & inter-meeting sync
          </div>
        </div>

        {/* OAuth Permissions Disclosure Card */}
        <div style={{
          background: 'rgba(255, 255, 255, 0.03)',
          border: '1px solid var(--border)',
          borderRadius: 10,
          padding: 14,
          marginBottom: 16,
          fontSize: 12,
        }}>
          <div style={{ fontWeight: 700, marginBottom: 8, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span>🔒</span> Permissions & Access
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, color: 'var(--text-secondary)' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
              <span style={{ color: 'var(--success)' }}>✓</span>
              <div>
                <strong style={{ color: 'var(--text-primary)' }}>Identity Profile:</strong> Authenticate account and isolate your tenant database.
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
              <span style={{ color: includeCalendar ? 'var(--primary)' : 'var(--text-muted)' }}>
                {includeCalendar ? '✓' : '○'}
              </span>
              <div>
                <strong style={{ color: 'var(--text-primary)' }}>Calendar & Documents (Read-Only):</strong> Automatically detect meetings and pull linked agendas to build briefings.
              </div>
            </div>
          </div>

          <label style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            marginTop: 10,
            paddingTop: 8,
            borderTop: '1px solid var(--border)',
            cursor: 'pointer',
            fontWeight: 600,
            color: 'var(--text-primary)',
          }}>
            <input
              type="checkbox"
              checked={includeCalendar}
              onChange={e => setIncludeCalendar(e.target.checked)}
              style={{ width: 16, height: 16, accentColor: 'var(--primary)', cursor: 'pointer' }}
            />
            <span>Include Calendar & Docs permissions (Recommended)</span>
          </label>
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <button
            className="btn btn-primary"
            onClick={handleGoogleSignIn}
            disabled={loading}
            style={{
              padding: '12px 20px',
              fontSize: 14,
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 10,
            }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
            </svg>
            {loading ? 'Connecting...' : 'Sign in with Google'}
          </button>

          {/* Privacy & Governance Notice */}
          <div style={{
            background: 'rgba(255, 255, 255, 0.02)',
            border: '1px solid var(--border)',
            borderRadius: 8,
            padding: '10px 12px',
            fontSize: 11,
            color: 'var(--text-secondary)',
            marginTop: 4,
          }}>
            <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2 }}>
              🛡️ Enterprise Compliance Guardrails
            </div>
            <div>
              Strict Draft-Only invariant enforced for all communications. Two-Party Consent legally required for live attendance and transcription.
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 4 }}>
            <button
              className="btn btn-ghost"
              onClick={() => setShowOAuthHelp(v => !v)}
              style={{ fontSize: 11, color: 'var(--indigo)', padding: '2px 4px' }}
            >
              {showOAuthHelp ? 'Hide Google Cloud Guide ▲' : 'Google OAuth Configuration Guide ▼'}
            </button>
          </div>

          {/* OAuth Troubleshooting & Redirect URI Info */}
          {showOAuthHelp && (
            <div style={{
              background: 'rgba(239, 68, 68, 0.05)',
              border: '1px solid rgba(239, 68, 68, 0.25)',
              borderRadius: 8,
              padding: '12px 14px',
              fontSize: 11,
              marginTop: 6,
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
            }}>
              <div>
                <strong style={{ color: 'var(--rose)', display: 'block', marginBottom: 2 }}>
                  1. Fix "Error 403: access_denied" (App in Testing Mode)
                </strong>
                <span style={{ color: 'var(--text-secondary)' }}>
                  Google Cloud blocks unapproved accounts when the OAuth consent screen is unpublished. To allow <code>saitanuku81@gmail.com</code> and <code>saitanuku460@gmail.com</code>:
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
  );
}
