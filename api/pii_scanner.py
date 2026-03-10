"""
PII Scanner Module - AI Usage Policy Compliance

Scans document content for Personally Identifiable Information (PII)
before it is sent to external AI services. Blocks requests containing
real customer data while allowing template variables to pass through.

Policy Reference: Newcourse Communications AI Usage Policy V1.0

Detection layers:
  1. Template-variable presence check (documents without {[TAG]} markers are suspect)
  2. SSN pattern matching
  3. Real mailing address detection
  4. Real person-name heuristics
  5. Bare dollar amounts (outside template Money() wrappers)
  6. Real email and phone detection
  7. Long digit-string (account / loan number) detection
"""
import re
from datetime import datetime, timezone

# ── Template Variable Patterns (SAFE) ──────────────────────────────────────

TEMPLATE_PATTERNS = [
    r'\{\[[\w\.]+\]\}',       # {[TAG]} or {[plsMatrix.Name]}
    r'\[\[[A-Z]\w+\]\]',      # [[TAG]]
    r'\{\{[A-Z]\w+\}\}',      # {{TAG}}
    r'\{Compress\(',           # {Compress(...)}
    r'\{Math\(',               # {Math(...)}
    r'\{Money\(',              # {Money(...)}
    r'\{If\(',                 # {If(...)}
    r'\{DateAdd\(',            # {DateAdd(...)}
    r'\{Date\(',               # {Date(...)}
    r'\{Insert\(',             # {Insert(...)}
    r'\{Header\(',             # {Header(...)}
    r'\{Number\(',             # {Number(...)}
    r'\{Else',                 # {Else} / {Else If(...)}
    r'\{End If\}',             # {End If}
    r'\[M\d{3}\w?\]',         # [M594], [M567E6]
    r'\[L\d{3}\]',            # [L001]
    r'\[H\d{3}\]',            # [H003]
    r'\[C\d{3}\]',            # [C001]
    r'\[T\d{3}\]',            # [T101]
    r'\[Q\d{3}\]',            # [Q189]
    r'\[U\d{3}\]',            # [U018]
    r'plsMatrix\.\w+',        # plsMatrix.CompanyLongName
    r'\[Salutation\]',        # [Salutation]
    r'\[mailingAddress\]',    # [mailingAddress]
    r'\[tagHeader\]',         # [tagHeader]
    # Legacy/alternate template variable formats used in some source documents
    r'#[A-Z]\d{3}\w{0,3}#',  # #M594#, #L001E8#, #U072#, #L003#
    r'<[A-Z][a-zA-Z]{2,}>',  # <CSPhoneNumber>, <CompanyLongName>, <SeeReverse>
]

COMPILED_TEMPLATE_PATTERNS = [re.compile(p) for p in TEMPLATE_PATTERNS]


def _strip_template_vars(text):
    """Remove all template variable tokens so we can scan the remaining text for real PII."""
    cleaned = text
    for pattern in COMPILED_TEMPLATE_PATTERNS:
        cleaned = pattern.sub('', cleaned)
    return cleaned


# ── PII Detection Patterns ────────────────────────────────────────────────

SSN_PATTERN = re.compile(
    r'(?<!\d)'
    r'(?:\d{3}[-\s]\d{2}[-\s]\d{4}'
    r'|\d{9})'
    r'(?!\d)'
)

ACCOUNT_NUMBER_PATTERN = re.compile(
    r'(?<!\d)\d{8,17}(?!\d)'
)

REAL_EMAIL_PATTERN = re.compile(
    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
)

# US mailing address: number + street name + optional suffix, followed by city/state/zip
US_ADDRESS_PATTERN = re.compile(
    r'\b\d{1,6}\s+'                                      # street number
    r'(?:[NSEW]\.?\s+)?'                                  # optional directional
    r'[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3}\s+'       # street name words
    r'(?:St|Street|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Ln|Lane|Rd|Road|Ct|Court|Way|Pl|Place|Cir|Circle|Pkwy|Parkway)\b',
    re.IGNORECASE
)

CITY_STATE_ZIP_PATTERN = re.compile(
    r'[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?,?\s+'               # city name
    r'(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)'
    r'\s+\d{5}(?:-\d{4})?',
    re.IGNORECASE
)

# Real dollar amounts (bare $1,234.56 NOT inside a Money()/Math() wrapper)
BARE_DOLLAR_PATTERN = re.compile(
    r'(?<!\{Money\()\$\s?\d[\d,]+\.\d{2}\b'
)

