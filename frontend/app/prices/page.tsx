'use client';
import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';

const CATEGORY_COLORS: Record<string, string> = {
  Cisco:        'bg-blue-100 text-blue-700',
  Fortinet:     'bg-amber-100 text-amber-700',
  HP:           'bg-green-100 text-green-700',
  Microsoft:    'bg-purple-100 text-purple-700',
  Lenovo:       'bg-orange-100 text-orange-700',
  Dell:         'bg-pink-100 text-pink-700',
  Aruba:        'bg-teal-100 text-teal-700',
  'Palo Alto':  'bg-red-100 text-red-700',
  Other:        'bg-slate-100 text-slate-600',
};

function fmtPrice(price: number | null, currency: string) {
  if (price == null) return '—';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: currency || 'USD' }).format(price);
}

export default function PricesPage() {
  const router = useRouter();
  const [data, setData] = useState<{ items: any[]; categories: string[]; total: number } | null>(null);
  const [filters, setFilters] = useState({ category: '', vendor: '', search: '' });
  const [error, setError] = useState('');
  const [exporting, setExporting] = useState(false);

  // Extraction job state
  const [jobStatus, setJobStatus] = useState<any>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) { router.push('/login'); return; }
    load();
    // Check if a job is already running
    checkStatus();
  }, []);

  useEffect(() => { load(); }, [filters]);

  async function load() {
    try {
      const result = await api.getPrices({
        category: filters.category || undefined,
        vendor: filters.vendor || undefined,
        search: filters.search || undefined,
      });
      setData(result);
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function checkStatus() {
    try {
      const status = await api.getExtractStatus();
      setJobStatus(status);
      if (status.running) {
        startPolling();
      }
    } catch {}
  }

  function startPolling() {
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      try {
        const status = await api.getExtractStatus();
        setJobStatus(status);
        if (!status.running) {
          stopPolling();
          load(); // refresh the price list
        }
      } catch {}
    }, 3000);
  }

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  useEffect(() => () => stopPolling(), []);

  async function runExtract() {
    setError('');
    try {
      await api.extractPrices();
      // Start polling immediately
      const status = await api.getExtractStatus();
      setJobStatus(status);
      startPolling();
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function doExport() {
    setExporting(true);
    try {
      await api.exportPrices({
        category: filters.category || undefined,
        vendor: filters.vendor || undefined,
        search: filters.search || undefined,
      });
    } catch (err: any) {
      setError(err.message);
    } finally {
      setExporting(false);
    }
  }

  const isRunning = jobStatus?.running === true;
  const categories = data?.categories ?? [];

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Price List</h1>
          <p className="text-xs text-slate-400 mt-0.5">Prices extracted from received vendor emails</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={runExtract}
            disabled={isRunning}
            className="bg-slate-700 text-white text-sm px-4 py-2 rounded-lg hover:bg-slate-600 disabled:opacity-60"
          >
            {isRunning ? 'Scanning…' : 'Scan Emails for Prices'}
          </button>
          <button
            onClick={doExport}
            disabled={exporting || !data?.items.length}
            className="bg-green-600 text-white text-sm px-4 py-2 rounded-lg hover:bg-green-700 disabled:opacity-50"
          >
            {exporting ? 'Exporting…' : '↓ Export Excel'}
          </button>
        </div>
      </div>

      {/* Live progress bar */}
      {isRunning && jobStatus && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 mb-4">
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-medium text-blue-800">
              Scanning emails… {jobStatus.processed} processed, {jobStatus.total_quotes} quotes found
            </span>
            <span className="text-xs text-blue-600">
              {jobStatus.errors > 0 && `${jobStatus.errors} errors`}
            </span>
          </div>
          {jobStatus.folders_scanned?.length > 0 && (
            <p className="text-xs text-blue-600">
              Folders: {jobStatus.folders_scanned.join(', ')}
            </p>
          )}
          <div className="mt-2 h-1.5 bg-blue-200 rounded-full overflow-hidden">
            <div className="h-full bg-blue-500 rounded-full animate-pulse w-full" />
          </div>
        </div>
      )}

      {/* Done banner */}
      {jobStatus?.done && !isRunning && jobStatus.total_quotes > 0 && (
        <div className="bg-green-50 border border-green-200 text-green-800 text-sm px-4 py-3 rounded-lg mb-4">
          Scan complete — {jobStatus.processed} emails processed, <strong>{jobStatus.total_quotes} price quotes</strong> found
          {jobStatus.skipped > 0 && `, ${jobStatus.skipped} already done`}
          {jobStatus.errors > 0 && `, ${jobStatus.errors} errors`}.
          {jobStatus.folders_scanned?.length > 0 && (
            <span className="block text-xs text-green-700 mt-0.5">
              Folders scanned: {jobStatus.folders_scanned.join(', ')}
            </span>
          )}
        </div>
      )}

      {jobStatus?.done && !isRunning && jobStatus.error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded-lg mb-4">
          Scan error: {jobStatus.error}
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm px-4 py-3 rounded-lg mb-4">
          {error}
          <button className="ml-2 text-red-400 hover:text-red-600" onClick={() => setError('')}>✕</button>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        <div>
          <label className="block text-xs text-slate-500 mb-1">Category</label>
          <select
            value={filters.category}
            onChange={(e) => setFilters((f) => ({ ...f, category: e.target.value }))}
            className="border border-slate-300 rounded-lg px-2 py-1.5 text-sm focus:outline-none"
          >
            <option value="">All</option>
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Vendor</label>
          <input
            type="text"
            placeholder="Filter by vendor…"
            value={filters.vendor}
            onChange={(e) => setFilters((f) => ({ ...f, vendor: e.target.value }))}
            className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none w-44"
          />
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Search</label>
          <input
            type="text"
            placeholder="Product or part no…"
            value={filters.search}
            onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
            className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none w-52"
          />
        </div>
        {(filters.category || filters.vendor || filters.search) && (
          <div className="flex items-end">
            <button
              onClick={() => setFilters({ category: '', vendor: '', search: '' })}
              className="text-xs text-slate-500 hover:text-slate-800 border border-slate-300 rounded-lg px-3 py-1.5"
            >
              Clear filters
            </button>
          </div>
        )}
      </div>

      <p className="text-sm text-slate-500 mb-3">{data == null ? '…' : `${data.total} items`}</p>

      {/* Category chips */}
      {data && categories.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-4">
          {categories.map((cat) => {
            const count = data.items.filter((i) => i.category === cat).length;
            return (
              <button
                key={cat}
                onClick={() => setFilters((f) => ({ ...f, category: f.category === cat ? '' : cat }))}
                className={`text-xs font-medium px-3 py-1 rounded-full border transition-all ${
                  filters.category === cat
                    ? 'border-slate-700 ' + (CATEGORY_COLORS[cat] ?? 'bg-slate-100 text-slate-600')
                    : 'border-transparent ' + (CATEGORY_COLORS[cat] ?? 'bg-slate-100 text-slate-600')
                }`}
              >
                {cat} ({count})
              </button>
            );
          })}
        </div>
      )}

      {/* Table */}
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider">
              <tr>
                <th className="px-4 py-3 text-left">Category</th>
                <th className="px-4 py-3 text-left">Product</th>
                <th className="px-4 py-3 text-left">Part No.</th>
                <th className="px-4 py-3 text-right">Unit Price</th>
                <th className="px-4 py-3 text-left">Vendor</th>
                <th className="px-4 py-3 text-left">Source Email</th>
                <th className="px-4 py-3 text-left">Validity</th>
                <th className="px-4 py-3 text-left">Notes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data == null ? (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-slate-400">Loading…</td></tr>
              ) : data.items.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center">
                    <p className="text-slate-400 mb-2">No price quotes found yet</p>
                    <p className="text-xs text-slate-400">
                      Click <strong>Scan Emails for Prices</strong> to extract pricing from all your inbox folders.
                    </p>
                  </td>
                </tr>
              ) : data.items.map((item) => (
                <tr key={item.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${CATEGORY_COLORS[item.category] ?? 'bg-slate-100 text-slate-600'}`}>
                      {item.category || 'Other'}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-medium max-w-xs">
                    <span className="block truncate" title={item.product_name}>{item.product_name}</span>
                  </td>
                  <td className="px-4 py-3 text-slate-500 font-mono text-xs">{item.part_number || '—'}</td>
                  <td className="px-4 py-3 text-right font-semibold text-slate-800 whitespace-nowrap">
                    {fmtPrice(item.unit_price, item.currency)}
                  </td>
                  <td className="px-4 py-3">
                    <p className="text-slate-700 text-xs font-medium">{item.vendor_name || '—'}</p>
                    {item.vendor_email && <p className="text-slate-400 text-xs">{item.vendor_email}</p>}
                  </td>
                  <td className="px-4 py-3 text-slate-500 text-xs max-w-[180px]">
                    <span className="block truncate" title={item.effective_subject || item.email_subject}>
                      {item.effective_subject || item.email_subject || '—'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs whitespace-nowrap">{item.validity_date || '—'}</td>
                  <td className="px-4 py-3 text-slate-500 text-xs max-w-[200px]">
                    <span className="block truncate" title={item.notes}>{item.notes || '—'}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
