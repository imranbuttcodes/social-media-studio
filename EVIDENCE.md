# Acceptance Evidence & Verification Log

This document records concrete proof (command transcripts, automated test runs, logs) verifying each requirement from the specification.

---

### 1. Post Ingestion
- [ ] Post is ingested via URL or Markdown payload and stored as the single source of truth.
- [ ] Generation pipeline reads exclusively from the stored post.

#### Proof:
*(To be recorded in Phase 2)*

---

### 2. Constraint Profiles Enforcement
- [ ] Platform rules (character length, hashtag limits, formatting) are enforced in code.
- [ ] Rule-breaking variants are blocked before human review with clear descriptive error messages.

#### Proof:
*(To be recorded in Phase 2)*

---

### 3. Review Workflow & Approval Guard
- [ ] Variants cycle through states: `draft`, `approved`, `rejected`, `published`.
- [ ] Attempting to schedule an unapproved (`draft` or `rejected`) variant returns a `4xx` error code.

#### Proof:
*(To be recorded in Phase 3)*

---

### 4. Adapter Architecture & Swappability
- [ ] `SocialPublisher` abstract interface is implemented by current mock adapters (`MockXPublisher`, `MockLinkedInPublisher`, `MockDiscordPublisher`).
- [ ] Real Discord webhook / Telegram bot adapters are not implemented in this repository snapshot.
- [ ] Swapping the active publisher purely via configuration is not implemented (`ACTIVE_REAL_PUBLISHER` is currently unused).

#### Proof:
*(To be recorded in Phase 4)*

---

### 5. Idempotent Publishing & No Duplicates
- [ ] Idempotency key per variant and time slot prevents double posting under retries.
- [ ] Repeated publish calls result in exactly one published message.

#### Proof:
*(To be recorded in Phase 4)*

---

### 6. Durable Scheduling & Worker Resiliency
- [ ] Scheduled jobs are persisted in SQLite storage.
- [ ] Worker restarts mid-batch continue execution without creating duplicate posts.

#### Proof:
*(To be recorded in Phase 5)*

---

### 7. Publish History & Auditing
- [ ] Every publish attempt is recorded with status, timestamp, target adapter, and live message link or mock preview.
- [ ] Telegram publishing evidence cannot be completed yet because Telegram has validation constraints but no registered publisher adapter/generator output.

#### Proof:
*(To be recorded in Phase 5)*
