'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';

/* ── helpers ── */
function fmtNum(n: number) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + 'M';
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + 'K';
  return n.toLocaleString();
}
function fmtUSD(n: number, decimals = 4) {
  if (!n || n < 0.0001) return '$0.00';
  if (n < 0.01) return '< $0.01';
  return '$' + n.toFixed(decimals);
}
function purposeLabel(p: string) {
  const map: Record<string, string> = {
    email_analysis:     '✉️  Email Analysis',
    price_extraction:   '📄 Price Extraction',
    style_extract_paste:'✍️  Style Learning',
    deal_supplier_email:'🤝 Deal Emails',
    compose:            '📝 Compose',
    redraft:            '🔄 Re-Draft',
  };
  return map[p] ?? p.replace(/_/g, ' ');
}
function trendArrow(cur: number, prev: number) {
  if (prev === 0) return null;
  const pct = ((cur - prev) / prev) * 100;
  const up = pct > 0;
  return (
    <span className={`text-xs font-medium ml-1 ${up ? 'text-red-500' : 'text-green-600'}`}>
      {up ? '▲' : '▼'} {Math.abs(pct).toFixed(0)}% vs last month
    </span>
  );
}

export default function UsagePage() {
  const router = useRouter();
  const [data,        setData]        = useState<any>(null);
  const [error,       setError]       = useState('');
  const [balInput,    setBalInput]    = useState('');
  const [balSaving,   setBalSaving]   = useState(false);
  const [balMsg,      setBalMsg]      = useState('');

  useEffect(() => {
    if (!isAuthenticated()) { router.push('/login'); return; }
    load();
  }, []);

  async function load() {
    try {
      const d = await api.getUsageStats();
      setData(d);
      if (d.summary.manual_balance_usd != null)
        setBalInput(String(d.summary.manual_balance_usd));
    } catch (e: any) { setError(e.message); }
  }

  async function saveBalance() {
    setBalSaving(true);
    try {
      const val = balInput.trim() ? parseFloat(balInput) : null;
      await api.setAnthropicBalance(val);
      setBalMsg('Saved!');
      setTimeout(() => setBalMsg(''), 2000);
      load();
    } catch (e: any) { setBalMsg('Error: ' + e.message); }
    finally { setBalSaving(false); }
  }

  if (error) return <div className="p-8 text-red-600">{error}</div>;
  if (!data)  return <div className="p-8 text-slate-400">Loading…</div>;

  const { summary, by_purpose, daily, monthly, by_model, pricing } = data;

  /* bar chart scaling */
  const maxDailyCost  = Math.max(...daily.map((d: any) => d.est_cost_usd), 0.0001);
  const maxMonthlyCost = Math.max(...monthly.map((m: any) => m.est_cost_usd), 0.0001);

  return (
    <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex items-start justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">📊 AI Usage Dashboard</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Every API call this agent makes — cost, volume, and where the money goes.
          </p>
        </div>
        <a
          href="https://console.anthropic.com/settings/billing"
          target="_blank" rel="noreferrer"
          className="shrink-0 bg-slate-800 hover:bg-slate-700 text-white text-sm font-medium px-4 py-2 rounded-lg"
        >
          Open Anthropic Console →
        </a>
      </div>

      {/* ── Balance card ────────────────────────────────────────────────── */}
      <div className={`rounded-xl border-2 p-5 flex items-center justify-between gap-6 flex-wrap
        ${summary.manual_balance_usd != null ? 'bg-green-50 border-green-300' : 'bg-slate-50 border-dashed border-slate-300'}`}>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1">
            Anthropic Credit Balance
          </p>
          {summary.manual_balance_usd != null ? (
            <p className="text-4xl font-bold text-green-700">
              ${Number(summary.manual_balance_usd).toFixed(2)}
              <span className="text-sm font-normal text-green-600 ml-2">USD remaining</span>
            </p>
          ) : (
            <p className="text-slate-400 text-sm">Not set — Anthropic doesn't expose balance via API.<br/>Enter it manually below after checking your console.</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <input
            type="number"
            step="0.01"
            placeholder="Enter balance e.g. 18.50"
            value={balInput}
            onChange={e => setBalInput(e.target.value)}
            className="border border-slate-300 rounded-lg px-3 py-2 text-sm w-44 focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          <button
            onClick={saveBalance}
            disabled={balSaving}
            className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-3 py-2 rounded-lg disabled:opacity-50"
          >
            {balSaving ? '…' : 'Save'}
          </button>
          {balMsg && <span className="text-xs text-green-600">{balMsg}</span>}
        </div>
      </div>

      {/* ── 4 hero cards ────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <HeroCard
          label="This Month"
          value={fmtUSD(summary.this_month_cost_usd, 3)}
          sub={`${summary.this_month_calls} calls · day ${summary.day_of_month}`}
          footer={trendArrow(summary.this_month_cost_usd, summary.last_month_cost_usd)}
          color="blue"
        />
        <HeroCard
          label="Projected Month-End"
          value={fmtUSD(summary.projected_month_usd, 3)}
          sub="at current daily rate"
          color="amber"
        />
        <HeroCard
          label="Avg Cost / Email"
          value={fmtUSD(summary.avg_cost_per_email, 5)}
          sub={`across ${summary.emails_analyzed} emails`}
          color="purple"
        />
        <HeroCard
          label="All-Time Total"
          value={fmtUSD(summary.total_cost_usd, 3)}
          sub={`${fmtNum(summary.total_calls)} API calls total`}
          color="slate"
        />
      </div>

      {/* ── Where is the money going ─────────────────────────────────────── */}
      <section className="bg-white border border-slate-200 rounded-xl p-5">
        <h2 className="font-semibold text-slate-800 mb-1">💸 Where Is the Money Going?</h2>
        <p className="text-xs text-slate-400 mb-4">Sorted by cost, largest first.</p>
        <div className="space-y-3">
          {by_purpose.map((row: any) => (
            <div key={row.purpose}>
              <div className="flex justify-between text-sm mb-1">
                <span className="font-medium text-slate-700">{purposeLabel(row.purpose)}</span>
                <span className="text-slate-500">
                  {fmtUSD(row.est_cost_usd, 4)} · {row.calls} calls · {row.pct_of_total}%
                </span>
              </div>
              <div className="w-full bg-slate-100 rounded-full h-2">
                <div
                  className="h-2 rounded-full bg-blue-500"
                  style={{ width: `${row.pct_of_total}%` }}
                />
              </div>
            </div>
          ))}
        </div>
        {summary.top_cost_driver && (
          <p className="mt-4 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
            ⚠️ <strong>{purposeLabel(summary.top_cost_driver)}</strong> is your biggest cost driver ({summary.top_driver_pct}% of all spending).
          </p>
        )}
      </section>

      {/* ── Daily chart ─────────────────────────────────────────────────── */}
      <section className="bg-white border border-slate-200 rounded-xl p-5">
        <h2 className="font-semibold text-slate-800 mb-4">📅 Daily Cost — Last 30 Days</h2>
        {daily.length === 0 ? (
          <p className="text-sm text-slate-400">No data yet.</p>
        ) : (
          <>
            <div className="flex items-end gap-1" style={{ height: 120 }}>
              {daily.map((d: any) => {
                const h = Math.max(4, Math.round((d.est_cost_usd / maxDailyCost) * 100));
                const label = d.day.slice(5);
                return (
                  <div key={d.day} className="flex flex-col items-center flex-1 min-w-0 group relative">
                    <span className="hidden group-hover:block absolute bottom-full mb-1 z-10
                      bg-slate-800 text-white text-xs rounded px-2 py-1 whitespace-nowrap">
                      {d.day}<br/>
                      {d.calls} calls<br/>
                      {fmtUSD(d.est_cost_usd, 4)}<br/>
                      Cumulative: {fmtUSD(d.cumulative_usd, 3)}
                    </span>
                    <div
                      className="w-full bg-blue-400 hover:bg-blue-600 rounded-t cursor-default transition-colors"
                      style={{ height: `${h}px` }}
                    />
                    <span className="text-[8px] text-slate-400 mt-1">{label}</span>
                  </div>
                );
              })}
            </div>
            <p className="text-xs text-slate-400 mt-2 text-right">
              Hover each bar for details. Total this period: {fmtUSD(daily.reduce((s: number, d: any) => s + d.est_cost_usd, 0), 4)}
            </p>
          </>
        )}
      </section>

      {/* ── Monthly history ──────────────────────────────────────────────── */}
      <section className="bg-white border border-slate-200 rounded-xl p-5">
        <h2 className="font-semibold text-slate-800 mb-4">🗓️ Monthly History</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-400 border-b border-slate-100">
                <th className="pb-2 pr-4">Month</th>
                <th className="pb-2 pr-4 text-right">Calls</th>
                <th className="pb-2 pr-4 text-right">Est. Input Tokens</th>
                <th className="pb-2 pr-4 text-right">Est. Output Tokens</th>
                <th className="pb-2 text-right">Est. Cost</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {monthly.map((row: any, i: number) => (
                <tr key={row.month} className={`hover:bg-slate-50 ${i === 0 ? 'font-semibold text-slate-800' : 'text-slate-600'}`}>
                  <td className="py-2 pr-4">
                    {row.month} {i === 0 && <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded ml-1">this month</span>}
                  </td>
                  <td className="py-2 pr-4 text-right">{fmtNum(row.calls)}</td>
                  <td className="py-2 pr-4 text-right">{fmtNum(row.est_input_tokens)}</td>
                  <td className="py-2 pr-4 text-right">{fmtNum(row.est_output_tokens)}</td>
                  <td className="py-2 text-right">{fmtUSD(row.est_cost_usd, 4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Monthly bar chart */}
        <div className="flex items-end gap-2 mt-6" style={{ height: 80 }}>
          {[...monthly].reverse().map((row: any) => {
            const h = Math.max(4, Math.round((row.est_cost_usd / maxMonthlyCost) * 64));
            return (
              <div key={row.month} className="flex flex-col items-center flex-1 group relative">
                <span className="hidden group-hover:block absolute bottom-full mb-1 z-10
                  bg-slate-800 text-white text-xs rounded px-2 py-1 whitespace-nowrap">
                  {row.month}: {fmtUSD(row.est_cost_usd, 4)}
                </span>
                <div className="w-full bg-purple-400 hover:bg-purple-600 rounded-t cursor-default" style={{ height: `${h}px` }} />
                <span className="text-[9px] text-slate-400 mt-1">{row.month.slice(5)}</span>
              </div>
            );
          })}
        </div>
      </section>

      {/* ── Pricing info ─────────────────────────────────────────────────── */}
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-xs text-amber-800">
        <strong>⚠️ Estimates only.</strong> {pricing.note}<br/>
        Rates used: <strong>${pricing.input_per_m_usd}/M input tokens</strong> · <strong>${pricing.output_per_m_usd}/M output tokens</strong> ({pricing.model}).
        Models: {by_model.map((m: any) => `${m.model || 'unknown'} (${m.calls} calls)`).join(' · ')}.
      </div>

    </div>
  );
}

function HeroCard({ label, value, sub, footer, color }: {
  label: string; value: string; sub: string; footer?: any; color: string;
}) {
  const styles: Record<string, string> = {
    blue:   'bg-blue-50   border-blue-200   text-blue-800',
    amber:  'bg-amber-50  border-amber-200  text-amber-800',
    purple: 'bg-purple-50 border-purple-200 text-purple-800',
    slate:  'bg-slate-50  border-slate-200  text-slate-800',
  };
  return (
    <div className={`border rounded-xl p-4 ${styles[color]}`}>
      <p className="text-xs font-semibold uppercase tracking-wide opacity-60 mb-1">{label}</p>
      <p className="text-2xl font-bold">{value}</p>
      <p className="text-xs opacity-60 mt-0.5">{sub}</p>
      {footer && <div className="mt-1">{footer}</div>}
    </div>
  );
}
