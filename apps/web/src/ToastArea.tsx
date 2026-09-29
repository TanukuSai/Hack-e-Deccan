// Toast notification system
import { useApp } from './store';

const ICONS: Record<string, string> = { success: '✓', error: '✗', info: 'ℹ' };
const COLORS: Record<string, string> = {
  success: 'var(--emerald)',
  error: 'var(--rose)',
  info: 'var(--indigo)',
};

export default function ToastArea() {
  const { state, dispatch } = useApp();
  return (
    <div className="toast-area">
      {state.toasts.map(t => (
        <div key={t.id} className="toast" onClick={() => dispatch({ type: 'REMOVE_TOAST', id: t.id })}>
          <span style={{ color: COLORS[t.type], fontSize: 16, flexShrink: 0 }}>{t.icon || ICONS[t.type]}</span>
          <span style={{ flex: 1, fontSize: 12 }}>{t.message}</span>
          <span style={{ color: 'var(--text-muted)', fontSize: 16, cursor: 'pointer' }}>×</span>
        </div>
      ))}
    </div>
  );
}
