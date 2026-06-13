'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '../../lib/api';

type BriefItem = { title: string; contact: string; detail: string; email_ids?: number[] };

type Briefing = {
  email_count: number;
  generated_at?: string;
  overview: string;
  attention: BriefItem[];
  vendors:   BriefItem[];
  priorities: string[];
};

export default function BriefingPage() {
  const router = useRouter();
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [loading, setLoading]   = useState(false);
  const [initLoading, setInitLoading] = useState(true);
  const [error, setError]       = useState('');

  // Open the inbox filtered to just the emails behind a briefing point
  function openEmails(item: BriefItem) {
    if (!item.email_ids || item.email_ids.length === 0) return;
    router.push(`/inbox?ids=${item.email_ids.join(',')}`);
  }

  // Load cached briefing on mount
  useEffect(() => {
    api.getCachedBriefing()
      .then(res => { if (res) setBriefing(res); })
      .catch(() => {})
      .finally(() => setInitLoading(false));
  }, []);

  async function generate() {
    setLoading(true);
    setError('');
    try {
      const res = await api.getDailySummary();
      setBriefing(res);
    } catch (e: any) {
      setError('Could not generate briefing: ' + e.message);
    } finally {
      setLoading(false);
    }
  }

  const today = new Date().toLocaleDateString('en-GB', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
  });

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-3xl mx-auto px-6 py-10">

        {/* Header */}
        <div className="flex items-start justify-between mb-8">
          <div>
            <h1 className="text-2xl font-bold text-slate-800">Daily Briefing</h1>
            <p className="text-sm text-slate-400 mt-1">{today}</p>
            {briefing?.generated_at && (
              <p className="text-xs text-slate-400 mt-0.5">
                Generated {new Date(briefing.generated_at).toLocaleString([], {
                  month: 'short', day: 'numeric',
                  hour: '2-digit', minute: '2-digit',
                })}
                {` · ${briefing.email_count} emails analysed`}
              </p>
            )}
          </div>
          <button
            onClick={generate}
            disabled={loading}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-slate-800 text-white text-sm font-medium hover:bg-slate-700 disabled:opacity-50 transition-colors"
          >
            {loading ? (
              <>
                <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
                </svg>
                Generating…
              </>
            ) : (
              <>📋 {briefing ? 'Refresh' : 'Generate Briefing'}</>
            )}
          </button>
        </div>

        {error && (
          <div className="mb-6 px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Empty state */}
        {!briefing && !loading && !initLoading && !error && (
          <div className="text-center py-24 text-slate-400">
            <p className="text-5xl mb-4">📋</p>
            <p className="text-lg font-medium text-slate-600 mb-1">No briefing yet</p>
            <p className="text-sm">Click "Generate Briefing" to get your daily email summary</p>
          </div>
        )}

        {/* Skeleton while loading */}
        {(loading || initLoading) && (
          <div className="space-y-4 animate-pulse">
            <div className="h-28 rounded-xl bg-slate-200" />
            <div className="h-40 rounded-xl bg-slate-200" />
            <div className="h-32 rounded-xl bg-slate-200" />
            <div className="h-36 rounded-xl bg-slate-200" />
          </div>
        )}

        {/* Briefing cards */}
        {briefing && !loading && (
          <div className="space-y-4">

            {/* Overview */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
              <p className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3">Overview</p>
              <p className="text-base text-slate-700 leading-relaxed">{briefing.overview}</p>
            </div>

            {/* Needs Attention */}
            {briefing.attention.length > 0 && (
              <div className="bg-white rounded-xl border border-amber-200 p-5 shadow-sm">
                <div className="flex items-center gap-2 mb-4">
                  <span className="text-lg">🔔</span>
                  <p className="text-xs font-bold text-amber-600 uppercase tracking-widest">Needs Your Attention</p>
                  <span className="ml-auto bg-amber-100 text-amber-700 text-xs font-semibold px-2 py-0.5 rounded-full">
                    {briefing.attention.length}
                  </span>
                </div>
                <div className="space-y-3">
                  {briefing.attention.map((item, i) => {
                    const clickable = (item.email_ids?.length ?? 0) > 0;
                    return (
                      <div
                        key={i}
                        onClick={() => openEmails(item)}
                        className={`flex gap-3 p-3 rounded-lg bg-amber-50 border border-amber-100 ${clickable ? 'cursor-pointer hover:bg-amber-100 hover:border-amber-300 transition-colors' : ''}`}
                      >
                        <div className="mt-0.5 w-2 h-2 rounded-full bg-amber-400 shrink-0" />
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-semibold text-slate-800">{item.title}</p>
                          {item.contact && (
                            <p className="text-xs text-slate-500 mt-0.5">From: {item.contact}</p>
                          )}
                          <p className="text-sm text-slate-600 mt-1 leading-relaxed">{item.detail}</p>
                          {clickable && (
                            <p className="text-xs font-medium text-amber-700 mt-2">
                              → Open {item.email_ids!.length} email{item.email_ids!.length > 1 ? 's' : ''}
                            </p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Vendors / Quotes */}
            {briefing.vendors.length > 0 && (
              <div className="bg-white rounded-xl border border-blue-200 p-5 shadow-sm">
                <div className="flex items-center gap-2 mb-4">
                  <span className="text-lg">📦</span>
                  <p className="text-xs font-bold text-blue-600 uppercase tracking-widest">Vendors & Quotes</p>
                  <span className="ml-auto bg-blue-100 text-blue-700 text-xs font-semibold px-2 py-0.5 rounded-full">
                    {briefing.vendors.length}
                  </span>
                </div>
                <div className="space-y-3">
                  {briefing.vendors.map((item, i) => {
                    const clickable = (item.email_ids?.length ?? 0) > 0;
                    return (
                      <div
                        key={i}
                        onClick={() => openEmails(item)}
                        className={`flex gap-3 p-3 rounded-lg bg-blue-50 border border-blue-100 ${clickable ? 'cursor-pointer hover:bg-blue-100 hover:border-blue-300 transition-colors' : ''}`}
                      >
                        <div className="mt-0.5 w-2 h-2 rounded-full bg-blue-400 shrink-0" />
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-semibold text-slate-800">{item.title}</p>
                          {item.contact && (
                            <p className="text-xs text-slate-500 mt-0.5">{item.contact}</p>
                          )}
                          <p className="text-sm text-slate-600 mt-1 leading-relaxed">{item.detail}</p>
                          {clickable && (
                            <p className="text-xs font-medium text-blue-700 mt-2">
                              → Open {item.email_ids!.length} email{item.email_ids!.length > 1 ? 's' : ''}
                            </p>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Today's Priorities */}
            {briefing.priorities.length > 0 && (
              <div className="bg-white rounded-xl border border-green-200 p-5 shadow-sm">
                <div className="flex items-center gap-2 mb-4">
                  <span className="text-lg">✅</span>
                  <p className="text-xs font-bold text-green-600 uppercase tracking-widest">Today's Priorities</p>
                </div>
                <ol className="space-y-2">
                  {briefing.priorities.map((p, i) => (
                    <li key={i} className="flex gap-3 items-start">
                      <span className="shrink-0 w-6 h-6 rounded-full bg-green-100 text-green-700 text-xs font-bold flex items-center justify-center mt-0.5">
                        {i + 1}
                      </span>
                      <p className="text-sm text-slate-700 leading-relaxed">{p}</p>
                    </li>
                  ))}
                </ol>
              </div>
            )}

            {/* No attention items */}
            {briefing.attention.length === 0 && briefing.vendors.length === 0 && (
              <div className="bg-green-50 rounded-xl border border-green-200 p-5 text-center">
                <p className="text-2xl mb-1">🎉</p>
                <p className="text-sm font-medium text-green-700">All caught up — nothing urgent in the last 48 hours.</p>
              </div>
            )}

          </div>
        )}

      </div>
    </div>
  );
}
