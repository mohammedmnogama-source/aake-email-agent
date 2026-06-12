'use client';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

// ── Category config ──────────────────────────────────────────────────────────
const CATEGORIES: { key: string; label: string; icon: string; color: string; placeholder: string }[] = [
  {
    key: 'company',
    label: 'Company Info',
    icon: '🏢',
    color: 'bg-blue-50 border-blue-200',
    placeholder: 'e.g. We are AAKE, an IT reseller based in Kuwait.',
  },
  {
    key: 'products',
    label: 'Products & Brands',
    icon: '📦',
    color: 'bg-purple-50 border-purple-200',
    placeholder: 'e.g. We resell Cisco, Fortinet, HP, and Microsoft.',
  },
  {
    key: 'delivery',
    label: 'Delivery & Logistics',
    icon: '🚚',
    color: 'bg-orange-50 border-orange-200',
    placeholder: 'e.g. Standard lead time is 4–6 weeks.',
  },
  {
    key: 'terms',
    label: 'Payment & Terms',
    icon: '💳',
    color: 'bg-green-50 border-green-200',
    placeholder: 'e.g. We quote in KWD. 50% upfront, 50% on delivery.',
  },
  {
    key: 'customers',
    label: 'Key Rules & Customers',
    icon: '🤝',
    color: 'bg-pink-50 border-pink-200',
    placeholder: 'e.g. Never discount below 10% margin without approval.',
  },
  {
    key: 'vendors',
    label: 'Vendors & Suppliers',
    icon: '🏭',
    color: 'bg-yellow-50 border-yellow-200',
    placeholder: 'e.g. Redington is our main Fortinet distributor. Contact: Hala Adam.',
  },
  {
    key: 'team',
    label: 'Team & Roles',
    icon: '👥',
    color: 'bg-indigo-50 border-indigo-200',
    placeholder: 'e.g. Mustafa Fakhruddin is Enterprise Sales Manager.',
  },
  {
    key: 'communication',
    label: 'Communication Rules',
    icon: '✉️',
    color: 'bg-teal-50 border-teal-200',
    placeholder: 'e.g. Always sign off as: Mustafa Fakhruddin | Enterprise Sales Manager | AAKE.',
  },
  {
    key: 'other',
    label: 'Other',
    icon: '📝',
    color: 'bg-slate-50 border-slate-200',
    placeholder: 'Any other fact the AI should always know.',
  },
];

type Fact = { id: number; fact: string; category: string; updated_at: string };

// Rough token estimate: ~4 chars per token
function estimateTokens(facts: Fact[]) {
  return Math.ceil(facts.reduce((sum, f) => sum + f.fact.length, 0) / 4);
}

