'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';

function fmt(dateStr: string) {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  });
}

const CATEGORIES = ['', 'lead_inquiry', 'vendor_inquiry', 'support', 'spam', 'other'];
const ACTIONS = ['', 'draft_reply', 'forward_to_vendor', 'extract_lead_info', 'summarize', 'no_action'];
const DECISIONS = ['', 'approved', 'rejected'];

export default function HistoryPage() {
  const router = useRouter();
  const [data, setData] = useState<{ total: number; items: any[] } | null>(null);
  const [error, setError] = useState('');
  const [filters, setFilters] = useState({ category: '', action: '', decision: '' });

  useEffect(() => {
    if (!isAuthenticated()) { router.push('/login'); return; }
    load();
  }, [filters]);

  async function load() {
    try {
      const result = await api.getHistory(filters as any);
      setData(result);
    } catch (err: any) {
      setError(err.message);
    }
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-6">
      <h1 className="text-xl font-bold text-slate-800 mb-4">History</h1>

      <div className="flex gap-3 mb-4 flex-wrap">
        {[
          { label: 'Category', key: 'category', options: CATEGORIES },
          { label: 'AI Action', key: 'action', options: ACTIONS },
          { label: 'Decision', key: 'decision', options: DECISIONS },
        ].map(({ label, key, options }) => (
          <div key={key}>
            <label className="block text-xs text-slate-500 mb-1">{label}</label>
            <select
              value={filters[key as keyof typeof filters]}
              onChange={(e) => setFilters((f) => ({ ...f, [key]: e.target.value }))}
              className="border border-slate-300 rounded-lg px-2 py-1.5 text-sm focus:outline-none"
            >
              {options.map((o) => (
                <option key={o} value={o}>
                  {o || 'All'}
                </option>
              ))}
            </select>
          </div>
        ))}
      </div>

      {error && <p className="text-red-500 text-sm mb-4">{error}</p>}

      <p className="text-sm text-slate-500 mb-3">{data?.total ?? '…'} records</p>

      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider">
            <tr>
              <th className="px-4 py-3 text-left">Subject</th>
              <th className="px-4 py-3 text-left">From</th>
              <th className="px-4 py-3 text-left">Category</th>
              <th className="px-4 py-3 text-left">Action</th>
              <th className="px-4 py-3 text-left">Decision</th>
              <th className="px-4 py-3 text-left">Date</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {!data ? (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-400">Loading…</td></tr>
            ) : data.items.length === 0 ? (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-400">No records yet</td></tr>
            ) : data.items.map((row) => (
              <tr key={row.id} className="hover:bg-slate-50">
                <td className="px-4 py-3 max-w-xs truncate font-medium">{row.subject}</td>
                <td className="px-4 py-3 text-slate-500 text-xs">{row.from_address}</td>
                <td className="px-4 py-3 text-slate-600">{row.category || '—'}</td>
                <td className="px-4 py-3 text-slate-600">{row.suggested_action || '—'}</td>
                <td className="px-4 py-3">
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                    row.decision === 'approved' ? 'bg-green-100 text-green-700' :
                    row.decision === 'rejected' ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-600'
                  }`}>
                    {row.decision}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-400 text-xs whitespace-nowrap">{fmt(row.decided_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
