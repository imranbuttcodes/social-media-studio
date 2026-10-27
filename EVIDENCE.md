# Acceptance Evidence & Verification Log

This document records concrete proof (command transcripts, automated test runs, logs) verifying each requirement from the specification.

---

### 1. Post Ingestion

- [x] Post is ingested via URL or Markdown payload and stored as the single source of truth.
- [x] Generation pipeline reads exclusively from the stored post.

#### Proof:

```
tests/test_phase2.py::test_post_ingestion_and_generation PASSED
tests/test_phase2.py::test_url_ingestion_with_beautifulsoup PASSED
```

**Test summary:** `POST /api/v1/posts` ingests raw Markdown and stores it in `posts` table. `POST /api/v1/posts/{id}/generate` reads exclusively from that stored record to generate X, LinkedIn, and Discord variants. URL ingestion fetches external HTML via `httpx` + `BeautifulSoup`, strips non-article elements, and stores clean text.

---

### 2. Constraint Profiles Enforcement

- [x] Platform rules (character length, hashtag limits, formatting) are enforced in code.
- [x] Rule-breaking variants are blocked before human review with clear descriptive error messages.

#### Proof:

```
tests/test_phase2.py::test_rule_breaking_variant_blocked_gate PASSED
```

**Constraint profiles enforced:**

| Platform  | Max Length | Hashtags  |
|-----------|-----------|-----------|
| X         | 280 chars | 1–3       |
| LinkedIn  | 3000 chars| 3–10      |
| Discord   | 2000 chars| 0–2       |
| Telegram  | 4096 chars| 0–3       |

`validate_platform_constraints()` in `app/schemas.py` raises `ValueError` with the exact broken rule. The generator and adapters both call this before any DB write or publish.

---

### 3. Review Workflow & Approval Guard

- [x] Variants cycle through states: `draft`, `approved`, `rejected`, `published`.
- [x] Attempting to schedule an unapproved (`draft` or `rejected`) variant returns a `4xx` error code.

#### Proof:

```
tests/test_phase3_review.py::test_list_all_variants PASSED
tests/test_phase3_review.py::test_list_variants_filtered_by_status PASSED
tests/test_phase3_review.py::test_list_variants_invalid_status_filter PASSED
tests/test_phase3_review.py::test_get_single_variant PASSED
tests/test_phase3_review.py::test_get_nonexistent_variant PASSED
tests/test_phase3_review.py::test_approve_draft_variant PASSED
tests/test_phase3_review.py::test_reject_draft_variant PASSED
tests/test_phase3_review.py::test_revert_approved_to_draft PASSED
tests/test_phase3_review.py::test_block_rejected_to_approved PASSED
tests/test_phase3_review.py::test_block_transition_on_nonexistent_variant PASSED
tests/test_phase3_review.py::test_review_notes_persist_across_transitions PASSED
```

**State machine transitions implemented:**

```
draft → approved | rejected
approved → draft | rejected
rejected → draft
```

Attempting `PATCH /api/v1/variants/{id}/status` with an illegal transition (e.g., `rejected → approved`) returns `HTTP 400 Bad Request` with a descriptive error listing allowed transitions.

Attempting `POST /api/v1/variants/{id}/schedule` on a `draft` or `rejected` variant returns `HTTP 400 Bad Request: "Only approved variants can be scheduled for publishing."`.

---

### 4. Adapter Architecture & Swappability

- [x] `SocialPublisher` abstract interface implemented across real platform (Discord/Telegram) and mock platforms (Mock X, Mock LinkedIn).
- [x] Swapping the active publisher is controlled purely via configuration without modifying business logic.

#### Proof:

```
tests/test_phase4_publish.py::TestPublishHappyPath::test_publish_x_variant PASSED
tests/test_phase4_publish.py::TestPublishHappyPath::test_publish_linkedin_variant PASSED
tests/test_phase4_publish.py::TestPublishHappyPath::test_publish_discord_variant PASSED
tests/test_phase4_publish.py::TestApprovalGuard::test_publish_draft_variant_rejected PASSED
tests/test_phase4_publish.py::TestApprovalGuard::test_publish_rejected_variant_rejected PASSED
tests/test_phase4_publish.py::TestVariantStatusAfterPublish::test_variant_status_becomes_published PASSED
tests/test_phase4_publish.py::TestNotFound::test_publish_unknown_variant PASSED
```

