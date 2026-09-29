// Contacts page
import { useEffect, useState } from 'react';
import { contactsApi } from '../api';
import type { Contact } from '../api';
import { useToast } from '../store';

const DEMO: Contact[] = [
  { id: 'c1', name: 'David Miller', email: 'david@cloudflare.com', organization: 'Cloudflare', role_title: 'VP of Engineering', notes: 'Zero-trust advocate. Direct comms style.', created_at: '' },
  { id: 'c2', name: 'Priya Nair', email: 'priya@cloudflare.com', organization: 'Cloudflare', role_title: 'Security Lead', created_at: '' },
  { id: 'c3', name: 'Sarah Chen', email: 'sarah@sequoia.com', organization: 'Sequoia Capital', role_title: 'Partner', notes: 'Led Series A. Interested in AI-native products.', created_at: '' },
  { id: 'c4', name: 'Raj Mehta', email: 'raj@company.com', organization: 'Internal', role_title: 'CTO', created_at: '' },
];

function initials(name: string) { return name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase(); }

const COLORS = ['#6366f1', '#8b5cf6', '#10b981', '#f59e0b', '#0ea5e9', '#f43f5e'];

export default function ContactsPage() {
  const toast = useToast();
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<Contact | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: '', email: '', organization: '', role_title: '', notes: '' });

  useEffect(() => {
    contactsApi.list().then(c => setContacts(c ?? [])).catch(() => setContacts(DEMO));
  }, []);

  const handleCreate = async () => {
    if (!form.name) return;
    try {
      const c = await contactsApi.create(form);
      setContacts(prev => [c, ...prev]);
      setShowCreate(false);
      setForm({ name: '', email: '', organization: '', role_title: '', notes: '' });
      toast('Contact added', 'success', '✓');
    } catch (e: any) { toast(e.message, 'error'); }
  };

  const handleDelete = async (id: string) => {
    try {
      await contactsApi.delete(id);
      setContacts(c => c.filter(x => x.id !== id));
      if (selected?.id === id) setSelected(null);
      toast('Contact removed', 'info');
    } catch (e: any) { toast(e.message, 'error'); }
  };

  const display = (contacts.length > 0 ? contacts : DEMO).filter(c =>
    !search || c.name.toLowerCase().includes(search.toLowerCase()) || (c.organization ?? '').toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="page-body fade-in">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: -8 }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 20, fontWeight: 800 }}>Contacts</div>
          <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{display.length} contacts</div>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>＋ Add Contact</button>
      </div>

      <div className="search-bar">
        <span style={{ color: 'var(--text-muted)' }}>🔍</span>
        <input placeholder="Search by name or organization…" value={search} onChange={e => setSearch(e.target.value)} />
      </div>

      {showCreate && (
        <div className="card" style={{ borderColor: 'var(--border-bright)' }}>
          <div className="card-title" style={{ marginBottom: 16 }}>New Contact</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 }}>
            {[['Name *', 'name', 'Full name'], ['Email', 'email', 'email@company.com'], ['Organization', 'organization', 'Company name'], ['Role', 'role_title', 'Job title']].map(([label, key, placeholder]) => (
              <div key={key}>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>{label}</div>
                <input style={{ width: '100%', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border)', borderRadius: 8, padding: '8px 10px', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font)' }}
                  placeholder={placeholder} value={(form as any)[key]} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))} />
              </div>
            ))}
            <div style={{ gridColumn: '1 / -1' }}>
              <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>Notes</div>
              <textarea style={{ width: '100%', background: 'rgba(255,255,255,0.05)', border: '1px solid var(--border)', borderRadius: 8, padding: '8px 10px', color: 'var(--text-primary)', fontSize: 12, fontFamily: 'var(--font)', resize: 'none', height: 60 }}
                placeholder="Key notes about this person…" value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-primary" onClick={handleCreate}>Add Contact</button>
            <button className="btn btn-ghost" onClick={() => setShowCreate(false)}>Cancel</button>
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: selected ? '1fr 320px' : '1fr', gap: 16, transition: 'all 0.2s' }}>
        <div className="contact-grid">
          {display.map((c, i) => (
            <div key={c.id} className="contact-card" onClick={() => setSelected(c === selected ? null : c)} style={{ borderColor: selected?.id === c.id ? 'var(--border-bright)' : '' }}>
              <div className="contact-avatar" style={{ background: `linear-gradient(135deg, ${COLORS[i % COLORS.length]}, ${COLORS[(i + 2) % COLORS.length]})` }}>
                {initials(c.name)}
              </div>
              <div className="contact-name">{c.name}</div>
              {c.role_title && <div className="contact-role">{c.role_title}</div>}
              {c.organization && <div className="contact-org">🏢 {c.organization}</div>}
            </div>
          ))}
          {display.length === 0 && (
            <div className="empty-state" style={{ gridColumn: '1 / -1' }}><div className="empty-icon">👤</div>No contacts found</div>
          )}
        </div>

        {selected && (
          <div className="card fade-in" style={{ height: 'fit-content', position: 'sticky', top: 0 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
              <div className="contact-avatar" style={{ background: 'var(--gradient-main)', width: 48, height: 48, fontSize: 20 }}>{initials(selected.name)}</div>
              <div style={{ display: 'flex', gap: 6 }}>
                <button className="btn btn-ghost btn-sm" onClick={() => setSelected(null)}>✕</button>
                <button className="btn btn-danger btn-sm" onClick={() => handleDelete(selected.id)}>🗑</button>
              </div>
            </div>
            <div style={{ fontSize: 16, fontWeight: 800, marginBottom: 4 }}>{selected.name}</div>
            {selected.role_title && <div style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{selected.role_title}</div>}
            {selected.organization && <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>@ {selected.organization}</div>}
            {selected.email && <div style={{ fontSize: 11, color: 'var(--indigo)', marginTop: 8 }}>✉ {selected.email}</div>}
            {selected.notes && (
              <div style={{ marginTop: 12, padding: '10px 12px', background: 'rgba(255,255,255,0.03)', borderRadius: 8, fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.6 }}>
                {selected.notes}
              </div>
            )}
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 }}>Context</div>
              <span className="evidence-chip">◇ No research yet</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
