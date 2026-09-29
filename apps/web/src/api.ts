// API client — all calls to the Meeting Prep Agent backend
// Base URL is read from VITE_API_URL env var, falls back to localhost

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

// ─── Auth ─────────────────────────────────────────────────────────────────
export type UserProfile = {
  id: string;
  email: string;
  full_name?: string;
  account_status?: string;
  monthly_budget_usd?: number;
  current_month_spend_usd?: number;
  timezone?: string;
};

function getToken(): string | null {
  return localStorage.getItem('mpa_token');
}

export function setToken(token: string) {
  localStorage.setItem('mpa_token', token);
}

export function removeToken() {
  localStorage.removeItem('mpa_token');
  localStorage.removeItem('mpa_user');
}

export function getStoredUser(): UserProfile | null {
  const s = localStorage.getItem('mpa_user');
  if (!s) return null;
  try { return JSON.parse(s); } catch { return null; }
}

export function setStoredUser(user: UserProfile) {
  localStorage.setItem('mpa_user', JSON.stringify(user));
}

async function api<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> ?? {}),
  };
  if (token) (headers as Record<string, string>)['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...options, headers });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail ?? `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const authApi = {
  getGoogleAuthUrl: (redirectUri: string, includeCalendar = false, state?: string) => {
    const q = new URLSearchParams({ redirect_uri: redirectUri, include_calendar: String(includeCalendar) });
    if (state) q.set('state', state);
    return api<{ authorization_url: string; scopes: string[] }>(`/api/v1/auth/google/url?${q}`);
  },
  googleCallback: (code: string, redirectUri: string, state?: string) =>
    api<{ access_token: string; token_type: string; user: UserProfile }>('/api/v1/auth/google/callback', {
      method: 'POST',
      body: JSON.stringify({ code, redirect_uri: redirectUri, state }),
    }),
  devLogin: (email?: string, name?: string) =>
    api<{ access_token: string; token_type: string; user: UserProfile }>('/api/v1/auth/dev-login', {
      method: 'POST',
      body: JSON.stringify({ email, name }),
    }),
  me: () => api<UserProfile>('/api/v1/auth/me'),
  logout: () => api<{ status: string }>('/api/v1/auth/logout', { method: 'POST' }),
};

// ─── Meetings ─────────────────────────────────────────────────────────────
export type Meeting = {
  id: string;
  title: string;
  purpose?: string;
  start_time: string;
  end_time: string;
  status: string;
  effective_importance: number;
  user_importance_override?: number;
  join_url?: string;
  has_transcript?: boolean;
  calendar_source?: string;
  active_prep_job_id?: string;
  meeting_version: number;
  created_at: string;
  updated_at: string;
};

export const meetingsApi = {
  list: (limit = 20, status?: string) => {
    const q = new URLSearchParams({ limit: String(limit) });
    if (status) q.set('status', status);
    return api<Meeting[]>(`/api/v1/meetings?${q}`);
  },
  get: (id: string) => api<Meeting>(`/api/v1/meetings/${id}`),
  create: (payload: Partial<Meeting>) =>
    api<Meeting>('/api/v1/meetings', { method: 'POST', body: JSON.stringify(payload) }),
  analyzeOutcome: (id: string, notes?: string) =>
    api(`/api/v1/meetings/${id}/analyze-outcome`, {
      method: 'POST',
      body: notes ? JSON.stringify({ notes }) : undefined,
    }),
};

// ─── Briefings ────────────────────────────────────────────────────────────
export type Briefing = {
  id: string;
  meeting_id: string;
  version: number;
  is_latest: boolean;
  executive_summary?: string;
  attendee_profiles?: any[];
  strategic_priorities?: any[];
  talking_points?: any[];
  conflicts_detected?: any[];
  degraded_reason?: string;
  evidence_items?: any[];
  created_at: string;
};

export type BriefingMessage = {
  role: 'user' | 'assistant';
  content: string;
  created_at?: string;
};

export const briefingsApi = {
  latest: (meeting_id: string) => api<Briefing>(`/api/v1/briefings/meeting/${meeting_id}/latest`),
  history: (meeting_id: string) => api<Briefing[]>(`/api/v1/briefings/meeting/${meeting_id}/history`),
  generate: (meeting_id: string, force_refresh = false) =>
    api<Briefing>('/api/v1/briefings/generate', {
      method: 'POST',
      body: JSON.stringify({ meeting_id, force_refresh }),
    }),
  askFollowUp: (meeting_id: string, question: string, history: BriefingMessage[] = []) =>
    api<{ answer: string; suggested_talking_points?: string[]; reminders?: string[]; action_items?: string[] }>(
      `/api/v1/briefings/meeting/${meeting_id}/conversation`,
      {
        method: 'POST',
        body: JSON.stringify({ question, history }),
      }
    ),
};

// ─── Commitments / Reminders ──────────────────────────────────────────────
export type Commitment = {
  id: string;
  meeting_id?: string;
  project_id?: string;
  description: string;
  responsible_person?: string;
  due_date?: string;
  status: string;
  is_confirmed: boolean;
  epistemic_class: string;
  commitment_type?: string;
  source_excerpt?: string;
  created_at: string;
};

// Alias for Reminders
export type Reminder = Commitment;

