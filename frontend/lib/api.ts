import { getToken, clearToken } from './auth';

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options.headers as Record<string, string>) ?? {}),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(path, { ...options, headers });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    if (res.status === 401 && !path.includes('/auth/login')) {
      clearToken();
      window.location.href = '/login';
    }
    throw new Error(err.detail ?? 'Request failed');
  }

  return res.json();
}

export const api = {
  login: (password: string) =>
    request<{ token: string }>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),

  getInbox: () => request<{ total: number; items: any[] }>('/api/inbox'),
  getEmail: (id: number) => request<any>(`/api/inbox/${id}`),

  approve: (emailId: number, suggestionId: number, draft?: { to?: string; subject?: string; content?: string }, overrideAction?: string) =>
    request<any>(`/api/decisions/${emailId}/approve`, {
      method: 'POST',
      body: JSON.stringify({
        suggestion_id: suggestionId,
        ...(draft ? { draft_to: draft.to, draft_subject: draft.subject, draft_content: draft.content } : {}),
        ...(overrideAction ? { override_action: overrideAction } : {}),
      }),
    }),
  reject: (emailId: number, suggestionId: number, reason?: string) =>
    request<any>(`/api/decisions/${emailId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ suggestion_id: suggestionId, rejection_reason: reason }),
    }),
  reanalyze: (emailId: number) =>
    request<any>(`/api/decisions/${emailId}/reanalyze`, { method: 'POST' }),

  answerClarification: (suggestionId: number, moAnswer: string) =>
    request<any>(`/api/clarifications/${suggestionId}/answer`, {
      method: 'POST',
      body: JSON.stringify({ mo_answer: moAnswer }),
    }),
  skipClarification: (suggestionId: number) =>
    request<any>(`/api/clarifications/${suggestionId}/skip`, { method: 'POST' }),
  manuallyHandled: (suggestionId: number) =>
    request<any>(`/api/clarifications/${suggestionId}/manually_handled`, { method: 'POST' }),

  getHistory: (params?: { category?: string; action?: string; decision?: string }) => {
    const qs = new URLSearchParams(
      Object.fromEntries(Object.entries(params ?? {}).filter(([, v]) => v))
    ).toString();
    return request<{ total: number; items: any[] }>(`/api/history${qs ? '?' + qs : ''}`);
  },

  getLeads: (status?: string) =>
    request<any[]>(`/api/leads${status ? '?status=' + status : ''}`),
  updateLeadStatus: (id: number, status: string, notes?: string) =>
    request<any>(`/api/leads/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status, notes }),
    }),

  getVendors: () => request<any[]>('/api/vendors'),
  createVendor: (data: any) =>
    request<any>('/api/vendors', { method: 'POST', body: JSON.stringify(data) }),
  updateVendor: (id: number, data: any) =>
    request<any>(`/api/vendors/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteVendor: (id: number) =>
    request<any>(`/api/vendors/${id}`, { method: 'DELETE' }),

  getSettings: () =>
    request<Record<string, { value: string; description: string }>>('/api/settings'),
  updateSetting: (key: string, value: string) =>
    request<any>(`/api/settings/${key}`, {
      method: 'PATCH',
      body: JSON.stringify({ value }),
    }),
  changePassword: (currentPassword: string, newPassword: string) =>
    request<any>('/api/settings/change-password', {
      method: 'POST',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }),
  getAuditLog: () => request<any[]>('/api/settings/audit-log'),

  getStyleStatus: () => request<any>('/api/style/status'),
  refreshStyle: () => request<any>('/api/style/refresh', { method: 'POST' }),
  confirmStyle: (profileJson: string, emailCount: number) =>
    request<any>('/api/style/confirm', {
      method: 'POST',
      body: JSON.stringify({ profile_json: profileJson, email_count: emailCount }),
    }),

  getPrices: (params?: { category?: string; vendor?: string; search?: string }) => {
    const qs = new URLSearchParams();
    if (params?.category) qs.set('category', params.category);
    if (params?.vendor) qs.set('vendor', params.vendor);
    if (params?.search) qs.set('search', params.search);
    return request<{ items: any[]; categories: string[]; total: number }>(
      `/api/prices${qs.toString() ? '?' + qs.toString() : ''}`
    );
  },
  extractPrices: () => request<any>('/api/prices/extract', { method: 'POST' }),
  getExtractStatus: () => request<any>('/api/prices/extract/status'),
  extractPricesForEmail: (emailId: number) =>
    request<any>(`/api/prices/extract/${emailId}`, { method: 'POST' }),
  searchContacts: (q: string) =>
    request<{ email: string; name: string | null; frequency: number }[]>(
      `/api/contacts/search?q=${encodeURIComponent(q)}&limit=8`
    ),
  scanContacts: () => request<any>('/api/contacts/scan', { method: 'POST' }),

  submitBatch: async (emails: { source: string; text?: string; subject?: string; from_address?: string; user_instruction?: string }[], files: File[]) => {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const fd = new FormData();
    fd.append('emails_json', JSON.stringify(emails));
    files.forEach(f => fd.append('files', f));
    const res = await fetch('/api/batches/submit', { method: 'POST', headers, body: fd });
    if (res.status === 401) { clearToken(); window.location.href = '/login'; throw new Error('Unauthorized'); }
    if (!res.ok) { const err = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(err.detail ?? 'Submit failed'); }
    return res.json() as Promise<{ batch_id: number; status: string; total: number }>;
  },

  getBatchStatus: (batchId: number) =>
    request<{ batch_id: number; status: string; total: number; processed: number; email_ids: number[]; error_msg: string | null }>(
      `/api/batches/${batchId}/status`
    ),

  // --- Customers ---
  listCustomers: () => request<any[]>('/api/customers'),
  getCustomer: (id: number) => request<any>(`/api/customers/${id}`),
  createCustomer: (data: any) =>
    request<any>('/api/customers', { method: 'POST', body: JSON.stringify(data) }),
  updateCustomer: (id: number, data: any) =>
    request<any>(`/api/customers/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteCustomer: (id: number) =>
    request<any>(`/api/customers/${id}`, { method: 'DELETE' }),

  // --- Business Facts (Company Brain) ---
  listFacts: () => request<any[]>('/api/facts'),
  createFact: (fact: string, category: string) =>
    request<any>('/api/facts', { method: 'POST', body: JSON.stringify({ fact, category }) }),
  updateFact: (id: number, fact: string, category: string) =>
    request<any>(`/api/facts/${id}`, { method: 'PUT', body: JSON.stringify({ fact, category }) }),
  deleteFact: (id: number) =>
    request<any>(`/api/facts/${id}`, { method: 'DELETE' }),

  // --- Deals ---
  listDeals: () => request<any[]>('/api/deals'),
  createDeal: (data: any) => request<any>('/api/deals', { method: 'POST', body: JSON.stringify(data) }),
  getDeal: (id: number) => request<any>(`/api/deals/${id}`),
  updateDeal: (id: number, data: any) => request<any>(`/api/deals/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteDeal: (id: number) => request<any>(`/api/deals/${id}`, { method: 'DELETE' }),

  addDealItem: (dealId: number, data: any) =>
    request<any>(`/api/deals/${dealId}/items`, { method: 'POST', body: JSON.stringify(data) }),
  updateDealItem: (dealId: number, itemId: number, data: any) =>
    request<any>(`/api/deals/${dealId}/items/${itemId}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteDealItem: (dealId: number, itemId: number) =>
    request<any>(`/api/deals/${dealId}/items/${itemId}`, { method: 'DELETE' }),

  createSupplierRequest: (dealId: number, data: any) =>
    request<any>(`/api/deals/${dealId}/supplier-requests`, { method: 'POST', body: JSON.stringify(data) }),
  updateSupplierRequest: (dealId: number, srId: number, data: any) =>
    request<any>(`/api/deals/${dealId}/supplier-requests/${srId}`, { method: 'PUT', body: JSON.stringify(data) }),

  createSupplierQuote: (dealId: number, data: any) =>
    request<any>(`/api/deals/${dealId}/supplier-quotes`, { method: 'POST', body: JSON.stringify(data) }),
  updateSupplierQuote: (dealId: number, sqId: number, data: any) =>
    request<any>(`/api/deals/${dealId}/supplier-quotes/${sqId}`, { method: 'PUT', body: JSON.stringify(data) }),

  createCustomerQuote: (dealId: number, data: any) =>
    request<any>(`/api/deals/${dealId}/customer-quotes`, { method: 'POST', body: JSON.stringify(data) }),
  updateCustomerQuote: (dealId: number, cqId: number, data: any) =>
    request<any>(`/api/deals/${dealId}/customer-quotes/${cqId}`, { method: 'PUT', body: JSON.stringify(data) }),

  recordCustomerPO: (dealId: number, data: any) =>
    request<any>(`/api/deals/${dealId}/customer-po`, { method: 'POST', body: JSON.stringify(data) }),
  recordSupplierPO: (dealId: number, data: any) =>
    request<any>(`/api/deals/${dealId}/supplier-po`, { method: 'POST', body: JSON.stringify(data) }),

  extractDealEmail: (emailText: string) =>
    request<{ customer_name: string; customer_email: string | null; description: string; items: any[] }>(
      '/api/deals/extract-email', { method: 'POST', body: JSON.stringify({ email_text: emailText }) }
    ),

  extractDealPdf: async (file: File) => {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch('/api/deals/extract-email-pdf', { method: 'POST', headers, body: fd });
    if (res.status === 401) { clearToken(); window.location.href = '/login'; throw new Error('Unauthorized'); }
    if (!res.ok) { const err = await res.json().catch(() => ({ detail: res.statusText })); throw new Error(err.detail ?? 'PDF extraction failed'); }
    return res.json() as Promise<{ customer_name: string; customer_email: string | null; description: string; items: any[] }>;
  },
  getDealNextStep: (dealId: number) =>
    request<{ next_step: string }>(`/api/deals/${dealId}/next-step`),

  exportPrices: async (params?: { category?: string; vendor?: string; search?: string }) => {
    const qs = new URLSearchParams();
    if (params?.category) qs.set('category', params.category);
    if (params?.vendor) qs.set('vendor', params.vendor);
    if (params?.search) qs.set('search', params.search);
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(
      `/api/prices/export${qs.toString() ? '?' + qs.toString() : ''}`,
      { headers }
    );
    if (!res.ok) throw new Error('Export failed');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `AAKE_Price_List_${new Date().toISOString().slice(0, 10)}.xlsx`;
    a.click();
    URL.revokeObjectURL(url);
  },

  // ── Usage ─────────────────────────────────────────────────────────────────
  getUsageStats: () =>
    request<any>('/api/usage'),

  setAnthropicBalance: (balance_usd: number | null) =>
    request<any>('/api/usage/balance', {
      method: 'PATCH',
      body: JSON.stringify({ balance_usd }),
    }),

  // ── Follow-up chaser ──────────────────────────────────────────────────────
  runFollowupChaser: () =>
    request<{ created: number; message: string }>('/api/inbox/run-followup-chaser', { method: 'POST' }),

  // ── Thread summary ────────────────────────────────────────────────────────
  summarizeThread: (emailId: number) =>
    request<{ thread_count: number; summary_text: string }>(`/api/inbox/${emailId}/thread-summary`, { method: 'POST' }),

  // ── Daily summary ─────────────────────────────────────────────────────────
  getCachedBriefing: () =>
    request<{
      email_count: number;
      generated_at: string;
      overview: string;
      attention: { title: string; contact: string; detail: string }[];
      vendors:   { title: string; contact: string; detail: string }[];
      priorities: string[];
    } | null>('/api/inbox/daily-summary'),

  getDailySummary: () =>
    request<{
      email_count: number;
      overview: string;
      attention: { title: string; contact: string; detail: string }[];
      vendors:   { title: string; contact: string; detail: string }[];
      priorities: string[];
    }>('/api/inbox/daily-summary', { method: 'POST' }),

  // ── Suggested Tasks (staging proposals) ──────────────────────────────────
  listPendingTasks: () =>
    request<any[]>('/api/suggested-tasks/pending'),
  getTask: (id: number) =>
    request<any>(`/api/suggested-tasks/${id}`),
  updateTask: (id: number, data: { description?: string; payload?: any; confidence?: number; evidence_quote?: string }) =>
    request<any>(`/api/suggested-tasks/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  approveTask: (id: number) =>
    request<any>(`/api/suggested-tasks/${id}/approve`, { method: 'POST' }),
  rejectTask: (id: number) =>
    request<any>(`/api/suggested-tasks/${id}/reject`, { method: 'POST' }),

  // ── Trust ─────────────────────────────────────────────────────────────────
  listTrust: () =>
    request<{ threshold: number; categories: any[] }>('/api/trust'),

  revokeTrust: (category: string) =>
    request<{ revoked: string }>(`/api/trust/${category}/revoke`, { method: 'POST' }),
};
