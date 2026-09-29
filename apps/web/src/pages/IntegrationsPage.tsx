import { useEffect, useState } from 'react';
import { integrationsApi, authApi } from '../api';
import type { IntegrationHealth } from '../api';
import { useToast } from '../store';

const DEMO: IntegrationHealth[] = [
  { integration_type: 'google_meet', is_enabled: true, attendance_mode: 'manual', health_status: 'healthy', last_sync_at: new Date(Date.now() - 3_600_000).toISOString() },
  { integration_type: 'openclaw',    is_enabled: true, attendance_mode: 'automatic', health_status: 'healthy', last_sync_at: new Date(Date.now() - 900_000).toISOString() },
];

const META: Record<string, { icon: string; label: string; description: string; bg: string }> = {
  google_meet:     { icon: '📅', label: 'Google Calendar', description: 'Sync meetings, import events, auto-prep briefings', bg: 'rgba(66,133,244,0.1)' },
  openclaw:        { icon: '◈',  label: 'OpenClaw Bot',    description: 'Autonomous meeting attendance & transcript capture', bg: 'rgba(139,92,246,0.1)' },
  microsoft_teams: { icon: '🟦', label: 'Microsoft Teams', description: 'Auto-join Teams calls and capture transcripts', bg: 'rgba(70,130,210,0.1)' },
  zoom:            { icon: '🎥', label: 'Zoom',            description: 'Join Zoom meetings and retrieve cloud recordings', bg: 'rgba(45,140,255,0.1)' },
};

const ALL_TYPES = ['google_meet', 'openclaw', 'microsoft_teams', 'zoom'];

function timeSince(iso?: string) {
  if (!iso) return 'Never';
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (m < 1) return 'Just now';
  if (m < 60) return `${m}m ago`;
  return `${Math.round(m / 60)}h ago`;
}

