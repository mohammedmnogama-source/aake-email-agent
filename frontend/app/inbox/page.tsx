'use client';
import { useEffect, useState } from 'react';
import { api } from '../../lib/api';

function formatEmailDate(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const isYesterday = date.toDateString() === yesterday.toDateString();
  if (isToday) return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (isYesterday) return `Yesterday ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function getEmailState(email: any): 'accepted' | 'dismissed' | 'review' | 'pending' {
  if (email.was_approved > 0 || email.auto_finished) return 'accepted';
  if (email.manually_handled) return 'dismissed';
  if (email.status === 'decided') return 'review';
  return 'pending';
}

const CATEGORY_COLORS: Record<string, string> = {
  lead:                 'bg-green-100 text-green-800',
  vendor_quote_request: 'bg-blue-100 text-blue-800',
  customer_inquiry:     'bg-purple-100 text-purple-800',
  internal:             'bg-gray-100 text-gray-700',
  spam:                 'bg-red-100 text-red-700',
  other:                'bg-slate-100 text-slate-600',
};

const ACTION_LABELS: Record<string, string> = {
  draft_reply:        '✉️ Draft reply ready',
  forward_to_vendor:  '📤 Forward to vendor',
  extract_lead_info:  '👤 New lead',
  summarize_only:     '📋 Summary only',
  create_rfq:         '📝 Create RFQ',
  no_action:          '—',
};

async function post(path: string, data?: object) {
  const token = localStorage.getItem('aake_token');
  const res = await fetch(`${path}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      ...(data ? { 'Content-Type': 'application/json' } : {}),
    },
    body: data ? JSON.stringify(data) : undefined,
  });
  return res.json();
}

async function get(path: string) {
  const token = localStorage.getItem('aake_token');
  const res = await fetch(`${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  return res.json();
}

async function patch(path: string) {
  const token = localStorage.getItem('aake_token');
  await fetch(`${path}`, {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${token}` },
  });
}

