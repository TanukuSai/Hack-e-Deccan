// Settings page
import { useState } from 'react';
import { useToast } from '../store';
import { setToken } from '../api';

export default function SettingsPage() {
  const toast = useToast();
  const [apiUrl, setApiUrl] = useState(import.meta.env.VITE_API_URL ?? 'http://localhost:8000');
  const [token, setTokenInput] = useState(localStorage.getItem('mpa_token') ?? '');
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    setToken(token);
    localStorage.setItem('mpa_api_url', apiUrl);
    await new Promise(r => setTimeout(r, 400));
    setSaving(false);
    toast('Settings saved', 'success', '✓');
  };

  const handleHealthCheck = async () => {
    try {
      const res = await fetch(`${apiUrl}/health/dependencies`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      toast(`System status: ${data.status} — DB ${data.dependencies?.database?.status ?? '?'} · LLM ${data.dependencies?.llm_provider?.status ?? '?'}`, 'success', '✓');
    } catch (e: any) { toast(`Health check failed: ${e.message}`, 'error', '✗'); }
  };

  return (
    <div className="page-body fade-in">
      <div style={{ marginBottom: -8 }}>
        <div style={{ fontSize: 20, fontWeight: 800 }}>Settings</div>
        <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>API connection, authentication, and preferences</div>
      </div>

      <div className="card">
        <div className="card-title" style={{ marginBottom: 16 }}>API Connection</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6 }}>API Base URL</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <input style={{ flex: 1, background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-primary)', fontSize: 13, fontFamily: 'var(--font-mono)' }}
                value={apiUrl} onChange={e => setApiUrl(e.target.value)} placeholder="http://localhost:8000" />
              <button className="btn btn-ghost" onClick={handleHealthCheck}>🩺 Test</button>
            </div>
          </div>
          <div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6 }}>Bearer Token (JWT)</div>
            <input type="password" style={{ width: '100%', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border)', borderRadius: 8, padding: '8px 12px', color: 'var(--text-primary)', fontSize: 13, fontFamily: 'var(--font-mono)' }}
              value={token} onChange={e => setTokenInput(e.target.value)} placeholder="eyJhbGci..." />
            <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>
              This token is stored locally and sent as the Authorization header. Get it from Supabase Auth.
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
          <button className={`btn btn-primary ${saving ? 'pulse' : ''}`} onClick={handleSave} disabled={saving}>
            {saving ? 'Saving…' : 'Save Settings'}
          </button>
        </div>
      </div>

      <div className="card">
        <div className="card-title" style={{ marginBottom: 14 }}>About</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {[
            ['Version', '1.0.0 — Gates 1–7 complete'],
            ['API', 'FastAPI + PostgreSQL + Supabase RLS'],
            ['LLM', 'Groq (llama-3.3-70b-versatile)'],
            ['Memory', 'Hindsight (vectorize.io)'],
            ['Test Coverage', '40/40 passing'],
            ['Auth', 'Supabase Auth + Row Level Security'],
          ].map(([label, val]) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--border)', fontSize: 12 }}>
              <span style={{ color: 'var(--text-muted)' }}>{label}</span>
              <span style={{ color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>{val}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
