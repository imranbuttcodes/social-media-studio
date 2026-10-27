# Build Log & AI Usage Record

This log documents development decisions, architectural implementations, and AI assistance throughout the development of Social Media Studio.

---

## Phase 1: Architecture & System Design
* **Date:** 2026-10-12
* **What was planned:**
  - Designed the data model: `posts`, `variants`, `schedule_slots`, `publish_attempts`.
  - Defined strict platform constraint profiles (character length limits, hashtag bounds, and tone rules for X, LinkedIn, Discord/Telegram).
  - Designed the `SocialPublisher` abstract base interface and planned adapter implementations (`DiscordWebhookPublisher`, `TelegramBotPublisher`, `MockXPublisher`, `MockLinkedInPublisher`).
  - Outlined the review workflow state machine (`draft` -> `approved` / `rejected` -> `published`) and durable scheduling with persistent SQLite job storage.
* **AI Assistance:**
  - Assisted in structuring the system design document (`docs/DESIGN.md`) and adapter architecture patterns.
  - Formulated constraint profiles to prevent oversized or malformed posts before human review.

---

## Phase 2: Post Ingestion & Variant Generation
* **Date:** 2026-10-13
* **What was built:**
  - `app/database.py`: SQLAlchemy engine, `SessionLocal`, `Base`, and `get_db` FastAPI dependency using SQLite.
  - `app/models.py`: `Post` and `Variant` SQLAlchemy ORM models with UUID primary keys, string status columns, and `Post → Variant` one-to-many relationship with cascade delete.
  - `app/schemas.py`: `PostCreate`, `PostResponse`, `VariantCreateManual`, `VariantResponse` Pydantic models. Defined `PLATFORM_CONSTRAINTS` dict and `validate_platform_constraints()` utility.
  - `app/services/generator.py`: `fetch_url_content()` async function using `httpx` + `BeautifulSoup` to scrape clean article text from external URLs. `generate_platform_variants()` creates tailored content for X (≤280 chars, punchy hook), LinkedIn (professional paragraphs, 3+ hashtags), and Discord (community announcement tone).
  - `app/main.py`: `POST /api/v1/posts` (ingest) and `POST /api/v1/posts/{id}/generate` endpoints.
* **Key decisions:**
  - Variants are always generated from the stored post, never from raw request body — enforces single source of truth.
  - `validate_platform_constraints()` called during generation and again in each adapter before publish — double guard.
  - Hashtags stored as JSON string in a `Text` column (no separate table) for simplicity.
* **Tests written:** `tests/test_phase2.py` — 3 tests covering ingestion, generation, and constraint blocking.
* **AI Assistance:**
  - Generated BeautifulSoup scraping logic and regex-based Markdown stripping.
  - Suggested using `model_validator` in Pydantic for cross-field validation of `content` vs `source_url`.

---

## Phase 3: Review Workflow & Approval State Machine
* **Date:** 2026-10-13
* **What was built:**
  - `PATCH /api/v1/variants/{id}/status` endpoint implementing a strict state machine.
  - `ALLOWED_TRANSITIONS` dict guards every transition — illegal moves return `HTTP 400` with exact error messages.
  - `GET /api/v1/variants` with optional `?status=` query filter.
  - `GET /api/v1/variants/{id}` single variant retrieval.
  - `VariantReviewUpdate` schema using `Literal["approved", "rejected", "draft"]` to reject invalid status strings at the Pydantic layer.
  - `review_notes` field persisted across transitions for editorial context.
* **Key decisions:**
  - State machine table (`ALLOWED_TRANSITIONS`) is defined as a plain Python dict — easy to read, audit, and extend.
  - `published` status is terminal — no outbound transitions from it (set by the publisher, not by the reviewer).
* **Tests written:** `tests/test_phase3_review.py` — 11 tests covering all valid transitions, all illegal transitions, filter queries, and note persistence.
* **AI Assistance:**
  - Structured state machine dict pattern and error message formatting.

---

