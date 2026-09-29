// Sidebar + nav component
import { useApp } from './store';
import type { Page } from './store';

const NAV: { page: Page; icon: string; label: string; badge?: number }[] = [
  { page: 'dashboard',    icon: '⌂',  label: 'Dashboard' },
  { page: 'meetings',     icon: '📅', label: 'Meetings',    badge: 3 },
  { page: 'briefing',     icon: '✦',  label: 'Briefings' },
  { page: 'commitments',  icon: '✓',  label: 'Commitments', badge: 5 },
  { page: 'contacts',     icon: '👤', label: 'Contacts' },
  { page: 'projects',     icon: '◫',  label: 'Projects' },
  { page: 'intelligence', icon: '◈',  label: 'Intelligence' },
  { page: 'integrations', icon: '⟳',  label: 'Integrations' },
  { page: 'settings',     icon: '⚙',  label: 'Settings' },
];

export default function Sidebar({ onOpenAuth }: { onOpenAuth?: () => void }) {
  const { state, dispatch } = useApp();
  const navigate = (page: Page) => dispatch({ type: 'SET_PAGE', page });

  const initial = state.user?.full_name
    ? state.user.full_name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
    : state.user?.email
    ? state.user.email[0].toUpperCase()
    : '✦';

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="sidebar-logo-icon">✦</div>
        <div>
          <div className="sidebar-logo-text">Meeting Prep</div>
          <div className="sidebar-logo-sub">Agent Dashboard</div>
        </div>
      </div>

      <div className="sidebar-section-label">Navigation</div>

      {NAV.map(item => (
        <div
          key={item.page}
          className={`nav-item ${state.page === item.page ? 'active' : ''}`}
          onClick={() => navigate(item.page)}
        >
          <span className="nav-icon">{item.icon}</span>
          <span>{item.label}</span>
          {item.badge && <span className="nav-badge">{item.badge}</span>}
        </div>
      ))}

      <div
        className="sidebar-footer"
        style={{ cursor: 'pointer' }}
        onClick={onOpenAuth}
        title={state.isAuthenticated ? 'Account Profile' : 'Click to Sign In'}
      >
        <div className="user-avatar" style={{ background: state.isAuthenticated ? 'var(--primary)' : 'rgba(255,255,255,0.1)' }}>
          {initial}
        </div>
        <div className="user-info" style={{ flex: 1, minWidth: 0 }}>
          <div className="user-name" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {state.user?.full_name ?? (state.isAuthenticated ? 'User' : 'Guest Account')}
          </div>
          <div className="user-email" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {state.user?.email ?? 'Click to sign in with Google'}
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
            style={{ padding: '4px 6px', fontSize: 11 }}
          >
            ↪
          </button>
        )}
      </div>
    </aside>
  );
}
