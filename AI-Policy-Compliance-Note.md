# AI Usage Policy — Letter Template Formatter Compliance Note

**Author:** Josh H. (Programmer, Newcourse Communications)
**Date:** March 2026
**Re:** AI Usage Policy V1.0 compliance for the Letter Template Formatter
**Status:** Compliant — see details below

---

## Background

The Letter Template Formatter mentioned in the Efficiency Initiatives Proposal uses AI (Anthropic Claude) to convert Word/PDF template documents into production-ready HTML. Before adopting AI, I first attempted a rule-based approach using regex find-and-replace to handle the conversion programmatically without any external AI service. That approach couldn't reliably handle the variety of template structures, conditional logic, and formatting nuances across our document library, which led to the current AI-assisted approach.

---

## What the Tool Processes

The tool processes **template documents only** — files containing placeholder variables like `{[M594]}`, `{[Salutation]}`, `{Compress(...)}`. These are the same templates we work with daily in NcConnect. They contain no customer names, no real loan numbers, no real addresses, and no financial data. Real customer data is merged at print time by the production system, never by this tool.

## What Gets Sent to the AI Service

| Sent to Anthropic Claude | Contains Real Customer Data? |
|---|---|
| Template text with placeholder variables (`{[M594]}`, `{[Salutation]}`) | No |
| Formatting metadata (bold, font size, alignment) | No |
| Formatting rules and examples (our HTML style guide) | No |
| Template variable naming conventions and helper functions | No |

**Nothing containing customer PII, financial data, or account-specific information is sent.**

---

## Safeguards In Place (Live)

All of the following are implemented and deployed at https://ncformatter.vercel.app/ today:

**Three-Layer PII Blocking** — automated scanning at every stage before data can reach the AI:

1. **Client-side (browser)** — scans the extracted document content before any API call is made
2. **Document extraction endpoint** — scans immediately after Word parsing, before the extracted content is even returned to the browser
3. **AI generation endpoint** — final gate, scans again before anything is sent to Claude

**What the scanner detects and blocks:**
- Documents with **no template variables** (likely a populated/merged letter, not a template)
- Social Security Number patterns
- Real US mailing addresses (street + city/state/ZIP)
- Real person names in salutations (e.g., "Dear John Smith" instead of "Dear {[Salutation]}")
- Date of birth patterns
- Real email addresses (outside known servicer domains)
- Long digit strings (possible account/loan numbers)
- Clusters of bare dollar amounts outside template `Money()` functions

**Additional safeguards:**
- **Audit logging** — every document processed or blocked is logged with timestamp, event type, filename, severity, and finding count (captured in Vercel's log infrastructure)
- **Policy notice banner** — displayed prominently in the app header before the upload area
- **Distinct error display** — blocked documents show a red-bordered explanation with specific findings and policy reference
- **API key hygiene** — no credentials are logged, even partially, in server output

---

## Compliance Against the Policy

| Policy Requirement | Status |
|---|---|
| No Customer PII sent to AI | **Compliant** — templates contain placeholders, not real data; PII scanner blocks real data |
| No Sensitive Financial Data | **Compliant** — financial fields are template variables, not real amounts |
| No Proprietary/Confidential Information | **Compliant** — formatting rules are sent, not client contracts or pricing |
| No Direct Customer-Facing Content without review | **Compliant** — programmer reviews all output before use |
| No Sensitive Code or Security Information | **Compliant** — no passwords, keys, or architecture details sent to AI |
| Permitted: Document drafting with templates | **Exact match** for this use case |
| Permitted: Code development with sample/generic data | **Exact match** for this use case |
| Best Practice: Review all AI outputs | **Compliant** — human-in-the-loop at every step |

---

## Action Item: API Account Migration

The Anthropic API key currently in use is on my **personal account**. Per the policy: *"Personal AI tool accounts should not be used for work-related tasks with company data."*

**Recommended action:** Set up a company-managed Anthropic account and migrate the API key. This is a straightforward configuration change (swap one environment variable in Vercel). No code changes required.

---

## Optional Further Steps

These are not required for compliance but would strengthen the posture:

| Action | Effort | Benefit |
|---|---|---|
| Migrate to company-managed Anthropic account | Low (env var swap) | Resolves the one open compliance gap |
| Establish enterprise DPA with Anthropic | Low (legal/procurement) | Contractual data protection guarantees |
| Add user authentication to the tool | Medium | Ties usage to specific employees for accountability |
| Persist audit logs to permanent storage | Low | Long-term compliance evidence beyond Vercel's retention |
| Add "Reviewed" checkbox before Copy HTML is enabled | Low | Formalizes the human review step |

---

*This note accompanies the Programmer Efficiency & Profitability Initiatives proposal and addresses compliance with the Newcourse Communications AI Usage Policy V1.0 (01/05/2026).*