export default function FactsPage() {
  const [facts, setFacts]           = useState<Fact[]>([]);
  const [loading, setLoading]       = useState(true);
  const [editingId, setEditingId]   = useState<number | null>(null);
  const [editText, setEditText]     = useState('');
  const [addingCat, setAddingCat]   = useState<string | null>(null);
  const [newText, setNewText]       = useState('');
  const [saving, setSaving]         = useState(false);
  const [toast, setToast]           = useState('');

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(''), 2500);
  }

  async function load() {
    setLoading(true);
    try { setFacts(await api.listFacts()); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  async function handleAdd(category: string) {
    if (!newText.trim()) return;
    setSaving(true);
    try {
      await api.createFact(newText.trim(), category);
      setNewText('');
      setAddingCat(null);
      await load();
      showToast('Fact added — Claude will use this from now on.');
    } finally { setSaving(false); }
  }

  async function handleUpdate(id: number, category: string) {
    if (!editText.trim()) return;
    setSaving(true);
    try {
      await api.updateFact(id, editText.trim(), category);
      setEditingId(null);
      await load();
      showToast('Updated.');
    } finally { setSaving(false); }
  }

  async function handleDelete(id: number) {
    if (!confirm('Delete this fact?')) return;
    await api.deleteFact(id);
    await load();
    showToast('Deleted.');
  }

  const tokens = estimateTokens(facts);
  const tokenPct = Math.min(100, Math.round((tokens / 4000) * 100));
  const tokenColor = tokenPct > 90 ? 'bg-red-500' : tokenPct > 70 ? 'bg-amber-400' : 'bg-emerald-500';

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">

      {/* ── Header ── */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-1">
          <span className="text-3xl">🧠</span>
          <h1 className="text-2xl font-bold text-slate-900">Company Brain</h1>
        </div>
        <p className="text-slate-500 text-sm ml-12">
          Everything Claude knows about AAKE. Every fact here is injected into every AI draft.
        </p>
      </div>

      {/* ── Token budget bar ── */}
      <div className="mb-8 bg-white border border-slate-200 rounded-xl p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-slate-600">AI Context Budget</span>
          <span className={`text-xs font-semibold ${tokenPct > 90 ? 'text-red-600' : tokenPct > 70 ? 'text-amber-600' : 'text-emerald-600'}`}>
            ~{tokens} / 4,000 tokens used ({tokenPct}%)
          </span>
        </div>
        <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
          <div className={`h-full rounded-full transition-all ${tokenColor}`} style={{ width: `${tokenPct}%` }} />
        </div>
        {tokenPct > 90 && (
          <p className="mt-2 text-xs text-red-600">
            ⚠️ Getting close to the limit. Consider trimming or combining facts.
          </p>
        )}
      </div>

      {/* ── Toast ── */}
      {toast && (
        <div className="fixed top-4 right-4 z-50 bg-slate-900 text-white text-sm px-4 py-2 rounded-lg shadow-lg">
          {toast}
        </div>
      )}

      {loading ? (
        <div className="text-center text-slate-400 py-16">Loading facts…</div>
      ) : (
        <div className="space-y-5">
          {CATEGORIES.map(cat => {
            const catFacts = facts.filter(f => f.category === cat.key);
            const isAdding = addingCat === cat.key;

            return (
              <div key={cat.key} className={`border rounded-xl overflow-hidden ${cat.color}`}>

                {/* Category header */}
                <div className="flex items-center justify-between px-5 py-3">
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{cat.icon}</span>
                    <span className="font-semibold text-slate-800 text-sm">{cat.label}</span>
                    {catFacts.length > 0 && (
                      <span className="text-xs text-slate-400 font-normal">({catFacts.length})</span>
                    )}
                  </div>
                  <button
                    onClick={() => { setAddingCat(isAdding ? null : cat.key); setNewText(''); }}
                    className="text-xs px-3 py-1 rounded-full bg-white border border-slate-300 text-slate-600 hover:bg-slate-50 font-medium"
                  >
                    + Add fact
                  </button>
                </div>

                {/* Facts list */}
                <div className="bg-white divide-y divide-slate-100">
                  {catFacts.length === 0 && !isAdding && (
                    <p className="px-5 py-4 text-sm text-slate-400 italic">
                      No facts yet — click "Add fact" to teach Claude about {cat.label.toLowerCase()}.
                    </p>
                  )}

                  {catFacts.map(fact => (
                    <div key={fact.id} className="group flex items-start gap-3 px-5 py-3">
                      {editingId === fact.id ? (
                        // Inline edit mode
                        <div className="flex-1 flex gap-2">
                          <input
                            autoFocus
                            value={editText}
                            onChange={e => setEditText(e.target.value)}
                            onKeyDown={e => {
                              if (e.key === 'Enter') handleUpdate(fact.id, fact.category);
                              if (e.key === 'Escape') setEditingId(null);
                            }}
                            className="flex-1 text-sm border border-blue-400 rounded-lg px-3 py-1.5 outline-none focus:ring-2 focus:ring-blue-200"
                          />
                          <button
                            onClick={() => handleUpdate(fact.id, fact.category)}
                            disabled={saving}
                            className="text-xs px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                          >
                            Save
                          </button>
                          <button
                            onClick={() => setEditingId(null)}
                            className="text-xs px-3 py-1.5 border border-slate-300 rounded-lg text-slate-500 hover:bg-slate-50"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <>
                          <span className="text-slate-400 text-sm mt-0.5">•</span>
                          <p className="flex-1 text-sm text-slate-700 leading-relaxed">{fact.fact}</p>
                          {/* Controls — shown on hover */}
                          <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                            <button
                              onClick={() => { setEditingId(fact.id); setEditText(fact.fact); }}
                              className="text-xs px-2 py-1 rounded text-slate-400 hover:text-blue-600 hover:bg-blue-50"
                              title="Edit"
                            >
                              ✏️
                            </button>
                            <button
                              onClick={() => handleDelete(fact.id)}
                              className="text-xs px-2 py-1 rounded text-slate-400 hover:text-red-600 hover:bg-red-50"
                              title="Delete"
                            >
                              🗑️
                            </button>
                          </div>
                        </>
                      )}
                    </div>
                  ))}

                  {/* Add new fact row */}
                  {isAdding && (
                    <div className="flex gap-2 px-5 py-3 bg-slate-50">
                      <input
                        autoFocus
                        value={newText}
                        onChange={e => setNewText(e.target.value)}
                        onKeyDown={e => {
                          if (e.key === 'Enter') handleAdd(cat.key);
                          if (e.key === 'Escape') { setAddingCat(null); setNewText(''); }
                        }}
                        placeholder={cat.placeholder}
                        className="flex-1 text-sm border border-blue-400 rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-blue-200"
                      />
                      <button
                        onClick={() => handleAdd(cat.key)}
                        disabled={saving || !newText.trim()}
                        className="text-xs px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium"
                      >
                        Add
                      </button>
                      <button
                        onClick={() => { setAddingCat(null); setNewText(''); }}
                        className="text-xs px-3 py-2 border border-slate-300 rounded-lg text-slate-500 hover:bg-white"
                      >
                        Cancel
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── Bottom note ── */}
      <p className="mt-8 text-xs text-slate-400 text-center">
        Changes take effect on the next email analyzed. No restart needed.
      </p>
    </div>
  );
}
