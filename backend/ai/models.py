from enum import Enum
from typing import Literal

from pydantic import BaseModel


class EmailCategory(str, Enum):
    lead = "lead"
    vendor_quote_request = "vendor_quote_request"
    customer_inquiry = "customer_inquiry"
    internal = "internal"
    spam = "spam"
    other = "other"


class SuggestedAction(str, Enum):
    draft_reply = "draft_reply"
    forward_to_vendor = "forward_to_vendor"
    extract_lead_info = "extract_lead_info"
    summarize_only = "summarize_only"
    ignore = "ignore"
    create_rfq = "create_rfq"
    no_action = "no_action"


class ExtractedData(BaseModel):
    name: str | None = None
    company: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    request_summary: str | None = None


class SuggestedRecipient(BaseModel):
    vendor_id: int | None = None
    name: str
    email: str
    why: str


class TaskItem(BaseModel):
    type: str                       # create_rfq | draft_reply | forward_to_vendor | ...
    description: str
    payload: dict = {}
    sequence_order: int = 0
    depends_on: int | None = None   # 0-based index into tasks list


class GeminiResponse(BaseModel):
    category: EmailCategory | None = None
    suggested_action: SuggestedAction | None = None
    reasoning: str = ""
    summary: str | None = None      # 2-3 sentence plain-English summary
    tasks: list[TaskItem] = []      # checklist of tasks (new model)
    draft_subject: str | None = None
    draft_to: str | None = None
    draft_content: str | None = None
    extracted_data: ExtractedData | None = None
    suggested_vendor_id: int | None = None
    confidence_note: str | None = None
    # Clarification fields
    needs_clarification: bool = False
    clarification_type: Literal["action", "recipient"] | None = None
    clarification_question: str | None = None
    clarification_options: list[str] | None = None
    suggested_recipients: list[SuggestedRecipient] | None = None
