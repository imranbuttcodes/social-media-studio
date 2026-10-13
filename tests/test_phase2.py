import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.schemas import validate_platform_constraints
from unittest.mock import AsyncMock, patch

client = TestClient(app)


def test_post_ingestion_and_generation():
    """
    Tests:
    1. Ingestion of raw Markdown post.
    2. Generation of platform variants (X, LinkedIn, Discord).
    3. Verification that generated variants satisfy their platform constraint profiles.
    """
    post_payload = {
        "title": "Scaling Distributed Systems with Reliable Messaging",
        "content": (
            "Building distributed backends requires managing async queues, network partitions, "
            "and idempotent message processing to prevent duplicate operations."
        )
    }
    #  Ingest post
    ingest_res = client.post("/api/v1/posts", json=post_payload)
    assert ingest_res.status_code == 201
    post_data = ingest_res.json()
    post_id = post_data["id"]
    assert post_data["title"] == post_payload["title"]

    #  Generate variants
    gen_res = client.post(f"/api/v1/posts/{post_id}/generate")
    assert gen_res.status_code == 200
    variants = gen_res.json()
    assert len(variants) == 3

    platforms = {v["platform"] for v in variants}
    assert platforms == {"x", "linkedin", "discord"}

    # Check X variant length <= 280
    x_variant = next(v for v in variants if v["platform"] == "x")
    assert len(x_variant["content"]) <= 280
    assert x_variant["status"] == "draft"


def test_rule_breaking_variant_blocked_gate():
    """
    GATE REQUIREMENT (Phase 2 & Probe 2):
    Proves that a rule-breaking variant is blocked with an error naming the broken rule.
    """
    #  X post exceeding 280 characters
    oversized_x_text = "A" * 310
    bad_x_payload = {
        "platform": "x",
        "content": oversized_x_text,
        "hashtags": ["#Tech"]
    }
    res = client.post("/api/v1/variants/validate-custom", json=bad_x_payload)
    assert res.status_code == 422
    assert "exceeds X limit of 280 characters" in res.text

    # LinkedIn post missing required hashtags (needs at least 3)
    bad_li_payload = {
        "platform": "linkedin",
        "content": "Professional takeaway on system architecture.",
        "hashtags": ["#Tech"]  # Only 1 hashtag, minimum is 3
    }
    res_li = client.post("/api/v1/variants/validate-custom", json=bad_li_payload)
    assert res_li.status_code == 422
    assert "requires at least 3 hashtag(s)" in res_li.text


def test_url_ingestion_with_beautifulsoup():
    """
    Tests URL ingestion and verifies that BeautifulSoup correctly strips
    nav and footer tags while preserving core article content.
    """
    mock_html = """
    <html>
      <body>
        <nav><a href="/">Home</a></nav>
        <article>
          <p>Event-driven systems decouple services through message queues.</p>
        </article>
        <footer><p>Copyright 2026</p></footer>
      </body>
    </html>
    """
    

    async def mock_fetch(url: str):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(mock_html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)

    with patch("app.main.fetch_url_content", side_effect=mock_fetch):
        res = client.post("/api/v1/posts", json={
            "title": "Event Driven Design",
            "source_url": "https://example.com/blog/eda"
        })
        assert res.status_code == 201
        data = res.json()
        assert "Event-driven systems decouple services" in data["content"]
        assert "Home" not in data["content"]
        assert "Copyright" not in data["content"]