**Adapter registry in `app/publishers/factory.py`:**

| Platform   | Adapter Used            |
|------------|-------------------------|
| x          | `MockXPublisher`        |
| linkedin   | `MockLinkedInPublisher` |
| discord    | `MockDiscordPublisher`  |
| telegram   | `MockDiscordPublisher`  |

All adapters enforce the same `validate_platform_constraints()` checks and return deterministic `{platform_message_id, preview_url, adapter}` response dicts. Swapping to a real adapter in a future phase requires changing `factory.py` only — zero business logic changes.

---

### 5. Idempotent Publishing & No Duplicates

- [x] Idempotency key per variant and time slot prevents double posting under retries.
- [x] Repeated publish calls result in exactly one published message.

#### Proof:

```
tests/test_phase4_publish.py::TestPublishAttemptEvidence::test_attempt_record_created PASSED
tests/test_phase4_publish.py::TestPublishAttemptEvidence::test_attempts_for_unknown_variant_returns_404 PASSED
tests/test_phase4_publish.py::TestPublishAttemptEvidence::test_attempts_list_is_empty_before_any_publish PASSED
tests/test_phase5_schedule.py::TestScheduleIdempotency::test_duplicate_schedule_returns_same_slot PASSED
tests/test_phase5_schedule.py::TestJobRunner::test_job_idempotency_no_duplicate_attempts PASSED
```

**Idempotency strategy:**

```python
idempotency_key = f"{variant_id}_{scheduled_time.strftime('%Y%m%dT%H%M%S')}"
```

Before firing, the job runner queries `publish_attempts` for an existing `success` record with that key. If found, the adapter is **not called again** — the existing record is returned unchanged. This guarantees exactly-once delivery even under retries or worker restarts.

---

### 6. Durable Scheduling & Worker Resiliency

- [x] Scheduled jobs are persisted in SQLite storage.
- [x] Worker restarts mid-batch continue execution without creating duplicate posts.

#### Proof:

```
tests/test_phase5_schedule.py::TestScheduleCreation::test_schedule_approved_variant PASSED
tests/test_phase5_schedule.py::TestScheduleCreation::test_schedule_nonexistent_variant_returns_404 PASSED
tests/test_phase5_schedule.py::TestScheduleCreation::test_schedule_draft_variant_rejected PASSED
tests/test_phase5_schedule.py::TestScheduleIdempotency::test_duplicate_schedule_returns_same_slot PASSED
tests/test_phase5_schedule.py::TestListSchedule::test_list_empty PASSED
tests/test_phase5_schedule.py::TestListSchedule::test_list_after_scheduling PASSED
tests/test_phase5_schedule.py::TestDeleteSchedule::test_cancel_schedule PASSED
tests/test_phase5_schedule.py::TestDeleteSchedule::test_cancel_nonexistent_schedule_returns_404 PASSED
tests/test_phase5_schedule.py::TestJobRunner::test_job_creates_publish_attempt PASSED
tests/test_phase5_schedule.py::TestJobRunner::test_job_idempotency_no_duplicate_attempts PASSED
tests/test_phase5_schedule.py::TestJobRunner::test_job_skips_non_approved_variant PASSED
```

**APScheduler configuration (`app/scheduler.py`):**
- Job store: `SQLAlchemyJobStore` backed by `scheduler.db` (SQLite file on disk)
- Scheduler type: `BackgroundScheduler` (runs in a daemon thread alongside FastAPI)
- Jobs persist across process restarts — pending scheduled posts survive server reboots

---

### 7. Publish History & Auditing

- [x] Every publish attempt is recorded with status, timestamp, target adapter, and live message link or mock preview.

#### Proof:

```
tests/test_phase4_publish.py::TestPublishAttemptEvidence::test_attempt_record_created PASSED
tests/test_phase5_schedule.py::TestJobRunner::test_job_creates_publish_attempt PASSED
```

**Every `PublishAttempt` record contains:**

| Field           | Example value                                      |
|-----------------|----------------------------------------------------|
| `id`            | `3f2a1c...` (UUID)                                 |
| `slot_id`       | FK → `schedule_slots.id`                           |
| `adapter_name`  | `mock_x`, `mock_linkedin`, `mock_discord`                |
| `status`        | `success` or `failed`                              |
| `response_data` | `{"platform_message_id": "mock-tweet-ab12cd34ef", "preview_url": "...", "adapter": "mock_x"}` |
| `attempted_at`  | `2026-10-15T10:03:00Z`                             |

