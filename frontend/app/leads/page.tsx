'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';

const STATUSES = ['new', 'contacted', 'qualified', 'lost', 'converted'];

const STATUS_COLORS: Record<string, string> = {
  new: 'bg-blue-100 text-blue-700',
  contacted: 'bg-yellow-100 text-yellow-700',
  qualified: 'bg-green-100 text-green-700',
  lost: 'bg-red-100 text-red-600',
  converted: 'bg-purple-100 text-purple-700',
};

function fmt(dateStr: string) {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

export default function LeadsPage() {
  const router = useRouter();
  const [leads, setLeads] = useState<any[]>([]);
  const [filter, setFilter] = useState('');
  const [error, setError] = useState('');
  const [updating, setUpdating] = useState<number | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) { router.push('/login'); return; }
    load();
  }, [filter]);

  async function load() {
    try {
      const data = await api.getLeads(filter || undefined);
      setLeads(data);
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function updateStatus(leadId: number, status: string) {
    setUpdating(leadId);
    try {
      await api.updateLeadStatus(leadId, status);
      setLeads((prev) => prev.map((l) => l.id === leadId ? { ...l, status } : l));
    } catch (err: any) {
      setError(err.message);
    } finally {
      setUpdating(null);
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold text-slate-800">Leads</h1>
        <div className="flex items-center gap-2">
          <label className="text-sm text-slate-500">Filter:</label>
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="border border-slate-300 rounded-lg px-2 py-1.5 text-sm focus:outline-none"
          >
            <option value="">All</option>
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>

      {error && <p className="text-red-500 text-sm mb-4">{error}</p>}

      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider">
            <tr>
              <th className="px-4 py-3 text-left">From</th>
              <th className="px-4 py-3 text-left">Subject</th>
              <th className="px-4 py-3 text-left">Status</th>
              <th className="px-4 py-3 text-left">Date</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {leads.length === 0 ? (
              <tr><td colSpan={4} className="px-4 py-8 text-center text-slate-400">No leads yet</td></tr>
            ) : leads.map((lead) => (
              <tr key={lead.id} className="hover:bg-slate-50">
                <td className="px-4 py-3">
                  <p className="font-medium">{lead.from_name || lead.from_email}</p>
                  <p className="text-slate-400 text-xs">{lead.from_email}</p>
                </td>
                <td className="px-4 py-3 text-slate-600 max-w-xs truncate">{lead.subject}</td>
                <td className="px-4 py-3">
                  <select
                    value={lead.status}
                    disabled={updating === lead.id}
                    onChange={(e) => updateStatus(lead.id, e.target.value)}
                    className={`text-xs font-medium px-2 py-1 rounded-full border-0 cursor-pointer focus:outline-none focus:ring-1 focus:ring-slate-400 ${
                      STATUS_COLORS[lead.status] ?? 'bg-gray-100 text-gray-600'
                    }`}
                  >
                    {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </td>
                <td className="px-4 py-3 text-slate-400 text-xs">{fmt(lead.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
