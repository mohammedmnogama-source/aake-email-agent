'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';

const APPROVED_LABEL: Record<number, string> = {
  0:  'Pending',
  1:  'Approved',
  [-1]: 'Rejected',
};
const APPROVED_COLORS: Record<number, string> = {
  0:  'bg-yellow-100 text-yellow-700',
  1:  'bg-green-100 text-green-700',
  [-1]: 'bg-red-100 text-red-600',
};

function fmt(d: string | null) {
  if (!d) return '—';
  return new Date(d).toLocaleString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function pct(v: number | null) {
  if (v == null) return '—';
  return `${Math.round(v * 100)}%`;
}

export default function SuggestedTasksPage() {
  const router = useRouter();
  const [tasks, setTasks] = useState<any[]>([]);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [detail, setDetail] = useState<any>(null);
  const [editDesc, setEditDesc] = useState('');
  const [editConf, setEditConf] = useState('');
  const [editQuote, setEditQuote] = useState('');
  const [editPayload, setEditPayload] = useState('');
  const [payloadError, setPayloadError] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');

  useEffect(() => {
    if (!isAuthenticated()) { router.push('/login'); return; }
    load();
  }, []);

  async function load() {
    try {
      const data = await api.listPendingTasks();
      setTasks(data);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function openDetail(id: number) {
    if (expanded === id) { setExpanded(null); setDetail(null); return; }
    try {
      const d = await api.getTask(id);
      setDetail(d);
      setExpanded(id);
      setEditDesc(d.description ?? '');
      setEditConf(d.confidence != null ? String(d.confidence) : '');
      setEditQuote(d.evidence_quote ?? '');
      // pretty-print the stored JSON string
      try {
        setEditPayload(JSON.stringify(JSON.parse(d.payload ?? '{}'), null, 2));
      } catch {
        setEditPayload(d.payload ?? '{}');
      }
      setPayloadError('');
      setMsg('');
    } catch (e: any) {
      setError(e.message);
    }
  }

  function validatePayload(raw: string): any | null {
    try { return JSON.parse(raw); } catch { return null; }
  }

  async function save(id: number) {
    const parsed = validatePayload(editPayload);
    if (parsed === null) { setPayloadError('Payload is not valid JSON'); return; }
    setPayloadError('');
    setBusy(true);
    try {
      const confNum = editConf !== '' ? parseFloat(editConf) : undefined;
      await api.updateTask(id, {
        description: editDesc,
        payload: parsed,
        ...(confNum != null && !isNaN(confNum) ? { confidence: confNum } : {}),
        evidence_quote: editQuote || undefined,
      });
      setMsg('Saved.');
      await load();
      await openDetailSilent(id);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function openDetailSilent(id: number) {
    try {
      const d = await api.getTask(id);
      setDetail(d);
    } catch { /* ignore */ }
  }

  async function approve(id: number) {
    setBusy(true);
    try {
      await api.approveTask(id);
      setMsg('Marked approved (staged only — not sent to ERP).');
      setExpanded(null);
      setDetail(null);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function reject(id: number) {
    setBusy(true);
    try {
      await api.rejectTask(id);
      setMsg('Rejected.');
      setExpanded(null);
      setDetail(null);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-6">

      {/* ── Safety banner ────────────────────────────────────────────────── */}
      <div className="mb-5 bg-amber-50 border border-amber-200 rounded-xl px-5 py-3 text-sm text-amber-800 flex flex-col gap-0.5">
        <p className="font-semibold">Staged only — Not yet sent to ERP</p>
        <p className="text-amber-700">Approving a proposal here only marks it <code className="bg-amber-100 px-1 rounded text-xs">approved=1</code>. It does <strong>not</strong> create CRM records and does <strong>not</strong> call ERP APIs.</p>
      </div>

      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold text-slate-800">AI Proposals</h1>
        <button
          onClick={load}
          className="text-xs text-slate-500 border border-slate-200 rounded-lg px-3 py-1.5 hover:bg-slate-50"
        >
          Refresh
        </button>
      </div>

      {error && <p className="text-red-500 text-sm mb-3">{error}</p>}
      {msg   && <p className="text-green-600 text-sm mb-3">{msg}</p>}

      {tasks.length === 0 ? (
        <div className="bg-white border border-slate-200 rounded-xl px-6 py-12 text-center text-slate-400 text-sm">
          No pending proposals
        </div>
      ) : (
        <div className="space-y-2">
          {tasks.map((t) => (
            <div key={t.id} className="bg-white border border-slate-200 rounded-xl overflow-hidden">

              {/* ── Row summary ──────────────────────────────────────────── */}
              <button
                onClick={() => openDetail(t.id)}
                className="w-full text-left px-5 py-4 flex items-center gap-4 hover:bg-slate-50 transition-colors"
              >
                <span className="text-xs text-slate-400 w-8">#{t.id}</span>
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${APPROVED_COLORS[t.approved] ?? 'bg-gray-100 text-gray-500'}`}>
                  {APPROVED_LABEL[t.approved] ?? t.approved}
                </span>
                <span className="text-xs font-mono bg-slate-100 text-slate-600 px-2 py-0.5 rounded">{t.task_type}</span>
                <span className="flex-1 text-sm text-slate-700 truncate">{t.description}</span>
                <span className="text-xs text-slate-400">{pct(t.confidence)}</span>
                <span className="text-xs text-slate-400">{fmt(t.created_at)}</span>
                <span className="text-slate-400 text-xs ml-1">{expanded === t.id ? '▲' : '▼'}</span>
              </button>

              {/* ── Expanded detail ───────────────────────────────────────── */}
              {expanded === t.id && detail && (
                <div className="border-t border-slate-100 px-5 py-5 space-y-5 bg-slate-50">

                  {/* Read-only metadata */}
                  <div className="grid grid-cols-2 gap-3 text-xs text-slate-500">
                    <Field label="ID"          value={String(detail.id)} />
                    <Field label="Email ID"    value={String(detail.email_id)} />
                    <Field label="Suggestion ID" value={String(detail.suggestion_id)} />
                    <Field label="Task Type"   value={detail.task_type} />
                    <Field label="Approved"    value={`${detail.approved} (${APPROVED_LABEL[detail.approved] ?? detail.approved})`} />
                    <Field label="Executed At" value={fmt(detail.executed_at)} />
                    <Field label="ERP Ref"     value={detail.erp_reference ?? '—'} />
                    <Field label="Error"       value={detail.error_message ?? '—'} />
                    <Field label="Created At"  value={fmt(detail.created_at)} />
                  </div>

                  <hr className="border-slate-200" />

                  {/* Editable fields */}
                  <div className="space-y-3">
                    <label className="block">
                      <span className="text-xs font-medium text-slate-600">Description</span>
                      <input
                        value={editDesc}
                        onChange={(e) => setEditDesc(e.target.value)}
                        className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
                      />
                    </label>

                    <div className="grid grid-cols-2 gap-3">
                      <label className="block">
                        <span className="text-xs font-medium text-slate-600">Confidence (0–1)</span>
                        <input
                          value={editConf}
                          onChange={(e) => setEditConf(e.target.value)}
                          placeholder="e.g. 0.85"
                          className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
                        />
                      </label>
                      <label className="block">
                        <span className="text-xs font-medium text-slate-600">Evidence Quote</span>
                        <input
                          value={editQuote}
                          onChange={(e) => setEditQuote(e.target.value)}
                          className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
                        />
                      </label>
                    </div>

                    <label className="block">
                      <span className="text-xs font-medium text-slate-600">Payload (JSON)</span>
                      <textarea
                        value={editPayload}
                        onChange={(e) => { setEditPayload(e.target.value); setPayloadError(''); }}
                        rows={10}
                        className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-300"
                      />
                      {payloadError && <p className="text-red-500 text-xs mt-1">{payloadError}</p>}
                    </label>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-3 pt-1">
                    <button
                      disabled={busy}
                      onClick={() => save(detail.id)}
                      className="px-4 py-2 text-sm bg-slate-700 text-white rounded-lg hover:bg-slate-800 disabled:opacity-50"
                    >
                      Save edits
                    </button>

                    {detail.approved !== 1 && detail.executed_at == null && (
                      <button
                        disabled={busy}
                        onClick={() => approve(detail.id)}
                        className="px-4 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
                        title="Marks approved=1 only. Does not call ERP or create CRM records."
                      >
                        Approve (staged only)
                      </button>
                    )}

                    {detail.approved !== -1 && (
                      <button
                        disabled={busy}
                        onClick={() => reject(detail.id)}
                        className="px-4 py-2 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
                        title="Marks rejected. Does not delete the source email."
                      >
                        Reject
                      </button>
                    )}

                    <span className="ml-auto text-xs text-slate-400 italic">
                      Approve does not create CRM records or call ERP
                    </span>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-slate-400">{label}: </span>
      <span className="text-slate-700 font-mono">{value}</span>
    </div>
  );
}