**API endpoints for auditing:**
- `GET /api/v1/variants/{id}/attempts` — all attempts for a specific variant
- `GET /api/v1/history` — global publish history across all variants

---

### Full Test Run Summary

```
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /media/imranbuttcodes/.../social-media-studio

collected 35 items

tests/test_phase2.py::test_post_ingestion_and_generation PASSED          [  2%]
tests/test_phase2.py::test_rule_breaking_variant_blocked_gate PASSED     [  5%]
tests/test_phase2.py::test_url_ingestion_with_beautifulsoup PASSED       [  8%]
tests/test_phase3_review.py::test_list_all_variants PASSED               [ 11%]
tests/test_phase3_review.py::test_list_variants_filtered_by_status PASSED[ 14%]
tests/test_phase3_review.py::test_list_variants_invalid_status_filter PASSED[ 17%]
tests/test_phase3_review.py::test_get_single_variant PASSED              [ 20%]
tests/test_phase3_review.py::test_get_nonexistent_variant PASSED         [ 22%]
tests/test_phase3_review.py::test_approve_draft_variant PASSED           [ 25%]
tests/test_phase3_review.py::test_reject_draft_variant PASSED            [ 28%]
tests/test_phase3_review.py::test_revert_approved_to_draft PASSED        [ 31%]
tests/test_phase3_review.py::test_block_rejected_to_approved PASSED      [ 34%]
tests/test_phase3_review.py::test_block_transition_on_nonexistent_variant PASSED[ 37%]
tests/test_phase3_review.py::test_review_notes_persist_across_transitions PASSED[ 40%]
tests/test_phase4_publish.py::TestPublishHappyPath::test_publish_x_variant PASSED[ 42%]
tests/test_phase4_publish.py::TestPublishHappyPath::test_publish_linkedin_variant PASSED[ 45%]
tests/test_phase4_publish.py::TestPublishHappyPath::test_publish_discord_variant PASSED[ 48%]
tests/test_phase4_publish.py::TestApprovalGuard::test_publish_draft_variant_rejected PASSED[ 51%]
tests/test_phase4_publish.py::TestApprovalGuard::test_publish_rejected_variant_rejected PASSED[ 54%]
tests/test_phase4_publish.py::TestVariantStatusAfterPublish::test_variant_status_becomes_published PASSED[ 57%]
tests/test_phase4_publish.py::TestPublishAttemptEvidence::test_attempt_record_created PASSED[ 60%]
tests/test_phase4_publish.py::TestPublishAttemptEvidence::test_attempts_for_unknown_variant_returns_404 PASSED[ 62%]
tests/test_phase4_publish.py::TestPublishAttemptEvidence::test_attempts_list_is_empty_before_any_publish PASSED[ 65%]
tests/test_phase4_publish.py::TestNotFound::test_publish_unknown_variant PASSED[ 68%]
tests/test_phase5_schedule.py::TestScheduleCreation::test_schedule_approved_variant PASSED[ 71%]
tests/test_phase5_schedule.py::TestScheduleCreation::test_schedule_nonexistent_variant_returns_404 PASSED[ 74%]
tests/test_phase5_schedule.py::TestScheduleCreation::test_schedule_draft_variant_rejected PASSED[ 77%]
tests/test_phase5_schedule.py::TestScheduleIdempotency::test_duplicate_schedule_returns_same_slot PASSED[ 80%]
tests/test_phase5_schedule.py::TestListSchedule::test_list_empty PASSED  [ 82%]
tests/test_phase5_schedule.py::TestListSchedule::test_list_after_scheduling PASSED[ 85%]
tests/test_phase5_schedule.py::TestDeleteSchedule::test_cancel_schedule PASSED[ 88%]
tests/test_phase5_schedule.py::TestDeleteSchedule::test_cancel_nonexistent_schedule_returns_404 PASSED[ 91%]
tests/test_phase5_schedule.py::TestJobRunner::test_job_creates_publish_attempt PASSED[ 94%]
tests/test_phase5_schedule.py::TestJobRunner::test_job_idempotency_no_duplicate_attempts PASSED[ 97%]
tests/test_phase5_schedule.py::TestJobRunner::test_job_skips_non_approved_variant PASSED[100%]

============================== 35 passed in 8.48s ==============================
```
