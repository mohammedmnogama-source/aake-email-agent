from pydantic import BaseModel


class EmailAddress(BaseModel):
    email: str
    name: str = ""


class RawEmail(BaseModel):
    imap_uid: int
    folder_path: str
    subject: str
    from_address: str
    from_name: str
    to_addresses: list[EmailAddress]
    cc_addresses: list[EmailAddress]
    body_text: str
    body_preview: str
    received_at: str          # ISO 8601
    has_attachments: bool
