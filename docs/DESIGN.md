# Design Document: Social Media Studio

## 1. Problem Statement
Content creators and marketing teams frequently publish long-form blog articles and need to distribute them across multiple social media platforms (X/Twitter, LinkedIn, Discord, and potentially Telegram in future work). 

Manually crafting tailored versions is time-consuming, and naive automated posting systems present critical operational risks:
1. **Rule Violations:** Different platforms enforce strict, distinct constraints (e.g., character limits, hashtag formatting, conversational vs professional tone).
2. **Unreviewed Content Leaks:** Automated drafts must never bypass human editorial review.
3. **Double-Posting Glitches:** Network timeouts and worker retries often publish identical posts multiple times to client feeds.
4. **Fragile Scheduling:** Memory-based schedulers lose pending campaigns when workers restart or deploy.

**Social Media Studio** solves this with automated variant generation, constraint validation, a gated review workflow, durable SQLite-backed scheduling, and an adapter publishing layer with idempotency guarantees.

---

## 2. Platform Constraint Profiles

| Platform | Max Character Length | Min / Max Hashtags | Tone / Formatting Rules |
|---|---|---|---|
| **X (Twitter)** | 280 characters | 1 to 3 hashtags | Punchy, engaging hook, short sentences. |
| **LinkedIn** | 3,000 characters | 3 to 10 hashtags | Professional, structured paragraphs, career / industry takeaway. |
| **Discord** | 2,000 characters | 0 to 2 hashtags | Direct community announcement with Markdown links and emojis. |
| **Telegram** | 4,096 characters | 0 to 3 hashtags | Telegram channel announcement constraints are defined in schemas only. |

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
* `post_id` (VARCHAR, Foreign Key -> `posts.id`, Indexed)
* `platform` (VARCHAR) — `x`, `linkedin`, `discord`, `telegram` (schema-valid, but see adapter support below)
* `content` (TEXT, Non-null)
* `hashtags` (TEXT, JSON array of strings)
* `status` (VARCHAR) — `draft`, `approved`, `rejected`, `published`
* `review_notes` (TEXT, Nullable)
* `created_at` (TIMESTAMP)
* `updated_at` (TIMESTAMP)

### `schedule_slots`
* `id` (VARCHAR / UUID, Primary Key)
* `variant_id` (VARCHAR, Foreign Key -> `variants.id`, Indexed)
* `scheduled_time` (TIMESTAMP, Indexed)
* `idempotency_key` (VARCHAR, Unique, Indexed)
* `status` (VARCHAR) — `pending`, `processing`, `completed`, `failed`

### `publish_attempts` (Publish History)
* `id` (VARCHAR / UUID, Primary Key)
* `slot_id` (VARCHAR, Foreign Key -> `schedule_slots.id`, Indexed)
* `adapter_name` (VARCHAR) — currently mock adapter names such as `mock_x`, `mock_linkedin`, `mock_discord`
* `status` (VARCHAR) — `success`, `failed`
* `response_data` (TEXT, Nullable — contains message ID / preview)
* `attempted_at` (TIMESTAMP)

---

## 4. Publisher Adapter Architecture

```python
from abc import ABC, abstractmethod
from typing import Dict, Any

class SocialPublisher(ABC):
    @abstractmethod
    async def publish(self, content: str, hashtags: list[str], idempotency_key: str) -> Dict[str, Any]:
        """
        Publishes content to the designated platform.
        Must guarantee idempotency: calling publish with the same
        idempotency_key must never produce duplicate messages.
        """
        pass
```

### Implementations (current):
1. `MockXPublisher`
2. `MockLinkedInPublisher`
3. `MockDiscordPublisher`

The factory (`app/publishers/factory.py`) uses a hard-coded registry for `x`, `linkedin`, and `discord`.  
`ACTIVE_REAL_PUBLISHER` is not currently used by runtime code.

### Telegram status
- Telegram exists in platform validation schemas.
- The deterministic generator does not create Telegram variants.
- The publisher factory has no Telegram adapter registration.
- Result: Telegram variants can validate, but cannot currently be published.

---

## 5. API Surface

* `GET /health`
* `POST /api/v1/posts` — Ingest article via URL or raw Markdown.
* `GET /api/v1/posts/{post_id}` — Retrieve a stored post.
* `POST /api/v1/posts/{post_id}/generate` — Generate draft platform variants.
* `POST /api/v1/variants/validate-custom` — Validate manual variant payload against platform constraints.
* `GET /api/v1/variants` — List variants (optional `?status=` filter).
* `GET /api/v1/variants/{variant_id}` — Retrieve a variant.
* `PATCH /api/v1/variants/{variant_id}/status` — Apply review-state transition.
* `POST /api/v1/variants/{variant_id}/publish` — Publish approved variant through registered adapter.
* `GET /api/v1/variants/{variant_id}/attempts` — Variant-scoped publish audit trail.
* `POST /api/v1/variants/{variant_id}/schedule` — Schedule an approved variant.
* `GET /api/v1/schedule` — List schedule slots.
* `DELETE /api/v1/schedule/{job_id}` — Delete a scheduled slot/job.

---

## 6. Durable Scheduling & Idempotency Strategy
* Scheduling runs via `APScheduler` backed by SQLite storage (`apscheduler_jobs` table). Pending jobs survive server restarts.
* Each publish action uses an `idempotency_key = f"{variant_id}_{scheduled_time}"`.
* Before firing, the publisher checks `publish_attempts`. If a success record exists for that key, publishing is bypassed safely.

---

## 7. Generation Behavior (Current)
* `app/services/generator.py` is deterministic and template-driven.
* It currently generates variants only for `x`, `linkedin`, and `discord`.
* `GEMINI_API_KEY` is present in environment templates but is currently unused by the generator/runtime.

---

## 8. Explicit Non-Goals
1. **No Real Twitter/X or LinkedIn OAuth Tokens:** High-friction paid API tiers are avoided; these platforms are proven via robust Mock Adapters.
2. **No Real Discord or Telegram Publishing in Current Implementation:** Real webhook/bot adapters are not currently implemented in this repository snapshot.
3. **No Image Generation / Video Processing:** The pipeline strictly focuses on text, formatting, hooks, and hashtags.
4. **No Complex Multi-user Permission Roles:** Focuses on the single editor review workflow.
