import { useEffect, useState } from 'react';
import { AppProvider, useApp, useToast } from './store';
import Sidebar from './Sidebar';
import ToastArea from './ToastArea';
import AuthModal from './AuthModal';
import { authApi, setToken } from './api';
import DashboardPage   from './pages/DashboardPage';
import MeetingsPage    from './pages/MeetingsPage';
import BriefingPage    from './pages/BriefingPage';
import ChatPage        from './pages/ChatPage';
import CommitmentsPage from './pages/CommitmentsPage';
import ContactsPage    from './pages/ContactsPage';
import ProjectsPage    from './pages/ProjectsPage';
import IntelligencePage from './pages/IntelligencePage';
import IntegrationsPage from './pages/IntegrationsPage';
import SettingsPage    from './pages/SettingsPage';

const PAGE_META: Record<string, { title: string; subtitle: string }> = {
  chat:         { title: 'Agent Chat',          subtitle: 'Contextual Executive Sparring & Pre-Meeting Advisory' },
  dashboard:    { title: 'Executive Command',   subtitle: 'Daily Operating Context & Action Triage' },
  briefing:     { title: 'Meeting Briefing',    subtitle: '60-Second Epistemic Dossier & Strategic Priorities' },
  commitments:  { title: 'Reminders Ledger',    subtitle: 'Commitments Needing Confirmation & Triage' },
  meetings:     { title: 'Meeting Schedule',    subtitle: 'Upcoming Calendar & Preparation Status' },
  contacts:     { title: 'Stakeholder Dossiers',subtitle: 'Counterparty Intelligence & Interaction History' },
  projects:     { title: 'Key Initiatives',     subtitle: 'Strategic Project Engagements & Deliverables' },
  intelligence: { title: 'Deep Intelligence',   subtitle: 'OpenClaw Reconnaissance & Long-Term Memory' },
  integrations: { title: 'Integrations & Bot',  subtitle: 'Google Calendar, OpenClaw Attendance & Memory' },
  settings:     { title: 'Settings',            subtitle: 'Tenant Preferences & Operational Parameters' },
};

function Router() {
  const { state } = useApp();
  switch (state.page) {
    case 'chat':         return <ChatPage />;
    case 'dashboard':    return <DashboardPage />;
    case 'meetings':     return <MeetingsPage />;
    case 'briefing':     return <BriefingPage />;
    case 'commitments':  return <CommitmentsPage />;
    case 'contacts':     return <ContactsPage />;
    case 'projects':     return <ProjectsPage />;
    case 'intelligence': return <IntelligencePage />;
    case 'integrations': return <IntegrationsPage />;
    case 'settings':     return <SettingsPage />;
    default:             return <ChatPage />;
  }
}

function Shell() {
  const { state, dispatch } = useApp();
  const toast = useToast();
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  // Check for Google OAuth callback code in URL
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const callbackState = params.get('state');

    if (code) {
      const redirectUri = `${window.location.origin}/auth/google/callback`;
      toast('Connecting Google account...', 'info', '✦');

      authApi.googleCallback(code, redirectUri, callbackState || undefined)
        .then(res => {
          setToken(res.access_token);
          dispatch({ type: 'LOGIN', user: res.user });
          toast(`Connected as ${res.user.full_name || res.user.email}!`, 'success', '✓');
        })
        .catch(err => {
          toast(err.message || 'Google Sign-In failed', 'error', '✗');
        })
        .finally(() => {
          window.history.replaceState({}, document.title, window.location.pathname);
        });
    }
  }, [dispatch, toast]);

  const currentMeta = PAGE_META[state.page] || { title: 'Executive Assistant', subtitle: 'Autonomous Meeting Intelligence' };

  return (
    <div className="app-layout">
      {/* Mobile top navigation header */}
      <div className="mobile-header">
        <div className="mobile-brand">
          <span style={{ color: 'var(--indigo)' }}>✦</span> Executive Prep
        </div>
        <button
          className="mobile-nav-toggle"
          onClick={() => setMobileOpen(!mobileOpen)}
          aria-label="Toggle navigation menu"
        >
          {mobileOpen ? '✕' : '☰'}
        </button>
      </div>

      {/* Mobile backdrop */}
      {mobileOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.6)',
            zIndex: 45,
          }}
          onClick={() => setMobileOpen(false)}
        />
      )}

      <Sidebar
        onOpenAuth={() => setShowAuthModal(true)}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />

      <main className="main-content">
        <header className="topbar">
          <div>
            <div className="topbar-title">{currentMeta.title}</div>
            <div className="topbar-subtitle">{currentMeta.subtitle}</div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {state.isAuthenticated && state.user ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <span className="badge badge-healthy" style={{ fontSize: 10 }}>
                  ✓ {state.user.full_name || state.user.email}
                </span>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => dispatch({ type: 'LOGOUT' })}
                  title="Sign out"
                >
                  Sign Out
                </button>
              </div>
            ) : (
              <button
                className="btn btn-primary btn-sm"
                onClick={() => setShowAuthModal(true)}
              >
                Sign In
              </button>
            )}
          </div>
        </header>

        <Router />
      </main>

      <ToastArea />
      {showAuthModal && <AuthModal onDismiss={() => setShowAuthModal(false)} />}
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  );
}