## Phase 4: Publisher Adapters & Idempotency
* **Date:** 2026-10-14
* **What was built:**
  - `app/publishers/base.py`: `SocialPublisher` abstract base class with `adapter_name` class attribute and abstract `publish()` async method. `PublishError` exception for adapter failures.
  - `app/publishers/mock_x.py`, `mock_linkedin.py`, `mock_discord.py`: Three mock adapters each validating platform constraints then returning a deterministic response dict with `platform_message_id`, `preview_url`, and `adapter` fields. No real API calls made.
  - `app/publishers/factory.py`: `get_publisher(platform)` function — resolves `mock_x`, `mock_linkedin`, `mock_discord` for all platforms. Swapping to a real adapter in a future phase requires changing this file only.
  - `app/models.py`: Added `ScheduleSlot` and `PublishAttempt` ORM models.
  - `POST /api/v1/variants/{id}/publish` — on-demand publish endpoint.
  - `GET /api/v1/variants/{id}/attempts` — per-variant audit endpoint.
  - `GET /api/v1/history` — global publish history endpoint.
  - Idempotency: `idempotency_key = f"{variant_id}_{scheduled_time}"` — before calling an adapter, checks for existing successful `PublishAttempt` and returns it unchanged if found.
* **Key decisions:**
  - All platforms use mock adapters to avoid paid API tiers (X, LinkedIn) and unnecessary external dependencies (Discord, Telegram). Mock adapters enforce identical constraint validation.
  - `adapter_name` as a class-level string attribute records exactly which adapter fired in every `PublishAttempt` row.
  - `PublishAttempt` is always written — even on failure — so the audit log is complete.
  - On adapter failure, variant stays `approved` (not blocked) so a reviewer can retry.
* **Tests written:** `tests/test_phase4_publish.py` — 10 tests across 4 test classes covering happy paths, approval guard, status transitions, attempt evidence, and 404 handling.
* **AI Assistance:**
  - Abstract class pattern for `SocialPublisher`, idempotency key design and guard logic.


---

## Phase 5: Durable Scheduler & Job Runner
* **Date:** 2026-10-15
* **What was built:**
  - `app/scheduler.py`: `BackgroundScheduler` configured with `SQLAlchemyJobStore` backed by `scheduler.db`. Started on import, gracefully shut down via `atexit`. `get_scheduler()` helper exposes the singleton.
  - `app/jobs.py`: `run_publish_job(variant_id, scheduled_iso)` — the APScheduler entry point. Loads the variant, checks approval, rebuilds idempotency key, queries for existing successful attempt (idempotency guard), calls the adapter, persists `PublishAttempt`, updates variant to `published`.
  - `POST /api/v1/variants/{id}/schedule` — creates a `ScheduleSlot` and registers an APScheduler `date` trigger job. Idempotent: returns existing slot if same `idempotency_key` already exists.
  - `GET /api/v1/schedule` — lists all schedule slots.
  - `DELETE /api/v1/schedule/{job_id}` — cancels a scheduled job and deletes its slot.
  - `app/scripts/seed.py` — seed script creating 3 sample posts + variants for demo/dev use.
  - `tests/conftest.py` — shared `TestingSessionLocal` engine and `autouse` `clean_db` fixture. Centralizes `app.dependency_overrides[get_db]` so all test modules share one test DB without fighting each other.
* **Key decisions:**
  - Testing the job runner **directly** (patching `SessionLocal`) rather than waiting for the APScheduler background thread — eliminates timing flakiness in tests entirely.
  - Shared `conftest.py` instead of per-module DB setup — prevents the override collision that was breaking Phase 2/3/4 tests when Phase 5 tests loaded.
  - Jobs persist in `scheduler.db` separately from `social_studio.db` — scheduler state is independent of application data.
* **Tests written:** `tests/test_phase5_schedule.py` — 11 tests across 5 test classes covering schedule CRUD, idempotency, list/cancel, job execution, job idempotency, and approval guard.
* **AI Assistance:**
  - APScheduler `SQLAlchemyJobStore` configuration.
  - `conftest.py` shared fixture strategy to resolve test DB isolation conflicts.
  - Direct job runner testing pattern.
