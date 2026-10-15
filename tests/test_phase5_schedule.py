"""
test_phase5_schedule.py
=======================
Phase 5 test suite — Durable Scheduler & Evidence.

Tests cover:
  1. Schedule endpoint: POST /variants/{id}/schedule creates a ScheduleSlot.
  2. Approval guard: scheduling a non-approved variant → 400.
  3. Idempotency: scheduling the same time twice returns the same slot.
  4. List schedules: GET /schedule returns all slots.
  5. Cancel schedule: DELETE /schedule/{job_id} removes the slot.
  6. Job runner: run_publish_job creates a PublishAttempt and marks variant published.
  7. Job runner idempotency: running the job twice does not create duplicate attempts.

No external network calls are made — all publishing uses mock adapters.
DB setup is handled by tests/conftest.py (shared test engine + autouse clean_db).
"""

import json
import pytest

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.jobs import run_publish_job

# Import the TestingSessionLocal from conftest so we can patch jobs.SessionLocal
from tests.conftest import TestingSessionLocal


# --- Helpers ---

def _create_approved_variant(client: TestClient, platform: str = "x") -> str:
    """Create a post, generate a variant, approve it, and return the variant_id."""
    if platform == "x":
        content = "Event-driven architecture decouples services through async message queues."
        hashtags_str = json.dumps(["eda", "backend"])
    elif platform == "linkedin":
        content = (
            "Event-driven architecture (EDA) is a software design pattern in which "
            "components communicate by emitting and reacting to events. This approach "
            "decouples producers from consumers, enabling highly scalable and resilient "
            "distributed systems. Teams adopting EDA benefit from independent deployability "
            "and cleaner service boundaries."
        )
        hashtags_str = json.dumps(["eda", "backend", "architecture", "distributed"])
    else:
        content = "Community update: event-driven systems are now live in our platform!"
        hashtags_str = json.dumps(["update"])

    # 1. Create post
    post_res = client.post(
        "/api/v1/posts",
        json={"title": f"Schedule Test ({platform})", "content": content},
    )
    assert post_res.status_code == 201, post_res.text
    post_id = post_res.json()["id"]

    # 2. Generate variant (mock the generator to control content exactly)
    mock_variants = [{"platform": platform, "content": content, "hashtags": hashtags_str}]
    with patch("app.main.generate_platform_variants", return_value=mock_variants):
        gen_res = client.post(f"/api/v1/posts/{post_id}/generate")
    assert gen_res.status_code == 200, gen_res.text
    variant_id = gen_res.json()[0]["id"]

    # 3. Approve the variant via the review endpoint
    review_res = client.patch(
        f"/api/v1/variants/{variant_id}/status",
        json={"status": "approved", "review_notes": "Approved for Phase 5 test"},
    )
    assert review_res.status_code == 200, review_res.text
    assert review_res.json()["status"] == "approved"

    return variant_id


# --- Tests ---


class TestScheduleCreation:
    """POST /variants/{id}/schedule creates a ScheduleSlot."""

    def test_schedule_approved_variant(self, client):
        variant_id = _create_approved_variant(client)
        scheduled_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

        res = client.post(
            f"/api/v1/variants/{variant_id}/schedule",
            json={"scheduled_time": scheduled_time},
        )
        assert res.status_code == 201, res.text
        slot = res.json()
        assert slot["variant_id"] == variant_id
        assert slot["status"] == "pending"
        assert "idempotency_key" in slot
        assert slot["idempotency_key"].startswith(variant_id)

    def test_schedule_nonexistent_variant_returns_404(self, client):
        scheduled_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        res = client.post(
            "/api/v1/variants/does-not-exist/schedule",
            json={"scheduled_time": scheduled_time},
        )
        assert res.status_code == 404

    def test_schedule_draft_variant_rejected(self, client):
        """A draft (non-approved) variant cannot be scheduled."""
        post_res = client.post(
            "/api/v1/posts",
            json={"title": "Draft Schedule Test", "content": "Some test content for draft."},
        )
        post_id = post_res.json()["id"]
        mock_variants = [
            {"platform": "x", "content": "Draft test tweet content.", "hashtags": json.dumps(["test", "draft"])}
        ]
        with patch("app.main.generate_platform_variants", return_value=mock_variants):
            gen_res = client.post(f"/api/v1/posts/{post_id}/generate")
        variant_id = gen_res.json()[0]["id"]

        scheduled_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        res = client.post(
            f"/api/v1/variants/{variant_id}/schedule",
            json={"scheduled_time": scheduled_time},
        )
        assert res.status_code == 400
        assert "approved" in res.json()["detail"].lower()


class TestScheduleIdempotency:
    """Scheduling the same variant at the same time returns the same slot."""

    def test_duplicate_schedule_returns_same_slot(self, client):
        variant_id = _create_approved_variant(client)
        scheduled_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        payload = {"scheduled_time": scheduled_time}

        # First schedule
        res1 = client.post(f"/api/v1/variants/{variant_id}/schedule", json=payload)
        assert res1.status_code == 201
        slot1 = res1.json()

        # Second schedule — same time, same variant → same slot
        res2 = client.post(f"/api/v1/variants/{variant_id}/schedule", json=payload)
        assert res2.status_code == 201
        slot2 = res2.json()

        assert slot2["id"] == slot1["id"]
        assert slot2["idempotency_key"] == slot1["idempotency_key"]


