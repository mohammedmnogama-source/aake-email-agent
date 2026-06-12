'use client';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';

type Item = { product_name: string; qty: string; specs: string };

export default function NewDealPage() {
  const router = useRouter();

  // Tab: 'manual' or 'paste'
  const [tab, setTab] = useState<'manual' | 'paste'>('manual');

  // Existing customers for the picker
  const [customers, setCustomers] = useState<any[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>('');

  // Manual form fields
  const [customerName, setCustomerName] = useState('');
  const [customerEmail, setCustomerEmail] = useState('');

  useEffect(() => {
    api.listCustomers().then(setCustomers).catch(() => {});
  }, []);
  const [description, setDescription] = useState('');
  const [items, setItems] = useState<Item[]>([{ product_name: '', qty: '', specs: '' }]);

  // Paste tab
  const [pasteText, setPasteText] = useState('');
  const [extracting, setExtracting] = useState(false);
  const [extractError, setExtractError] = useState('');
  const [pdfFileName, setPdfFileName] = useState('');

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');

  // When a customer is picked from the dropdown, auto-fill name + email
  function pickCustomer(id: string) {
    setSelectedCustomerId(id);
    if (!id) return;
    const c = customers.find(c => String(c.id) === id);
    if (c) {
      setCustomerName(c.name);
      setCustomerEmail(c.email || '');
    }
  }

  // Fill form fields from AI extraction result
  function applyExtracted(result: any) {
    if (result.customer_name) setCustomerName(result.customer_name);
    if (result.customer_email) setCustomerEmail(result.customer_email);
    if (result.description) setDescription(result.description);
    if (result.items && result.items.length > 0) {
      setItems(result.items.map((it: any) => ({
        product_name: it.product_name || '',
        qty: it.qty != null ? String(it.qty) : '',
        specs: it.specs || '',
      })));
    }
  }

  // Handle PDF file upload → extract with AI
  async function handlePdfUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setPdfFileName(file.name);
    setExtracting(true);
    setExtractError('');
    try {
      const result = await api.extractDealPdf(file);
      applyExtracted(result);
    } catch (err: any) {
      setExtractError(err.message ?? 'PDF extraction failed');
    } finally {
      setExtracting(false);
      e.target.value = ''; // reset so same file can be re-uploaded
    }
  }

  // Add/remove line item rows
  function addItem() {
    setItems([...items, { product_name: '', qty: '', specs: '' }]);
  }
  function removeItem(i: number) {
    setItems(items.filter((_, idx) => idx !== i));
  }
  function updateItem(i: number, field: keyof Item, value: string) {
    const copy = [...items];
    copy[i] = { ...copy[i], [field]: value };
    setItems(copy);
  }

  // Submit the deal
  async function submit() {
    if (!customerName.trim()) { setSaveError('Customer name is required.'); return; }
    setSaving(true);
    setSaveError('');
    try {
      const validItems = items.filter(it => it.product_name.trim());
      const deal = await api.createDeal({
        customer_name: customerName.trim(),
        customer_email: customerEmail.trim() || undefined,
        description: description.trim() || undefined,
        source_type: tab === 'paste' ? 'email_paste' : 'manual',
        source_raw_text: tab === 'paste' ? pasteText : undefined,
        customer_id: selectedCustomerId ? parseInt(selectedCustomerId) : undefined,
      });
      // Add line items
      for (const item of validItems) {
        await api.addDealItem(deal.deal.id, {
          product_name: item.product_name.trim(),
          qty: item.qty ? parseInt(item.qty) : undefined,
          specs: item.specs.trim() || undefined,
        });
      }
      router.push(`/deals/${deal.deal.id}`);
    } catch (e: any) {
      setSaveError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto p-6">
      <h1 className="text-2xl font-bold text-slate-800 mb-6">New Deal</h1>

      {/* Tab toggle */}
      <div className="flex border border-slate-200 rounded-lg overflow-hidden mb-6">
        <button
          onClick={() => setTab('manual')}
          className={`flex-1 py-2 text-sm font-medium transition-colors ${tab === 'manual' ? 'bg-slate-800 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'}`}
        >
          Fill in manually
        </button>
        <button
          onClick={() => setTab('paste')}
          className={`flex-1 py-2 text-sm font-medium transition-colors ${tab === 'paste' ? 'bg-slate-800 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'}`}
        >
          Paste email
        </button>
      </div>

      {/* Paste tab — email text area + Extract button */}
      {tab === 'paste' && (
        <div className="mb-6">
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Paste the customer's inquiry email
          </label>
          <textarea
            value={pasteText}
            onChange={e => setPasteText(e.target.value)}
            rows={8}
            placeholder="Paste the full email text here..."
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
          />
          {extractError && (
            <p className="text-xs text-red-500 mt-1">{extractError}</p>
          )}
          <div className="mt-2 flex items-center gap-3 flex-wrap">
            <button
              type="button"
              disabled={extracting || !pasteText.trim()}
              onClick={async () => {
                setExtracting(true);
                setExtractError('');
                try {
                  const result = await api.extractDealEmail(pasteText);
                  applyExtracted(result);
                } catch (e: any) {
                  setExtractError(e.message ?? 'Extraction failed');
                } finally {
                  setExtracting(false);
                }
              }}
              className="bg-blue-600 text-white px-4 py-2 rounded text-sm font-medium hover:bg-blue-500 disabled:opacity-50 transition-colors"
            >
              {extracting ? 'Extracting…' : 'Extract with AI'}
            </button>

            <span className="text-xs text-slate-400">or</span>

            {/* Hidden file input */}
            <input
              id="pdf-upload"
              type="file"
              accept=".pdf"
              className="hidden"
              onChange={handlePdfUpload}
            />
            <label
              htmlFor="pdf-upload"
              className={`cursor-pointer border border-slate-300 text-slate-600 px-4 py-2 rounded text-sm font-medium hover:bg-slate-50 transition-colors ${extracting ? 'opacity-50 pointer-events-none' : ''}`}
            >
              {extracting && pdfFileName ? 'Extracting…' : 'Upload PDF'}
            </label>
            {pdfFileName && !extracting && (
              <span className="text-xs text-slate-400 truncate max-w-xs">{pdfFileName}</span>
            )}
          </div>
          <p className="text-xs text-slate-400 mt-1">
            AI will fill in the customer name, email, description, and line items below.
          </p>
        </div>
      )}

      {/* Customer details */}
      <div className="space-y-4 mb-6">
        {/* Existing customer picker — auto-fills name + email */}
        {customers.length > 0 && (
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Pick existing customer
            </label>
            <select
              value={selectedCustomerId}
              onChange={e => pickCustomer(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400 bg-white"
            >
              <option value="">— Select a customer —</option>
              {customers.map(c => (
                <option key={c.id} value={String(c.id)}>
                  {c.name}{c.company ? ` (${c.company})` : ''}
                </option>
              ))}
            </select>
          </div>
        )}
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Customer name <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={customerName}
            onChange={e => setCustomerName(e.target.value)}
            placeholder="e.g. Gulf Networks"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Customer email</label>
          <input
            type="email"
            value={customerEmail}
            onChange={e => setCustomerEmail(e.target.value)}
            placeholder="e.g. info@gulfnet.kw"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Description</label>
          <input
            type="text"
            value={description}
            onChange={e => setDescription(e.target.value)}
            placeholder="Brief one-line summary of what they need"
            className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-400"
          />
        </div>
      </div>

      {/* Line items */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-2">
          <label className="text-sm font-medium text-slate-700">Products / Line Items</label>
          <button
            onClick={addItem}
            className="text-xs text-slate-500 hover:text-slate-800 border border-slate-200 rounded px-2 py-1 transition-colors"
          >
            + Add item
          </button>
        </div>
        <div className="space-y-2">
          {items.map((item, i) => (
            <div key={i} className="flex gap-2 items-start">
              <input
                type="text"
                value={item.product_name}
                onChange={e => updateItem(i, 'product_name', e.target.value)}
                placeholder="Product name"
                className="flex-1 border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-slate-400"
              />
              <input
                type="text"
                value={item.qty}
                onChange={e => updateItem(i, 'qty', e.target.value)}
                placeholder="Qty"
                className="w-16 border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-slate-400"
              />
              <input
                type="text"
                value={item.specs}
                onChange={e => updateItem(i, 'specs', e.target.value)}
                placeholder="Specs / notes"
                className="flex-1 border border-slate-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-slate-400"
              />
              {items.length > 1 && (
                <button
                  onClick={() => removeItem(i)}
                  className="text-slate-400 hover:text-red-500 px-1 py-1.5 text-sm"
                >
                  ×
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      {saveError && (
        <div className="mb-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
          {saveError}
        </div>
      )}

      <div className="flex gap-3">
        <button
          onClick={submit}
          disabled={saving}
          className="bg-slate-800 text-white px-6 py-2 rounded text-sm font-medium hover:bg-slate-700 disabled:opacity-50 transition-colors"
        >
          {saving ? 'Creating...' : 'Create Deal'}
        </button>
        <button
          onClick={() => router.push('/deals')}
          className="text-slate-500 hover:text-slate-700 px-4 py-2 text-sm transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
