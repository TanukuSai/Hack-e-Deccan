// Global state store — minimal reactive state using React context + useReducer
import { createContext, useContext, useReducer, useCallback, type Dispatch, type ReactNode } from 'react';
import type { UserProfile } from './api';
import { getStoredUser, setStoredUser, removeToken } from './api';

export type Page =
  | 'dashboard'
  | 'meetings'
  | 'briefing'
  | 'contacts'
  | 'projects'
  | 'commitments'
  | 'intelligence'
  | 'integrations'
  | 'settings';

export interface Toast {
  id: string;
  message: string;
  type: 'success' | 'error' | 'info';
  icon?: string;
}

interface State {
  page: Page;
  selectedMeetingId: string | null;
  toasts: Toast[];
  syncing: boolean;
  user: UserProfile | null;
  isAuthenticated: boolean;
}

type Action =
  | { type: 'SET_PAGE'; page: Page; meetingId?: string }
  | { type: 'SELECT_MEETING'; id: string }
  | { type: 'ADD_TOAST'; toast: Toast }
  | { type: 'REMOVE_TOAST'; id: string }
  | { type: 'SET_SYNCING'; value: boolean }
  | { type: 'LOGIN'; user: UserProfile }
  | { type: 'LOGOUT' }
  | { type: 'UPDATE_USER'; user: Partial<UserProfile> };

const storedUser = getStoredUser();

const initial: State = {
  page: 'dashboard',
  selectedMeetingId: null,
  toasts: [],
  syncing: false,
  user: storedUser,
  isAuthenticated: !!storedUser || !!localStorage.getItem('mpa_token'),
};

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'SET_PAGE':
      return { ...state, page: action.page, selectedMeetingId: action.meetingId ?? state.selectedMeetingId };
    case 'SELECT_MEETING':
      return { ...state, selectedMeetingId: action.id };
    case 'ADD_TOAST':
      return { ...state, toasts: [...state.toasts.slice(-4), action.toast] };
    case 'REMOVE_TOAST':
      return { ...state, toasts: state.toasts.filter(t => t.id !== action.id) };
    case 'SET_SYNCING':
      return { ...state, syncing: action.value };
    case 'LOGIN':
      setStoredUser(action.user);
      return { ...state, user: action.user, isAuthenticated: true };
    case 'LOGOUT':
      removeToken();
      return { ...state, user: null, isAuthenticated: false };
    case 'UPDATE_USER':
      if (!state.user) return state;
      const updated = { ...state.user, ...action.user };
      setStoredUser(updated);
      return { ...state, user: updated };
    default:
      return state;
  }
}

const Ctx = createContext<{ state: State; dispatch: Dispatch<Action> } | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initial);
  return <Ctx.Provider value={{ state, dispatch }}>{children}</Ctx.Provider>;
}

export function useApp() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useApp outside AppProvider');
  return ctx;
}

export function useToast() {
  const { dispatch } = useApp();
  return useCallback((message: string, type: Toast['type'] = 'info', icon = '') => {
    const id = Math.random().toString(36).slice(2);
    dispatch({ type: 'ADD_TOAST', toast: { id, message, type, icon } });
    setTimeout(() => dispatch({ type: 'REMOVE_TOAST', id }), 4000);
  }, [dispatch]);
}
