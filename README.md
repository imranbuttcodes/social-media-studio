# Social Media Studio

A multi-platform social media campaign generator, editorial review workflow, and scheduled publishing service built with **FastAPI** and **SQLite**.

---

## Architecture Overview

```
                      +-----------------------------+
                      |   Source Blog Post / URL    |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |       Ingestion Layer       |
                      |   - URL Scraper / Markdown  |
                      |   - Stored Single Source    |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      | Variant Generator & Guards  |
                      |   - Enforce Character Limits|
                      |   - Hashtag & Tone Rules    |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |       Review Workflow       |
                      | draft -> approved | rejected|
                      +--------------+--------------+
                                     | (Approved Only)
                                     v
                      +-----------------------------+
                      |   Durable SQLite Scheduler  |
                      |   - APScheduler (Persistent)|
                      |   - Idempotency Deduplication
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |   SocialPublisher Adapter   |
                      |  +-- MockXPublisher         |
                      |  +-- MockLinkedInPublisher  |
                      |  +-- MockDiscordPublisher   |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |   Audit / Publish History   |
                      +-----------------------------+
```

---

## Core Features

1. **Single Source Ingestion:**
   - Ingests long-form articles via URL or raw Markdown.
   - All variants derive strictly from the stored source of truth.
2. **Constraint Profile Validation:**
   - Platform-specific limits enforced in schema validation: X (280), LinkedIn (3000), Discord (2000), Telegram (4096).
   - Rule-violating drafts are caught and blocked before human review.
3. **Approval Gated Workflow:**
   - Strict state machine transitions (`draft` &rarr; `approved` / `rejected` &rarr; `published`).
   - Unapproved variants cannot be scheduled (returns `4xx`).
4. **Adapter Pattern Publishing:**
   - Pluggable `SocialPublisher` architecture.
   - Current implementation uses mock adapters only: `MockXPublisher`, `MockLinkedInPublisher`, `MockDiscordPublisher`.
   - Telegram is validated by schemas but has no registered publisher adapter, so Telegram variants cannot currently be published.
5. **Durable Scheduling & Idempotency:**
   - Background jobs persist across server reboots.
   - Guaranteed single-delivery via unique idempotency keys per slot.
6. **Deterministic Variant Generation:**
   - `app/services/generator.py` uses deterministic template logic (no Gemini/AI generation).
   - `GEMINI_API_KEY` is currently unused by runtime code.

---

## Quickstart

### Prerequisites
* Python 3.10+
* Virtual environment (`.venv`)

### Installation & Run

1. **Clone the repository:**
   ```bash
   git clone https://github.com/imranbuttcodes/social-media-studio.git
   cd social-media-studio
   ```

2. **Set up virtual environment:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure environment:**
   ```bash
   cp .env.example .env
   ```

4. **Start the API & scheduler:**
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

API documentation and interactive testing will be live at `http://localhost:8000/docs`.

---

## Documentation Links
* [System Design Document](docs/DESIGN.md)
* [Acceptance Evidence](EVIDENCE.md)
* [Build Log](BUILDLOG.md)

---

## Known Limitations
* **Mock adapters only:** Publishing is currently mock-only for X, LinkedIn, and Discord via `MockXPublisher`, `MockLinkedInPublisher`, and `MockDiscordPublisher`.
* **Telegram is not publishable yet:** Telegram appears in validation schemas, but the generator does not produce Telegram variants and the publisher factory has no Telegram adapter.
* **Adapter selection is code-defined:** `app/publishers/factory.py` uses a hard-coded registry; `ACTIVE_REAL_PUBLISHER` is not used at runtime.
* **No global history endpoint:** There is no `GET /api/v1/history`; publish audit is available per variant at `GET /api/v1/variants/{variant_id}/attempts`.
* **No built-in seed script:** `python -m app.scripts.seed` is unavailable in this repository.
* **Text Only:** Current release focuses on copy, hooks, and hashtags without automated image asset generation.

---

## API Routes (Current)

- `GET /health`
- `POST /api/v1/posts`
- `GET /api/v1/posts/{post_id}`
- `POST /api/v1/posts/{post_id}/generate`
- `POST /api/v1/variants/validate-custom`
- `GET /api/v1/variants`
- `GET /api/v1/variants/{variant_id}`
- `PATCH /api/v1/variants/{variant_id}/status`
- `POST /api/v1/variants/{variant_id}/publish`
- `GET /api/v1/variants/{variant_id}/attempts`
- `POST /api/v1/variants/{variant_id}/schedule`
- `GET /api/v1/schedule`
- `DELETE /api/v1/schedule/{job_id}`
