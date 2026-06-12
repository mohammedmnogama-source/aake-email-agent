'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';

// Colour for each deal status
const STATUS_COLORS: Record<string, string> = {
  inquiry:     'bg-blue-100 text-blue-800',
  sourcing:    'bg-yellow-100 text-yellow-800',
  quoted:      'bg-purple-100 text-purple-800',
  negotiating: 'bg-orange-100 text-orange-800',
  won:         'bg-green-100 text-green-800',
  fulfilled:   'bg-teal-100 text-teal-800',
  closed:      'bg-gray-100 text-gray-700',
  lost:        'bg-red-100 text-red-800',
  cancelled:   'bg-gray-100 text-gray-500',
};

export default function DealsPage() {
  const [deals, setDeals] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    api.listDeals()
      .then(setDeals)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-8 text-slate-500">Loading deals...</div>;
  if (error)   return <div className="p-8 text-red-600">{error}</div>;

  return (
    <div className="max-w-6xl mx-auto p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-slate-800">Deals</h1>
        <Link
          href="/deals/new"
          className="bg-slate-800 text-white px-4 py-2 rounded text-sm hover:bg-slate-700 transition-colors"
        >
          + New Deal
        </Link>
      </div>

      {deals.length === 0 ? (
        <div className="text-center py-20 text-slate-400">
          No deals yet.{' '}
          <Link href="/deals/new" className="text-slate-600 underline">Create your first deal</Link>
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="text-left px-4 py-3 text-slate-600 font-medium">Ref</th>
                <th className="text-left px-4 py-3 text-slate-600 font-medium">Customer</th>
                <th className="text-left px-4 py-3 text-slate-600 font-medium">Description</th>
                <th className="text-left px-4 py-3 text-slate-600 font-medium">Status</th>
                <th className="text-center px-4 py-3 text-slate-600 font-medium">Requests</th>
                <th className="text-center px-4 py-3 text-slate-600 font-medium">Quotes</th>
                <th className="text-left px-4 py-3 text-slate-600 font-medium">Updated</th>
              </tr>
            </thead>
            <tbody>
              {deals.map((deal, i) => (
                <tr
                  key={deal.id}
                  className={`border-b border-slate-100 hover:bg-slate-50 cursor-pointer ${i % 2 === 0 ? '' : 'bg-slate-50/30'}`}
                >
                  <td className="px-4 py-3">
                    <Link href={`/deals/${deal.id}`} className="font-mono text-slate-700 hover:text-slate-900">
                      {deal.ref_number}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <Link href={`/deals/${deal.id}`} className="block">
                      <div className="font-medium text-slate-800">{deal.customer_name}</div>
                      {deal.customer_email && (
                        <div className="text-slate-400 text-xs">{deal.customer_email}</div>
                      )}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-slate-600 max-w-xs truncate">
                    {deal.description || '—'}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium capitalize ${STATUS_COLORS[deal.status] ?? 'bg-gray-100 text-gray-600'}`}>
                      {deal.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center text-slate-600">
                    {deal.supplier_request_count ?? 0}
                  </td>
                  <td className="px-4 py-3 text-center text-slate-600">
                    {deal.supplier_quote_count ?? 0}
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs">
                    {deal.updated_at ? new Date(deal.updated_at).toLocaleDateString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
