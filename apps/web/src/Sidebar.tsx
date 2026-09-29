import { useApp } from './store';
import type { Page } from './store';

interface SidebarProps {
  onOpenAuth?: () => void;
  mobileOpen?: boolean;
  onCloseMobile?: () => void;
}

export default function Sidebar({ onOpenAuth, mobileOpen, onCloseMobile }: SidebarProps) {
  const { state, dispatch } = useApp();

  const navigate = (page: Page) => {
    dispatch({ type: 'SET_PAGE', page });
    if (onCloseMobile) onCloseMobile();
  };

  const initial = state.user?.full_name
    ? state.user.full_name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
    : state.user?.email
    ? state.user.email[0].toUpperCase()
    : '✦';

  return (
    <aside className={`sidebar ${mobileOpen ? 'mobile-open' : ''}`}>
      <div className="sidebar-logo">
        <div className="sidebar-logo-icon">✦</div>
        <div>
          <div className="sidebar-logo-text">Executive Prep</div>
          <div className="sidebar-logo-sub">Autonomous Agent</div>
        </div>
      </div>

      <div className="sidebar-section-label">Core Executive</div>
      <div
        className={`nav-item ${state.page === 'chat' ? 'active' : ''}`}
        onClick={() => navigate('chat')}
      >
        <span className="nav-icon">💬</span>
        <span>Agent Chat</span>
      </div>
      <div
        className={`nav-item ${state.page === 'dashboard' ? 'active' : ''}`}
        onClick={() => navigate('dashboard')}
      >
        <span className="nav-icon">⚡</span>
        <span>Dashboard</span>
      </div>
      <div
        className={`nav-item ${state.page === 'briefing' ? 'active' : ''}`}
        onClick={() => navigate('briefing')}
      >
        <span className="nav-icon">✦</span>
        <span>Briefings</span>
      </div>
      <div
        className={`nav-item ${state.page === 'commitments' ? 'active' : ''}`}
        onClick={() => navigate('commitments')}
      >
        <span className="nav-icon">⏰</span>
        <span>Reminders</span>
      </div>
      <div
        className={`nav-item ${state.page === 'meetings' ? 'active' : ''}`}
        onClick={() => navigate('meetings')}
      >
        <span className="nav-icon">📅</span>
        <span>Meetings</span>
      </div>

      <div className="sidebar-section-label">Context & History</div>
      <div
        className={`nav-item ${state.page === 'contacts' ? 'active' : ''}`}
        onClick={() => navigate('contacts')}
      >
        <span className="nav-icon">👤</span>
        <span>Contacts</span>
      </div>
      <div
        className={`nav-item ${state.page === 'projects' ? 'active' : ''}`}
        onClick={() => navigate('projects')}
      >
        <span className="nav-icon">◫</span>
        <span>Projects</span>
      </div>

      <div className="sidebar-section-label">System & Security</div>
      <div
        className={`nav-item ${state.page === 'integrations' ? 'active' : ''}`}
        onClick={() => navigate('integrations')}
      >
        <span className="nav-icon">⟳</span>
        <span>Integrations</span>
      </div>
      <div
        className={`nav-item ${state.page === 'settings' ? 'active' : ''}`}
        onClick={() => navigate('settings')}
      >
        <span className="nav-icon">⚙</span>
        <span>Settings</span>
      </div>

      <div className="sidebar-footer">
        <div
          className="user-profile-row"
          style={{ cursor: 'pointer' }}
          onClick={onOpenAuth}
          title={state.isAuthenticated ? 'Account Profile' : 'Click to Sign In'}
        >
          <div className="user-avatar">
            {initial}
          </div>
          <div className="user-info">
            <div className="user-name">
              {state.user?.full_name ?? (state.isAuthenticated ? 'Executive' : 'Demo Account')}
            </div>
            <div className="user-email">
              {state.user?.email ?? 'Connect Google Calendar'}
            </div>
          </div>
          {state.isAuthenticated && (
            <button
              className="btn btn-ghost btn-sm"
              onClick={(e) => {
                e.stopPropagation();
                dispatch({ type: 'LOGOUT' });
              }}
              title="Sign Out"
              style={{ padding: '2px 6px', fontSize: 10 }}
            >
              ↪
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}