class TestListSchedule:
    """GET /schedule returns all schedule slots."""

    def test_list_empty(self, client):
        res = client.get("/api/v1/schedule")
        assert res.status_code == 200
        assert res.json() == []

    def test_list_after_scheduling(self, client):
        variant_id = _create_approved_variant(client)
        scheduled_time = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        client.post(
            f"/api/v1/variants/{variant_id}/schedule",
            json={"scheduled_time": scheduled_time},
        )

        res = client.get("/api/v1/schedule")
        assert res.status_code == 200
        slots = res.json()
        assert len(slots) >= 1
        assert slots[0]["variant_id"] == variant_id


class TestDeleteSchedule:
    """DELETE /schedule/{job_id} removes the slot and cancels the APScheduler job."""

    def test_cancel_schedule(self, client):
        variant_id = _create_approved_variant(client)
        scheduled_time = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()

        res = client.post(
            f"/api/v1/variants/{variant_id}/schedule",
            json={"scheduled_time": scheduled_time},
        )
        assert res.status_code == 201
        idempotency_key = res.json()["idempotency_key"]

        # Delete schedule
        del_res = client.delete(f"/api/v1/schedule/{idempotency_key}")
        assert del_res.status_code == 204

        # Verify slot is gone
        list_res = client.get("/api/v1/schedule")
        assert list_res.status_code == 200
        remaining = [s for s in list_res.json() if s["idempotency_key"] == idempotency_key]
        assert remaining == []

    def test_cancel_nonexistent_schedule_returns_404(self, client):
        res = client.delete("/api/v1/schedule/no-such-key")
        assert res.status_code == 404


class TestJobRunner:
    """Directly invoke run_publish_job to test the background job logic."""

    def test_job_creates_publish_attempt(self, client):
        """run_publish_job should create a PublishAttempt and mark variant published."""
        variant_id = _create_approved_variant(client)
        scheduled_time = datetime.now(timezone.utc) + timedelta(seconds=1)
        scheduled_iso = scheduled_time.isoformat()

        # Patch SessionLocal in jobs.py to use our test DB
        with patch("app.jobs.SessionLocal", TestingSessionLocal):
            run_publish_job(variant_id, scheduled_iso)

        # Verify a PublishAttempt was created via the API
        res = client.get(f"/api/v1/variants/{variant_id}/attempts")
        assert res.status_code == 200
        attempts = res.json()
        assert len(attempts) >= 1
        assert attempts[0]["status"] == "success"
        assert attempts[0]["adapter_name"] == "mock_x"

        # Verify response_data contains expected keys from the mock adapter
        response_data = json.loads(attempts[0]["response_data"])
        assert "platform_message_id" in response_data
        assert "preview_url" in response_data
        assert response_data["adapter"] == "mock_x"

        # Verify variant status changed to 'published'
        variant_res = client.get(f"/api/v1/variants/{variant_id}")
        assert variant_res.status_code == 200
        assert variant_res.json()["status"] == "published"

    def test_job_idempotency_no_duplicate_attempts(self, client):
        """Running the same job twice should not create a second PublishAttempt."""
        variant_id = _create_approved_variant(client)
        scheduled_time = datetime.now(timezone.utc) + timedelta(seconds=1)
        scheduled_iso = scheduled_time.isoformat()

        with patch("app.jobs.SessionLocal", TestingSessionLocal):
            run_publish_job(variant_id, scheduled_iso)
            # Run a second time — should be idempotent
            run_publish_job(variant_id, scheduled_iso)

        res = client.get(f"/api/v1/variants/{variant_id}/attempts")
        assert res.status_code == 200
        attempts = res.json()
        # Only one attempt should exist (idempotency guard in the job)
        assert len(attempts) == 1

    def test_job_skips_non_approved_variant(self, client):
        """run_publish_job should silently exit if variant is not approved."""
        post_res = client.post(
            "/api/v1/posts",
            json={"title": "Draft Job Test", "content": "Content for job skip test."},
        )
        post_id = post_res.json()["id"]
        mock_variants = [
            {"platform": "x", "content": "Draft tweet for job test.", "hashtags": json.dumps(["test"])}
        ]
        with patch("app.main.generate_platform_variants", return_value=mock_variants):
            gen_res = client.post(f"/api/v1/posts/{post_id}/generate")
        variant_id = gen_res.json()[0]["id"]

        scheduled_iso = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()

        with patch("app.jobs.SessionLocal", TestingSessionLocal):
            run_publish_job(variant_id, scheduled_iso)

        # No attempts should be created — variant was not approved
        res = client.get(f"/api/v1/variants/{variant_id}/attempts")
        assert res.status_code == 200
        assert res.json() == []
