import { useEffect, useState } from 'react';
import { AppProvider, useApp, useToast } from './store';
import Sidebar from './Sidebar';
import ToastArea from './ToastArea';
import AuthModal from './AuthModal';
import { authApi, setToken } from './api';
import DashboardPage   from './pages/DashboardPage';
import MeetingsPage    from './pages/MeetingsPage';
import BriefingPage    from './pages/BriefingPage';
import CommitmentsPage from './pages/CommitmentsPage';
import ContactsPage    from './pages/ContactsPage';
import ProjectsPage    from './pages/ProjectsPage';
import IntelligencePage from './pages/IntelligencePage';
import IntegrationsPage from './pages/IntegrationsPage';
import SettingsPage    from './pages/SettingsPage';

const PAGE_TITLES: Record<string, string> = {
  dashboard:    'Dashboard',
  meetings:     'Meetings',
  briefing:     'Briefings',
  commitments:  'Commitments',
  contacts:     'Contacts',
  projects:     'Projects',
  intelligence: 'Intelligence',
  integrations: 'Integrations',
  settings:     'Settings',
};

function Router() {
  const { state } = useApp();
  switch (state.page) {
    case 'dashboard':    return <DashboardPage />;
    case 'meetings':     return <MeetingsPage />;
    case 'briefing':     return <BriefingPage />;
    case 'commitments':  return <CommitmentsPage />;
    case 'contacts':     return <ContactsPage />;
    case 'projects':     return <ProjectsPage />;
    case 'intelligence': return <IntelligencePage />;
    case 'integrations': return <IntegrationsPage />;
    case 'settings':     return <SettingsPage />;
    default:             return <DashboardPage />;
  }
}

function Shell() {
  const { state, dispatch } = useApp();
  const toast = useToast();
  const [showAuthModal, setShowAuthModal] = useState(false);

  // Check for Google OAuth callback code in URL
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const callbackState = params.get('state');

    if (code) {
      const redirectUri = `${window.location.origin}/auth/google/callback`;
      toast('Exchanging Google credentials...', 'info', '✦');

      authApi.googleCallback(code, redirectUri, callbackState || undefined)
        .then(res => {
          setToken(res.access_token);
          dispatch({ type: 'LOGIN', user: res.user });
          toast(`Welcome, ${res.user.full_name || res.user.email}!`, 'success', '✓');
        })
        .catch(err => {
          toast(err.message || 'Google Sign-In failed', 'error', '✗');
        })
        .finally(() => {
          // Clean code and query params from URL without refreshing
          window.history.replaceState({}, document.title, window.location.pathname);
        });
    }
  }, [dispatch, toast]);

  return (
    <div className="app-layout">
      <Sidebar onOpenAuth={() => setShowAuthModal(true)} />
      <main className="main-content">
        <div className="topbar">
          <div>
            <div className="topbar-title">{PAGE_TITLES[state.page]}</div>
            <div className="topbar-subtitle">Meeting Prep Agent</div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {state.isAuthenticated && state.user ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span className="badge badge-healthy" style={{ fontSize: 11 }}>
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
                style={{ display: 'flex', alignItems: 'center', gap: 6 }}
              >
                <span>🔒</span> Sign In with Google
              </button>
            )}
          </div>
        </div>
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
