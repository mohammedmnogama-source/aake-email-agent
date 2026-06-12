from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from backend.database.connection import get_connection
from backend.database.repositories import deals as repo
from backend.ai import deal_ai
from backend.middleware.auth import require_auth

router = APIRouter(prefix="/api/deals", tags=["deals"], dependencies=[Depends(require_auth)])


# ---------------------------------------------------------------------------
# Request body schemas
# ---------------------------------------------------------------------------

class CreateDealBody(BaseModel):
    customer_name: str
    customer_email: str | None = None
    description: str | None = None
    source_type: str = "manual"
    source_raw_text: str | None = None
    customer_id: int | None = None


class UpdateDealBody(BaseModel):
    status: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    description: str | None = None


class ItemBody(BaseModel):
    product_name: str
    qty: int | None = None
    specs: str | None = None
    notes: str | None = None


class SupplierRequestBody(BaseModel):
    vendor_name: str
    vendor_email: str | None = None
    vendor_id: int | None = None


class UpdateSupplierRequestBody(BaseModel):
    status: str | None = None
    vendor_email: str | None = None
    sent_at: str | None = None


class SupplierQuoteBody(BaseModel):
    vendor_name: str | None = None
    supplier_request_id: int | None = None
    total_amount: float | None = None
    currency: str = "KWD"
    valid_until: str | None = None
    notes: str | None = None
    raw_email_text: str | None = None


class UpdateSupplierQuoteBody(BaseModel):
    status: str | None = None
    total_amount: float | None = None
    currency: str | None = None
    valid_until: str | None = None
    notes: str | None = None


class CustomerQuoteBody(BaseModel):
    total_amount: float | None = None
    currency: str = "KWD"
    valid_until: str | None = None
    notes: str | None = None


class UpdateCustomerQuoteBody(BaseModel):
    status: str | None = None
    total_amount: float | None = None
    currency: str | None = None
    valid_until: str | None = None
    notes: str | None = None
    sent_at: str | None = None


class CustomerPOBody(BaseModel):
    customer_quote_id: int | None = None
    customer_po_number: str | None = None
    amount: float | None = None
    currency: str = "KWD"
    received_at: str | None = None
    notes: str | None = None


class SupplierPOBody(BaseModel):
    supplier_request_id: int | None = None
    supplier_quote_id: int | None = None
    vendor_name: str | None = None
    vendor_email: str | None = None
    aake_po_number: str | None = None
    amount: float | None = None
    currency: str = "KWD"
    issued_at: str | None = None
    notes: str | None = None


class ExtractEmailBody(BaseModel):
    email_text: str


# ---------------------------------------------------------------------------
# Deal endpoints
# ---------------------------------------------------------------------------

@router.get("")
def list_deals():
    conn = get_connection()
    try:
        rows = repo.list_deals(conn)
    finally:
        conn.close()
    return [dict(r) for r in rows]


@router.post("", status_code=201)
def create_deal(body: CreateDealBody):
    conn = get_connection()
    try:
        deal_id = repo.create_deal(
            conn,
            customer_name=body.customer_name,
            customer_email=body.customer_email,
            description=body.description,
            source_type=body.source_type,
            source_raw_text=body.source_raw_text,
            customer_id=body.customer_id,
        )
        return repo.get_deal_full(conn, deal_id)
    finally:
        conn.close()


@router.post("/extract-email")
def extract_email(body: ExtractEmailBody):
    """Stateless: parse a pasted email and return extracted deal fields. No DB writes."""
    if not body.email_text.strip():
        raise HTTPException(400, "email_text is required")
    result = deal_ai.extract_deal_from_email(body.email_text)
    return result


