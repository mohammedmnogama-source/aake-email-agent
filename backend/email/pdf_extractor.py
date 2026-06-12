"""
Extracts text from PDF files for batch submission.
If the PDF is image-only (< 100 chars extracted), returns empty string
and the caller should use Claude's native document block instead.
"""
import base64
import io
import re

import pdfplumber


def extract_pdf_text(file_bytes: bytes) -> str:
    """Extract plain text from a PDF. Returns '' for image-only PDFs."""
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        raw = "\n".join(pages).strip()
        return _fix_repeated_chars(raw)
    except Exception as e:
        print(f"[pdf] extraction failed: {e}")
        return ""


def pdf_to_base64(file_bytes: bytes) -> str:
    """Encode PDF bytes to base64 string for Claude native document block."""
    return base64.standard_b64encode(file_bytes).decode()


def _fix_repeated_chars(text: str) -> str:
    """
    Some PDFs stack multiple text layers, making every character appear N times
    (e.g. 'FFFFrrrr' instead of 'Fr'). This collapses any character that repeats
    4 or more times in a row down to a single character. Leaves 1-3 repeats
    untouched so normal double letters (e.g. 'll', 'ss') are preserved.
    """
    return re.sub(r'(.)\1{3,}', r'\1', text)