# Person name heuristic: "Dear John Smith," or "Mr./Mrs./Ms. Firstname Lastname"
SALUTATION_NAME_PATTERN = re.compile(
    r'Dear\s+(?!{|\[)[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+',
    re.MULTILINE
)

TITLE_NAME_PATTERN = re.compile(
    r'\b(?:Mr|Mrs|Ms|Miss|Dr|Prof)\.?\s+[A-Z][a-z]+\s+[A-Z][a-z]+',
)

# Date of birth: "DOB", "Date of Birth", "Birth Date" followed by a real date
DOB_PATTERN = re.compile(
    r'(?:DOB|Date\s+of\s+Birth|Birth\s*Date)\s*:?\s*'
    r'(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
    re.IGNORECASE
)

# Known-safe servicer emails / domains
SAFE_EMAIL_DOMAINS = {
    'commercebank.com',
    'example.com',
    'newcoursecc.com',
}


def _is_safe_email(email_str):
    domain = email_str.lower().split('@')[-1]
    return domain in SAFE_EMAIL_DOMAINS


# ── Scan Result Object ────────────────────────────────────────────────────

class PIIScanResult:
    def __init__(self):
        self.has_pii = False
        self.has_template_vars = False
        self.findings = []
        self.severity = 'CLEAR'   # CLEAR, WARNING, BLOCKED

    def add_finding(self, category, detail, severity='BLOCKED'):
        self.findings.append({
            'category': category,
            'detail': detail,
            'severity': severity,
        })
        if severity == 'BLOCKED':
            self.has_pii = True
            self.severity = 'BLOCKED'
        elif severity == 'WARNING' and self.severity != 'BLOCKED':
            self.severity = 'WARNING'

    def to_dict(self):
        return {
            'has_pii': self.has_pii,
            'has_template_vars': self.has_template_vars,
            'severity': self.severity,
            'findings': self.findings,
            'finding_count': len(self.findings),
        }


# ── Core Scanning ─────────────────────────────────────────────────────────

def scan_text_for_pii(text):
    """
    Scan a block of text for potential PII.

    Returns a PIIScanResult with findings.
    """
    result = PIIScanResult()

    if not text or not isinstance(text, str):
        return result

    for pattern in COMPILED_TEMPLATE_PATTERNS:
        if pattern.search(text):
            result.has_template_vars = True
            break

    cleaned = _strip_template_vars(text)

    # 1. SSN detection (always BLOCKED)
    ssn_matches = SSN_PATTERN.findall(cleaned)
    for m in ssn_matches:
        digits_only = re.sub(r'\D', '', m)
        if digits_only.startswith('000') or digits_only[3:5] == '00' or digits_only[5:] == '0000':
            continue
        result.add_finding('SSN', f'Possible Social Security Number detected: {m[:3]}-**-****')

    # 2. Date of birth (BLOCKED)
    if DOB_PATTERN.search(cleaned):
        result.add_finding('DOB', 'Date of birth pattern detected')

    # 3. Real mailing address detection (BLOCKED)
    if US_ADDRESS_PATTERN.search(cleaned) and CITY_STATE_ZIP_PATTERN.search(cleaned):
        result.add_finding(
            'ADDRESS',
            'Real US mailing address pattern detected (street + city/state/zip)',
            severity='BLOCKED'
        )
    elif CITY_STATE_ZIP_PATTERN.search(cleaned):
        result.add_finding(
            'ADDRESS',
            'City/State/ZIP pattern detected outside template variables',
            severity='WARNING'
        )

    # 4. Person name heuristics (BLOCKED — "Dear John Smith,")
    sal_match = SALUTATION_NAME_PATTERN.search(cleaned)
    if sal_match:
        result.add_finding(
            'PERSON_NAME',
            f'Real person name in salutation: "{sal_match.group()[:20]}..."',
            severity='BLOCKED'
        )
    title_match = TITLE_NAME_PATTERN.search(cleaned)
    if title_match:
        result.add_finding(
            'PERSON_NAME',
            f'Titled person name detected: "{title_match.group()[:20]}..."',
            severity='WARNING'
        )

    # 5. Bare dollar amounts not inside Money()/Math() (WARNING)
    bare_dollars = BARE_DOLLAR_PATTERN.findall(cleaned)
    if len(bare_dollars) >= 3:
        result.add_finding(
            'FINANCIAL_DATA',
            f'{len(bare_dollars)} bare dollar amounts detected outside template functions',
            severity='WARNING'
        )

    # 6. Real email detection
    email_matches = REAL_EMAIL_PATTERN.findall(cleaned)
    for email in email_matches:
        if not _is_safe_email(email):
            result.add_finding('EMAIL', f'Real email address detected: {email[:3]}***', severity='WARNING')

    # 7. Account number detection (long digit strings)
    acct_matches = ACCOUNT_NUMBER_PATTERN.findall(cleaned)
    for acct in acct_matches:
        digits = re.sub(r'\D', '', acct)
        if len(digits) >= 10:
            result.add_finding('ACCOUNT_NUMBER', f'Possible account/loan number ({len(digits)} digits)', severity='WARNING')

    return result


