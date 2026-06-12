'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';

const EMPTY_FORM = {
  name: '', company: '', email: '', phone: '',
  brands: '', product_categories: '', notes: '',
};

export default function VendorsPage() {
  const router = useRouter();
  const [vendors, setVendors] = useState<any[]>([]);
  const [error, setError] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);

  useEffect(() => {
    if (!isAuthenticated()) { router.push('/login'); return; }
    load();
  }, []);

  async function load() {
    try {
      const data = await api.getVendors();
      setVendors(data);
    } catch (err: any) {
      setError(err.message);
    }
  }

  function openCreate() {
    setForm(EMPTY_FORM);
    setEditId(null);
    setShowForm(true);
  }

  function openEdit(vendor: any) {
    setForm({
      name: vendor.name ?? '',
      company: vendor.company ?? '',
      email: vendor.email ?? '',
      phone: vendor.phone ?? '',
      brands: (vendor.brands ?? []).join(', '),
      product_categories: (vendor.product_categories ?? []).join(', '),
      notes: vendor.notes ?? '',
    });
    setEditId(vendor.id);
    setShowForm(true);
  }

  function parseList(s: string): string[] {
    return s.split(',').map((x) => x.trim()).filter(Boolean);
  }

  async function save() {
    setSaving(true);
    setError('');
    const payload = {
      ...form,
      brands: parseList(form.brands),
      product_categories: parseList(form.product_categories),
    };
    try {
      if (editId) {
        await api.updateVendor(editId, payload);
      } else {
        await api.createVendor(payload);
      }
      setShowForm(false);
      await load();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function deleteVendor(id: number) {
    try {
      await api.deleteVendor(id);
      setConfirmDelete(null);
      await load();
    } catch (err: any) {
      setError(err.message);
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-bold text-slate-800">Vendors</h1>
        <button
          onClick={openCreate}
          className="bg-slate-800 text-white text-sm px-4 py-2 rounded-lg hover:bg-slate-700"
        >
          + Add Vendor
        </button>
      </div>

      {error && <p className="text-red-500 text-sm mb-4">{error}</p>}

      {showForm && (
        <div className="bg-white border border-slate-200 rounded-xl p-5 mb-5">
          <h2 className="font-semibold text-slate-800 mb-4">{editId ? 'Edit Vendor' : 'New Vendor'}</h2>
          <div className="grid grid-cols-2 gap-3">
            {[
              { key: 'name', label: 'Contact Name', required: true },
              { key: 'company', label: 'Company' },
              { key: 'email', label: 'Email' },
              { key: 'phone', label: 'Phone' },
              { key: 'brands', label: 'Brands (comma-separated)' },
              { key: 'product_categories', label: 'Categories (comma-separated)' },
            ].map(({ key, label, required }) => (
              <div key={key}>
                <label className="text-xs text-slate-500 mb-1 block">
                  {label}{required && <span className="text-red-500">*</span>}
                </label>
                <input
                  value={form[key as keyof typeof form]}
                  onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                  className="w-full border border-slate-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-slate-400"
                />
              </div>
            ))}
          </div>
          <div className="mt-3">
            <label className="text-xs text-slate-500 mb-1 block">Notes</label>
            <textarea
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              rows={2}
              className="w-full border border-slate-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-slate-400"
            />
          </div>
          <div className="flex gap-2 mt-4">
            <button
              onClick={save}
              disabled={saving || !form.name}
              className="bg-slate-800 text-white text-sm px-4 py-2 rounded-lg hover:bg-slate-700 disabled:opacity-50"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
            <button
              onClick={() => setShowForm(false)}
              className="text-sm text-slate-600 border border-slate-300 px-4 py-2 rounded-lg hover:bg-slate-50"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider">
            <tr>
              <th className="px-4 py-3 text-left">Name / Company</th>
              <th className="px-4 py-3 text-left">Email</th>
              <th className="px-4 py-3 text-left">Brands</th>
              <th className="px-4 py-3 text-left">Categories</th>
              <th className="px-4 py-3 text-left">Status</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {vendors.length === 0 ? (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-slate-400">No vendors yet</td></tr>
            ) : vendors.map((v) => (
              <tr key={v.id} className="hover:bg-slate-50">
                <td className="px-4 py-3">
                  <p className="font-medium">{v.name}</p>
                  {v.company && <p className="text-slate-400 text-xs">{v.company}</p>}
                </td>
                <td className="px-4 py-3 text-slate-600">{v.email || '—'}</td>
                <td className="px-4 py-3 text-slate-500 text-xs">{(v.brands ?? []).join(', ') || '—'}</td>
                <td className="px-4 py-3 text-slate-500 text-xs">{(v.product_categories ?? []).join(', ') || '—'}</td>
                <td className="px-4 py-3">
                  <span className={`text-xs px-2 py-0.5 rounded-full ${v.active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'}`}>
                    {v.active ? 'Active' : 'Inactive'}
                  </span>
                </td>
                <td className="px-4 py-3 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <button
                      onClick={() => openEdit(v)}
                      className="text-xs text-slate-600 hover:text-slate-900"
                    >
                      Edit
                    </button>
                    {confirmDelete === v.id ? (
                      <>
                        <button
                          onClick={() => deleteVendor(v.id)}
                          className="text-xs text-red-600 font-semibold"
                        >
                          Confirm
                        </button>
                        <button
                          onClick={() => setConfirmDelete(null)}
                          className="text-xs text-slate-400"
                        >
                          Cancel
                        </button>
                      </>
                    ) : (
                      <button
                        onClick={() => setConfirmDelete(v.id)}
                        className="text-xs text-red-400 hover:text-red-600"
                      >
                        Delete
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
