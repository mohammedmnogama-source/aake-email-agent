'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';

function fmt(dateStr: string) {
  if (!dateStr) return 'Never';
  return new Date(dateStr).toLocaleString('en-GB');
}

export default function SettingsPage() {
  const router = useRouter();
  const [settings, setSettings] = useState<Record<string, { value: string; description: string }>>({});
  const [auditLog, setAuditLog] = useState<any[]>([]);
  const [styleStatus, setStyleStatus] = useState<any>(null);
  const [styleDryRun, setStyleDryRun] = useState<any>(null);
  const [trust, setTrust] = useState<{ threshold: number; categories: any[] } | null>(null);
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');
  const [pw, setPw] = useState({ current: '', new: '', confirm: '' });
  const [loading, setLoading] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) { router.push('/login'); return; }
    loadAll();
  }, []);

  async function loadAll() {
    try {
      const [s, a, ss, t] = await Promise.all([
        api.getSettings(),
        api.getAuditLog(),
        api.getStyleStatus(),
        api.listTrust().catch(() => null),
      ]);
      setSettings(s);
      setAuditLog(a);
      setStyleStatus(ss);
      setTrust(t);
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function handleRevokeTrust(category: string) {
    setLoading(`trust_${category}`);
    try {
      await api.revokeTrust(category);
      const t = await api.listTrust();
      setTrust(t);
      flash(`Trust revoked for ${category}`);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(null);
    }
  }

  async function toggle(key: string) {
    const cur = settings[key]?.value;
    const newVal = cur === '1' ? '0' : '1';
    setLoading(key);
    try {
      await api.updateSetting(key, newVal);
      setSettings((s) => ({ ...s, [key]: { ...s[key], value: newVal } }));
      flash('Saved');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(null);
    }
  }

  async function saveSetting(key: string, value: string) {
    setLoading(key);
    try {
      await api.updateSetting(key, value);
      setSettings((s) => ({ ...s, [key]: { ...s[key], value } }));
      flash('Saved');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(null);
    }
  }

  async function changePw() {
    if (pw.new !== pw.confirm) { setError('Passwords do not match'); return; }
    setLoading('pw');
    try {
      await api.changePassword(pw.current, pw.new);
      setPw({ current: '', new: '', confirm: '' });
      flash('Password changed');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(null);
    }
  }

  async function refreshStyle() {
    setLoading('style');
    setError('');
    try {
      const res = await api.refreshStyle();
      if (res.dry_run) {
        setStyleDryRun(res);
        flash('Style profile ready — review and confirm below');
      } else {
        setStyleDryRun(null);
        await loadAll();
        flash('Style profile refreshed and saved');
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(null);
    }
  }

  async function confirmStyle() {
    if (!styleDryRun) return;
    setLoading('confirm_style');
    try {
      await api.confirmStyle(JSON.stringify(styleDryRun.profile), styleDryRun.email_count);
      setStyleDryRun(null);
      await loadAll();
      flash('Style confirmed and saved');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(null);
    }
  }

  function flash(m: string) {
    setMsg(m);
    setTimeout(() => setMsg(''), 3000);
  }

  const testMode = settings['test_mode']?.value === '1';
  const useStyle = settings['use_style_for_drafts']?.value === '1';

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
      <h1 className="text-xl font-bold text-slate-800">Settings</h1>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded-lg">
          {error}
          <button className="ml-2 text-red-400 hover:text-red-600" onClick={() => setError('')}>✕</button>
        </div>
      )}
      {msg && (
        <div className="bg-green-50 border border-green-200 text-green-700 text-sm px-4 py-3 rounded-lg">{msg}</div>
      )}

      {/* General */}
      <section className="bg-white border border-slate-200 rounded-xl p-5">
        <h2 className="font-semibold text-slate-800 mb-4">General</h2>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Test Mode</p>
              <p className="text-xs text-slate-400">Approvals write to files, not real Drafts</p>
            </div>
            <button
              onClick={() => toggle('test_mode')}
              disabled={loading === 'test_mode'}
              className={`w-12 h-6 rounded-full transition-colors ${testMode ? 'bg-red-500' : 'bg-slate-300'}`}
            >
              <span className={`block w-4 h-4 bg-white rounded-full mx-1 transition-transform ${testMode ? 'translate-x-6' : ''}`} />
            </button>
          </div>

          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Use Style in Drafts</p>
              <p className="text-xs text-slate-400">Include your writing style when generating drafts</p>
            </div>
            <button
              onClick={() => toggle('use_style_for_drafts')}
              disabled={loading === 'use_style_for_drafts'}
              className={`w-12 h-6 rounded-full transition-colors ${useStyle ? 'bg-green-500' : 'bg-slate-300'}`}
            >
              <span className={`block w-4 h-4 bg-white rounded-full mx-1 transition-transform ${useStyle ? 'translate-x-6' : ''}`} />
            </button>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex-1">
              <p className="text-sm font-medium mb-1">Poll Interval (minutes)</p>
              <input
                type="number"
                defaultValue={settings['poll_interval_min']?.value ?? '15'}
                min={1}
                max={120}
                onBlur={(e) => saveSetting('poll_interval_min', e.target.value)}
                className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm w-24 focus:outline-none"
              />
            </div>
            <div className="flex-1">
              <p className="text-sm font-medium mb-1">AI Model</p>
              <input
                type="text"
                defaultValue={settings['ai_model']?.value ?? ''}
                onBlur={(e) => saveSetting('ai_model', e.target.value)}
                className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm w-full focus:outline-none"
              />
            </div>
          </div>
        </div>
      </section>

      {/* Style Learner */}
      <section className="bg-white border border-slate-200 rounded-xl p-5">
        <h2 className="font-semibold text-slate-800 mb-1">Writing Style</h2>
        <p className="text-xs text-slate-400 mb-4">Analyzes your sent emails to generate a style profile for AI drafts</p>
        <div className="text-sm text-slate-600 mb-3 space-y-1">
          <p>Status: <span className="font-medium">{styleStatus?.confirmed ? 'Confirmed' : 'Not confirmed'}</span></p>
          <p>Last updated: <span className="font-medium">{fmt(styleStatus?.last_updated)}</span></p>
          <p>Emails analyzed: <span className="font-medium">{styleStatus?.email_count ?? 0}</span></p>
        </div>
        <button
          onClick={refreshStyle}
          disabled={loading === 'style'}
          className="bg-slate-800 text-white text-sm px-4 py-2 rounded-lg hover:bg-slate-700 disabled:opacity-50"
        >
          {loading === 'style' ? 'Analyzing…' : 'Refresh Style'}
        </button>

        {styleDryRun && (
          <div className="mt-4 border border-amber-200 bg-amber-50 rounded-lg p-4">
            <p className="text-sm font-semibold text-amber-800 mb-2">
              Dry-run complete ({styleDryRun.email_count} emails analyzed)
            </p>
            <pre className="text-xs text-slate-700 whitespace-pre-wrap overflow-auto max-h-48 bg-white border border-slate-200 rounded p-3">
              {JSON.stringify(styleDryRun.profile, null, 2)}
            </pre>
            <button
              onClick={confirmStyle}
              disabled={loading === 'confirm_style'}
              className="mt-3 bg-amber-600 text-white text-sm px-4 py-2 rounded-lg hover:bg-amber-700 disabled:opacity-50"
            >
              {loading === 'confirm_style' ? 'Saving…' : 'Confirm & Save Style'}
            </button>
          </div>
        )}
      </section>

      {/* Password */}
      <section className="bg-white border border-slate-200 rounded-xl p-5">
        <h2 className="font-semibold text-slate-800 mb-4">Change Password</h2>
        <div className="space-y-3 max-w-sm">
          {[
            { key: 'current', label: 'Current Password' },
            { key: 'new', label: 'New Password' },
            { key: 'confirm', label: 'Confirm New Password' },
          ].map(({ key, label }) => (
            <div key={key}>
              <label className="text-xs text-slate-500 mb-1 block">{label}</label>
              <input
                type="password"
                value={pw[key as keyof typeof pw]}
                onChange={(e) => setPw((p) => ({ ...p, [key]: e.target.value }))}
                className="w-full border border-slate-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none"
              />
            </div>
          ))}
          <button
            onClick={changePw}
            disabled={loading === 'pw' || !pw.current || !pw.new}
            className="bg-slate-800 text-white text-sm px-4 py-2 rounded-lg hover:bg-slate-700 disabled:opacity-50"
          >
            {loading === 'pw' ? 'Saving…' : 'Change Password'}
          </button>
        </div>
      </section>

      {/* Audit Log */}
      <section className="bg-white border border-slate-200 rounded-xl p-5">
        <h2 className="font-semibold text-slate-800 mb-4">AI Audit Log (last 50 calls)</h2>
        <div className="overflow-auto max-h-64">
          <table className="w-full text-xs">
            <thead className="text-slate-400 uppercase tracking-wider">
              <tr>
                <th className="text-left py-1 pr-4">Time</th>
                <th className="text-left py-1 pr-4">Purpose</th>
                <th className="text-left py-1 pr-4">Model</th>
                <th className="text-left py-1 pr-4">Prompt</th>
                <th className="text-left py-1 pr-4">Response</th>
                <th className="text-left py-1">Redactions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {auditLog.length === 0 ? (
                <tr><td colSpan={6} className="py-4 text-center text-slate-400">No API calls yet</td></tr>
              ) : auditLog.map((row) => (
                <tr key={row.id} className="hover:bg-slate-50">
                  <td className="py-1.5 pr-4 text-slate-400 whitespace-nowrap">{fmt(row.timestamp)}</td>
                  <td className="py-1.5 pr-4 text-slate-600">{row.purpose}</td>
                  <td className="py-1.5 pr-4 text-slate-500">{row.model?.split('-').slice(-1)[0]}</td>
                  <td className="py-1.5 pr-4 text-slate-500">{row.prompt_size} chars</td>
                  <td className="py-1.5 pr-4 text-slate-500">{row.response_size} chars</td>
                  <td className="py-1.5 text-slate-500">{row.redactions_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* ── Trust Panel ───────────────────────────────────────────────────── */}
      <section className="bg-white border border-slate-200 rounded-xl p-5">
        <h2 className="font-semibold text-slate-800 mb-1">🔒 Category Trust</h2>
        <p className="text-sm text-slate-500 mb-4">
          A category becomes trusted after {trust?.threshold ?? 10} consecutive approvals without edits.
          Trusted categories get drafts auto-placed in your IMAP Drafts folder.
          Prices in a draft always block auto-finish.
        </p>
        {(!trust || trust.categories.length === 0) ? (
          <p className="text-sm text-slate-400">No approvals yet — start approving drafts to build trust.</p>
        ) : (
          <div className="space-y-3">
            {trust.categories.map((cat) => {
              const pct = Math.min(100, Math.round((cat.streak / (trust.threshold || 10)) * 100));
              return (
                <div key={cat.category} className="border border-slate-100 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-slate-700 capitalize">{cat.category.replace(/_/g, ' ')}</span>
                      {cat.trusted ? (
                        <span className="text-xs bg-green-100 text-green-700 border border-green-200 px-2 py-0.5 rounded-full font-medium">✅ Trusted</span>
                      ) : (
                        <span className="text-xs bg-slate-100 text-slate-500 px-2 py-0.5 rounded-full">{cat.streak}/{trust.threshold} streak</span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-xs text-slate-400">
                      <span>{cat.total_approved} approved · {cat.total_edited} edited</span>
                      {cat.trusted && (
                        <button
                          onClick={() => handleRevokeTrust(cat.category)}
                          disabled={loading === `trust_${cat.category}`}
                          className="text-red-500 hover:text-red-700 font-medium disabled:opacity-50"
                        >
                          Revoke
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="w-full bg-slate-100 rounded-full h-1.5">
                    <div
                      className={`h-1.5 rounded-full transition-all ${cat.trusted ? 'bg-green-500' : 'bg-blue-400'}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
