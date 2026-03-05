"""
PII Scanner Module - AI Usage Policy Compliance

Scans document content for Personally Identifiable Information (PII)
before it is sent to external AI services. Blocks requests containing
real customer data while allowing template variables to pass through.

Policy Reference: Newcourse Communications AI Usage Policy V1.0
"""
import re

# Template variable patterns that are SAFE (not real data)
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
    r'(?:\d{3}[-\s]\d{2}[-\s]\d{4}'  # 123-45-6789 or 123 45 6789
    r'|\d{9})'                        # 123456789
    r'(?!\d)'
)

ACCOUNT_NUMBER_PATTERN = re.compile(
    r'(?<!\d)\d{8,17}(?!\d)'
)

REAL_PHONE_PATTERN = re.compile(
    r'(?<!\d)'
    r'(?:\+?1[-.\s]?)?'
    r'(?:\(?\d{3}\)?[-.\s]?)'
    r'\d{3}[-.\s]?\d{4}'
    r'(?!\d)'
)

REAL_EMAIL_PATTERN = re.compile(
    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'
)

# Known safe servicer emails / phones that appear in templates
SAFE_EMAILS = {
    'mortgagedefault@commercebank.com',
    'example@example.com',
}

SAFE_PHONE_PREFIXES = [
    '1-800-', '1-888-', '1-877-', '1-866-', '1-855-', '1-844-',
    '800-', '888-', '877-', '866-', '855-', '844-',
]

DATE_PATTERN = re.compile(
    r'(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'
    r'|(?:(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})'
)

DOLLAR_AMOUNT_PATTERN = re.compile(
    r'\$\s?\d[\d,]*\.?\d{0,2}'
)


def _is_safe_phone(phone_str):
    normalized = re.sub(r'[\s.()\-]', '', phone_str)
    if normalized.startswith('1'):
        normalized = normalized[1:]
    if normalized.startswith('8') and len(normalized) == 10:
        return True
    return False


def _is_safe_email(email_str):
    return email_str.lower() in SAFE_EMAILS


# ── Main Scanning Function ────────────────────────────────────────────────

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


def scan_text_for_pii(text):
    """
    Scan a block of text for potential PII.

    Returns a PIIScanResult with findings. If has_pii is True, the text
    should NOT be sent to an external AI service.
    """
    result = PIIScanResult()

    if not text or not isinstance(text, str):
        return result

    for pattern in COMPILED_TEMPLATE_PATTERNS:
        if pattern.search(text):
            result.has_template_vars = True
            break

    cleaned = _strip_template_vars(text)

    # SSN detection
    ssn_matches = SSN_PATTERN.findall(cleaned)
    for m in ssn_matches:
        digits_only = re.sub(r'\D', '', m)
        if digits_only.startswith('000') or digits_only[3:5] == '00' or digits_only[5:] == '0000':
            continue
        result.add_finding('SSN', f'Possible Social Security Number detected: {m[:3]}-**-****')

    # Real email detection (not template variable, not safe list)
    email_matches = REAL_EMAIL_PATTERN.findall(cleaned)
    for email in email_matches:
        if not _is_safe_email(email):
            result.add_finding('EMAIL', f'Real email address detected: {email[:3]}***', severity='WARNING')

    # Account number detection: long digit strings not near template context
    acct_matches = ACCOUNT_NUMBER_PATTERN.findall(cleaned)
    for acct in acct_matches:
        digits = re.sub(r'\D', '', acct)
        if len(digits) >= 10:
            result.add_finding('ACCOUNT_NUMBER', f'Possible account/loan number ({len(digits)} digits)', severity='WARNING')

    return result


def scan_ir_for_pii(ir):
    """
    Scan an entire IR document structure for PII.

    Returns a PIIScanResult aggregating all findings across all blocks.
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

    # Also scan text boxes in meta
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

    # If NO template variables were found AND the document has substantial text,
    # this is likely a populated/merged document, not a template.
    if not aggregate.has_template_vars and len(full_text) > 200:
        aggregate.add_finding(
            'NO_TEMPLATE_VARS',
            'Document contains no template variables ({[TAG]} format). '
            'This may be a populated/merged document with real customer data. '
            'Only template documents should be processed.',
            severity='BLOCKED'
        )

    return aggregate


def build_error_response(scan_result):
    """Build a user-friendly error message from a PII scan result."""
    if not scan_result.has_pii and scan_result.severity != 'BLOCKED':
        return None

    findings_summary = []
    for f in scan_result.findings:
        findings_summary.append(f"- [{f['category']}] {f['detail']}")

    msg = (
        "DOCUMENT BLOCKED - PII Policy Violation Detected\n\n"
        "This document appears to contain real customer data and cannot be "
        "sent to the AI service per the Newcourse Communications AI Usage Policy.\n\n"
        "Findings:\n" + '\n'.join(findings_summary) + "\n\n"
        "Please ensure you are uploading a TEMPLATE document (containing "
        "variables like {[M594]}, {[Salutation]}, etc.) rather than a "
        "populated/merged letter with real customer information.\n\n"
        "If you believe this is a false positive, contact your manager or the CPTO."
    )
    return msg
