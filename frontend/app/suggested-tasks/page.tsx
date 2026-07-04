'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';

// Task types that are real ERP actions (Phase 2+).
// Anything else is legacy/informational and should not be executed.
const ERP_ACTION_TYPES = new Set([
  'create_lead', 'create_rfq', 'create_deal',
  'create_task', 'create_contact', 'log_email_to_deal',
]);

const STALE_CLAIM_MS = 120_000; // must match backend STALE_CLAIM_SECONDS

const APPROVED_LABEL: Record<number, string> = {
  0: 'Pending',
  1: 'Approved',
  [-1]: 'Rejected',
};
const APPROVED_COLORS: Record<number, string> = {
  0:    'bg-yellow-100 text-yellow-700',
  1:    'bg-green-100 text-green-700',
  [-1]: 'bg-red-100 text-red-600',
};
const EXEC_COLORS: Record<string, string> = {
  pending:   'bg-slate-100 text-slate-600',
  executing: 'bg-blue-100 text-blue-700',
  executed:  'bg-emerald-100 text-emerald-700',
  failed:    'bg-red-100 text-red-700',
};

function fmt(d: string | null) {
  if (!d) return '—';
  return new Date(d).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}
function pct(v: number | null | undefined) {
  if (v == null) return null;
  return `${Math.round(v * 100)}%`;
}
// Executing claim older than the stale threshold may be re-triggered by a human.
// Backend claim guard is authoritative; this only drives button visibility.
function isStaleExecuting(t: any): boolean {
  if (t?.execution_status !== 'executing' || !t?.execution_claimed_at) return false;
  const claimed = Date.parse((t.execution_claimed_at as string).replace(' ', 'T') + 'Z');
  return !isNaN(claimed) && Date.now() - claimed > STALE_CLAIM_MS;
}
function canExecute(t: any): boolean {
  return (
    t?.task_type === 'create_task' &&
    t?.approved === 1 &&
    !t?.executed_at &&
    (t?.execution_status === 'pending' || t?.execution_status === 'failed' || isStaleExecuting(t))
  );
}