export default function InboxPage() {
  const [emails, setEmails]           = useState<any[]>([]);
  const [selected, setSelected]       = useState<any | null>(null);
  const [editedDraft, setEditedDraft] = useState('');
  const [loading, setLoading]         = useState(true);
  const [syncing, setSyncing]         = useState(false);
  const [syncStatus, setSyncStatus]   = useState<any | null>(null);
  const [backfilling, setBackfilling] = useState(false);
  const [sentSync, setSentSync]       = useState<{running:boolean;indexed:number;total:number;done:boolean;error:string|null;collection_count:number} | null>(null);
  const [sentSyncPoll, setSentSyncPoll] = useState<ReturnType<typeof setInterval> | null>(null);
  const [learnStats, setLearnStats]     = useState<any | null>(null);
  const [chaserRunning, setChaserRunning] = useState(false);
  const [approving, setApproving]       = useState(false);
  const [redrafting, setRedrafting]     = useState(false);
  const [threadSummary, setThreadSummary] = useState<{ thread_count: number; summary_text: string } | null>(null);
  const [threadLoading, setThreadLoading] = useState(false);
  const [dailySummary, setDailySummary] = useState<{ email_count: number; overview: string; attention: { title: string; contact: string; detail: string }[]; vendors: { title: string; contact: string; detail: string }[]; priorities: string[] } | null>(null);
  const [dailyLoading, setDailyLoading] = useState(false);
  const [redraftNote, setRedraftNote]   = useState('');
  const [message, setMessage]           = useState('');

  // Search + filter state
  const [search, setSearch]           = useState('');
  const [activeFilter, setActiveFilter] = useState('all');

  // ERP — RFQ modal
  const [erpModal, setErpModal]       = useState(false);
  const [erpForm, setErpForm]         = useState({ subject: '', description: '', notes: '', received_date: '', customer_name: '' });
  const [erpSending, setErpSending]   = useState(false);

  // ERP — Lead modal
  const [leadModal, setLeadModal]     = useState(false);
  const [leadForm, setLeadForm]       = useState({ first_name: '', last_name: '', company: '', email: '', phone: '', notes: '' });
  const [leadSending, setLeadSending] = useState(false);

  // ERP — Task modal
  const [taskModal, setTaskModal]     = useState(false);
  const [taskForm, setTaskForm]       = useState({ title: '', description: '', priority: 'medium', due_date: '' });
  const [taskSending, setTaskSending] = useState(false);

  // Compose modal
  const [composeModal, setComposeModal] = useState(false);
  const [composeForm, setComposeForm]   = useState({ description: '', to_name: '', to_email: '', subject: '' });
  const [composeDraft, setComposeDraft] = useState('');
  const [composeLoading, setComposeLoading] = useState(false);

  function loadEmails() {
    setLoading(true);
    get('/api/inbox')
      .then(data => setEmails(Array.isArray(data) ? data : []))
      .catch(() => setEmails([]))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadEmails();
    // Load current sent_history count on mount so the Learn button shows it
    get('/api/inbox/sent-sync/status').then(s => setSentSync(s)).catch(() => {});
    // Load learning stats
    get('/api/inbox/learning-stats').then(s => setLearnStats(s)).catch(() => {});
  }, []);

  // Silent auto-refresh every 2 minutes to pick up scheduler-fetched emails
  useEffect(() => {
    const interval = setInterval(() => {
      if (!syncing) loadEmails();
    }, 120_000);
    return () => clearInterval(interval);
  }, [syncing]);

  async function handleSync() {
    setSyncing(true);
    setSyncStatus(null);
    setMessage('');
    try {
      await post('/api/inbox/sync');

      // Poll for live status every second until done
      const poll = setInterval(async () => {
        try {
          const status = await get('/api/inbox/sync-status');
          setSyncStatus(status);
          if (!status.running && (status.stage === 'done' || status.stage === 'error')) {
            clearInterval(poll);
            setSyncing(false);
            if (status.stage === 'done') {
              setMessage(status.message);
              loadEmails();
            } else {
              setMessage(`Sync error: ${status.error}`);
            }
            setTimeout(() => setSyncStatus(null), 4000);
          }
        } catch {
          clearInterval(poll);
          setSyncing(false);
          setMessage('Sync failed.');
        }
      }, 1000);

    } catch {
      setMessage('Sync failed.');
      setSyncing(false);
    }
  }

  async function handleBackfill() {
    setBackfilling(true);
    setMessage('');
    try {
      const res = await post('/api/inbox/backfill');
      setMessage(res.message || 'Backfill complete.');
    } catch {
      setMessage('Backfill failed.');
    } finally {
      setBackfilling(false);
    }
  }

  async function handleLearnSent() {
    if (sentSync?.running) return;
    setMessage('');
    // Start the job
    await post('/api/inbox/sent-sync');
    // Poll for progress every 2 seconds
    const poll = setInterval(async () => {
      try {
        const status = await get('/api/inbox/sent-sync/status');
        setSentSync(status);
        if (!status.running && status.done) {
          clearInterval(poll);
          setSentSyncPoll(null);
          if (status.error) {
            setMessage(`Sent sync failed: ${status.error}`);
          } else {
            setMessage(`Sent history indexed: ${status.indexed} new emails. Total in collection: ${status.collection_count}.`);
          }
        }
      } catch { clearInterval(poll); setSentSyncPoll(null); }
    }, 2000);
    setSentSyncPoll(poll);
    // Fetch initial status immediately
    const initial = await get('/api/inbox/sent-sync/status');
    setSentSync(initial);
  }

  async function handleRunChaser() {
    if (chaserRunning) return;
    setChaserRunning(true);
    setMessage('');
    try {
      const res = await post('/api/inbox/run-followup-chaser');
      setMessage(res.message);
      await loadEmails();
    } catch (e: any) {
      setMessage('Follow-up chaser error: ' + e.message);
    } finally {
      setChaserRunning(false);
    }
  }

  async function handleApprove() {
    if (!selected?.email?.id) return;
    setApproving(true);
    setMessage('');
    try {
      const res = await post(`/api/inbox/${selected.email.id}/approve`, {
        draft_content: editedDraft,
      });
      if (res.test_mode) {
        setMessage('Draft saved to test file (test mode is ON — turn it off in Settings for real drafts).');
      } else {
        setMessage('Draft saved to your Drafts folder. Open your email and hit Send.');
      }
      loadEmails();
    } catch {
      setMessage('Approve failed.');
    } finally {
      setApproving(false);
    }
  }

  async function handleRedraft() {
    if (!selected?.email?.id) return;
    setRedrafting(true);
    setMessage('');
    try {
      const res = await post(`/api/inbox/${selected.email.id}/redraft`, {
        current_draft: editedDraft,
        instruction: redraftNote,
      });
      if (res.draft) {
        setEditedDraft(res.draft);
        setRedraftNote('');
      }
    } catch {
      setMessage('Re-draft failed.');
    } finally {
      setRedrafting(false);
    }
  }

  async function handleDailySummary() {
    if (dailyLoading) return;
    setDailyLoading(true);
    setDailySummary(null);
    try {
      const res = await api.getDailySummary();
      setDailySummary(res);
    } catch (e: any) {
      setMessage('Daily summary failed: ' + e.message);
    } finally {
      setDailyLoading(false);
    }
  }

  async function handleThreadSummary() {
    if (!selected?.email?.id || threadLoading) return;
    setThreadLoading(true);
    setThreadSummary(null);
    try {
      const res = await api.summarizeThread(selected.email.id);
      setThreadSummary(res);
    } catch (e: any) {
      setMessage('Thread summary failed: ' + e.message);
    } finally {
      setThreadLoading(false);
    }
  }

  async function handleReject() {
    if (!selected?.email?.id) return;
    try {
      await post(`/api/inbox/${selected.email.id}/reject`);
      setMessage('Marked as rejected.');
      setSelected(null);
      loadEmails();
    } catch {
      setMessage('Reject failed.');
    }
  }

  function openErpModal() {
    if (!selected) return;
    const e = selected.email;
    const s = selected.suggestion;
    const dateStr = e.received_at
      ? new Date(e.received_at).toISOString().split('T')[0]
      : new Date().toISOString().split('T')[0];
    setErpForm({
      subject:       e.subject || '',
      description:   s?.summary || e.body_preview || '',
      notes:         `Imported from email on ${dateStr}`,
      received_date: dateStr,
      customer_name: e.from_name || '',
    });
    setErpModal(true);
  }

  async function sendToErp() {
    if (!selected?.email?.id) return;
    setErpSending(true);
    try {
      // Route through our FastAPI backend — avoids CORS issues
      const data = await post(`/api/inbox/${selected.email.id}/send-to-erp`, erpForm);
      if (data.ok) {
        setMessage(`✅ RFQ ${data.reference} created in ERP!`);
        setErpModal(false);
      } else {
        setMessage(`ERP error: ${data.error || 'Unknown error'}`);
      }
    } catch {
      setMessage('Could not reach ERP.');
    } finally {
      setErpSending(false);
    }
  }

  function openLeadModal() {
    if (!selected) return;
    const e = selected.email;
    // Split "Arifa Bi Naveed" → first="Arifa" last="Bi Naveed"
    const nameParts = (e.from_name || '').trim().split(' ');
    setLeadForm({
      first_name: nameParts[0] || '',
      last_name:  nameParts.slice(1).join(' ') || '',
      company:    '',
      email:      e.from_address || '',
      phone:      '',
      notes:      `From email: "${e.subject}" on ${e.received_at ? new Date(e.received_at).toLocaleDateString() : 'unknown date'}`,
    });
    setLeadModal(true);
  }

  async function saveLead() {
    if (!selected?.email?.id) return;
    setLeadSending(true);
    try {
      const data = await post(`/api/inbox/${selected.email.id}/save-as-lead`, leadForm);
      if (data.ok) {
        setMessage('👤 Lead saved in ERP!');
        setLeadModal(false);
      } else {
        setMessage(`Lead error: ${data.error || 'Unknown error'}`);
      }
    } catch {
      setMessage('Could not save lead. Is the ERP /api/leads endpoint built?');
    } finally {
      setLeadSending(false);
    }
  }

  function openTaskModal() {
    if (!selected) return;
    const e = selected.email;
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    setTaskForm({
      title:       `Follow up: ${e.subject || '(no subject)'}`,
      description: selected.suggestion?.summary || '',
      priority:    'medium',
      due_date:    tomorrow.toISOString().split('T')[0],
    });
    setTaskModal(true);
  }

  async function createTask() {
    if (!selected?.email?.id) return;
    setTaskSending(true);
    try {
      const data = await post(`/api/inbox/${selected.email.id}/create-task`, taskForm);
      if (data.ok) {
        setMessage('✅ Task created in ERP!');
        setTaskModal(false);
      } else {
        setMessage(`Task error: ${data.error || 'Unknown error'}`);
      }
    } catch {
      setMessage('Could not create task. Is the ERP /api/tasks endpoint built?');
    } finally {
      setTaskSending(false);
    }
  }

  async function openEmail(emailId: number) {
    const detail = await get(`/api/inbox/${emailId}`);
    setSelected(detail);
    setEditedDraft(detail?.suggestion?.draft_content || '');
    setThreadSummary(null);
    // Mark as read
    patch(`/api/inbox/${emailId}/read`);
    // Update local read state immediately without full reload
    setEmails(prev => prev.map(e => e.id === emailId ? { ...e, is_read: 1 } : e));
  }

  async function handleCompose() {
    if (!composeForm.description.trim()) return;
    setComposeLoading(true);
    setComposeDraft('');
    try {
      const data = await post('/api/inbox/compose', composeForm);
      setComposeDraft(data.draft || '');
    } catch {
      setComposeDraft('Failed to generate draft.');
    } finally {
      setComposeLoading(false);
    }
  }

  const unreadCount = emails.filter(e => !e.is_read).length;

  // Apply search + category filter client-side
  const filteredEmails = emails.filter(e => {
    if (activeFilter === 'followup_chaser') return e.source === 'followup_chaser';
    if (activeFilter === 'accepted')  return getEmailState(e) === 'accepted';
    if (activeFilter === 'dismissed') return getEmailState(e) === 'dismissed';
    if (activeFilter === 'review')    return getEmailState(e) === 'review';
    const q = search.toLowerCase();
    const matchesSearch = !q
      || (e.subject || '').toLowerCase().includes(q)
      || (e.from_name || '').toLowerCase().includes(q)
      || (e.from_address || '').toLowerCase().includes(q)
      || (e.summary || '').toLowerCase().includes(q);
    return matchesSearch; // 'all'
  });

  return (
    <div className="h-screen flex flex-col bg-white overflow-hidden">

      {/* ── Toolbar ── */}
      <div className="shrink-0 h-12 border-b border-slate-200 flex items-center px-4 gap-3 bg-white">
        <h1 className="text-base font-semibold text-slate-800">Inbox</h1>
        {unreadCount > 0 && (
          <span className="bg-blue-600 text-white text-xs font-bold px-2 py-0.5 rounded-full">
            {unreadCount}
          </span>
        )}
        <span className="text-xs text-slate-400">auto-sync every 15 min</span>
        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={handleLearnSent}
            disabled={sentSync?.running}
            className="text-xs px-3 py-1.5 rounded border border-slate-300 text-slate-600 hover:bg-slate-100 disabled:opacity-50"
            title={sentSync ? `${sentSync.collection_count} sent emails indexed` : 'Index your Sent folder so AI learns your writing style'}
          >
            {sentSync?.running
              ? `🧠 ${sentSync.indexed}${sentSync.total > 0 ? `/${sentSync.total}` : ''}…`
              : sentSync?.collection_count
              ? `🧠 Learn (${sentSync.collection_count})`
              : '🧠 Learn'}
          </button>
          <button
            onClick={handleDailySummary}
            disabled={dailyLoading}
            className="text-xs px-3 py-1.5 rounded border border-violet-300 text-violet-700 hover:bg-violet-50 disabled:opacity-50"
            title="Summarize all emails from today and yesterday"
          >
            {dailyLoading ? '📋 Summarizing…' : '📋 Daily Summary'}
          </button>
          <button
            onClick={handleRunChaser}
            disabled={chaserRunning}
            className="text-xs px-3 py-1.5 rounded border border-orange-300 text-orange-700 hover:bg-orange-50 disabled:opacity-50"
            title="Find contacts who haven't replied and create follow-up drafts"
          >
            {chaserRunning ? '⏰ Checking…' : '⏰ Follow-ups'}
          </button>
          <button
            onClick={() => { setComposeForm({ description: '', to_name: '', to_email: '', subject: '' }); setComposeDraft(''); setComposeModal(true); }}
            className="text-xs px-3 py-1.5 rounded bg-blue-600 text-white hover:bg-blue-700"
          >
            ✏️ Draft Email
          </button>
          <button
            onClick={handleSync}
            disabled={syncing}
            className="text-xs px-3 py-1.5 rounded bg-slate-800 text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {syncing ? 'Syncing...' : '🔄 Sync'}
          </button>
        </div>
      </div>

      {/* ── Sync progress banner ── */}
      {syncStatus && (
        <div className="shrink-0 border-b border-blue-200 bg-blue-50">
          <div className="px-4 py-2 flex items-center gap-3">
            {syncStatus.running && (
              <svg className="animate-spin h-3.5 w-3.5 text-blue-600 shrink-0" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
              </svg>
            )}
            {!syncStatus.running && syncStatus.stage === 'done' && <span className="text-sm">✅</span>}
            {!syncStatus.running && syncStatus.stage === 'error' && <span className="text-sm">❌</span>}
            <p className="text-xs text-blue-800 font-medium flex-1">{syncStatus.message}</p>
            {syncStatus.running && syncStatus.total > 0 && (
              <span className="text-xs text-blue-600 shrink-0">{syncStatus.current}/{syncStatus.total}</span>
            )}
          </div>
          {syncStatus.running && syncStatus.total > 0 && (
            <div className="h-0.5 bg-blue-100">
              <div
                className="h-0.5 bg-blue-500 transition-all duration-500"
                style={{ width: `${Math.round((syncStatus.current / syncStatus.total) * 100)}%` }}
              />
            </div>
          )}
        </div>
      )}

      {!syncStatus && message && (
        <div className="shrink-0 px-4 py-2 text-xs bg-blue-50 border-b border-blue-200 text-blue-800">
          {message}
        </div>
      )}

      {/* ── Daily Summary Panel ── */}
      {dailySummary && (
        <div className="shrink-0 border-b border-violet-200 bg-violet-50 px-4 py-3">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-semibold text-violet-600 uppercase tracking-wide">
              📋 Daily Briefing — {dailySummary.email_count} emails (last 48 hrs)
            </p>
            <button onClick={() => setDailySummary(null)} className="text-violet-300 hover:text-violet-600 text-lg leading-none">×</button>
          </div>
          <div className="text-sm text-slate-700 leading-relaxed max-h-64 overflow-y-auto space-y-1">
            <p className="text-slate-700">{dailySummary.overview}</p>
            {dailySummary.attention.length > 0 && (
              <div className="mt-2"><p className="text-xs font-bold text-amber-600 uppercase tracking-wide mb-1">🔔 Needs Attention</p>
                {dailySummary.attention.map((a, i) => <p key={i} className="text-slate-700">• {a.title}: {a.detail}</p>)}
              </div>
            )}
            {dailySummary.priorities.length > 0 && (
              <div className="mt-2"><p className="text-xs font-bold text-green-600 uppercase tracking-wide mb-1">✅ Priorities</p>
                {dailySummary.priorities.map((p, i) => <p key={i} className="text-slate-700">{i + 1}. {p}</p>)}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Learning stats bar (Phase 1.5) ── */}
      {learnStats && (
        <div className="shrink-0 border-b border-slate-100 bg-slate-50 px-4 py-2 flex items-center gap-4 flex-wrap">
          <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide">AI Learning</span>
          <span className="text-xs text-slate-600">
            <span className="font-semibold text-slate-800">{learnStats.approved_total}</span> approvals
          </span>
          <span className="text-xs text-slate-600">
            <span className="font-semibold text-slate-800">{learnStats.pct_clean_overall}%</span> accepted without edits
          </span>
          <span className="text-xs text-slate-600">
            <span className="font-semibold text-slate-800">{learnStats.sent_history_count}</span> sent emails indexed
          </span>
          {learnStats.approved_total === 0 && (
            <span className="text-[11px] text-amber-600 font-medium">
              ⚡ Start approving drafts to teach the AI your style
            </span>
          )}
          {Object.entries(learnStats.by_category || {}).map(([cat, s]: [string, any]) => (
            <span key={cat} className="text-[11px] bg-white border border-slate-200 rounded-full px-2 py-0.5 text-slate-500">
              {cat.replace(/_/g,' ')}: {s.pct_clean}%
            </span>
          ))}
        </div>
      )}

      {/* ── Two-panel layout ── */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── LEFT: email list ── */}
        <div className="w-[340px] shrink-0 border-r border-slate-200 flex flex-col overflow-hidden bg-white">

          {/* Search + filter */}
          <div className="shrink-0 p-3 border-b border-slate-100 space-y-2">
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search..."
              className="w-full text-xs border border-slate-200 rounded px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-slate-300 bg-white"
            />
            <div className="flex flex-wrap gap-1">
              {[
                { key: 'all',        label: 'All',           count: emails.length },
                { key: 'review',     label: '🔍 Under Review', count: emails.filter(e => getEmailState(e) === 'review').length },
                { key: 'accepted',   label: '✅ Accepted',    count: emails.filter(e => getEmailState(e) === 'accepted').length },
                { key: 'dismissed',  label: '✕ Dismissed',   count: emails.filter(e => getEmailState(e) === 'dismissed').length },
                ...(emails.filter(e => e.source === 'followup_chaser').length > 0
                  ? [{ key: 'followup_chaser', label: '⏰ Follow-ups', count: emails.filter(e => e.source === 'followup_chaser').length }]
                  : []),
              ].map(f => (
                <button
                  key={f.key}
                  onClick={() => setActiveFilter(f.key)}
                  className={`text-[11px] px-2 py-0.5 rounded-full border transition-colors ${
                    activeFilter === f.key
                      ? 'bg-slate-800 text-white border-slate-800'
                      : 'bg-white text-slate-600 border-slate-200 hover:border-slate-400'
                  }`}
                >
                  {f.label}
                  {f.count > 0 && (
                    <span className={`ml-1 ${activeFilter === f.key ? 'text-slate-300' : 'text-slate-400'}`}>{f.count}</span>
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* Scrollable email list */}
          <div className="flex-1 overflow-y-auto">
            {loading ? (
              <p className="text-slate-400 text-xs p-4">Loading...</p>
            ) : filteredEmails.length === 0 ? (
              <div className="text-center py-16 text-slate-400">
                {emails.length === 0 ? (
                  <>
                    <p className="text-3xl mb-2">📭</p>
                    <p className="text-sm font-medium">No emails yet</p>
                    <p className="text-xs mt-1">Click Sync to fetch from IMAP</p>
                  </>
                ) : (
                  <>
                    <p className="text-2xl mb-2">🔍</p>
                    <p className="text-sm font-medium">No match</p>
                    <button onClick={() => { setSearch(''); setActiveFilter('all'); }} className="text-xs text-blue-500 mt-1 hover:underline">Clear filter</button>
                  </>
                )}
              </div>
            ) : (
              <div>
                {filteredEmails.map(email => {
                  const isUnread = !email.is_read;
                  const isSelected = selected?.email?.id === email.id;
                  const isFollowup = email.source === 'followup_chaser';
                  const emailState = getEmailState(email);
                  const isDismissed = emailState === 'dismissed';
                  const isAccepted = emailState === 'accepted';
                  const dateStr = email.received_at ? formatEmailDate(email.received_at) : '';
                  return (
                    <div
                      key={email.id}
                      onClick={() => !isDismissed && openEmail(email.id)}
                      className={`flex items-start gap-2.5 px-3 py-3 border-b transition-colors ${
                        isDismissed
                          ? 'opacity-40 cursor-default border-b-slate-100'
                          : isSelected
                          ? 'bg-blue-50 border-l-2 border-l-blue-600 border-b-slate-100 cursor-pointer'
                          : isFollowup
                          ? 'bg-orange-50 border-b-orange-100 hover:bg-orange-100 cursor-pointer'
                          : 'border-b-slate-100 hover:bg-slate-50 cursor-pointer'
                      }`}
                    >
                      {/* Unread dot */}
                      <div className="mt-1.5 shrink-0 w-2 h-2 rounded-full" style={{ background: isUnread ? '#2563eb' : 'transparent' }} />

                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-1 mb-0.5">
                          <p className={`text-sm truncate ${isUnread && !isDismissed ? 'font-semibold text-slate-900' : 'font-medium text-slate-700'}`}>
                            {email.from_name || email.from_address || 'Unknown'}
                          </p>
                          <span className="text-[11px] text-slate-400 shrink-0 mt-0.5 whitespace-nowrap">{dateStr}</span>
                        </div>
                        <p className={`text-xs truncate mb-0.5 ${isUnread && !isDismissed ? 'text-slate-800' : 'text-slate-500'}`}>
                          {email.subject || '(no subject)'}
                        </p>
                        <div className="flex items-center gap-2">
                          {email.summary && (
                            <p className="text-[11px] text-slate-400 truncate flex-1">{email.summary}</p>
                          )}
                          {isDismissed && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded-full shrink-0 bg-slate-200 text-slate-500">dismissed</span>
                          )}
                          {isAccepted && !isDismissed && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded-full shrink-0 bg-green-100 text-green-700">accepted</span>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* ── RIGHT: detail pane ── */}
        <div className="flex-1 overflow-y-auto bg-white">
          {!selected ? (
            <div className="flex items-center justify-center h-full text-slate-400 text-sm">
              Select an email to view
            </div>
          ) : (
            <div className="p-6 space-y-5 max-w-3xl">

              {/* Email header */}
              <div className="pb-4 border-b border-slate-100">
                <h2 className="font-semibold text-slate-800 text-base mb-1">
                  {selected.email.subject || '(no subject)'}
                </h2>
                <p className="text-xs text-slate-500">
                  From: <span className="font-medium text-slate-700">{selected.email.from_name || selected.email.from_address || '—'}</span>
                  {selected.email.received_at && (
                    <span className="ml-2">{new Date(selected.email.received_at).toLocaleString()}</span>
                  )}
                </p>
                {selected.email.to_addresses && (
                  <p className="text-xs text-slate-500 mt-0.5">
                    To: <span className="font-medium text-slate-700">{selected.email.to_addresses}</span>
                  </p>
                )}
                {selected.suggestion?.category && (
                  <span className={`inline-block mt-2 text-xs px-2 py-0.5 rounded-full ${CATEGORY_COLORS[selected.suggestion.category] || 'bg-slate-100 text-slate-600'}`}>
                    {selected.suggestion.category.replace(/_/g, ' ')}
                  </span>
                )}
              </div>

              {/* Thread Summary button + result */}
              <div>
                <button
                  onClick={handleThreadSummary}
                  disabled={threadLoading}
                  className="text-xs px-3 py-1.5 rounded border border-violet-300 text-violet-700 hover:bg-violet-50 disabled:opacity-50 font-medium"
                >
                  {threadLoading ? '🧵 Analyzing thread...' : '🧵 Summarize Thread'}
                </button>

                {threadSummary && (
                  <div className="mt-3 bg-violet-50 border border-violet-200 rounded-lg p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <p className="text-xs font-semibold text-violet-500 uppercase tracking-wide">
                        Thread Summary — {threadSummary.thread_count} email{threadSummary.thread_count !== 1 ? 's' : ''}
                      </p>
                      <button onClick={() => setThreadSummary(null)} className="text-violet-300 hover:text-violet-500 text-lg leading-none">×</button>
                    </div>
                    <div className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed font-sans">
                      {threadSummary.summary_text.split('\n').map((line, i) => {
                        const isHeader = /^(CONTEXT|SUMMARY|STATUS|NEXT STEPS)$/.test(line.trim());
                        return isHeader
                          ? <p key={i} className="text-xs font-bold text-violet-600 uppercase tracking-wide mt-3 mb-1">{line.trim()}</p>
                          : <p key={i} className={line.trim() === '' ? 'mt-1' : 'text-sm text-slate-700'}>{line}</p>;
                      })}
                    </div>
                  </div>
                )}
              </div>

              {/* AI Summary */}
              {selected.suggestion?.summary && (
                <div className="bg-slate-50 rounded-lg p-4">
                  <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1.5">AI Summary</p>
                  <p className="text-sm text-slate-700">{selected.suggestion.summary}</p>
                  {selected.suggestion.reasoning && (
                    <p className="text-xs text-slate-400 mt-2 italic">{selected.suggestion.reasoning}</p>
                  )}
                </div>
              )}

              {/* Draft Reply */}
              {selected.suggestion?.draft_content && (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">Draft Reply</p>
                    <span className="text-xs text-slate-400">Edit, then approve or re-draft</span>
                  </div>

                  <textarea
                    value={editedDraft}
                    onChange={e => setEditedDraft(e.target.value)}
                    rows={8}
                    className="w-full text-sm text-slate-700 bg-slate-50 rounded-lg p-3 border border-slate-200 font-sans resize-y focus:outline-none focus:ring-2 focus:ring-blue-300 focus:border-blue-400"
                  />

                  {/* Re-draft row */}
                  <div className="mt-2 flex gap-2">
                    <input
                      value={redraftNote}
                      onChange={e => setRedraftNote(e.target.value)}
                      placeholder='Any changes? e.g. "make it shorter" or "mention we reply by Friday"'
                      className="flex-1 text-sm border border-slate-200 rounded px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-300"
                    />
                    <button
                      onClick={handleRedraft}
                      disabled={redrafting}
                      className="text-sm px-3 py-1.5 rounded bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50 font-medium whitespace-nowrap"
                    >
                      {redrafting ? '⏳ Drafting...' : '✨ Re-draft'}
                    </button>
                  </div>

                  {/* Action buttons */}
                  <div className="mt-3 flex gap-2 flex-wrap">
                    <button
                      onClick={handleApprove}
                      disabled={approving}
                      className="text-sm px-4 py-2 rounded bg-green-600 text-white hover:bg-green-500 disabled:opacity-50 font-medium"
                    >
                      {approving ? 'Saving...' : '✅ Approve — Save to Drafts'}
                    </button>
                    <button
                      onClick={handleReject}
                      className="text-sm px-4 py-2 rounded border border-red-200 text-red-600 hover:bg-red-50"
                    >
                      ✕ Reject
                    </button>
                    <button
                      onClick={() => setEditedDraft(selected.suggestion.draft_content)}
                      className="text-sm px-3 py-2 rounded border border-slate-300 text-slate-600 hover:bg-slate-100"
                    >
                      ↩ Reset
                    </button>
                    <button
                      onClick={() => { navigator.clipboard.writeText(editedDraft); setMessage('Draft copied to clipboard.'); }}
                      className="text-sm px-3 py-2 rounded border border-slate-300 text-slate-600 hover:bg-slate-100"
                    >
                      📋 Copy
                    </button>
                  </div>
                </div>
              )}

              {/* Dismiss button for emails without a draft (internal, spam, no_action) */}
              {!selected.suggestion?.draft_content && (
                <div className="flex gap-2">
                  <button
                    onClick={handleReject}
                    className="text-sm px-4 py-2 rounded border border-slate-300 text-slate-600 hover:bg-slate-100"
                  >
                    ✕ Dismiss
                  </button>
                </div>
              )}

              {/* ERP actions */}
              <div className="pt-2 border-t border-slate-100">
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">Send to ERP</p>
                <div className="flex gap-2 flex-wrap">
                  {['lead','customer_inquiry','other',null,undefined].includes(selected.suggestion?.category) && (
                    <button onClick={openErpModal}
                      className="text-sm px-3 py-1.5 rounded border border-indigo-300 text-indigo-700 hover:bg-indigo-50 font-medium">
                      📋 Create RFQ
                    </button>
                  )}
                  {selected.suggestion?.category === 'lead' && (
                    <button onClick={openLeadModal}
                      className="text-sm px-3 py-1.5 rounded border border-green-300 text-green-700 hover:bg-green-50 font-medium">
                      👤 Save as Lead
                    </button>
                  )}
                  <button onClick={openTaskModal}
                    className="text-sm px-3 py-1.5 rounded border border-amber-300 text-amber-700 hover:bg-amber-50 font-medium">
                    ✅ Create Task
                  </button>
                </div>
              </div>

              {/* Email body */}
              <div className="pt-2 border-t border-slate-100">
                <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">Email Body</p>
                <pre className="text-xs text-slate-600 bg-slate-50 rounded-lg p-3 whitespace-pre-wrap max-h-64 overflow-y-auto font-sans border border-slate-200">
                  {selected.email.body_text || selected.email.body_preview || '(empty)'}
                </pre>
              </div>

            </div>
          )}
        </div>

      </div>

      {/* ── Modals ── */}

      {/* Lead Modal */}
      {leadModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
            <h2 className="text-lg font-semibold text-slate-800 mb-1">Save as Lead</h2>
            <p className="text-xs text-slate-500 mb-4">Creates a new lead in Aqeeq Intelligence ERP.</p>
            <div className="space-y-3">
              <div className="flex gap-3">
                <div className="flex-1">
                  <label className="text-xs font-semibold text-slate-500 uppercase">First Name</label>
                  <input value={leadForm.first_name} onChange={e => setLeadForm(f => ({...f, first_name: e.target.value}))}
                    className="mt-1 w-full text-sm border border-slate-200 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-300" />
                </div>
                <div className="flex-1">
                  <label className="text-xs font-semibold text-slate-500 uppercase">Last Name</label>
                  <input value={leadForm.last_name} onChange={e => setLeadForm(f => ({...f, last_name: e.target.value}))}
                    className="mt-1 w-full text-sm border border-slate-200 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-300" />
                </div>
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-500 uppercase">Company</label>
                <input value={leadForm.company} onChange={e => setLeadForm(f => ({...f, company: e.target.value}))}
                  placeholder="Optional"
                  className="mt-1 w-full text-sm border border-slate-200 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-300" />
              </div>
              <div className="flex gap-3">
                <div className="flex-1">
                  <label className="text-xs font-semibold text-slate-500 uppercase">Email</label>
                  <input value={leadForm.email} onChange={e => setLeadForm(f => ({...f, email: e.target.value}))}
                    className="mt-1 w-full text-sm border border-slate-200 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-300" />
                </div>
                <div className="flex-1">
                  <label className="text-xs font-semibold text-slate-500 uppercase">Phone</label>
                  <input value={leadForm.phone} onChange={e => setLeadForm(f => ({...f, phone: e.target.value}))}
                    placeholder="Optional"
                    className="mt-1 w-full text-sm border border-slate-200 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-300" />
                </div>
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-500 uppercase">Notes</label>
                <input value={leadForm.notes} onChange={e => setLeadForm(f => ({...f, notes: e.target.value}))}
                  className="mt-1 w-full text-sm border border-slate-200 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-green-300" />
              </div>
            </div>
            <div className="mt-5 flex gap-2 justify-end">
              <button onClick={() => setLeadModal(false)}
                className="text-sm px-4 py-2 rounded border border-slate-300 text-slate-600 hover:bg-slate-100">Cancel</button>
              <button onClick={saveLead} disabled={leadSending}
                className="text-sm px-4 py-2 rounded bg-green-600 text-white hover:bg-green-500 disabled:opacity-50 font-medium">
                {leadSending ? 'Saving...' : '👤 Save Lead'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Task Modal */}
      {taskModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
            <h2 className="text-lg font-semibold text-slate-800 mb-1">Create Task</h2>
            <p className="text-xs text-slate-500 mb-4">Adds a follow-up task in Aqeeq Intelligence ERP.</p>
            <div className="space-y-3">
              <div>
                <label className="text-xs font-semibold text-slate-500 uppercase">Title</label>
                <input value={taskForm.title} onChange={e => setTaskForm(f => ({...f, title: e.target.value}))}
                  className="mt-1 w-full text-sm border border-slate-200 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-amber-300" />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-500 uppercase">Description</label>
                <textarea value={taskForm.description} onChange={e => setTaskForm(f => ({...f, description: e.target.value}))}
                  rows={3}
                  className="mt-1 w-full text-sm border border-slate-200 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-amber-300 resize-none" />
              </div>
              <div className="flex gap-3">
                <div className="flex-1">
                  <label className="text-xs font-semibold text-slate-500 uppercase">Priority</label>
                  <select value={taskForm.priority} onChange={e => setTaskForm(f => ({...f, priority: e.target.value}))}
                    className="mt-1 w-full text-sm border border-slate-200 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-amber-300">
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="urgent">Urgent</option>
                  </select>
                </div>
                <div className="flex-1">
                  <label className="text-xs font-semibold text-slate-500 uppercase">Due Date</label>
                  <input type="date" value={taskForm.due_date} onChange={e => setTaskForm(f => ({...f, due_date: e.target.value}))}
                    className="mt-1 w-full text-sm border border-slate-200 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-amber-300" />
                </div>
              </div>
            </div>
            <div className="mt-5 flex gap-2 justify-end">
              <button onClick={() => setTaskModal(false)}
                className="text-sm px-4 py-2 rounded border border-slate-300 text-slate-600 hover:bg-slate-100">Cancel</button>
              <button onClick={createTask} disabled={taskSending}
                className="text-sm px-4 py-2 rounded bg-amber-500 text-white hover:bg-amber-400 disabled:opacity-50 font-medium">
                {taskSending ? 'Creating...' : '✅ Create Task'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ERP Modal */}
      {erpModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 p-6">
            <h2 className="text-lg font-semibold text-slate-800 mb-1">Create RFQ in ERP</h2>
            <p className="text-xs text-slate-500 mb-4">Review and edit before sending to Aqeeq Intelligence ERP.</p>

            <div className="space-y-3">
              <div>
                <label className="text-xs font-semibold text-slate-500 uppercase">Subject / Title</label>
                <input
                  value={erpForm.subject}
                  onChange={e => setErpForm(f => ({ ...f, subject: e.target.value }))}
                  className="mt-1 w-full text-sm border border-slate-200 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-300"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-500 uppercase">Description / Scope</label>
                <textarea
                  value={erpForm.description}
                  onChange={e => setErpForm(f => ({ ...f, description: e.target.value }))}
                  rows={4}
                  className="mt-1 w-full text-sm border border-slate-200 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-300 resize-y"
                />
              </div>
              <div>
                <label className="text-xs font-semibold text-slate-500 uppercase">Internal Notes</label>
                <input
                  value={erpForm.notes}
                  onChange={e => setErpForm(f => ({ ...f, notes: e.target.value }))}
                  className="mt-1 w-full text-sm border border-slate-200 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-300"
                />
              </div>
              <div className="flex gap-3">
                <div className="flex-1">
                  <label className="text-xs font-semibold text-slate-500 uppercase">Customer Name</label>
                  <input
                    value={erpForm.customer_name}
                    onChange={e => setErpForm(f => ({ ...f, customer_name: e.target.value }))}
                    placeholder="Leave blank if unknown"
                    className="mt-1 w-full text-sm border border-slate-200 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                </div>
                <div className="w-40">
                  <label className="text-xs font-semibold text-slate-500 uppercase">Date Received</label>
                  <input
                    type="date"
                    value={erpForm.received_date}
                    onChange={e => setErpForm(f => ({ ...f, received_date: e.target.value }))}
                    className="mt-1 w-full text-sm border border-slate-200 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                </div>
              </div>
            </div>

            <div className="mt-5 flex gap-2 justify-end">
              <button
                onClick={() => setErpModal(false)}
                className="text-sm px-4 py-2 rounded border border-slate-300 text-slate-600 hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                onClick={sendToErp}
                disabled={erpSending}
                className="text-sm px-4 py-2 rounded bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50 font-medium"
              >
                {erpSending ? 'Sending...' : '📋 Create RFQ'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Compose Modal */}
      {composeModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-semibold text-slate-800">Draft an Email</h2>
                <p className="text-xs text-slate-500 mt-0.5">Tell me what you want to say — I'll write it for you.</p>
              </div>
              <button onClick={() => setComposeModal(false)} className="text-slate-400 hover:text-slate-600 text-xl leading-none">×</button>
            </div>

            <div className="space-y-3">
              <div>
                <label className="text-xs font-semibold text-slate-500 uppercase">What do you want to say?</label>
                <textarea
                  value={composeForm.description}
                  onChange={e => setComposeForm(f => ({ ...f, description: e.target.value }))}
                  placeholder={'e.g. "Tell GIH IT we received their monitor inquiry and will get back with pricing by Friday"'}
                  rows={3}
                  className="mt-1 w-full text-sm border border-slate-200 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-300 resize-none"
                />
              </div>
              <div className="flex gap-3">
                <div className="flex-1">
                  <label className="text-xs font-semibold text-slate-500 uppercase">To (Name)</label>
                  <input value={composeForm.to_name} onChange={e => setComposeForm(f => ({ ...f, to_name: e.target.value }))}
                    placeholder="Optional"
                    className="mt-1 w-full text-sm border border-slate-200 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-300" />
                </div>
                <div className="flex-1">
                  <label className="text-xs font-semibold text-slate-500 uppercase">Subject</label>
                  <input value={composeForm.subject} onChange={e => setComposeForm(f => ({ ...f, subject: e.target.value }))}
                    placeholder="Optional"
                    className="mt-1 w-full text-sm border border-slate-200 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-300" />
                </div>
              </div>
            </div>

            <div className="mt-4 flex gap-2 justify-end">
              <button onClick={() => setComposeModal(false)}
                className="text-sm px-4 py-2 rounded border border-slate-300 text-slate-600 hover:bg-slate-100">Cancel</button>
              <button onClick={handleCompose} disabled={composeLoading || !composeForm.description.trim()}
                className="text-sm px-4 py-2 rounded bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50 font-medium">
                {composeLoading ? 'Drafting...' : '✨ Generate Draft'}
              </button>
            </div>

            {/* Generated draft */}
            {composeDraft && (
              <div className="mt-4 border-t border-slate-100 pt-4">
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs font-semibold text-slate-500 uppercase">Draft</label>
                  <button
                    onClick={() => { navigator.clipboard.writeText(composeDraft); setMessage('Draft copied!'); }}
                    className="text-xs text-blue-600 hover:underline">
                    📋 Copy
                  </button>
                </div>
                <textarea
                  value={composeDraft}
                  onChange={e => setComposeDraft(e.target.value)}
                  rows={8}
                  className="w-full text-sm border border-slate-200 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-300 resize-none font-mono"
                />
                <p className="text-xs text-slate-400 mt-1">You can edit the draft above before copying.</p>
              </div>
            )}
          </div>
        </div>
      )}

    </div>
  );
}
