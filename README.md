# Social Media Studio

A multi-platform social media campaign generator, editorial review workflow, and scheduled publishing service built with **FastAPI**, **SQLite**, and **APScheduler**.

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
                      |  +-- Mock X / Twitter       |
                      |  +-- Mock LinkedIn          |
                      |  +-- Mock Discord           |
                      |  +-- Mock Telegram          |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |   Audit / Publish History   |
                      +-----------------------------+
```

---

## Core Features

1. **Single Source Ingestion** — Articles ingested via URL (BeautifulSoup scraper) or raw Markdown. All variants derive strictly from the stored post.
2. **Constraint Profile Validation** — Platform-specific limits enforced at generation time and again before publish (X: 280 chars, LinkedIn: 3000 chars, Discord/Telegram: 2000 chars).
3. **Approval Gated Workflow** — Strict state machine (`draft` → `approved`/`rejected` → `published`). Unapproved variants cannot be scheduled (returns `400`).
4. **Pluggable Adapter Architecture** — `SocialPublisher` abstract base class. Mock adapters for all platforms enforce full constraint validation and return deterministic preview responses. Swapping to a real adapter requires changing `factory.py` only.
5. **Durable Scheduling & Idempotency** — APScheduler with SQLite job store. Jobs survive server restarts. Unique idempotency key per slot prevents duplicate publishes.
6. **Full Audit Trail** — Every publish attempt recorded with status, timestamp, adapter name, and message preview.

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

API docs live at `http://localhost:8000/docs`.

---

## API Reference

| Method   | Endpoint                              | Description                                        |
|----------|---------------------------------------|----------------------------------------------------|
| `POST`   | `/api/v1/posts`                       | Ingest article via URL or Markdown                 |
| `POST`   | `/api/v1/posts/{id}/generate`         | Generate platform variants                         |
| `GET`    | `/api/v1/variants`                    | List variants (filter by `?status=`)               |
| `PATCH`  | `/api/v1/variants/{id}/status`        | Review workflow — approve / reject / revert        |
| `POST`   | `/api/v1/variants/{id}/publish`       | On-demand publish of an approved variant           |
| `GET`    | `/api/v1/variants/{id}/attempts`      | Publish attempt history for one variant            |
| `POST`   | `/api/v1/variants/{id}/schedule`      | Schedule an approved variant                       |
| `GET`    | `/api/v1/schedule`                    | List all schedule slots                            |
| `DELETE` | `/api/v1/schedule/{job_id}`           | Cancel a scheduled job                             |
| `GET`    | `/api/v1/history`                     | Global publish history across all variants         |

---

## Running Tests

```bash
python -m pytest tests/ -v
```

Expected: **35 passed**.

---

## Documentation Links
* [System Design Document](docs/DESIGN.md)
* [Acceptance Evidence](EVIDENCE.md)
* [Build Log](BUILDLOG.md)

---

## Known Limitations
* **Mock Adapters Only:** All platforms (X, LinkedIn, Discord, Telegram) use mock adapters that validate constraints and return deterministic preview responses without making real API calls. This avoids paid developer API tiers while fully proving the constraint, idempotency, and audit guarantees.
* **Text Only:** Current release focuses on copy, hooks, and hashtags — no image or video generation.
