"""
test_phase4_publish.py
======================
Phase 4 test suite — Publisher Adapters & Idempotency.

Tests cover:
  1. Happy path: POST /variants/{id}/publish succeeds for each mock platform.
  2. Approval guard: publishing a 'draft' or 'rejected' variant → 400.
  3. Variant-not-found: publishing unknown variant → 404.
  4. Variant status updated to 'published' after a successful publish.
  5. PublishAttempt evidence record created with status='success'.
  6. Audit endpoint: GET /variants/{id}/attempts returns the attempt.
  7. Audit endpoint: unknown variant → 404.

No external network calls are made — all publishing is handled by mock adapters.
"""

import json
import pytest

from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, engine, get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


# Test database setup (in-memory SQLite, isolated per test run)

TEST_DATABASE_URL = "sqlite:///./test_phase4.db"

test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

# Create all tables fresh for this test module.
Base.metadata.create_all(bind=test_engine)

client = TestClient(app)


# Shared helpers

def create_approved_variant(platform: str) -> str:
    """
    Creates a post, generates variants, and approves the variant for the
    requested platform.  Returns the variant_id of the approved variant.
    """
    # Create post
    if platform in ("x",):
        # X content: must be ≤ 280 chars and have 1–3 hashtags
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
        # Discord: ≤ 2000 chars, 0–2 hashtags
        content = "Community update: event-driven systems are now live in our platform!"
        hashtags_str = json.dumps(["update"])

    post_res = client.post("/api/v1/posts", json={"title": f"EDA Post ({platform})", "content": content})
    assert post_res.status_code == 201, post_res.text
    post_id = post_res.json()["id"]

    # 2. Generate variants — we patch the generator so we control the content exactly.
    from unittest.mock import patch

    mock_variants = [
        {"platform": platform, "content": content, "hashtags": hashtags_str}
    ]

    with patch("app.main.generate_platform_variants", return_value=mock_variants):
        gen_res = client.post(f"/api/v1/posts/{post_id}/generate")
    assert gen_res.status_code == 200, gen_res.text
    variants = gen_res.json()
    assert len(variants) == 1
    variant_id = variants[0]["id"]

    # 3. Approve the variant.
    review_res = client.patch(
        f"/api/v1/variants/{variant_id}/status",
        json={"status": "approved", "review_notes": "Approved for Phase 4 test"},
    )
    assert review_res.status_code == 200, review_res.text
    assert review_res.json()["status"] == "approved"

    return variant_id


# Tests

class TestPublishHappyPath:
    """Successful publish for each supported mock platform."""

    def test_publish_x_variant(self):
        variant_id = create_approved_variant("x")
        res = client.post(f"/api/v1/variants/{variant_id}/publish")

        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "success"
        assert data["adapter_name"] == "mock_x"
        # response_data is a JSON string in the DB; verify it contains expected keys.
        response_data = json.loads(data["response_data"])
        assert "platform_message_id" in response_data
        assert response_data["platform_message_id"].startswith("mock-tweet-")

    def test_publish_linkedin_variant(self):
        variant_id = create_approved_variant("linkedin")
        res = client.post(f"/api/v1/variants/{variant_id}/publish")

        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "success"
        assert data["adapter_name"] == "mock_linkedin"
        response_data = json.loads(data["response_data"])
        assert response_data["platform_message_id"].startswith("mock-li-")

    def test_publish_discord_variant(self):
        variant_id = create_approved_variant("discord")
        res = client.post(f"/api/v1/variants/{variant_id}/publish")

        assert res.status_code == 200, res.text
        data = res.json()
        assert data["status"] == "success"
        assert data["adapter_name"] == "mock_discord"
        response_data = json.loads(data["response_data"])
        assert response_data["platform_message_id"].startswith("mock-dc-")


