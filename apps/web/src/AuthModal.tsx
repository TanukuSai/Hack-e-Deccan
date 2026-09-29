import { useState } from 'react';
import { authApi, setToken } from './api';
import { useApp, useToast } from './store';

export default function AuthModal({ onDismiss }: { onDismiss?: () => void }) {
  const { dispatch } = useApp();
  const toast = useToast();
  const [includeCalendar, setIncludeCalendar] = useState(true);
  const [loading, setLoading] = useState(false);
  const [devEmail, setDevEmail] = useState('');
  const [showDevCustom, setShowDevCustom] = useState(false);

  const handleGoogleSignIn = async () => {
    setLoading(true);
    const redirectUri = `${window.location.origin}/auth/google/callback`;
    const state = Math.random().toString(36).substring(2, 15);
    sessionStorage.setItem('oauth_state', state);

    try {
      const res = await authApi.getGoogleAuthUrl(redirectUri, includeCalendar, state);
      if (res.authorization_url) {
        window.location.href = res.authorization_url;
      }
    } catch {
      toast('Redirecting to Google OAuth...', 'info', '🔗');
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
      const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID || 'your-google-client-id.apps.googleusercontent.com';
      const authUrl = `https://accounts.google.com/o/oauth2/auth?client_id=${encodeURIComponent(clientId)}&redirect_uri=${encodeURIComponent(redirectUri)}&response_type=code&scope=${encodeURIComponent(scopes.join(' '))}&access_type=offline&prompt=consent&state=${state}`;
      window.location.href = authUrl;
    } finally {
      setLoading(false);
    }
  };

  const handleDevLogin = async (customEmail?: string) => {
    setLoading(true);
    try {
      const res = await authApi.devLogin(
        customEmail || 'alex.mercer@executive.ai',
        customEmail ? customEmail.split('@')[0] : 'Alex Mercer'
      );
      setToken(res.access_token);
      dispatch({ type: 'LOGIN', user: res.user });
      toast(`Signed in as ${res.user.email}`, 'success', '✓');
      if (onDismiss) onDismiss();
    } catch {
      // Local fallback for offline mode
      const dummyUser = {
        id: '12194ecc-c581-4a81-a7ef-9bea2e8bcd58',
        email: customEmail || 'alex.mercer@executive.ai',
        full_name: 'Alex Mercer (Executive)',
        account_status: 'active',
        monthly_budget_usd: 25.0,
        current_month_spend_usd: 1.45,
      };
      setToken('dev-fallback-token');
      dispatch({ type: 'LOGIN', user: dummyUser });
      toast('Signed in (Local Demo Session)', 'success', '✓');
      if (onDismiss) onDismiss();
    } finally {
      setLoading(false);
    }
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
        maxWidth: 520,
        width: '100%',
        background: 'var(--surface-primary)',
        borderColor: 'rgba(99, 102, 241, 0.35)',
        boxShadow: '0 24px 64px rgba(0, 0, 0, 0.6), 0 0 32px rgba(99, 102, 241, 0.15)',
        padding: 32,
        borderRadius: 16,
      }}>
        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 56,
            height: 56,
            borderRadius: 14,
            background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(139, 92, 246, 0.2))',
            border: '1px solid rgba(99, 102, 241, 0.4)',
            fontSize: 28,
            marginBottom: 14,
          }}>
            ✦
          </div>
          <div style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-primary)' }}>
            Meeting Prep Agent
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4 }}>
            Autonomous intelligence briefings & decision tracking
          </div>
        </div>

        {/* OAuth Permissions Disclosure Card */}
        <div style={{
          background: 'rgba(255, 255, 255, 0.03)',
          border: '1px solid var(--border)',
          borderRadius: 10,
          padding: 16,
          marginBottom: 20,
          fontSize: 12,
        }}>
          <div style={{ fontWeight: 700, marginBottom: 8, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: 6 }}>
            <span>🔒</span> Permissions & Access
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, color: 'var(--text-secondary)' }}>
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
            marginTop: 12,
            paddingTop: 10,
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
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
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

          <div style={{ display: 'flex', alignItems: 'center', gap: 12, margin: '4px 0' }}>
            <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
            <span style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
              or quick evaluation
            </span>
            <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
          </div>

          <button
            className="btn btn-ghost"
            onClick={() => handleDevLogin()}
            disabled={loading}
            style={{
              padding: '10px 16px',
              fontSize: 13,
              fontWeight: 600,
              background: 'rgba(255, 255, 255, 0.04)',
            }}
          >
            ⚡ One-Click Demo Executive Login
          </button>

          {!showDevCustom ? (
            <button
              className="btn btn-ghost"
              onClick={() => setShowDevCustom(true)}
              style={{ fontSize: 11, color: 'var(--text-muted)', padding: 4 }}
            >
              Custom test email…
            </button>
          ) : (
            <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
              <input
                type="email"
                placeholder="your-test-email@example.com"
                value={devEmail}
                onChange={e => setDevEmail(e.target.value)}
                style={{
                  flex: 1,
                  padding: '6px 10px',
                  background: 'var(--surface-input)',
                  border: '1px solid var(--border)',
                  borderRadius: 6,
                  color: 'var(--text-primary)',
                  fontSize: 12,
                }}
              />
              <button
                className="btn btn-primary btn-sm"
                onClick={() => handleDevLogin(devEmail)}
                disabled={!devEmail.includes('@')}
              >
                Go
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
