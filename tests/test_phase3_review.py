import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _create_post_and_generate():
    """Helper: creates a post and generates variants, returns the variant list."""
    post_res = client.post("/api/v1/posts", json={
        "title": "Resilient Microservices with Circuit Breakers",
        "content": (
            "Circuit breakers prevent cascading failures in distributed systems. "
            "They monitor downstream calls and trip when error rates exceed a threshold. "
            "This pattern improves system resilience and user experience."
        )
    })
    assert post_res.status_code == 201
    post_id = post_res.json()["id"]

    gen_res = client.post(f"/api/v1/posts/{post_id}/generate")
    assert gen_res.status_code == 200
    variants = gen_res.json()
    assert len(variants) >= 1
    return variants


# --- Listing ---

def test_list_all_variants():
    """GET /api/v1/variants returns all variants without any filter."""
    variants = _create_post_and_generate()
    res = client.get("/api/v1/variants")
    assert res.status_code == 200
    data = res.json()
    # Should have at least the variants we just created
    assert len(data) >= len(variants)


def test_list_variants_filtered_by_status():
    """GET /api/v1/variants?status=draft returns only draft variants."""
    _create_post_and_generate()
    res = client.get("/api/v1/variants", params={"status": "draft"})
    assert res.status_code == 200
    data = res.json()
    for v in data:
        assert v["status"] == "draft"


def test_list_variants_invalid_status_filter():
    """GET /api/v1/variants?status=banana returns 400."""
    res = client.get("/api/v1/variants", params={"status": "banana"})
    assert res.status_code == 400
    assert "Invalid status filter" in res.json()["detail"]


# --- Single Variant Lookup ---

def test_get_single_variant():
    """GET /api/v1/variants/{id} returns the correct variant."""
    variants = _create_post_and_generate()
    variant_id = variants[0]["id"]

    res = client.get(f"/api/v1/variants/{variant_id}")
    assert res.status_code == 200
    assert res.json()["id"] == variant_id


def test_get_nonexistent_variant():
    """GET /api/v1/variants/{bad_id} returns 404."""
    res = client.get("/api/v1/variants/nonexistent-id-12345")
    assert res.status_code == 404


# --- Review Status Transitions ---

def test_approve_draft_variant():
    """draft → approved is a valid transition."""
    variants = _create_post_and_generate()
    variant_id = variants[0]["id"]
    assert variants[0]["status"] == "draft"

    res = client.patch(f"/api/v1/variants/{variant_id}/status", json={
        "status": "approved",
        "review_notes": "Looks great, approved for publishing."
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "approved"
    assert data["review_notes"] == "Looks great, approved for publishing."


def test_reject_draft_variant():
    """draft → rejected is a valid transition."""
    variants = _create_post_and_generate()
    variant_id = variants[0]["id"]

    res = client.patch(f"/api/v1/variants/{variant_id}/status", json={
        "status": "rejected",
        "review_notes": "Tone is too casual for LinkedIn."
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "rejected"
    assert data["review_notes"] == "Tone is too casual for LinkedIn."


def test_revert_approved_to_draft():
    """approved → draft is valid (send back for rework)."""
    variants = _create_post_and_generate()
    variant_id = variants[0]["id"]

    # First approve
    client.patch(f"/api/v1/variants/{variant_id}/status", json={"status": "approved"})

    # Then revert to draft
    res = client.patch(f"/api/v1/variants/{variant_id}/status", json={
        "status": "draft",
        "review_notes": "Needs more detail on circuit breaker thresholds."
    })
    assert res.status_code == 200
    assert res.json()["status"] == "draft"


def test_block_rejected_to_approved():
    """
    GATE REQUIREMENT (Phase 3):
    rejected → approved is NOT allowed. Must go through draft first.
    """
    variants = _create_post_and_generate()
    variant_id = variants[0]["id"]

    # Reject it first
    client.patch(f"/api/v1/variants/{variant_id}/status", json={"status": "rejected"})

    # Try to jump directly to approved
    res = client.patch(f"/api/v1/variants/{variant_id}/status", json={"status": "approved"})
    assert res.status_code == 400
    assert "Cannot transition" in res.json()["detail"]
    assert "'rejected'" in res.json()["detail"]


def test_block_transition_on_nonexistent_variant():
    """PATCH on a nonexistent variant returns 404."""
    res = client.patch("/api/v1/variants/does-not-exist/status", json={"status": "approved"})
    assert res.status_code == 404


def test_review_notes_persist_across_transitions():
    """Review notes from the latest transition overwrite previous notes."""
    variants = _create_post_and_generate()
    variant_id = variants[0]["id"]

    # Reject with a note
    client.patch(f"/api/v1/variants/{variant_id}/status", json={
        "status": "rejected",
        "review_notes": "First review: needs work."
    })

    # Revert to draft with a new note
    res = client.patch(f"/api/v1/variants/{variant_id}/status", json={
        "status": "draft",
        "review_notes": "Second review: sending back for edits."
    })
    assert res.json()["review_notes"] == "Second review: sending back for edits."