export default function SuggestedTasksPage() {
  const router = useRouter();
  const [pending, setPending]   = useState<any[]>([]);
  const [approved, setApproved] = useState<any[]>([]);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [detail, setDetail]     = useState<any>(null);
  const [editDesc, setEditDesc]     = useState('');
  const [editConf, setEditConf]     = useState('');
  const [editQuote, setEditQuote]   = useState('');
  const [editPayload, setEditPayload] = useState('');
  const [payloadError, setPayloadError] = useState('');
  const [bodyExpanded, setBodyExpanded] = useState(false);
  const [busy, setBusy]   = useState(false);
  const [error, setError] = useState('');
  const [msg, setMsg]     = useState('');

  useEffect(() => {
    if (!isAuthenticated()) { router.push('/login'); return; }
    load();
  }, []);

  async function load() {
    setError('');
    try {
      const [p, a] = await Promise.all([api.listPendingTasks(), api.listApprovedTasks()]);
      setPending(p);
      setApproved(a);
    } catch (e: any) { setError(e.message); }
  }

  async function openDetail(id: number) {
    if (expanded === id) { setExpanded(null); setDetail(null); return; }
    setBodyExpanded(false);
    setMsg('');
    try {
      const d = await api.getTask(id);
      setDetail(d);
      setExpanded(id);
      setEditDesc(d.description ?? '');
      setEditConf(d.confidence != null ? String(d.confidence) : '');
      setEditQuote(d.evidence_quote ?? '');
      try { setEditPayload(JSON.stringify(JSON.parse(d.payload ?? '{}'), null, 2)); }
      catch { setEditPayload(d.payload ?? '{}'); }
      setPayloadError('');
    } catch (e: any) { setError(e.message); }
  }

  async function refreshDetail(id: number) {
    try { setDetail(await api.getTask(id)); } catch { /* ignore */ }
  }

  async function save(id: number) {
    let parsed: any;
    try { parsed = JSON.parse(editPayload); }
    catch { setPayloadError('Payload is not valid JSON'); return; }
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
      setMsg('Saved. Editing reset this proposal to pending approval.');
      await load();
      await refreshDetail(id);
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function approve(id: number) {
    setBusy(true);
    try {
      await api.approveTask(id);
      setMsg('Approved. Use “Create Task in ERP” to execute — approval alone does not create a task.');
      await load();
      await refreshDetail(id);
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function reject(id: number) {
    setBusy(true);
    try {
      await api.rejectTask(id);
      setMsg('Rejected.');
      setExpanded(null); setDetail(null);
      await load();
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }

  async function execute(id: number) {
    setBusy(true);
    setError(''); setMsg('');
    try {
      const r = await api.executeTask(id);
      setMsg(
        r.duplicate
          ? `Reconciled with existing ERP task ${r.erp_reference}.`
          : `ERP task created: ${r.erp_reference}.`
      );
      await load();
      await refreshDetail(id);
    } catch (e: any) { setError(e.message); }
    finally { setBusy(false); }
  }

  const isErpAction = (taskType: string) => ERP_ACTION_TYPES.has(taskType);

  function renderRow(t: any) {
    return (
      <div key={t.id} className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        {/* List row */}
        <button
          onClick={() => openDetail(t.id)}
          className="w-full text-left px-5 py-4 flex items-center gap-3 hover:bg-slate-50 transition-colors"
        >
          <span className="text-xs text-slate-400 w-8 shrink-0">#{t.id}</span>
          <span className={`text-xs font-medium px-2 py-0.5 rounded-full shrink-0 ${APPROVED_COLORS[t.approved] ?? 'bg-gray-100 text-gray-500'}`}>
            {APPROVED_LABEL[t.approved] ?? t.approved}
          </span>
          {t.approved === 1 && t.execution_status && (
            <span className={`text-xs font-medium px-2 py-0.5 rounded-full shrink-0 ${EXEC_COLORS[t.execution_status] ?? 'bg-gray-100 text-gray-500'}`}>
              {t.execution_status}
            </span>
          )}
          <span className="text-xs font-mono bg-slate-100 text-slate-600 px-2 py-0.5 rounded shrink-0">{t.task_type}</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm text-slate-700 truncate">{t.description}</p>
            {(t.email_subject || t.email_from) && (
              <p className="text-xs text-slate-400 truncate">
                {t.email_from && <span>{t.email_from_name || t.email_from}</span>}
                {t.email_subject && <span className="ml-1">· {t.email_subject}</span>}
                {t.email_received_at && <span className="ml-1">· {fmt(t.email_received_at)}</span>}
              </p>
            )}
          </div>
          {pct(t.confidence) && <span className="text-xs text-slate-400 shrink-0">{pct(t.confidence)}</span>}
          <span className="text-slate-400 text-xs ml-1 shrink-0">{expanded === t.id ? '▲' : '▼'}</span>
        </button>

        {/* Expanded detail */}
        {expanded === t.id && detail && detail.id === t.id && renderDetail()}
      </div>
    );
  }

  function renderDetail() {
    const d = detail;
    const executing = d.execution_status === 'executing' && !isStaleExecuting(d);
    const executed  = !!d.executed_at;
    const editable  = !executed && d.execution_status !== 'executing' && d.execution_status !== 'executed';

    return (
      <div className="border-t border-slate-100 bg-slate-50 divide-y divide-slate-100">

        {/* ── Warnings ───────────────────────────────────────────── */}
        {(!d.evidence_quote || d.confidence == null || !isErpAction(d.task_type)) && (
          <div className="px-5 py-3 space-y-2">
            {!d.evidence_quote && (
              <WarningBox color="red">
                No evidence quote — verify manually before creating an ERP task.
              </WarningBox>
            )}
            {d.confidence == null && (
              <WarningBox color="amber">
                Legacy proposal or missing confidence — created before Phase 2 extraction.
              </WarningBox>
            )}
            {!isErpAction(d.task_type) && (
              <WarningBox color="blue">
                Task type <code className="bg-blue-50 px-1 rounded text-xs">{d.task_type}</code> is informational/staging only — not a supported ERP action type.
              </WarningBox>
            )}
          </div>
        )}

        {/* ── Source email context ───────────────────────────────── */}
        <Section title="Source Email">
          {d.email_context ? (
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2 text-xs">
                <Field label="Email ID"    value={String(d.email_id)} />
                <Field label="Received"    value={fmt(d.email_context.received_at)} />
                <Field label="From"        value={[d.email_context.from_name, d.email_context.from_address].filter(Boolean).join(' · ')} />
                <Field label="To"          value={d.email_context.to_addresses ?? '—'} />
                <Field label="Subject"     value={d.email_context.subject ?? '—'} />
                <Field label="Attachments" value={d.email_context.has_attachments ? 'Yes' : 'No'} />
                <Field label="Source"      value={d.email_context.source ?? '—'} />
              </div>
              {d.email_context.body_preview && (
                <div>
                  <button
                    onClick={() => setBodyExpanded(v => !v)}
                    className="text-xs text-blue-600 hover:underline mt-1"
                  >
                    {bodyExpanded ? 'Hide body' : 'Show body snippet'}
                  </button>
                  {bodyExpanded && (
                    <pre className="mt-2 text-xs bg-white border border-slate-200 rounded-lg p-3 whitespace-pre-wrap max-h-48 overflow-y-auto text-slate-600">
                      {d.email_context.body_preview}
                    </pre>
                  )}
                </div>
              )}
            </div>
          ) : (
            <p className="text-xs text-slate-400">Source email not found.</p>
          )}
        </Section>

        {/* ── AI suggestion context ──────────────────────────────── */}
        <Section title="AI Classification">
          {d.suggestion_context ? (
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2 text-xs">
                <Field label="Suggestion ID"   value={String(d.suggestion_id)} />
                <Field label="Category"        value={d.suggestion_context.category ?? '—'} />
                <Field label="Action"          value={d.suggestion_context.suggested_action ?? '—'} />
                <Field label="Confidence note" value={d.suggestion_context.confidence_note ?? '—'} />
              </div>
              {d.suggestion_context.summary && (
                <div className="text-xs text-slate-600 bg-white border border-slate-200 rounded-lg p-3">
                  <span className="font-medium text-slate-500">Summary: </span>{d.suggestion_context.summary}
                </div>
              )}
            </div>
          ) : (
            <p className="text-xs text-slate-400">AI suggestion not found.</p>
          )}
        </Section>

        {/* ── Proposal metadata ──────────────────────────────────── */}
        <Section title="Proposal">
          <div className="grid grid-cols-2 gap-2 text-xs">
            <Field label="ID"              value={String(d.id)} />
            <Field label="Task type"       value={d.task_type} />
            <Field label="Approval"        value={`${d.approved} — ${APPROVED_LABEL[d.approved] ?? d.approved}`} />
            <Field label="Execution"       value={d.execution_status ?? '—'} />
            <Field label="Executed at"     value={fmt(d.executed_at)} />
            <Field label="ERP reference"   value={d.erp_reference ?? '—'} />
            <Field label="Error"           value={d.error_message ?? '—'} />
            <Field label="Idempotency key" value={d.agent_suggestion_key ?? '—'} />
            <Field label="Created at"      value={fmt(d.created_at)} />
            <Field label="Confidence"      value={pct(d.confidence) ?? '(none)'} />
          </div>
        </Section>

        {/* ── Edit form (hidden once executing/executed) ─────────── */}
        {editable ? (
          <Section title="Edit">
            <p className="text-xs text-slate-400 mb-2">Saving an edit resets this proposal to pending approval.</p>
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
                  rows={8}
                  className="mt-1 w-full border border-slate-300 rounded-lg px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-blue-300"
                />
                {payloadError && <p className="text-red-500 text-xs mt-1">{payloadError}</p>}
              </label>
            </div>
          </Section>
        ) : (
          <Section title="Edit">
            <p className="text-xs text-slate-400">
              {executed ? 'This proposal has been executed and is locked.' : 'Execution is in progress — editing is disabled.'}
            </p>
          </Section>
        )}

        {/* ── Actions ────────────────────────────────────────────── */}
        <div className="px-5 py-4 flex flex-wrap items-center gap-3">
          {editable && (
            <button
              disabled={busy}
              onClick={() => save(d.id)}
              className="px-4 py-2 text-sm bg-slate-700 text-white rounded-lg hover:bg-slate-800 disabled:opacity-50"
            >
              Save edits
            </button>
          )}

          {editable && d.approved !== 1 && (
            <button
              disabled={busy}
              onClick={() => approve(d.id)}
              className="px-4 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
              title="Sets approved=1 only. Does not call ERP."
            >
              Approve
            </button>
          )}

          {canExecute(d) && (
            <button
              disabled={busy}
              onClick={() => execute(d.id)}
              className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              title="Creates the task in the ERP. Safe against repeated/concurrent clicks."
            >
              {busy ? 'Creating…' : (d.execution_status === 'failed' ? 'Retry Create Task in ERP' : 'Create Task in ERP')}
            </button>
          )}

          {executing && (
            <span className="px-3 py-2 text-sm text-blue-700 bg-blue-50 rounded-lg">Creating in ERP… (in progress)</span>
          )}

          {executed && (
            <span className="px-3 py-2 text-sm text-emerald-700 bg-emerald-50 rounded-lg">
              ✓ Created in ERP — {d.erp_reference}
            </span>
          )}

          {d.execution_status === 'failed' && d.error_message && (
            <span className="text-xs text-red-600">Last error: {d.error_message}</span>
          )}

          {editable && d.approved !== -1 && (
            <button
              disabled={busy}
              onClick={() => reject(d.id)}
              className="px-4 py-2 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
              title="Soft-reject. Does not delete the source email."
            >
              Reject
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-6">

      {/* Safety banner */}
      <div className="mb-5 bg-amber-50 border border-amber-200 rounded-xl px-5 py-3 text-sm text-amber-800">
        <p className="font-semibold">Approval and execution are separate</p>
        <p className="text-amber-700 text-xs mt-0.5">
          Approving a proposal does <strong>not</strong> create anything. Only the explicit
          <strong> “Create Task in ERP”</strong> button on an approved proposal sends it to the ERP,
          and it is safe against repeated or concurrent clicks.
        </p>
      </div>

      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold text-slate-800">AI Proposals</h1>
        <button onClick={load} className="text-xs text-slate-500 border border-slate-200 rounded-lg px-3 py-1.5 hover:bg-slate-50">
          Refresh
        </button>
      </div>

      {error && <p className="text-red-500 text-sm mb-3">{error}</p>}
      {msg   && <p className="text-green-600 text-sm mb-3">{msg}</p>}

      {/* ── Pending review ──────────────────────────────────────────────────── */}
      <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Pending review</h2>
      {pending.length === 0 ? (
        <div className="bg-white border border-slate-200 rounded-xl px-6 py-8 text-center text-slate-400 text-sm mb-6">
          No pending proposals
        </div>
      ) : (
        <div className="space-y-2 mb-6">{pending.map(renderRow)}</div>
      )}

      {/* ── Approved — ready to execute ─────────────────────────────────────── */}
      <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Approved</h2>
      {approved.length === 0 ? (
        <div className="bg-white border border-slate-200 rounded-xl px-6 py-8 text-center text-slate-400 text-sm">
          No approved proposals
        </div>
      ) : (
        <div className="space-y-2">{approved.map(renderRow)}</div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="px-5 py-4">
      <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">{title}</h3>
      {children}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-slate-400">{label}: </span>
      <span className="text-slate-700 font-mono break-all">{value}</span>
    </div>
  );
}

function WarningBox({ color, children }: { color: 'red' | 'amber' | 'blue'; children: React.ReactNode }) {
  const styles = {
    red:   'bg-red-50 border-red-200 text-red-700',
    amber: 'bg-amber-50 border-amber-200 text-amber-700',
    blue:  'bg-blue-50 border-blue-200 text-blue-700',
  };
  return (
    <div className={`border rounded-lg px-3 py-2 text-xs ${styles[color]}`}>
      {children}
    </div>
  );
}
