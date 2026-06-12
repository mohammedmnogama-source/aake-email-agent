'use client';
import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { api } from '@/lib/api';

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

// Simple collapsible section wrapper
function Section({ title, children, defaultOpen = true }: { title: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border border-slate-200 rounded-lg overflow-hidden mb-4">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 bg-slate-50 hover:bg-slate-100 transition-colors text-left"
      >
        <span className="font-medium text-slate-700 text-sm">{title}</span>
        <span className="text-slate-400 text-xs">{open ? '▲' : '▼'}</span>
      </button>
      {open && <div className="p-4">{children}</div>}
    </div>
  );
}

export default function DealDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const dealId = parseInt(id);

  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // AI next-step banner
  const [nextStep, setNextStep] = useState<string | null>(null);
  const [loadingNextStep, setLoadingNextStep] = useState(false);

  // Supplier email draft modal
  const [emailDraft, setEmailDraft] = useState<string | null>(null);

  // Modal states
  const [showAddItem, setShowAddItem] = useState(false);
  const [showAddSupplierReq, setShowAddSupplierReq] = useState(false);
  const [showAddSupplierQuote, setShowAddSupplierQuote] = useState(false);
  const [showAddCustomerQuote, setShowAddCustomerQuote] = useState(false);
  const [showAddCustomerPO, setShowAddCustomerPO] = useState(false);
  const [showAddSupplierPO, setShowAddSupplierPO] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const d = await api.getDeal(dealId);
      setData(d);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [dealId]);

  async function refreshNextStep() {
    setLoadingNextStep(true);
    try {
      const res = await api.getDealNextStep(dealId);
      setNextStep(res.next_step);
    } finally {
      setLoadingNextStep(false);
    }
  }

  async function changeStatus(status: string) {
    await api.updateDeal(dealId, { status });
    load();
  }

  async function deleteDeal() {
    if (!confirm('Delete this deal and all related records? This cannot be undone.')) return;
    await api.deleteDeal(dealId);
    router.push('/deals');
  }

  if (loading) return <div className="p-8 text-slate-500">Loading...</div>;
  if (error)   return <div className="p-8 text-red-600">{error}</div>;
  if (!data)   return null;

  const { deal, items, supplier_requests, supplier_quotes, customer_quotes, customer_pos, supplier_pos } = data;

  return (
    <div className="max-w-4xl mx-auto p-6">

      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <span className="font-mono text-lg font-bold text-slate-800">{deal.ref_number}</span>
            <span className={`px-2 py-0.5 rounded-full text-xs font-medium capitalize ${STATUS_COLORS[deal.status] ?? 'bg-gray-100 text-gray-600'}`}>
              {deal.status}
            </span>
          </div>
          <div className="text-xl font-semibold text-slate-700">{deal.customer_name}</div>
          {deal.customer_email && <div className="text-sm text-slate-400">{deal.customer_email}</div>}
        </div>
        <div className="flex gap-2">
          <select
            value={deal.status}
            onChange={e => changeStatus(e.target.value)}
            className="text-sm border border-slate-200 rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-slate-400"
          >
            {['inquiry','sourcing','quoted','negotiating','won','fulfilled','closed','lost','cancelled'].map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <button
            onClick={deleteDeal}
            className="text-sm text-red-500 hover:text-red-700 border border-red-200 hover:border-red-400 rounded px-3 py-1.5 transition-colors"
          >
            Delete
          </button>
        </div>
      </div>

      {/* AI Next Step banner */}
      {(nextStep || deal.ai_next_step) && (
        <div className="flex items-start gap-3 bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 mb-4">
          <span className="text-blue-500 text-lg leading-none mt-0.5">→</span>
          <p className="text-sm text-blue-800 flex-1">{nextStep ?? deal.ai_next_step}</p>
          <button
            onClick={refreshNextStep}
            disabled={loadingNextStep}
            className="text-xs text-blue-400 hover:text-blue-600 underline whitespace-nowrap disabled:opacity-50"
          >
            {loadingNextStep ? 'Thinking…' : 'Refresh'}
          </button>
        </div>
      )}
      {!nextStep && !deal.ai_next_step && (
        <div className="mb-4">
          <button
            onClick={refreshNextStep}
            disabled={loadingNextStep}
            className="text-xs text-blue-500 hover:text-blue-700 border border-blue-200 rounded px-3 py-1.5 transition-colors disabled:opacity-50"
          >
            {loadingNextStep ? 'Getting suggestion…' : 'Get AI next-step suggestion'}
          </button>
        </div>
      )}

      {/* Email draft modal */}
      {emailDraft && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full p-6">
            <div className="flex items-center justify-between mb-3">
              <span className="font-semibold text-slate-700">AI-generated supplier email</span>
              <button onClick={() => setEmailDraft(null)} className="text-slate-400 hover:text-slate-600 text-xl leading-none">×</button>
            </div>
            <p className="text-xs text-slate-400 mb-2">Copy this email and send it from your own email client.</p>
            <textarea
              readOnly
              value={emailDraft}
              rows={12}
              className="w-full border border-slate-200 rounded px-3 py-2 text-sm font-mono focus:outline-none resize-none"
            />
            <div className="flex gap-3 mt-3">
              <button
                onClick={() => { navigator.clipboard.writeText(emailDraft); }}
                className="bg-slate-800 text-white px-4 py-2 rounded text-sm hover:bg-slate-700 transition-colors"
              >
                Copy to clipboard
              </button>
              <button onClick={() => setEmailDraft(null)} className="text-slate-500 hover:text-slate-700 px-4 py-2 text-sm">
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Description */}
      {deal.description && (
        <div className="bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 mb-4 text-sm text-slate-600">
          {deal.description}
        </div>
      )}

      {/* Line items */}
      <Section title={`Inquiry Details — ${items.length} item(s)`}>
        {items.length > 0 ? (
          <table className="w-full text-sm mb-3">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-100">
                <th className="pb-2 font-medium">Product</th>
                <th className="pb-2 font-medium w-16">Qty</th>
                <th className="pb-2 font-medium">Specs</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item: any) => (
                <tr key={item.id} className="border-b border-slate-50">
                  <td className="py-2 text-slate-800">{item.product_name}</td>
                  <td className="py-2 text-slate-600">{item.qty ?? '—'}</td>
                  <td className="py-2 text-slate-500">{item.specs ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-slate-400 text-sm mb-3">No line items yet.</p>
        )}
        <button
          onClick={() => setShowAddItem(true)}
          className="text-xs border border-slate-200 rounded px-3 py-1.5 hover:bg-slate-50 transition-colors"
        >
          + Add item
        </button>

        {showAddItem && (
          <AddItemForm
            dealId={dealId}
            onSaved={() => { setShowAddItem(false); load(); }}
            onCancel={() => setShowAddItem(false)}
          />
        )}
      </Section>

      {/* Supplier requests */}
      <Section title={`Supplier Requests — ${supplier_requests.length}`} defaultOpen={true}>
        {supplier_requests.length > 0 && (
          <table className="w-full text-sm mb-3">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-100">
                <th className="pb-2 font-medium">Ref</th>
                <th className="pb-2 font-medium">Supplier</th>
                <th className="pb-2 font-medium">Email</th>
                <th className="pb-2 font-medium">Status</th>
                <th className="pb-2 font-medium">Sent</th>
              </tr>
            </thead>
            <tbody>
              {supplier_requests.map((sr: any) => (
                <tr key={sr.id} className="border-b border-slate-50">
                  <td className="py-2 font-mono text-xs text-slate-500">{sr.ref_number}</td>
                  <td className="py-2 text-slate-800 font-medium">{sr.vendor_name}</td>
                  <td className="py-2 text-slate-500 text-xs">{sr.vendor_email ?? '—'}</td>
                  <td className="py-2">
                    <span className={`text-xs px-1.5 py-0.5 rounded capitalize ${
                      sr.status === 'sent' ? 'bg-green-100 text-green-700' :
                      sr.status === 'replied' ? 'bg-blue-100 text-blue-700' :
                      sr.status === 'no_response' ? 'bg-red-100 text-red-700' :
                      'bg-gray-100 text-gray-600'
                    }`}>
                      {sr.status}
                    </span>
                    {sr.email_draft_text && (
                      <button
                        onClick={() => setEmailDraft(sr.email_draft_text)}
                        className="ml-2 text-xs text-blue-500 underline hover:text-blue-700"
                      >
                        View email
                      </button>
                    )}
                    {sr.status === 'draft' && (
                      <button
                        onClick={async () => {
                          await api.updateSupplierRequest(dealId, sr.id, { status: 'sent', sent_at: new Date().toISOString() });
                          load();
                        }}
                        className="ml-2 text-xs text-slate-500 underline hover:text-slate-700"
                      >
                        Mark sent
                      </button>
                    )}
                  </td>
                  <td className="py-2 text-slate-400 text-xs">{sr.sent_at ? new Date(sr.sent_at).toLocaleDateString() : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <button
          onClick={() => setShowAddSupplierReq(true)}
          className="text-xs border border-slate-200 rounded px-3 py-1.5 hover:bg-slate-50 transition-colors"
        >
          + Add supplier request
        </button>

        {showAddSupplierReq && (
          <AddSupplierRequestForm
            dealId={dealId}
            onSaved={() => { setShowAddSupplierReq(false); load(); }}
            onCancel={() => setShowAddSupplierReq(false)}
            onEmailDraft={(text) => { setShowAddSupplierReq(false); load(); setEmailDraft(text); }}
          />
        )}
      </Section>

      {/* Supplier quotes */}
      <Section title={`Supplier Quotes — ${supplier_quotes.length}`} defaultOpen={true}>
        {supplier_quotes.length > 0 && (
          <table className="w-full text-sm mb-3">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-100">
                <th className="pb-2 font-medium">Ref</th>
                <th className="pb-2 font-medium">Supplier</th>
                <th className="pb-2 font-medium">Amount</th>
                <th className="pb-2 font-medium">Valid Until</th>
                <th className="pb-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {supplier_quotes.map((sq: any) => (
                <tr key={sq.id} className="border-b border-slate-50">
                  <td className="py-2 font-mono text-xs text-slate-500">{sq.ref_number}</td>
                  <td className="py-2 text-slate-800">{sq.vendor_name ?? '—'}</td>
                  <td className="py-2 text-slate-700 font-medium">
                    {sq.total_amount != null ? `${sq.total_amount.toLocaleString()} ${sq.currency}` : '—'}
                  </td>
                  <td className="py-2 text-slate-400 text-xs">{sq.valid_until ?? '—'}</td>
                  <td className="py-2">
                    <span className={`text-xs px-1.5 py-0.5 rounded capitalize ${
                      sq.status === 'selected' ? 'bg-green-100 text-green-700' :
                      sq.status === 'rejected' ? 'bg-red-100 text-red-700' :
                      'bg-blue-100 text-blue-700'
                    }`}>
                      {sq.status}
                    </span>
                    {sq.status === 'received' && (
                      <button
                        onClick={async () => { await api.updateSupplierQuote(dealId, sq.id, { status: 'selected' }); load(); }}
                        className="ml-2 text-xs text-slate-500 underline hover:text-slate-700"
                      >
                        Select
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <button
          onClick={() => setShowAddSupplierQuote(true)}
          className="text-xs border border-slate-200 rounded px-3 py-1.5 hover:bg-slate-50 transition-colors"
        >
          + Record quote
        </button>

        {showAddSupplierQuote && (
          <AddSupplierQuoteForm
            dealId={dealId}
            supplierRequests={supplier_requests}
            onSaved={() => { setShowAddSupplierQuote(false); load(); }}
            onCancel={() => setShowAddSupplierQuote(false)}
          />
        )}
      </Section>

      {/* Customer quotation */}
      <Section title={`Customer Quotation — ${customer_quotes.length}`} defaultOpen={true}>
        {customer_quotes.length > 0 && (
          <div className="space-y-3 mb-3">
            {customer_quotes.map((cq: any) => (
              <div key={cq.id} className="border border-slate-100 rounded p-3">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-xs text-slate-500">{cq.ref_number}</span>
                  <span className={`text-xs px-1.5 py-0.5 rounded capitalize ${
                    cq.status === 'accepted' ? 'bg-green-100 text-green-700' :
                    cq.status === 'sent' ? 'bg-blue-100 text-blue-700' :
                    cq.status === 'rejected' ? 'bg-red-100 text-red-700' :
                    'bg-gray-100 text-gray-600'
                  }`}>
                    {cq.status}
                  </span>
                </div>
                <div className="text-lg font-bold text-slate-800">
                  {cq.total_amount != null ? `${cq.total_amount.toLocaleString()} ${cq.currency}` : 'Amount TBD'}
                </div>
                {cq.valid_until && <div className="text-xs text-slate-400">Valid until: {cq.valid_until}</div>}
                {cq.notes && <div className="text-sm text-slate-600 mt-1">{cq.notes}</div>}
                {cq.status === 'draft' && (
                  <button
                    onClick={async () => { await api.updateCustomerQuote(dealId, cq.id, { status: 'sent', sent_at: new Date().toISOString() }); load(); }}
                    className="mt-2 text-xs text-slate-500 underline hover:text-slate-700"
                  >
                    Mark as sent
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
        <button
          onClick={() => setShowAddCustomerQuote(true)}
          className="text-xs border border-slate-200 rounded px-3 py-1.5 hover:bg-slate-50 transition-colors"
        >
          + Create customer quote
        </button>

        {showAddCustomerQuote && (
          <AddCustomerQuoteForm
            dealId={dealId}
            onSaved={() => { setShowAddCustomerQuote(false); load(); }}
            onCancel={() => setShowAddCustomerQuote(false)}
          />
        )}
      </Section>

      {/* Purchase orders */}
      <Section title="Purchase Orders" defaultOpen={false}>
        <div className="grid grid-cols-2 gap-4">
          {/* Customer PO */}
          <div>
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">From Customer</h3>
            {customer_pos.length > 0 ? (
              customer_pos.map((po: any) => (
                <div key={po.id} className="border border-green-100 rounded p-3 bg-green-50 mb-2">
                  <div className="font-mono text-xs text-slate-500">{po.ref_number}</div>
                  <div className="font-bold text-slate-800">{po.customer_po_number ?? 'PO received'}</div>
                  {po.amount && <div className="text-sm text-slate-600">{po.amount.toLocaleString()} {po.currency}</div>}
                  {po.notes && <div className="text-xs text-slate-400 mt-1">{po.notes}</div>}
                </div>
              ))
            ) : (
              <p className="text-slate-400 text-xs mb-2">No PO yet.</p>
            )}
            <button
              onClick={() => setShowAddCustomerPO(true)}
              className="text-xs border border-slate-200 rounded px-3 py-1.5 hover:bg-slate-50 transition-colors"
            >
              + Record customer PO
            </button>
            {showAddCustomerPO && (
              <AddCustomerPOForm
                dealId={dealId}
                customerQuotes={customer_quotes}
                onSaved={() => { setShowAddCustomerPO(false); load(); }}
                onCancel={() => setShowAddCustomerPO(false)}
              />
            )}
          </div>

          {/* Supplier PO */}
          <div>
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">To Supplier</h3>
            {supplier_pos.length > 0 ? (
              supplier_pos.map((po: any) => (
                <div key={po.id} className="border border-blue-100 rounded p-3 bg-blue-50 mb-2">
                  <div className="font-mono text-xs text-slate-500">{po.ref_number}</div>
                  <div className="font-bold text-slate-800">{po.vendor_name ?? 'Supplier'}</div>
                  {po.aake_po_number && <div className="text-sm text-slate-600">PO# {po.aake_po_number}</div>}
                  {po.amount && <div className="text-sm text-slate-600">{po.amount.toLocaleString()} {po.currency}</div>}
                </div>
              ))
            ) : (
              <p className="text-slate-400 text-xs mb-2">No supplier PO issued yet.</p>
            )}
            <button
              onClick={() => setShowAddSupplierPO(true)}
              className="text-xs border border-slate-200 rounded px-3 py-1.5 hover:bg-slate-50 transition-colors"
            >
              + Issue supplier PO
            </button>
            {showAddSupplierPO && (
              <AddSupplierPOForm
                dealId={dealId}
                supplierRequests={supplier_requests}
                supplierQuotes={supplier_quotes}
                onSaved={() => { setShowAddSupplierPO(false); load(); }}
                onCancel={() => setShowAddSupplierPO(false)}
              />
            )}
          </div>
        </div>
      </Section>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Mini forms (inline modals)
// ---------------------------------------------------------------------------

function FormWrapper({ title, onCancel, children }: { title: string; onCancel: () => void; children: React.ReactNode }) {
  return (
    <div className="mt-3 border border-slate-200 rounded-lg p-4 bg-white shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-semibold text-slate-700">{title}</span>
        <button onClick={onCancel} className="text-slate-400 hover:text-slate-600 text-lg leading-none">×</button>
      </div>
      {children}
    </div>
  );
}

function AddItemForm({ dealId, onSaved, onCancel }: { dealId: number; onSaved: () => void; onCancel: () => void }) {
  const [name, setName] = useState('');
  const [qty, setQty] = useState('');
  const [specs, setSpecs] = useState('');
  const [saving, setSaving] = useState(false);

  return (
    <FormWrapper title="Add Line Item" onCancel={onCancel}>
      <div className="flex gap-2 mb-3">
        <input value={name} onChange={e => setName(e.target.value)} placeholder="Product name" className="flex-1 border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none" />
        <input value={qty} onChange={e => setQty(e.target.value)} placeholder="Qty" className="w-16 border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none" />
        <input value={specs} onChange={e => setSpecs(e.target.value)} placeholder="Specs" className="flex-1 border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none" />
      </div>
      <button
        onClick={async () => {
          if (!name.trim()) return;
          setSaving(true);
          await api.addDealItem(dealId, { product_name: name.trim(), qty: qty ? parseInt(qty) : undefined, specs: specs || undefined });
          onSaved();
        }}
        disabled={saving || !name.trim()}
        className="bg-slate-800 text-white px-4 py-1.5 rounded text-sm disabled:opacity-50"
      >
        {saving ? 'Saving...' : 'Add'}
      </button>
    </FormWrapper>
  );
}

function AddSupplierRequestForm({ dealId, onSaved, onCancel, onEmailDraft }: { dealId: number; onSaved: () => void; onCancel: () => void; onEmailDraft: (text: string) => void }) {
  const [vendorName, setVendorName] = useState('');
  const [vendorEmail, setVendorEmail] = useState('');
  const [saving, setSaving] = useState(false);

  return (
    <FormWrapper title="Add Supplier Request" onCancel={onCancel}>
      <div className="space-y-2 mb-3">
        <input value={vendorName} onChange={e => setVendorName(e.target.value)} placeholder="Supplier / distributor name" className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none" />
        <input value={vendorEmail} onChange={e => setVendorEmail(e.target.value)} placeholder="Supplier email (optional)" className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none" />
      </div>
      <p className="text-xs text-slate-400 mb-2">AI will generate a supplier request email you can copy.</p>
      <button
        onClick={async () => {
          if (!vendorName.trim()) return;
          setSaving(true);
          const res = await api.createSupplierRequest(dealId, { vendor_name: vendorName.trim(), vendor_email: vendorEmail || undefined });
          onSaved();
          if (res?.email_draft_text) onEmailDraft(res.email_draft_text);
        }}
        disabled={saving || !vendorName.trim()}
        className="bg-slate-800 text-white px-4 py-1.5 rounded text-sm disabled:opacity-50"
      >
        {saving ? 'Generating email…' : 'Add & generate email'}
      </button>
    </FormWrapper>
  );
}

function AddSupplierQuoteForm({ dealId, supplierRequests, onSaved, onCancel }: { dealId: number; supplierRequests: any[]; onSaved: () => void; onCancel: () => void }) {
  const [vendorName, setVendorName] = useState('');
  const [srId, setSrId] = useState('');
  const [amount, setAmount] = useState('');
  const [currency, setCurrency] = useState('KWD');
  const [validUntil, setValidUntil] = useState('');
  const [notes, setNotes] = useState('');
  const [rawEmail, setRawEmail] = useState('');
  const [saving, setSaving] = useState(false);

  return (
    <FormWrapper title="Record Supplier Quote" onCancel={onCancel}>
      <div className="space-y-2 mb-3">
        {supplierRequests.length > 0 && (
          <select value={srId} onChange={e => { setSrId(e.target.value); const sr = supplierRequests.find(r => r.id === parseInt(e.target.value)); if (sr) setVendorName(sr.vendor_name); }} className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none">
            <option value="">Select supplier request (optional)</option>
            {supplierRequests.map((sr: any) => <option key={sr.id} value={sr.id}>{sr.vendor_name} ({sr.ref_number})</option>)}
          </select>
        )}
        <input value={vendorName} onChange={e => setVendorName(e.target.value)} placeholder="Supplier name" className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none" />
        <div className="flex gap-2">
          <input value={amount} onChange={e => setAmount(e.target.value)} placeholder="Amount" type="number" className="flex-1 border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none" />
          <select value={currency} onChange={e => setCurrency(e.target.value)} className="border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none">
            <option>KWD</option><option>USD</option><option>EUR</option>
          </select>
        </div>
        <input value={validUntil} onChange={e => setValidUntil(e.target.value)} placeholder="Valid until (e.g. 2026-06-30)" className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none" />
        <input value={notes} onChange={e => setNotes(e.target.value)} placeholder="Notes" className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none" />
        <textarea value={rawEmail} onChange={e => setRawEmail(e.target.value)} placeholder="Paste supplier reply email (optional)" rows={3} className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none" />
      </div>
      <button
        onClick={async () => {
          setSaving(true);
          await api.createSupplierQuote(dealId, {
            vendor_name: vendorName || undefined,
            supplier_request_id: srId ? parseInt(srId) : undefined,
            total_amount: amount ? parseFloat(amount) : undefined,
            currency,
            valid_until: validUntil || undefined,
            notes: notes || undefined,
            raw_email_text: rawEmail || undefined,
          });
          onSaved();
        }}
        disabled={saving}
        className="bg-slate-800 text-white px-4 py-1.5 rounded text-sm disabled:opacity-50"
      >
        {saving ? 'Saving...' : 'Save Quote'}
      </button>
    </FormWrapper>
  );
}

function AddCustomerQuoteForm({ dealId, onSaved, onCancel }: { dealId: number; onSaved: () => void; onCancel: () => void }) {
  const [amount, setAmount] = useState('');
  const [currency, setCurrency] = useState('KWD');
  const [validUntil, setValidUntil] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  return (
    <FormWrapper title="Create Customer Quote" onCancel={onCancel}>
      <div className="space-y-2 mb-3">
        <div className="flex gap-2">
          <input value={amount} onChange={e => setAmount(e.target.value)} placeholder="Amount" type="number" className="flex-1 border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none" />
          <select value={currency} onChange={e => setCurrency(e.target.value)} className="border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none">
            <option>KWD</option><option>USD</option><option>EUR</option>
          </select>
        </div>
        <input value={validUntil} onChange={e => setValidUntil(e.target.value)} placeholder="Valid until (e.g. 2026-06-30)" className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none" />
        <input value={notes} onChange={e => setNotes(e.target.value)} placeholder="Notes" className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none" />
      </div>
      <button
        onClick={async () => {
          setSaving(true);
          await api.createCustomerQuote(dealId, {
            total_amount: amount ? parseFloat(amount) : undefined,
            currency,
            valid_until: validUntil || undefined,
            notes: notes || undefined,
          });
          onSaved();
        }}
        disabled={saving}
        className="bg-slate-800 text-white px-4 py-1.5 rounded text-sm disabled:opacity-50"
      >
        {saving ? 'Saving...' : 'Create Quote'}
      </button>
    </FormWrapper>
  );
}

function AddCustomerPOForm({ dealId, customerQuotes, onSaved, onCancel }: { dealId: number; customerQuotes: any[]; onSaved: () => void; onCancel: () => void }) {
  const [cqId, setCqId] = useState('');
  const [poNumber, setPoNumber] = useState('');
  const [amount, setAmount] = useState('');
  const [currency, setCurrency] = useState('KWD');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  return (
    <FormWrapper title="Record Customer PO" onCancel={onCancel}>
      <div className="space-y-2 mb-3">
        {customerQuotes.length > 0 && (
          <select value={cqId} onChange={e => setCqId(e.target.value)} className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none">
            <option value="">Link to customer quote (optional)</option>
            {customerQuotes.map((cq: any) => <option key={cq.id} value={cq.id}>{cq.ref_number} — {cq.total_amount} {cq.currency}</option>)}
          </select>
        )}
        <input value={poNumber} onChange={e => setPoNumber(e.target.value)} placeholder="Customer's PO number" className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none" />
        <div className="flex gap-2">
          <input value={amount} onChange={e => setAmount(e.target.value)} placeholder="Amount" type="number" className="flex-1 border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none" />
          <select value={currency} onChange={e => setCurrency(e.target.value)} className="border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none">
            <option>KWD</option><option>USD</option><option>EUR</option>
          </select>
        </div>
        <input value={notes} onChange={e => setNotes(e.target.value)} placeholder="Notes" className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none" />
      </div>
      <button
        onClick={async () => {
          setSaving(true);
          await api.recordCustomerPO(dealId, {
            customer_quote_id: cqId ? parseInt(cqId) : undefined,
            customer_po_number: poNumber || undefined,
            amount: amount ? parseFloat(amount) : undefined,
            currency,
            received_at: new Date().toISOString(),
            notes: notes || undefined,
          });
          onSaved();
        }}
        disabled={saving}
        className="bg-slate-800 text-white px-4 py-1.5 rounded text-sm disabled:opacity-50"
      >
        {saving ? 'Saving...' : 'Record PO'}
      </button>
    </FormWrapper>
  );
}

function AddSupplierPOForm({ dealId, supplierRequests, supplierQuotes, onSaved, onCancel }: { dealId: number; supplierRequests: any[]; supplierQuotes: any[]; onSaved: () => void; onCancel: () => void }) {
  const [srId, setSrId] = useState('');
  const [sqId, setSqId] = useState('');
  const [vendorName, setVendorName] = useState('');
  const [vendorEmail, setVendorEmail] = useState('');
  const [poNumber, setPoNumber] = useState('');
  const [amount, setAmount] = useState('');
  const [currency, setCurrency] = useState('KWD');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  return (
    <FormWrapper title="Issue Supplier PO" onCancel={onCancel}>
      <div className="space-y-2 mb-3">
        {supplierRequests.length > 0 && (
          <select value={srId} onChange={e => { setSrId(e.target.value); const sr = supplierRequests.find(r => r.id === parseInt(e.target.value)); if (sr) { setVendorName(sr.vendor_name); setVendorEmail(sr.vendor_email ?? ''); } }} className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none">
            <option value="">Link to supplier request (optional)</option>
            {supplierRequests.map((sr: any) => <option key={sr.id} value={sr.id}>{sr.vendor_name} ({sr.ref_number})</option>)}
          </select>
        )}
        {supplierQuotes.length > 0 && (
          <select value={sqId} onChange={e => setSqId(e.target.value)} className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none">
            <option value="">Link to supplier quote (optional)</option>
            {supplierQuotes.map((sq: any) => <option key={sq.id} value={sq.id}>{sq.vendor_name} — {sq.total_amount} {sq.currency} ({sq.ref_number})</option>)}
          </select>
        )}
        <input value={vendorName} onChange={e => setVendorName(e.target.value)} placeholder="Supplier name" className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none" />
        <input value={vendorEmail} onChange={e => setVendorEmail(e.target.value)} placeholder="Supplier email" className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none" />
        <input value={poNumber} onChange={e => setPoNumber(e.target.value)} placeholder="AAKE's PO number" className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none" />
        <div className="flex gap-2">
          <input value={amount} onChange={e => setAmount(e.target.value)} placeholder="Amount" type="number" className="flex-1 border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none" />
          <select value={currency} onChange={e => setCurrency(e.target.value)} className="border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none">
            <option>KWD</option><option>USD</option><option>EUR</option>
          </select>
        </div>
        <input value={notes} onChange={e => setNotes(e.target.value)} placeholder="Notes" className="w-full border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none" />
      </div>
      <button
        onClick={async () => {
          setSaving(true);
          await api.recordSupplierPO(dealId, {
            supplier_request_id: srId ? parseInt(srId) : undefined,
            supplier_quote_id: sqId ? parseInt(sqId) : undefined,
            vendor_name: vendorName || undefined,
            vendor_email: vendorEmail || undefined,
            aake_po_number: poNumber || undefined,
            amount: amount ? parseFloat(amount) : undefined,
            currency,
            issued_at: new Date().toISOString(),
            notes: notes || undefined,
          });
          onSaved();
        }}
        disabled={saving}
        className="bg-slate-800 text-white px-4 py-1.5 rounded text-sm disabled:opacity-50"
      >
        {saving ? 'Saving...' : 'Issue PO'}
      </button>
    </FormWrapper>
  );
}
