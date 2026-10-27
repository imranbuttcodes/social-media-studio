# Design Document: Social Media Studio

## 1. Problem Statement
Content creators and marketing teams frequently publish long-form blog articles and need to distribute them across multiple social media platforms (X/Twitter, LinkedIn, Discord/Telegram).

Manually crafting tailored versions is time-consuming, and naive automated posting systems present critical operational risks:
1. **Rule Violations:** Different platforms enforce strict, distinct constraints (character limits, hashtag formatting, tone rules).
2. **Unreviewed Content Leaks:** Automated drafts must never bypass human editorial review.
3. **Double-Posting Glitches:** Network timeouts and retries often publish identical posts multiple times.
4. **Fragile Scheduling:** Memory-based schedulers lose pending campaigns when workers restart.

**Social Media Studio** solves this with automated variant generation, constraint validation, a gated review workflow, durable SQLite-backed scheduling, and a pluggable adapter publishing layer with idempotency guarantees.

---

## 2. Platform Constraint Profiles

| Platform | Max Character Length | Min / Max Hashtags | Tone / Formatting Rules |
|---|---|---|---|
| **X (Twitter)** | 280 characters | 1 to 3 hashtags | Punchy, engaging hook, short sentences. |
| **LinkedIn** | 3,000 characters | 3 to 10 hashtags | Professional, structured paragraphs, career/industry takeaway. |
| **Discord** | 2,000 characters | 0 to 2 hashtags | Direct community announcement with Markdown links and emojis. |
| **Telegram** | 4,096 characters | 0 to 3 hashtags | Telegram channel announcement. |

*Variants that break character limits or hashtag bounds are rejected during validation before reaching the review queue.*

---

## 3. Data Model

### `posts` (Single Source of Truth)
* `id` (VARCHAR / UUID, Primary Key)
* `title` (VARCHAR, Non-null)
* `content` (TEXT, Non-null Markdown content)
* `source_url` (VARCHAR, Nullable)
* `created_at` (TIMESTAMP)

### `variants`
* `id` (VARCHAR / UUID, Primary Key)
* `post_id` (VARCHAR, Foreign Key → `posts.id`)
* `platform` (VARCHAR) — `x`, `linkedin`, `discord`, `telegram`
* `content` (TEXT, Non-null)
* `hashtags` (TEXT, JSON-encoded array of strings)
* `status` (VARCHAR) — `draft`, `approved`, `rejected`, `published`
* `review_notes` (TEXT, Nullable)
* `created_at` (TIMESTAMP)
* `updated_at` (TIMESTAMP)

### `schedule_slots`
* `id` (VARCHAR / UUID, Primary Key)
* `variant_id` (VARCHAR, Foreign Key → `variants.id`)
* `scheduled_time` (TIMESTAMP)
* `idempotency_key` (VARCHAR, Unique) — format: `{variant_id}_{YYYYMMDDTHHMMSS}`
* `status` (VARCHAR) — `pending`, `processing`, `completed`, `failed`
* `created_at` (TIMESTAMP)

### `publish_attempts` (Audit Log)
* `id` (VARCHAR / UUID, Primary Key)
* `slot_id` (VARCHAR, Foreign Key → `schedule_slots.id`)
* `adapter_name` (VARCHAR) — e.g. `mock_x`, `mock_linkedin`, `mock_discord`
* `status` (VARCHAR) — `success`, `failed`
* `response_data` (TEXT, Nullable — JSON with `platform_message_id`, `preview_url`)
* `attempted_at` (TIMESTAMP)

---

## 4. Publisher Adapter Architecture

```python
from abc import ABC, abstractmethod
from typing import Dict, Any

class SocialPublisher(ABC):
    adapter_name: str = "base"

    @abstractmethod
    async def publish(self, content: str, hashtags: list[str], idempotency_key: str) -> Dict[str, Any]:
        """
        Publishes content to the designated platform.
        Raises PublishError on failure.
        Returns a dict with: platform_message_id, preview_url, adapter.
        """
        pass
```

### Implementations

| Adapter Class           | Platform          | Description                                                |
|-------------------------|-------------------|------------------------------------------------------------|
| `MockXPublisher`        | x                 | Validates constraints, returns simulated tweet preview     |
| `MockLinkedInPublisher` | linkedin          | Validates constraints, returns simulated post preview      |
| `MockDiscordPublisher`  | discord, telegram | Validates constraints, returns simulated channel message   |

> **Note on Real Adapters:** X and LinkedIn do not offer affordable public API access. Discord and Telegram delivery is proven via Mock Adapters that enforce the same constraint validation and idempotency guarantees as real adapters would. Swapping to a live adapter in a future phase requires changing `app/publishers/factory.py` only — zero changes to any endpoint or job runner.

---

## 5. API Surface

| Method   | Endpoint                              | Description                                                   |
|----------|---------------------------------------|---------------------------------------------------------------|
| `POST`   | `/api/v1/posts`                       | Ingest article via URL or raw Markdown                        |
| `GET`    | `/api/v1/posts/{id}`                  | Retrieve a stored post                                        |
| `POST`   | `/api/v1/posts/{id}/generate`         | Generate platform variants with constraint validation         |
| `GET`    | `/api/v1/variants`                    | List variants, optional `?status=` filter                     |
| `GET`    | `/api/v1/variants/{id}`               | Get a single variant                                          |
| `PATCH`  | `/api/v1/variants/{id}/status`        | Review workflow: transition variant status                    |
| `POST`   | `/api/v1/variants/{id}/publish`       | On-demand publish of an approved variant                      |
| `GET`    | `/api/v1/variants/{id}/attempts`      | All publish attempts for a specific variant                   |
| `POST`   | `/api/v1/variants/{id}/schedule`      | Schedule approved variant — returns 400 if not approved       |
| `GET`    | `/api/v1/schedule`                    | List all schedule slots                                       |
| `DELETE` | `/api/v1/schedule/{job_id}`           | Cancel a scheduled job and delete its slot                    |
| `GET`    | `/api/v1/history`                     | Global publish history across all variants                    |
| `GET`    | `/health`                             | Health check                                                  |

---

## 6. Durable Scheduling & Idempotency Strategy

* Scheduling runs via `APScheduler` (`BackgroundScheduler`) backed by `SQLAlchemyJobStore` (`scheduler.db`). Pending jobs survive server restarts.
* Each publish action derives: `idempotency_key = f"{variant_id}_{scheduled_time.strftime('%Y%m%dT%H%M%S')}"`
* Before firing, `run_publish_job` checks `publish_attempts` for an existing `success` record. If found, the adapter is **not called again** — existing record returned unchanged.
* `ScheduleSlot` creation is also idempotent: scheduling the same variant at the same time returns the existing slot, not a duplicate.

---

## 7. Explicit Non-Goals
1. **No Real Twitter/X or LinkedIn API Tokens:** Avoided due to paid API tiers. Proven via Mock Adapters.
2. **No Image Generation / Video Processing:** Pipeline focuses on text, formatting, hooks, and hashtags.
3. **No Multi-user Permission Roles:** Single editor review workflow.