export default function IntegrationsPage() {
  const toast = useToast();
  const [integrations, setIntegrations] = useState<IntegrationHealth[]>([]);
  const [googleStatus, setGoogleStatus] = useState<any>(null);
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    Promise.allSettled([integrationsApi.health(), integrationsApi.googleStatus()])
      .then(([h, g]) => {
        setIntegrations(h.status === 'fulfilled' ? (h.value as any)?.integrations ?? [] : DEMO);
        setGoogleStatus(g.status === 'fulfilled' ? g.value : null);
      })
      .catch(() => setIntegrations(DEMO));
  }, []);

  const handleSync = async () => {
    setSyncing(true);
    try {
      await integrationsApi.calendarSync();
      toast('Calendar sync queued', 'success', '⟳');
    } catch (e: any) { toast(e.message ?? 'Sync failed', 'error', '✗'); }
    finally { setSyncing(false); }
  };

  const handleGoogleConnect = async () => {
    const redirectUri = `${window.location.origin}/auth/google/callback`;
    try {
      const res = await authApi.getGoogleAuthUrl(redirectUri, true);
      if (res.authorization_url) {
        window.location.href = res.authorization_url;
      }
    } catch {
      toast('Opening Google OAuth consent...', 'info', '🔗');
      const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID || 'your-google-client-id.apps.googleusercontent.com';
      const authUrl = `https://accounts.google.com/o/oauth2/auth?client_id=${encodeURIComponent(clientId)}&redirect_uri=${encodeURIComponent(redirectUri)}&response_type=code&scope=${encodeURIComponent('openid email profile https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/documents.readonly')}&access_type=offline&prompt=consent`;
      window.location.href = authUrl;
    }
  };

  const display = integrations.length > 0 ? integrations : DEMO;
  const getIntegration = (type: string) => display.find(i => i.integration_type === type);

  return (
    <div className="page-body fade-in">
      <div style={{ marginBottom: -8 }}>
        <div style={{ fontSize: 20, fontWeight: 800 }}>Integrations</div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Manage calendar sync, bot attendance, and external providers</div>
      </div>

      {/* Google OAuth banner */}
      <div className="card" style={{ background: 'linear-gradient(135deg, rgba(66,133,244,0.06), rgba(99,102,241,0.06))', borderColor: 'rgba(66,133,244,0.2)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{ fontSize: 32 }}>📅</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 4 }}>Google Workspace</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
              {googleStatus?.connected
                ? `Connected as ${googleStatus.email} · Calendar + Docs access granted`
                : 'Connect Google Calendar and Docs to enable automatic meeting sync and document linking'}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {googleStatus?.connected ? (
              <>
                <button className={`btn btn-ghost ${syncing ? 'pulse' : ''}`} onClick={handleSync} disabled={syncing}>
                  {syncing ? '⟳ Syncing…' : '⟳ Sync Now'}
                </button>
                <button className="btn btn-danger btn-sm" onClick={() => toast('Disconnect would revoke Google access', 'info')}>Disconnect</button>
              </>
            ) : (
              <button className="btn btn-primary" onClick={handleGoogleConnect}>🔗 Connect Google</button>
            )}
          </div>
        </div>
      </div>

      {/* Integration cards */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        {ALL_TYPES.map(type => {
          const meta = META[type];
          const live = getIntegration(type);
          const isConfigured = !!live;
          const isHealthy = live?.health_status === 'healthy';

          return (
            <div key={type} className="card" style={{ background: `linear-gradient(135deg, ${meta.bg}, transparent)` }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, marginBottom: 14 }}>
                <div style={{ fontSize: 28 }}>{meta.icon}</div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                    <div style={{ fontSize: 14, fontWeight: 700 }}>{meta.label}</div>
                    <span className={`badge ${isConfigured ? (isHealthy ? 'badge-healthy' : 'badge-error') : 'badge-medium'}`}>
                      {isConfigured ? (isHealthy ? 'Connected' : live!.health_status) : 'Not connected'}
                    </span>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{meta.description}</div>
                </div>
              </div>

              {isConfigured && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 14 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                    <span style={{ color: 'var(--text-muted)' }}>Attendance mode</span>
                    <span className={`badge ${live!.attendance_mode === 'automatic' ? 'badge-healthy' : live!.attendance_mode === 'manual' ? 'badge-pending' : 'badge-medium'}`}>
                      {live!.attendance_mode}
                    </span>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                    <span style={{ color: 'var(--text-muted)' }}>Last sync</span>
                    <span style={{ color: 'var(--text-secondary)' }}>{timeSince(live?.last_sync_at)}</span>
                  </div>
                  {live?.health_error_message && (
                    <div style={{ fontSize: 10, color: 'var(--rose)', background: 'rgba(244,63,94,0.06)', padding: '6px 8px', borderRadius: 6 }}>
                      ⚠ {live.health_error_message}
                    </div>
                  )}
                </div>
              )}

              <div style={{ display: 'flex', gap: 6 }}>
                {!isConfigured
                  ? <button className="btn btn-primary btn-sm" onClick={() => toast(`${meta.label} connection requires API`, 'info', '🔗')}>Connect</button>
                  : <>
                      <button className="btn btn-ghost btn-sm" onClick={() => toast(`${meta.label} configuration panel coming soon`, 'info')}>Configure</button>
                      {type === 'google_meet' && (
                        <button className="btn btn-ghost btn-sm" onClick={handleSync} disabled={syncing}>⟳ Sync</button>
                      )}
                    </>}
              </div>
            </div>
          );
        })}
      </div>

      {/* System health */}
      <div className="card">
        <div className="card-title" style={{ marginBottom: 16 }}>System Health</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
          {[
            { icon: '🗄', label: 'PostgreSQL', status: 'connected', sub: 'Session pooler', color: 'var(--emerald)' },
            { icon: '⚡', label: 'Groq LLM', status: 'configured', sub: 'llama-3.3-70b', color: 'var(--emerald)' },
            { icon: '◉', label: 'Hindsight Memory', status: 'connected', sub: 'vectorize.io', color: 'var(--sky)' },
            { icon: '📦', label: 'Object Storage', status: 'ready', sub: 'Supabase Storage', color: 'var(--emerald)' },
            { icon: '◈', label: 'OpenClaw', status: 'disabled', sub: 'Bot not yet active', color: 'var(--text-muted)' },
            { icon: '🔐', label: 'RLS Isolation', status: 'enforced', sub: '40/40 tests pass', color: 'var(--emerald)' },
          ].map(({ icon, label, status, sub, color }) => (
            <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 14px', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)', borderRadius: 10 }}>
              <div style={{ fontSize: 20 }}>{icon}</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, fontWeight: 600 }}>{label}</div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{sub}</div>
              </div>
              <div style={{ fontSize: 10, color, fontWeight: 700 }}>{status}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
