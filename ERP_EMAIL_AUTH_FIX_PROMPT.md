# ERP Prompt — Fix "Email Agent offline" error

Paste this entire message into your ERP Claude session.

---

## What broke and why

The email agent backend (`http://localhost:8000`) now requires a JWT login token
on every API call. Before this change all routes were open; now they return
`401 Unauthorized` without a token. That is why the ERP email section shows
"Email Agent offline" — it is calling `GET /api/inbox` with no auth header.

## What the ERP email inbox needs to do

1. **On mount (or when Retry is clicked):** call `POST http://localhost:8000/api/auth/login`
   with the email agent password → get back a JWT token.
2. **Store the token** in component state.
3. **Include the token** as `Authorization: Bearer <token>` on every subsequent
   call to the email agent (`GET /api/inbox`, etc.).
4. **Handle token expiry:** if any call returns 401, re-login and retry once.

## The login endpoint

```
POST http://localhost:8000/api/auth/login
Content-Type: application/json

{ "password": "<email-agent-dashboard-password>" }

→ { "token": "eyJ..." }
```

The password is the one set during email agent setup (stored as a bcrypt hash in
the agent's SQLite DB — not the ERP password). Mo must provide it as an env
variable or a config value in the ERP. A safe place is a Next.js env variable:

```
NEXT_PUBLIC_EMAIL_AGENT_PASSWORD=<the-password>
```

Or if the password is already stored somewhere in the ERP config, use that.

## Endpoints the ERP calls

Based on the backend logs, the ERP makes at least:
- `GET /api/inbox` — list emails
- `GET /api/health` — health check (this one is still OPEN, no auth needed)

All `/api/*` routes except `/api/health` and `/api/auth/login` now need the
`Authorization: Bearer <token>` header.

## Implementation pattern (React / Next.js)

```typescript
// Rough sketch — adapt to the ERP's actual file structure

const AGENT_BASE = 'http://localhost:8000';
const AGENT_PASSWORD = process.env.NEXT_PUBLIC_EMAIL_AGENT_PASSWORD ?? '';

async function getAgentToken(): Promise<string | null> {
  try {
    const res = await fetch(`${AGENT_BASE}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: AGENT_PASSWORD }),
    });
    if (!res.ok) return null;
    const data = await res.json();
    return data.token ?? null;
  } catch {
    return null;
  }
}

async function fetchInbox(token: string) {
  const res = await fetch(`${AGENT_BASE}/api/inbox`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (res.status === 401) return null; // token expired — re-login
  return res.json();
}

// In your component:
useEffect(() => {
  (async () => {
    const token = await getAgentToken();
    if (!token) { setOffline(true); return; }
    const data = await fetchInbox(token);
    if (!data) { setOffline(true); return; }
    setEmails(data);
  })();
}, []);
```

## Summary of changes needed

1. Add `NEXT_PUBLIC_EMAIL_AGENT_PASSWORD` to ERP env (Vercel env vars + local `.env.local`)
2. Create a `getAgentToken()` helper that POSTs to `/api/auth/login`
3. Call `getAgentToken()` on mount and on every Retry click
4. Pass the token as `Authorization: Bearer <token>` on all agent API calls
5. If a call returns 401, re-run `getAgentToken()` and retry once

Do NOT hardcode the password in the source code. Use the env variable.
