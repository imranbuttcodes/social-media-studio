from fastapi import FastAPI, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import Base, engine, get_db
from app.models import Post, Variant
from app.schemas import (
    PostCreate,
    PostResponse,
    VariantResponse,
    VariantCreateManual,
    VariantReviewUpdate,
    validate_platform_constraints
)
from app.services.generator import fetch_url_content, generate_platform_variants


# --- Review State Machine ---
# Defines which status transitions are allowed.
# Key = current status, Value = set of statuses it can move to.
ALLOWED_TRANSITIONS = {
    "draft":    {"approved", "rejected"},
    "approved": {"draft", "rejected"},
    "rejected": {"draft"},
}

# Initialize database schema tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Social Media Studio API",
    description="Multi-platform campaign generator, review workflow, and scheduled publishing service.",
    version="1.0.0"
)


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok", "service": "social-media-studio"}


# --- Phase 2: Post Ingestion & Generation ---

@app.post("/api/v1/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED, tags=["Ingestion"])
async def create_post(payload: PostCreate, db: Session = Depends(get_db)):
    """
    Ingests a blog post as raw Markdown or fetches from a URL.
    The stored post acts as the single source of truth for all campaign generation.
    """
    content = payload.content

    # If URL provided and no manual content, fetch external content
    if payload.source_url and not content:
        try:
            content = await fetch_url_content(payload.source_url)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to fetch content from URL: {str(e)}"
            )

    new_post = Post(
        title=payload.title,
        content=content,
        source_url=payload.source_url
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    return new_post


@app.get("/api/v1/posts/{post_id}", response_model=PostResponse, tags=["Ingestion"])
def get_post(post_id: str, db: Session = Depends(get_db)):
    """Retrieves a single stored post."""
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return post


@app.post("/api/v1/posts/{post_id}/generate", response_model=List[VariantResponse], tags=["Generation"])
def generate_variants_for_post(post_id: str, db: Session = Depends(get_db)):
    """
    Generates platform-tailored variants (X, LinkedIn, Discord) from the stored post.
    Each variant is validated against platform constraint profiles and saved as 'draft'.
    """
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    generated_data = generate_platform_variants(post.title, post.content)
    created_variants = []

    for item in generated_data:
        variant = Variant(
            post_id=post.id,
            platform=item["platform"],
            content=item["content"],
            hashtags=item["hashtags"],
            status="draft"
        )
        db.add(variant)
        created_variants.append(variant)

    db.commit()
    for v in created_variants:
        db.refresh(v)

    return created_variants


@app.post("/api/v1/variants/validate-custom", tags=["Validation"])
def validate_custom_variant(payload: VariantCreateManual):
    """
    Validates any custom or proposed variant content against the platform constraint profile.
    Returns 200 if valid, or 422 with the exact broken rule if invalid.
    """
    return {
        "status": "valid",
        "platform": payload.platform,
        "character_count": len(payload.content),
        "hashtag_count": len(payload.hashtags),
        "message": "Content successfully complies with platform constraint profile."
    }


# --- Phase 3: Review Workflow & Approval Guard ---

@app.get("/api/v1/variants", response_model=List[VariantResponse], tags=["Review"])
def list_variants(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by variant status (draft, approved, rejected)"),
    db: Session = Depends(get_db)
):
    """
    Lists all variants across every post.
    Optionally filter by status: ?status=draft, ?status=approved, etc.
    """
    query = db.query(Variant)

    if status_filter:
        valid_statuses = {"draft", "approved", "rejected", "published"}
        if status_filter not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status filter '{status_filter}'. Must be one of: {sorted(valid_statuses)}"
            )
        query = query.filter(Variant.status == status_filter)

    return query.order_by(Variant.created_at.desc()).all()


@app.get("/api/v1/variants/{variant_id}", response_model=VariantResponse, tags=["Review"])
def get_variant(variant_id: str, db: Session = Depends(get_db)):
    """Retrieves a single variant by ID."""
    variant = db.query(Variant).filter(Variant.id == variant_id).first()
    if not variant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
    return variant


@app.patch("/api/v1/variants/{variant_id}/status", response_model=VariantResponse, tags=["Review"])
def update_variant_status(variant_id: str, payload: VariantReviewUpdate, db: Session = Depends(get_db)):
    """
    Transitions a variant through the review state machine.

    Allowed transitions:
      draft    → approved | rejected
      approved → draft | rejected
      rejected → draft

    Any other transition returns 400 Bad Request.
    Optionally attach review_notes explaining the decision.
    """
    variant = db.query(Variant).filter(Variant.id == variant_id).first()
    if not variant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")

    current = variant.status
    requested = payload.status

    # State machine guard
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if requested not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot transition from '{current}' to '{requested}'. Allowed transitions from '{current}': {sorted(allowed)}"
        )

    variant.status = requested
    if payload.review_notes is not None:
        variant.review_notes = payload.review_notes

    db.commit()
    db.refresh(variant)
    return variant