export const commitmentsApi = {
  list: (filters: Record<string, string | boolean | undefined> = {}) => {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(filters)) {
      if (v !== undefined) q.set(k, String(v));
    }
    return api<Commitment[]>(`/api/v1/commitments?${q}`);
  },
  create: (payload: Partial<Commitment>) =>
    api<Commitment>('/api/v1/commitments', { method: 'POST', body: JSON.stringify(payload) }),
  confirm: (id: string) =>
    api<Commitment>(`/api/v1/commitments/${id}/confirm`, { method: 'POST' }),
  update: (id: string, payload: Partial<Commitment>) =>
    api<Commitment>(`/api/v1/commitments/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
};

// Export remindersApi alias pointing to the commitments endpoints
export const remindersApi = commitmentsApi;

// ─── Inter-Meeting Task Report & Sync ──────────────────────────────────────
export type InterMeetingSyncResult = {
  current_meeting_id: string;
  current_meeting_title: string;
  previous_meeting?: {
    id: string;
    title: string;
    start_time: string;
    shared_participants: string[];
  };
  report_document_id?: string;
  report_filename: string;
  summary_of_progress: string;
  synced_reminders: {
    id: string;
    owner_name: string;
    description: string;
    previous_status: string;
    new_status: string;
    is_confirmed: boolean;
    status_changed: boolean;
    matched_excerpt?: string;
    notes?: string;
  }[];
  new_reminders_added: Commitment[];
  total_completed: number;
  total_in_progress: number;
  briefing_updated: boolean;
  synced_at: string;
};

export const interMeetingApi = {
  getContext: (meetingId: string) =>
    api<any>(`/api/v1/meetings/${meetingId}/inter-meeting-context`),
  uploadReportText: (meetingId: string, reportText: string, filename = 'inter_meeting_task_report.txt') =>
    api<InterMeetingSyncResult>(`/api/v1/meetings/${meetingId}/task-report`, {
      method: 'POST',
      body: JSON.stringify({ report_text: reportText, filename }),
    }),
  uploadReportFile: async (meetingId: string, file: File): Promise<InterMeetingSyncResult> => {
    const form = new FormData();
    form.append('file', file);
    const token = localStorage.getItem('mpa_token');
    const res = await fetch(`${BASE}/api/v1/meetings/${meetingId}/task-report/upload`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    if (!res.ok) {
      const errText = await res.text();
      try {
        const parsed = JSON.parse(errText);
        throw new Error(parsed.detail || errText);
      } catch {
        throw new Error(errText);
      }
    }
    return res.json();
  },
};

// ─── Contacts ─────────────────────────────────────────────────────────────
export type Contact = {
  id: string;
  name: string;
  email?: string;
  organization?: string;
  role_title?: string;
  notes?: string;
  created_at: string;
};

export const contactsApi = {
  list: () => api<Contact[]>('/api/v1/contacts'),
  create: (payload: Partial<Contact>) =>
    api<Contact>('/api/v1/contacts', { method: 'POST', body: JSON.stringify(payload) }),
  delete: (id: string) =>
    api<void>(`/api/v1/contacts/${id}`, { method: 'DELETE' }),
};

// ─── Projects ─────────────────────────────────────────────────────────────
export type Project = {
  id: string;
  name: string;
  description?: string;
  status: string;
  created_at: string;
};

export type ProjectProgress = {
  project_id: string;
  name: string;
  total_commitments: number;
  completed_commitments: number;
  pending_commitments: number;
  missed_commitments: number;
  blockers: any[];
  completion_pct: number;
};

export const projectsApi = {
  list: () => api<Project[]>('/api/v1/projects'),
  progress: (id: string) => api<ProjectProgress>(`/api/v1/projects/${id}/progress`),
  create: (payload: Partial<Project>) =>
    api<Project>('/api/v1/projects', { method: 'POST', body: JSON.stringify(payload) }),
};

// ─── Integrations ─────────────────────────────────────────────────────────
export type IntegrationHealth = {
  integration_type: string;
  is_enabled: boolean;
  attendance_mode: string;
  health_status: string;
  last_sync_at?: string;
  transcript_capture_enabled?: boolean;
  health_error_message?: string;
};

export const integrationsApi = {
  health: () => api<{ integrations: IntegrationHealth[] }>('/api/v1/integrations/health'),
  googleStatus: () => api<any>('/api/v1/integrations/google/status'),
  calendarSync: (force = false) =>
    api(`/api/v1/integrations/calendar/sync?force_full=${force}`, { method: 'POST' }),
  configureMeeting: (integration_type: string, config: any) =>
    api(`/api/v1/integrations/meeting/${integration_type}`, {
      method: 'PUT',
      body: JSON.stringify(config),
    }),
  transcriptUpload: (payload: any) =>
    api('/api/v1/integrations/transcripts/upload', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  transcripts: (meeting_id: string) =>
    api<any>(`/api/v1/integrations/transcripts/${meeting_id}`),
  requestAttendance: (meeting_id: string, payload: any) =>
    api(`/api/v1/integrations/attendance/${meeting_id}/request`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
};

// ─── System Health ─────────────────────────────────────────────────────────
export const systemApi = {
  health: () => api<any>('/health/dependencies'),
};
