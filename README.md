# Social Media Studio

A multi-platform social media campaign generator, editorial review workflow, and scheduled publishing service built with **FastAPI**, **SQLite**, and **Discord / Telegram Webhooks**.

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
                      |  +-- Discord Webhook (Real) |
                      |  +-- Telegram Bot (Real)    |
                      |  +-- Mock X / Twitter       |
                      |  +-- Mock LinkedIn          |
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
   - Platform-specific limits (X: 280 chars, LinkedIn: 3000 chars, Discord/Telegram: 2000 chars).
   - Rule-violating drafts are caught and blocked before human review.
3. **Approval Gated Workflow:**
   - Strict state machine transitions (`draft` &rarr; `approved` / `rejected` &rarr; `published`).
   - Unapproved variants cannot be scheduled (returns `4xx`).
4. **Adapter Pattern Publishing:**
   - Pluggable `SocialPublisher` architecture.
   - Publishes to real platforms (Discord/Telegram) and mock platforms (Mock X, Mock LinkedIn).
5. **Durable Scheduling & Idempotency:**
   - Background jobs persist across server reboots.
   - Guaranteed single-delivery via unique idempotency keys per slot.

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

4. **Seed sample post data:**
   ```bash
   python -m app.scripts.seed
   ```

5. **Start the API & scheduler:**
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
* **Mock Adapters for X & LinkedIn:** X (Twitter) and LinkedIn utilize mock storage adapters to avoid paid developer API tiers. Real delivery is demonstrated on Discord or Telegram.
* **Text Only:** Current release focuses on copy, hooks, and hashtags without automated image asset generation.
