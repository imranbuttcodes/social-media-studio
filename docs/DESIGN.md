# Design Document: Social Media Studio

## 1. Problem Statement
Content creators and marketing teams frequently publish long-form blog articles and need to distribute them across multiple social media platforms (X/Twitter, LinkedIn, Discord/Telegram). 

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
| **LinkedIn** | 3,000 characters | 3 to 5 hashtags | Professional, structured paragraphs, career / industry takeaway. |
| **Discord / Telegram** | 2,000 characters | 0 to 2 hashtags | Direct community announcement with Markdown links and emojis. |

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
* `platform` (VARCHAR) — `x`, `linkedin`, `discord`, `telegram`
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
* `adapter_name` (VARCHAR) — `discord`, `telegram`, `mock_x`, `mock_linkedin`
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
    async def publish(self, content: str, idempotency_key: str) -> Dict[str, Any]:
        """
        Publishes content to the designated platform.
        Must guarantee idempotency: calling publish with the same
        idempotency_key must never produce duplicate messages.
        """
        pass
```

### Implementations:
1. `DiscordWebhookPublisher`: Publishes real messages via Discord Webhook HTTP POST.
2. `TelegramBotPublisher`: Publishes real messages to a Telegram channel/chat.
3. `MockXPublisher`: Validates payload and stores simulated tweet preview in DB.
4. `MockLinkedInPublisher`: Validates payload and stores simulated post preview in DB.

*Swapping adapters is controlled through configuration (`ACTIVE_REAL_PUBLISHER`), requiring zero changes to core publishing code.*

---

## 5. API Surface

* `POST /api/v1/posts` — Ingest article via URL or raw Markdown.
* `POST /api/v1/posts/{id}/generate` — Generate platform variants using constraint validation.
* `GET /api/v1/variants` — List variants (filter by status: `draft`, `approved`, etc.).
* `PATCH /api/v1/variants/{id}/status` — Review workflow: transition variant to `approved` or `rejected`.
* `POST /api/v1/variants/{id}/schedule` — Schedule an approved variant. *Returns 400 Bad Request if variant is still `draft` or `rejected`.*
* `GET /api/v1/history` — View full publish history and delivered message previews.

---

## 6. Durable Scheduling & Idempotency Strategy
* Scheduling runs via `APScheduler` backed by SQLite storage (`apscheduler_jobs` table). Pending jobs survive server restarts.
* Each publish action uses an `idempotency_key = f"{variant_id}_{scheduled_time}"`.
* Before firing, the publisher checks `publish_attempts`. If a success record exists for that key, publishing is bypassed safely.

---

## 7. Explicit Non-Goals
1. **No Real Twitter/X or LinkedIn OAuth Tokens:** High-friction paid API tiers are avoided; these platforms are proven via robust Mock Adapters.
2. **No Image Generation / Video Processing:** The pipeline strictly focuses on text, formatting, hooks, and hashtags.
3. **No Complex Multi-user Permission Roles:** Focuses on the single editor review workflow.
