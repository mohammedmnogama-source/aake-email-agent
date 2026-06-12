from contextlib import contextmanager
from typing import Generator

from imap_tools import MailBox

from backend.config import settings


@contextmanager
def get_mailbox() -> Generator[MailBox, None, None]:
    """Open an authenticated IMAP connection. Always closes on exit."""
    mb = MailBox(settings.imap_host, port=settings.imap_port)
    try:
        mb.login(settings.email_address, settings.email_password)
        yield mb
    finally:
        try:
            mb.logout()
        except Exception:
            pass