def scan_ir_for_pii(ir):
    """
    Scan an entire IR document structure for PII.
    """
    aggregate = PIIScanResult()

    if not ir or not isinstance(ir, dict):
        return aggregate

    blocks = ir.get('blocks', [])
    all_text_parts = []

    for block in blocks:
        if block.get('type') == 'paragraph':
            runs = block.get('runs', [])
            text = ''.join(r.get('text', '') for r in runs)
            if text.strip():
                all_text_parts.append(text)
        elif block.get('type') == 'table':
            for row in block.get('rows', []):
                for cell in row.get('cells', []):
                    for content_block in cell.get('content', []):
                        if content_block.get('type') == 'paragraph':
                            runs = content_block.get('runs', [])
                            text = ''.join(r.get('text', '') for r in runs)
                            if text.strip():
                                all_text_parts.append(text)
        elif block.get('type') == 'textbox':
            for row in block.get('rows', []):
                runs = row.get('runs', [])
                text = ''.join(r.get('text', '') for r in runs)
                if text.strip():
                    all_text_parts.append(text)

    meta = ir.get('meta', {})
    for tb in meta.get('textBoxes', []):
        for row in tb.get('rows', []):
            runs = row.get('runs', [])
            text = ''.join(r.get('text', '') for r in runs)
            if text.strip():
                all_text_parts.append(text)

    full_text = '\n'.join(all_text_parts)

    block_result = scan_text_for_pii(full_text)

    aggregate.has_template_vars = block_result.has_template_vars
    aggregate.has_pii = block_result.has_pii
    aggregate.severity = block_result.severity
    aggregate.findings = block_result.findings

    if not aggregate.has_template_vars and len(full_text) > 200:
        aggregate.add_finding(
            'NO_TEMPLATE_VARS',
            'Document contains no template variables ({[TAG]} format). '
            'This may be a populated/merged document with real customer data. '
            'Only template documents should be processed.',
            severity='BLOCKED'
        )

    return aggregate


# ── Error Response Builder ────────────────────────────────────────────────

def build_error_response(scan_result):
    """Build a user-friendly error message from a PII scan result."""
    if not scan_result.has_pii and scan_result.severity != 'BLOCKED':
        return None

    findings_summary = []
    for f in scan_result.findings:
        findings_summary.append(f"- [{f['category']}] {f['detail']}")

    msg = (
        "DOCUMENT BLOCKED — PII Policy Violation Detected\n\n"
        "This document appears to contain real customer data and cannot be "
        "sent to the AI service per the Newcourse Communications AI Usage Policy.\n\n"
        "Findings:\n" + '\n'.join(findings_summary) + "\n\n"
        "Please ensure you are uploading a TEMPLATE document (containing "
        "variables like {[M594]}, {[Salutation]}, etc.) rather than a "
        "populated/merged letter with real customer information.\n\n"
        "If you believe this is a false positive, contact your manager or the CPTO."
    )
    return msg


# ── Audit Logger ──────────────────────────────────────────────────────────

def log_audit_event(event_type, file_name=None, scan_result=None, detail=None):
    """
    Write a structured audit line to stdout (captured by Vercel's log drain).

    Format: [AUDIT] <ISO timestamp> | <event> | file=<name> | severity=<sev> | findings=<n> | detail=<msg>
    """
    ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    sev = scan_result.severity if scan_result else 'N/A'
    count = scan_result.to_dict()['finding_count'] if scan_result else 0
    safe_name = (file_name or 'unknown').replace('|', '_')
    safe_detail = (detail or '').replace('|', '_')[:200]
    print(
        f"[AUDIT] {ts} | {event_type} | file={safe_name} "
        f"| severity={sev} | findings={count} | detail={safe_detail}"
    )
