import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.ai.redactor import redact

cases = [
    ("My civil ID is 287123456789 please verify",        True),
    ("Send to KW81CBKU0000000000001234560101",            True),
    ("Card: 4532-1234-5678-9012",                        True),
    ("password: mySecretPass123",                        True),
    ("API key: sk-ant-1234567890abcdefghij",             True),
    ("Order #4532 has 12 units, ID: AAKE-2025-001",      False),
    ("4532-1234-5678-9012",                              True),
    ("4532 1234 5678 9012",                              True),
    ("4532123456789012",                                 True),
    ("Item 4532, qty 1234, ref 5678 invoice 9012",       False),
    ("AMEX 3782 822463 10005",                           True),
    ("Phone: 9876-5432",                                 False),
]

all_pass = True
for i, (text, should_redact) in enumerate(cases, 1):
    result, count = redact(text)
    did_redact = count > 0
    passed = did_redact == should_redact
    if not passed:
        all_pass = False
    mark = "PASS" if passed else "FAIL"
    expect = "redact" if should_redact else "keep"
    print(f"[{mark}] #{i:02d} (expect={expect})")
    print(f"       IN : {text}")
    print(f"       OUT: {result}  [{count} redaction(s)]")
    print()

print("All tests passed." if all_pass else "FAILURES detected above.")