class TestApprovalGuard:
    """Publishing non-approved variants must be rejected."""

    def test_publish_draft_variant_rejected(self):
        """A draft variant cannot be published directly."""
        post_res = client.post(
            "/api/v1/posts",
            json={"title": "Draft Guard Test", "content": "Some test content for the draft variant."},
        )
        post_id = post_res.json()["id"]

        from unittest.mock import patch
        mock_variants = [
            {
                "platform": "x",
                "content": "Draft test tweet content here.",
                "hashtags": json.dumps(["test", "draft"]),
            }
        ]
        with patch("app.main.generate_platform_variants", return_value=mock_variants):
            gen_res = client.post(f"/api/v1/posts/{post_id}/generate")
        variant_id = gen_res.json()[0]["id"]

        # Variant is still 'draft' — publish must fail.
        res = client.post(f"/api/v1/variants/{variant_id}/publish")
        assert res.status_code == 400
        assert "approved" in res.json()["detail"].lower()

    def test_publish_rejected_variant_rejected(self):
        """A rejected variant cannot be published."""
        post_res = client.post(
            "/api/v1/posts",
            json={"title": "Rejected Guard Test", "content": "Content for a rejected variant publish test."},
        )
        post_id = post_res.json()["id"]

        from unittest.mock import patch
        mock_variants = [
            {
                "platform": "x",
                "content": "Rejected tweet content testing.",
                "hashtags": json.dumps(["test", "rejected"]),
            }
        ]
        with patch("app.main.generate_platform_variants", return_value=mock_variants):
            gen_res = client.post(f"/api/v1/posts/{post_id}/generate")
        variant_id = gen_res.json()[0]["id"]

        # Move to rejected.
        client.patch(f"/api/v1/variants/{variant_id}/status", json={"status": "rejected"})

        res = client.post(f"/api/v1/variants/{variant_id}/publish")
        assert res.status_code == 400
        assert "approved" in res.json()["detail"].lower()


class TestVariantStatusAfterPublish:
    """After a successful publish the variant status must be 'published'."""

    def test_variant_status_becomes_published(self):
        variant_id = create_approved_variant("x")
        publish_res = client.post(f"/api/v1/variants/{variant_id}/publish")
        assert publish_res.status_code == 200

        # Fetch the variant and confirm its status.
        get_res = client.get(f"/api/v1/variants/{variant_id}")
        assert get_res.status_code == 200
        assert get_res.json()["status"] == "published"


class TestPublishAttemptEvidence:
    """PublishAttempt record must be persisted and queryable."""

    def test_attempt_record_created(self):
        variant_id = create_approved_variant("linkedin")
        client.post(f"/api/v1/variants/{variant_id}/publish")

        res = client.get(f"/api/v1/variants/{variant_id}/attempts")
        assert res.status_code == 200
        attempts = res.json()
        assert len(attempts) >= 1
        assert attempts[0]["status"] == "success"
        assert attempts[0]["adapter_name"] == "mock_linkedin"

    def test_attempts_for_unknown_variant_returns_404(self):
        res = client.get("/api/v1/variants/non-existent-uuid/attempts")
        assert res.status_code == 404

    def test_attempts_list_is_empty_before_any_publish(self):
        """Before publishing, the attempts list is empty (not a 404)."""
        post_res = client.post(
            "/api/v1/posts",
            json={"title": "Empty Attempts Test", "content": "Content for empty attempts test case."},
        )
        post_id = post_res.json()["id"]

        from unittest.mock import patch
        mock_variants = [
            {"platform": "discord", "content": "Pre-publish discord test message.", "hashtags": json.dumps([])}
        ]
        with patch("app.main.generate_platform_variants", return_value=mock_variants):
            gen_res = client.post(f"/api/v1/posts/{post_id}/generate")
        variant_id = gen_res.json()[0]["id"]

        res = client.get(f"/api/v1/variants/{variant_id}/attempts")
        assert res.status_code == 200
        assert res.json() == []


class TestNotFound:
    """Publish endpoint must return 404 for unknown variant IDs."""

    def test_publish_unknown_variant(self):
        res = client.post("/api/v1/variants/does-not-exist/publish")
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()
