"""
backend/routers/usage.py — AI usage & cost analytics.

Aggregates from api_audit_log (all calls) and ai_suggestions (token counts).
Cost estimates use Claude Haiku 4.5 public pricing — actual billing is on
the Anthropic console; these numbers are approximate.
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from backend.database.connection import get_connection
from backend.middleware.auth import require_auth

router = APIRouter(prefix="/api/usage", tags=["usage"], dependencies=[Depends(require_auth)])

# Claude Haiku 4.5 approximate pricing (USD per 1M tokens)
_INPUT_COST_PER_M  = 0.80
_OUTPUT_COST_PER_M = 4.00
_CHARS_PER_TOKEN   = 4


def _tok(chars: int) -> int:
    return max(0, round((chars or 0) / _CHARS_PER_TOKEN))


def _usd(input_tokens: int, output_tokens: int) -> float:
    return (
        (input_tokens  / 1_000_000) * _INPUT_COST_PER_M
      + (output_tokens / 1_000_000) * _OUTPUT_COST_PER_M
    )


class BalanceUpdate(BaseModel):
    balance_usd: Optional[float] = None


@router.get("")
def get_usage_stats():
    conn = get_connection()
    try:
        # ── All-time totals ───────────────────────────────────────────────
        totals = conn.execute("""
            SELECT COUNT(*) as calls,
                   SUM(prompt_size)   as p_chars,
                   SUM(response_size) as r_chars
            FROM api_audit_log
        """).fetchone()

        all_calls  = totals["calls"]    or 0
        all_p      = totals["p_chars"]  or 0
        all_r      = totals["r_chars"]  or 0
        all_in     = _tok(all_p)
        all_out    = _tok(all_r)
        all_cost   = _usd(all_in, all_out)

        # ── This month ────────────────────────────────────────────────────
        this_month = conn.execute("""
            SELECT COUNT(*) as calls,
                   SUM(prompt_size)   as p_chars,
                   SUM(response_size) as r_chars
            FROM api_audit_log
            WHERE timestamp >= DATE('now','start of month')
        """).fetchone()

        tm_calls = this_month["calls"]   or 0
        tm_in    = _tok(this_month["p_chars"] or 0)
        tm_out   = _tok(this_month["r_chars"] or 0)
        tm_cost  = _usd(tm_in, tm_out)

        # ── Last month ────────────────────────────────────────────────────
        last_month = conn.execute("""
            SELECT COUNT(*) as calls,
                   SUM(prompt_size)   as p_chars,
                   SUM(response_size) as r_chars
            FROM api_audit_log
            WHERE timestamp >= DATE('now','start of month','-1 month')
              AND timestamp <  DATE('now','start of month')
        """).fetchone()

        lm_cost = _usd(
            _tok(last_month["p_chars"] or 0),
            _tok(last_month["r_chars"] or 0)
        )

        # ── Month projection ──────────────────────────────────────────────
        now = datetime.now(timezone.utc)
        day_of_month  = now.day
        days_in_month = 30   # close enough for projection
        projected_cost = (tm_cost / day_of_month * days_in_month) if day_of_month > 0 else 0

        # ── Avg cost per email ────────────────────────────────────────────
        email_tokens = conn.execute("""
            SELECT AVG(prompt_tokens)     as avg_in,
                   AVG(completion_tokens) as avg_out,
                   COUNT(*) as cnt
            FROM ai_suggestions
            WHERE prompt_tokens > 0
        """).fetchone()
        avg_in   = email_tokens["avg_in"]  or 0
        avg_out  = email_tokens["avg_out"] or 0
        avg_cost_per_email = _usd(avg_in, avg_out)

        # ── By purpose ────────────────────────────────────────────────────
        by_purpose_rows = conn.execute("""
            SELECT purpose,
                   COUNT(*) as calls,
                   SUM(prompt_size)   as p_chars,
                   SUM(response_size) as r_chars
            FROM api_audit_log
            GROUP BY purpose
            ORDER BY (SUM(prompt_size)+SUM(response_size)) DESC
        """).fetchall()

        by_purpose = []
        for row in by_purpose_rows:
            in_tok  = _tok(row["p_chars"] or 0)
            out_tok = _tok(row["r_chars"] or 0)
            cost    = _usd(in_tok, out_tok)
            by_purpose.append({
                "purpose":           row["purpose"],
                "calls":             row["calls"],
                "est_input_tokens":  in_tok,
                "est_output_tokens": out_tok,
                "est_cost_usd":      round(cost, 5),
                "pct_of_total":      round(cost / all_cost * 100, 1) if all_cost > 0 else 0,
            })

        # ── Daily last 30 days ────────────────────────────────────────────
        daily_rows = conn.execute("""
            SELECT DATE(timestamp) as day,
                   COUNT(*) as calls,
                   SUM(prompt_size)   as p_chars,
                   SUM(response_size) as r_chars
            FROM api_audit_log
            WHERE timestamp >= DATE('now','-30 days')
            GROUP BY DATE(timestamp)
            ORDER BY day ASC
        """).fetchall()

        daily = []
        cumulative = 0.0
        for row in daily_rows:
            in_tok  = _tok(row["p_chars"] or 0)
            out_tok = _tok(row["r_chars"] or 0)
            cost    = _usd(in_tok, out_tok)
            cumulative += cost
            daily.append({
                "day":               row["day"],
                "calls":             row["calls"],
                "est_input_tokens":  in_tok,
                "est_output_tokens": out_tok,
                "est_cost_usd":      round(cost, 5),
                "cumulative_usd":    round(cumulative, 5),
            })

        # ── Monthly last 6 months ─────────────────────────────────────────
        monthly_rows = conn.execute("""
            SELECT strftime('%Y-%m', timestamp) as month,
                   COUNT(*) as calls,
                   SUM(prompt_size)   as p_chars,
                   SUM(response_size) as r_chars
            FROM api_audit_log
            GROUP BY strftime('%Y-%m', timestamp)
            ORDER BY month DESC
            LIMIT 6
        """).fetchall()

        monthly = []
        for row in monthly_rows:
            in_tok  = _tok(row["p_chars"] or 0)
            out_tok = _tok(row["r_chars"] or 0)
            monthly.append({
                "month":             row["month"],
                "calls":             row["calls"],
                "est_input_tokens":  in_tok,
                "est_output_tokens": out_tok,
                "est_cost_usd":      round(_usd(in_tok, out_tok), 5),
            })

        # ── Manual balance from settings ──────────────────────────────────
        bal_row = conn.execute(
            "SELECT value FROM settings WHERE key = 'anthropic_balance_usd'"
        ).fetchone()
        manual_balance = float(bal_row["value"]) if bal_row and bal_row["value"] else None

        # ── Models used ───────────────────────────────────────────────────
        by_model = conn.execute("""
            SELECT model, COUNT(*) as calls
            FROM api_audit_log
            GROUP BY model ORDER BY calls DESC
        """).fetchall()

        return {
            "summary": {
                "total_calls":           all_calls,
                "total_input_tokens":    all_in,
                "total_output_tokens":   all_out,
                "total_cost_usd":        round(all_cost, 4),
                "this_month_calls":      tm_calls,
                "this_month_cost_usd":   round(tm_cost, 4),
                "last_month_cost_usd":   round(lm_cost, 4),
                "projected_month_usd":   round(projected_cost, 4),
                "avg_cost_per_email":    round(avg_cost_per_email, 5),
                "emails_analyzed":       email_tokens["cnt"] or 0,
                "day_of_month":          day_of_month,
                "manual_balance_usd":    manual_balance,
                "top_cost_driver":       by_purpose[0]["purpose"] if by_purpose else None,
                "top_driver_pct":        by_purpose[0]["pct_of_total"] if by_purpose else 0,
            },
            "by_purpose": by_purpose,
            "daily":      daily,
            "monthly":    monthly,
            "by_model":   [dict(r) for r in by_model],
            "pricing": {
                "input_per_m_usd":  _INPUT_COST_PER_M,
                "output_per_m_usd": _OUTPUT_COST_PER_M,
                "model":            "claude-haiku-4-5 (approximate)",
                "note":             "Estimates from character counts (4 chars ≈ 1 token). Check Anthropic Console for exact billing.",
            },
        }
    finally:
        conn.close()


@router.patch("/balance")
def set_manual_balance(body: BalanceUpdate):
    """Store Mo's manually entered Anthropic credit balance for display."""
    conn = get_connection()
    try:
        val = str(body.balance_usd) if body.balance_usd is not None else ""
        conn.execute(
            "INSERT INTO settings (key, value, description) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            ("anthropic_balance_usd", val, "Manually entered Anthropic credit balance (USD)")
        )
        conn.commit()
        return {"saved": True, "balance_usd": body.balance_usd}
    finally:
        conn.close()
