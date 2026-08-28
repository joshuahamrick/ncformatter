#!/usr/bin/env python3
"""Regression checks for api/pii_scanner.py template detection.

Run: python test_pii_scanner.py
"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent / "api"))

import pii_scanner


FAILURES = []


def check(name, condition, detail=''):
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        FAILURES.append(name)


# A real-world template using descriptive bracket placeholders (LM093 style).
DESCRIPTIVE_TEMPLATE = """
[LetterDate]
[BorrowerName]
[MailAddr1]
[MailCity], [State] [Zip]
Loan #: [LoanNumber]
Dear [Borrower(s)],
If you accept this Trial Period Plan, you will be required to make three monthly
payments in the amount of $[TrialPymtAmt1] by [TrialOfferExp].
Please contact us at [SPOC/Loss Mit Phone].
Sincerely,
[Company Long Name]
"""

# A template using the coded formats the scanner already understood.
CODED_TEMPLATE = """
{[M594]}
Dear {[Salutation]},
Your loan {[M567]} is due on {Date(M100)} for {Money(M200)}.
"""

# A populated/merged letter with real customer data and no placeholders.
MERGED_LETTER = """
March 3, 2026
Jonathan Whitfield
482 Maple Grove Drive
Tulsa, OK 74133
Dear Jonathan Whitfield,
Your loan is past due. SSN: 412-88-9310.
Please remit payment to our office.
""" + ("Additional boilerplate paragraph text to exceed the length gate. " * 6)

# A merged letter that happens to contain a few bracketed editorial notes.
MERGED_WITH_STRAY_BRACKETS = """
March 3, 2026
Jonathan Whitfield
482 Maple Grove Drive
Tulsa, OK 74133
Dear Jonathan Whitfield,
[sic] The amount [see enclosed] is past due as of [note].
""" + ("Additional boilerplate paragraph text to exceed the length gate. " * 6)

# Disclosure template: public regulator/agency office addresses are NOT customer PII.
# Mirrors First United Bank Trust Disclosures V18 (FTC ECOA + state banking/AG units).
DISCLOSURE_TEMPLATE = """
Important Disclosures
Federal law requires us to advise you that {[CompanyLongName]} (NMLS ID {[NMLID]})
as the servicer of your loan, is responsible for collecting your payments.
Equal Credit Opportunity Act:
The Equal Credit Opportunity Act prohibits creditors from discriminating against
credit applicants. Send comments to:
Federal Trade Commission
Equal Credit Opportunity
600 Pennsylvania Avenue, NW
Washington, DC 20580
1-877-FTC-HELP
Hawaii Property Owners - {[CompanyLongName]} is licensed by the Division of Financial
Institutions. A borrower may file a complaint about {[CompanyLongName]} with the
Commissioner using the following address: Division of Financial Institutions
Department of Commerce and Consumer Affairs King Kalakaua Building 335 Merchant
Street, Rm. 221, Honolulu, HI 96813
West Virginia Property Owners - The activities of collection agencies in West
Virginia are regulated by the Attorney General's Consumer Protection Division,
812 Quarrier Street, Charleston, WV 25301.
Montana Property Owners - A borrower may file a complaint about {[CompanyLongName]}
with the Department: Division of Banking and Financial Institutions, 301 South
Park, Suite 316, PO Box 200546, Helena, MT 59620 Phone: (406) 841-2920
"""

# Template that also contains a real customer mailing address — still blocked.
TEMPLATE_WITH_CUSTOMER_ADDRESS = """
{[L001]}
Dear {[Salutation]},
Please mail correspondence to the borrower at:
482 Maple Grove Drive
Tulsa, OK 74133
Sincerely,
{[plsMatrix.CompanyLongName]}
"""


print("Descriptive-placeholder template (LM093 style):")
r = pii_scanner.scan_text_for_pii(DESCRIPTIVE_TEMPLATE)
check("recognised as a template", r.has_template_vars)
check("not flagged as PII", not r.has_pii, r.findings)

print("Coded-placeholder template still recognised:")
r = pii_scanner.scan_text_for_pii(CODED_TEMPLATE)
check("recognised as a template", r.has_template_vars)
check("not flagged as PII", not r.has_pii, r.findings)

print("Merged letter with real customer data:")
r = pii_scanner.scan_text_for_pii(MERGED_LETTER)
check("not recognised as a template", not r.has_template_vars)
check("blocked", r.severity == 'BLOCKED', r.findings)
check("SSN detected", any(f['category'] == 'SSN' for f in r.findings), r.findings)
check("real name detected", any(f['category'] == 'PERSON_NAME' for f in r.findings), r.findings)

print("Merged letter with stray bracketed words:")
r = pii_scanner.scan_text_for_pii(MERGED_WITH_STRAY_BRACKETS)
check("not recognised as a template", not r.has_template_vars)
check("blocked", r.severity == 'BLOCKED', r.findings)

print("Disclosure template with agency office addresses:")
r = pii_scanner.scan_text_for_pii(DISCLOSURE_TEMPLATE)
check("recognised as a template", r.has_template_vars)
check("not blocked", r.severity != 'BLOCKED', r.findings)
check("no ADDRESS block", not any(f['category'] == 'ADDRESS' and f['severity'] == 'BLOCKED' for f in r.findings), r.findings)

print("Template that also contains a customer mailing address:")
r = pii_scanner.scan_text_for_pii(TEMPLATE_WITH_CUSTOMER_ADDRESS)
check("recognised as a template", r.has_template_vars)
check("blocked on ADDRESS", r.severity == 'BLOCKED', r.findings)
check("ADDRESS finding", any(f['category'] == 'ADDRESS' for f in r.findings), r.findings)

print("IR-level gate:")
ir = {'blocks': [{'type': 'paragraph', 'runs': [{'text': line}]}
                 for line in DESCRIPTIVE_TEMPLATE.strip().split('\n')]}
r = pii_scanner.scan_ir_for_pii(ir)
check("descriptive template passes the IR gate", r.severity == 'CLEAR', r.findings)

ir = {'blocks': [{'type': 'paragraph', 'runs': [{'text': line}]}
                 for line in DISCLOSURE_TEMPLATE.strip().split('\n')]}
r = pii_scanner.scan_ir_for_pii(ir)
check("disclosure template passes the IR gate", r.severity != 'BLOCKED', r.findings)

ir = {'blocks': [{'type': 'paragraph', 'runs': [{'text': line}]}
                 for line in MERGED_LETTER.strip().split('\n')]}
r = pii_scanner.scan_ir_for_pii(ir)
check("merged letter blocked at the IR gate", r.severity == 'BLOCKED', r.findings)

print()
if FAILURES:
    print(f"{len(FAILURES)} check(s) failed: {FAILURES}")
    sys.exit(1)
print("All checks passed.")