@router.post("/extract-email-pdf")
async def extract_email_pdf(file: UploadFile = File(...)):
    """Stateless: upload a PDF email and return extracted deal fields. No DB writes."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted")
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(400, "Uploaded file is empty")
    result = deal_ai.extract_deal_from_pdf(pdf_bytes)
    return result


@router.get("/{deal_id}")
def get_deal(deal_id: int):
    conn = get_connection()
    try:
        result = repo.get_deal_full(conn, deal_id)
    finally:
        conn.close()
    if not result:
        raise HTTPException(404, "Deal not found")
    return result


@router.put("/{deal_id}")
def update_deal(deal_id: int, body: UpdateDealBody):
    conn = get_connection()
    try:
        if not repo.get_deal(conn, deal_id):
            raise HTTPException(404, "Deal not found")
        repo.update_deal(conn, deal_id, body.model_dump(exclude_none=True))
        return repo.get_deal_full(conn, deal_id)
    finally:
        conn.close()


@router.delete("/{deal_id}", status_code=204)
def delete_deal(deal_id: int):
    conn = get_connection()
    try:
        if not repo.get_deal(conn, deal_id):
            raise HTTPException(404, "Deal not found")
        repo.delete_deal(conn, deal_id)
    finally:
        conn.close()


@router.get("/{deal_id}/next-step")
def get_next_step(deal_id: int):
    """Ask AI for the next action on this deal, save result, and return it."""
    conn = get_connection()
    try:
        full = repo.get_deal_full(conn, deal_id)
        if not full:
            raise HTTPException(404, "Deal not found")
        suggestion = deal_ai.suggest_next_step(
            deal=full["deal"],
            items=full["items"],
            supplier_requests=full["supplier_requests"],
            supplier_quotes=full["supplier_quotes"],
            customer_quotes=full["customer_quotes"],
        )
        repo.update_deal(conn, deal_id, {"ai_next_step": suggestion})
        return {"next_step": suggestion}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Line items
# ---------------------------------------------------------------------------

@router.post("/{deal_id}/items", status_code=201)
def add_item(deal_id: int, body: ItemBody):
    conn = get_connection()
    try:
        if not repo.get_deal(conn, deal_id):
            raise HTTPException(404, "Deal not found")
        item_id = repo.add_item(conn, deal_id, body.product_name, body.qty, body.specs, body.notes)
        return {"id": item_id}
    finally:
        conn.close()


@router.put("/{deal_id}/items/{item_id}")
def update_item(deal_id: int, item_id: int, body: ItemBody):
    conn = get_connection()
    try:
        repo.update_item(conn, item_id, body.model_dump(exclude_none=True))
        return {"ok": True}
    finally:
        conn.close()


@router.delete("/{deal_id}/items/{item_id}", status_code=204)
def delete_item(deal_id: int, item_id: int):
    conn = get_connection()
    try:
        repo.delete_item(conn, item_id)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Supplier requests
# ---------------------------------------------------------------------------

@router.post("/{deal_id}/supplier-requests", status_code=201)
def create_supplier_request(deal_id: int, body: SupplierRequestBody):
    conn = get_connection()
    try:
        full = repo.get_deal_full(conn, deal_id)
        if not full:
            raise HTTPException(404, "Deal not found")
        # Generate AI email draft for Mo to copy-paste
        email_draft = deal_ai.draft_supplier_request_email(
            deal=full["deal"],
            items=full["items"],
            vendor_name=body.vendor_name,
            conn=conn,
        )
        sr_id = repo.create_supplier_request(
            conn, deal_id,
            vendor_name=body.vendor_name,
            vendor_email=body.vendor_email,
            vendor_id=body.vendor_id,
            email_draft_text=email_draft or None,
        )
        return {"id": sr_id, "email_draft_text": email_draft}
    finally:
        conn.close()


@router.put("/{deal_id}/supplier-requests/{sr_id}")
def update_supplier_request(deal_id: int, sr_id: int, body: UpdateSupplierRequestBody):
    conn = get_connection()
    try:
        repo.update_supplier_request(conn, sr_id, body.model_dump(exclude_none=True))
        return {"ok": True}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Supplier quotes
# ---------------------------------------------------------------------------

@router.post("/{deal_id}/supplier-quotes", status_code=201)
def create_supplier_quote(deal_id: int, body: SupplierQuoteBody):
    conn = get_connection()
    try:
        if not repo.get_deal(conn, deal_id):
            raise HTTPException(404, "Deal not found")
        sq_id = repo.create_supplier_quote(
            conn, deal_id,
            vendor_name=body.vendor_name,
            supplier_request_id=body.supplier_request_id,
            total_amount=body.total_amount,
            currency=body.currency,
            valid_until=body.valid_until,
            notes=body.notes,
            raw_email_text=body.raw_email_text,
        )
        return {"id": sq_id}
    finally:
        conn.close()


@router.put("/{deal_id}/supplier-quotes/{sq_id}")
def update_supplier_quote(deal_id: int, sq_id: int, body: UpdateSupplierQuoteBody):
    conn = get_connection()
    try:
        repo.update_supplier_quote(conn, sq_id, body.model_dump(exclude_none=True))
        return {"ok": True}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Customer quotes
# ---------------------------------------------------------------------------

@router.post("/{deal_id}/customer-quotes", status_code=201)
def create_customer_quote(deal_id: int, body: CustomerQuoteBody):
    conn = get_connection()
    try:
        full = repo.get_deal_full(conn, deal_id)
        if not full:
            raise HTTPException(404, "Deal not found")
        # Generate AI cover email draft — no prices, those go in the PDF attachment
        try:
            email_draft = deal_ai.draft_customer_quote_email(
                deal=full["deal"],
                items=full["items"],
                conn=conn,
            )
        except Exception:
            email_draft = None  # quote always saved even if AI fails
        cq_id = repo.create_customer_quote(
            conn, deal_id,
            total_amount=body.total_amount,
            currency=body.currency,
            valid_until=body.valid_until,
            notes=body.notes,
            email_draft_text=email_draft or None,
        )
        return {"id": cq_id, "email_draft_text": email_draft}
    finally:
        conn.close()


@router.put("/{deal_id}/customer-quotes/{cq_id}")
def update_customer_quote(deal_id: int, cq_id: int, body: UpdateCustomerQuoteBody):
    conn = get_connection()
    try:
        repo.update_customer_quote(conn, cq_id, body.model_dump(exclude_none=True))
        return {"ok": True}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Purchase orders
# ---------------------------------------------------------------------------

@router.post("/{deal_id}/customer-po", status_code=201)
def record_customer_po(deal_id: int, body: CustomerPOBody):
    conn = get_connection()
    try:
        if not repo.get_deal(conn, deal_id):
            raise HTTPException(404, "Deal not found")
        po_id = repo.create_customer_po(
            conn, deal_id,
            customer_quote_id=body.customer_quote_id,
            customer_po_number=body.customer_po_number,
            amount=body.amount,
            currency=body.currency,
            received_at=body.received_at,
            notes=body.notes,
        )
        # Auto-advance deal to won when customer PO received
        repo.update_deal(conn, deal_id, {"status": "won"})
        return {"id": po_id}
    finally:
        conn.close()


@router.post("/{deal_id}/supplier-po", status_code=201)
def record_supplier_po(deal_id: int, body: SupplierPOBody):
    conn = get_connection()
    try:
        if not repo.get_deal(conn, deal_id):
            raise HTTPException(404, "Deal not found")
        po_id = repo.create_supplier_po(
            conn, deal_id,
            supplier_request_id=body.supplier_request_id,
            supplier_quote_id=body.supplier_quote_id,
            vendor_name=body.vendor_name,
            vendor_email=body.vendor_email,
            aake_po_number=body.aake_po_number,
            amount=body.amount,
            currency=body.currency,
            issued_at=body.issued_at,
            notes=body.notes,
        )
        # Auto-advance deal to fulfilled when supplier PO issued
        repo.update_deal(conn, deal_id, {"status": "fulfilled"})
        return {"id": po_id}
    finally:
        conn.close()
