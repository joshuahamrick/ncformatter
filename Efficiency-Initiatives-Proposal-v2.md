# Programmer Efficiency & Profitability Initiatives

Author: Josh H. (Programmer, New Course Communications)

Date: February 2026

---

## THE GOAL

### Automate the pipeline from CRF creation to "Samples Under Review."

### Programmers review and approve work — instead of building it by hand.

### Every initiative in this document is a building block toward that objective.

---

## Executive Summary

I propose a focused set of improvements that translate directly into higher throughput, faster turnaround, and improved profitability:

- Automating letter template formatting and related workflow steps
- Hiring a dedicated in-house QC team to handle paper QCs
- Systematically removing friction in NcConnect and adjacent processes

These foundational pieces enable a much larger win: **full end-to-end automation of the CRF-to-samples pipeline**. This includes the conversion and creation work currently housed in our legacy system — work that has been considered un-automatable. The letter template formatter I've built is the key piece that changes that. If we drop a CRF's attached Word template into the formatter, the conversion step becomes automated. The programmer becomes a reviewer, not a builder.

This plan prioritizes quick wins that compound, followed by structural fixes that enable complete workflow automation.

---

## Phase 1: Foundational Automation

**These initiatives deliver immediate impact and enable the ultimate automation pipeline.** Each piece below is a building block that makes the end-to-end automation possible.

### 1) Letter Template Formatter & Automation Suite (highest ROI)

- **What**: A drag-and-drop app that ingests a Word/PDF template and outputs production-ready HTML aligned to our standards, including PLS Matrix tagging and helper functions like `Money()`, `Math()`, and `Compress()`.
- **Status**: Concept and prior prototype exist; currently undergoing second iteration. I can provide a short demo link and a simple test document.
- **Impact**: Cuts manual letter build time dramatically for the creation/formatting portion and reduces rework by standardizing output.
- **Why now**: This replaces a large block of repetitive, error-prone effort with deterministic, standardized output — freeing dev time for higher-value tasks.
- **Broader implication**: The same formatter that accelerates manual letter builds can be dropped into a fully automated pipeline. A CRF comes in, the attached Word template feeds into the formatter, and the output is production-ready HTML — no human hands required for the conversion step. This is the key that makes legacy conversion automation possible (see Phase 2).

### 2) Dedicated QC Operations (focus programmers on development)

- Hire a dedicated in-house QC team to handle paper QCs (physical copies delivered after client orders), so programmers stay focused on programming.
- **Impact**: Reclaims substantial daily time otherwise spent doing tedious proofing of work we've already programmed, freeing up time to work on new requests.

### Process and Platform Improvements

These foundational improvements support Phase 1 efficiency gains and enable Phase 2 automation:

#### Streamline NcConnect Core Workflow

- Systematically fix high-friction bugs (tab resets, unreliable save flows, counter-intuitive task steps, PDF version preview issues) that force programmers to reopen tasks or take detours.
- Grow the developer team to reduce backlog and accelerate fixes/iteration, possibly introduce AI-assisted workflows.
- Combine letter "product creation" and "composition creation" into a single action — when a product is created, its composition may be composed and ready for assignment. (low friction task, low priority)

#### CRF Folder Automation

- On CRF creation, automatically create the server folder and ingest all CRF-attached files — removing a fully manual step and repeated deep file path navigation.

#### Unified Workspace for Data Drops & File Reviewing

- Link the programming drive and data-dropping drive directly into NcConnect for a single, in-app flow.
- Provide a one-stop "Drop Data" component (select files and drop) to eliminate deep path navigation across multiple shares.
- Introduce a one-click solution to view the most recent files uploaded for a specific product, eliminating deep path navigation.

#### Client Transparency Portal

- Add a client view with:
  - Programming queue: items in development and not yet promoted
  - Live production assets: current letter/insert versions
  - Optional preview of in-progress versions
- **Outcome**: Fewer status pings and misunderstandings (e.g., insert updates not yet promoted to a letter), less back-and-forth, faster approvals.

#### Checklists & Training

- AE checklist (what to include with each CRF: all client files, client email/context, required metadata). Goal: reduce back-and-forth and ensure "first-pass completeness."
- Client submission checklist (what they must provide and how): improves clarity and reduces multi-day clarifications.

#### NcConnect Code Editor Upgrade

- Improve the embedded editor: multi-cursor (Ctrl/Cmd-D), reliable save behavior (no "click out to save"), and common editor ergonomics.
- Optional: minimal, opinionated formatter/linters to catch simple mistakes and reduce nit rework.

#### QC Ordering Automation

- When daily reports are created, automatically order QCs by link of CRF number (from SharePoint or its successor) to the relevant file/letter in NcConnect. Eliminates manual searching and ordering.

#### Knowledge Base & AI-Powered Support Chatbot

- **What**: Build an AI-integrated chatbot (or intelligent knowledge base system) that can answer team questions instantly by drawing from our documentation and accumulated Q&A knowledge.
- **Impact**: 
  - Alleviates management resources and time spent answering routine questions
  - Eliminates wasted time siphoning through documentation or asking colleagues (saving the colleagues time as well)
  - Provides instant responses to technical questions
- **Why now**: This addresses a hidden productivity drain — time spent searching for answers or waiting on responses. It also frees up management's time by reducing the tedious task of answering questions.

#### Infrastructure Considerations

- Add capacity and tuning so sample processing is consistently fast (reduce the current multi-minute waits).
- Improve observability and error transparency (clear reasons for suppressed files and actionable error codes surfaced in UI/logs).

---

## Phase 2: End-to-End Automation — Including Legacy System Conversions

> **The Ultimate Goal:** Once Phase 1 foundational pieces are in place, we build a fully automated pipeline that transforms CRF creation to "Samples Under Review" from hours/days to near-instantaneous.

**Critical:** The architecture of all Phase 1 initiatives should be designed with this end-to-end vision in mind.

### Legacy Conversion Automation — What Was "Un-Automatable"

The conversion and creation process in our legacy system has long been considered un-automatable. Each CRF requires a programmer to manually read a Word template, interpret the structure, translate it into production HTML with the correct variable tagging, helper functions, conditional logic, and formatting standards. It's tedious, error-prone, and accounts for a large portion of programming time per CRF.

The letter template formatter changes this. It already handles that conversion automatically — ingesting a Word template, extracting structure, detecting formatting patterns, and outputting production-ready HTML. It's operational and improving with every document it processes.

With that piece in place, the path forward is straightforward:

- A CRF comes in with an attached Word template.
- The template feeds into the formatter.
- Production-ready HTML comes out — tagged, formatted, and ready for review.
- The programmer reviews the output, handles any edge cases, and approves it.

**This is another massive time-saver that was previously considered impossible.** It eliminates the most labor-intensive, repetitive portion of the programmer's workload and replaces it with a review step. The programmer operates at a higher level — applying judgment, catching exceptions, and ensuring quality — rather than doing the ground-level conversion work by hand. This pattern compounds with everything else in this document: the more we automate the routine, the more time our programmers spend on work that actually requires their expertise.

### The Complete Automation Pipeline

**Automated Workflow: SharePoint CRF Creation to Samples Under Review**

1. **CRF Creation Trigger**: When a CRF is created in SharePoint, the automation pipeline activates
2. **Automatic Folder Creation**: Server folder structure is created automatically
3. **File Ingestion**: All CRF-attached files are automatically downloaded and organized
4. **Composition & Product Creation**: Letter compositions and products are automatically created in NcConnect based on CRF metadata (standardizing the AE and client input becomes prominent here)
5. **Template Formatting**: Word templates are automatically formatted using the Letter Template Formatter
6. **Package Assembly**: If AEs follow standardized formatting/forms, product packages can be automatically assembled
7. **Sample Generation**: Files are automatically dropped to trigger sample generation
8. **Dashboard View**: Formatted letters and samples appear in the NCC dashboard, ready for programmer review

### Impact

- **Role Transformation**: Programmers shift from manual execution to strategic review and quality assurance
- **Legacy System**: Conversions that were considered un-automatable become automated, with the programmer serving as reviewer rather than builder
- **Consistency**: Standardized processes eliminate variability and reduce errors
- **Scalability**: System can handle increased volume without proportional increases in programmer time

### Prerequisites

This vision requires:
- Successful implementation of foundational automation (letter formatter, CRF folder automation, etc.)
- Standardized AE submission processes (forms or structured package formats)
- Robust error handling and validation at each pipeline stage
- Clear review checkpoints where human judgment is required
- Dashboard/reporting infrastructure to surface automated outputs

### Architecture Considerations

When building the foundational pieces, we should design with this end-to-end vision in mind:
- **API-First Design**: Components should expose APIs for integration, not just UI workflows
- **Event-Driven Architecture**: CRF creation, file uploads, and other triggers should emit events that downstream systems can react to
- **Idempotent Operations**: Automated steps should be safe to retry and idempotent
- **Audit Trails**: Every automated action should be logged for review and debugging
- **Graceful Degradation**: System should handle failures gracefully and surface issues for human intervention

### Implementation Phases

1. **Phase 1** (Current): Implement foundational automation pieces
2. **Phase 2**: Connect SharePoint/webhook triggers to initiate automated workflows
3. **Phase 3**: Build pipeline orchestration layer to coordinate multi-step automation
4. **Phase 4**: Develop review dashboard and quality checkpoints
5. **Phase 5**: Refine and expand automation based on learnings and edge cases

---

## What This Improves

- Faster completion of programming updates
- Faster sample generation
- Fewer manual steps to build letters
- More time for programming (paper QCs handled by a dedicated QC team)
- Less time spent navigating and dropping files (unified workspace, automating file path navigation/file generation)
- Fewer client status questions (client transparency portal)
- Smoother daily work in NcConnect (fewer bugs, reliable saves, better editor)
- Quicker startup on new work — we eliminate the most time-intensive portion of our programmers' workload, shifting effort from repetitive setup tasks to higher-value work. This increases both speed and output, effectively raising our value per programmer.
- Reduced context-switching for programmers (QC team covers paper QCs, QC orders being automated)
- **Legacy conversions move from "un-automatable" manual work to automated conversion with human review** — another massive time-saver that compounds with everything above

## Optional: AI-Enabled Acceleration (guardrailed)

- With approved tooling (e.g., Cursor, Claude Code) and lightweight process guardrails, we can amplify individual output (faster refactors, codemods, documentation, test generation). This is a force-multiplier, not a dependency.

## Security & Access Considerations

- Some items (e.g., automating server folder creation; linking NcConnect to programming/data-drop drives) depend on existing network segmentation and VPN-only access to file shares. That separation is intentional and should be preserved.
- Recommended approach: keep segmentation, but enable these actions through secure server-side services (least-privilege service accounts, RBAC, audit logs) exposed via NcConnect APIs — not direct client access to file shares.
- Apply Zero-Trust principles (conditional access, scoped permissions) and ensure all automated actions are logged and reviewable.
- If policy or risk posture prevents direct integration, we can still reduce friction with lighter options (e.g., automatic SharePoint folder scaffolding, pre-configured drop locations, guided shortcuts) that avoid changing trust boundaries.
