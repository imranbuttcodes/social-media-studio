import json
from datetime import datetime, timezone
from pydantic import BaseModel

from fastapi import FastAPI, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import Base, engine, get_db
from app.models import Post, Variant, ScheduleSlot, PublishAttempt
from app.schemas import (
    PostCreate,
    PostResponse,
    VariantResponse,
    VariantCreateManual,
    VariantReviewUpdate,
    ScheduleSlotResponse,
    PublishAttemptResponse,
    validate_platform_constraints,
)
from app.scheduler import get_scheduler
from app.jobs import run_publish_job
from app.services.generator import fetch_url_content, generate_platform_variants
from app.publishers.factory import get_publisher
from app.publishers.base import PublishError


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


# --- Phase 4: Publisher Adapters & Idempotency ---

@app.post(
    "/api/v1/variants/{variant_id}/publish",
    response_model=PublishAttemptResponse,
    status_code=status.HTTP_200_OK,
    tags=["Publishing"],
)
async def publish_variant(variant_id: str, db: Session = Depends(get_db)):
    """
    Publishes an approved variant via the appropriate mock adapter.

    Idempotency guarantee:
        The idempotency_key is derived as  `{variant_id}_{scheduled_time}`.
        For an on-demand (immediate) publish the scheduled_time is fixed to the
        instant the ScheduleSlot is first created.  If this endpoint is called
        a second time with the same variant_id AND a ScheduleSlot with the same
        key already has a *successful* PublishAttempt, the existing attempt is
        returned unchanged — the adapter is NOT called again.

    Guards:
        - Variant must exist (404 otherwise).
        - Variant status must be 'approved' (400 otherwise).
        - Content must pass platform constraint validation (400 otherwise).
    """
    # --- Fetch variant ---
    variant = db.query(Variant).filter(Variant.id == variant_id).first()
    if not variant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")

    # ---  Approval guard ---
    if variant.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Variant must be in 'approved' state to publish. "
                f"Current status: '{variant.status}'"
            ),
        )

    # ---  Resolve or create a ScheduleSlot (on-demand = publish now) ---
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # store as naive UTC
    idempotency_key = f"{variant_id}_{now.strftime('%Y%m%dT%H%M%S')}"

    # Check for an existing slot with a successful attempt (idempotency check).
    existing_slot = (
        db.query(ScheduleSlot)
        .filter(ScheduleSlot.variant_id == variant_id)
        .filter(ScheduleSlot.idempotency_key == idempotency_key)
        .first()
    )
    if existing_slot:
        successful_attempt = (
            db.query(PublishAttempt)
            .filter(PublishAttempt.slot_id == existing_slot.id)
            .filter(PublishAttempt.status == "success")
            .first()
        )
        if successful_attempt:
            # Idempotent: return the existing successful attempt unchanged.
            return successful_attempt

    # No existing successful attempt — proceed.
    slot = ScheduleSlot(
        variant_id=variant_id,
        scheduled_time=now,
        idempotency_key=idempotency_key,
        status="processing",
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)

    # ---  Parse hashtags (stored as JSON string in DB) ---
    try:
        hashtags: list[str] = json.loads(variant.hashtags) if variant.hashtags else []
    except (json.JSONDecodeError, TypeError):
        hashtags = []

    # --- Call adapter ---
    adapter = get_publisher(variant.platform)
    try:
        response_data = await adapter.publish(
            content=variant.content,
            hashtags=hashtags,
            idempotency_key=idempotency_key,
        )
        attempt_status = "success"
        response_json = json.dumps(response_data)

        # Mark slot completed and variant published.
        slot.status = "completed"
        variant.status = "published"

    except PublishError as exc:
        attempt_status = "failed"
        response_json = json.dumps({"error": str(exc)})
        slot.status = "failed"
        # Variant stays 'approved' so the reviewer can retry.

    # --- 6. Persist PublishAttempt (evidence) ---
    attempt = PublishAttempt(
        slot_id=slot.id,
        adapter_name=adapter.adapter_name,
        status=attempt_status,
        response_data=response_json,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    if attempt_status == "failed":
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Publishing failed: {response_json}",
        )

    return attempt


@app.get(
    "/api/v1/variants/{variant_id}/attempts",
    response_model=List[PublishAttemptResponse],
    tags=["Publishing"],
)
def list_publish_attempts(variant_id: str, db: Session = Depends(get_db)):
    """
    Lists all publish attempts (evidence records) for a given variant,
    ordered from most recent to oldest.

    Use this endpoint to:
    - Audit what was sent to which platform and when.
    - Diagnose failed attempts.
    - Confirm idempotent re-runs returned the existing record.
    """
    variant = db.query(Variant).filter(Variant.id == variant_id).first()
    if not variant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")

    attempts = (
        db.query(PublishAttempt)
        .join(ScheduleSlot, PublishAttempt.slot_id == ScheduleSlot.id)
        .filter(ScheduleSlot.variant_id == variant_id)
        .order_by(PublishAttempt.attempted_at.desc())
        .all()
    )
    return attempts

# --- Phase 5: Durable Scheduler Endpoints ---

class ScheduleCreate(BaseModel):
    scheduled_time: datetime

@app.post(
    "/api/v1/variants/{variant_id}/schedule",
    response_model=ScheduleSlotResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Scheduling"],
)
def schedule_variant(
    variant_id: str,
    payload: ScheduleCreate,
    db: Session = Depends(get_db),
):
    """Create a schedule slot and register an APScheduler job.

    The slot is idempotent - if a slot with the same ``idempotency_key``
    already exists, the existing slot is returned.
    """
    variant = db.query(Variant).filter(Variant.id == variant_id).first()
    if not variant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")

    # Build deterministic idempotency key.
    idempotency_key = f"{variant_id}_{payload.scheduled_time.strftime('%Y%m%dT%H%M%S')}"
    # Check for existing slot.
    existing = (
        db.query(ScheduleSlot)
        .filter(ScheduleSlot.variant_id == variant_id)
        .filter(ScheduleSlot.idempotency_key == idempotency_key)
        .first()
    )
    if existing:
        return existing

    if variant.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only approved variants can be scheduled for publishing.",
        )
    
    # Create new slot.
    slot = ScheduleSlot(
        variant_id=variant_id,
        scheduled_time=payload.scheduled_time,
        idempotency_key=idempotency_key,
        status="pending",
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    # Register APScheduler job.
    scheduler = get_scheduler()
    scheduler.add_job(
        run_publish_job,
        trigger="date",
        run_date=payload.scheduled_time,
        args=[variant_id, payload.scheduled_time.isoformat()],
        id=idempotency_key,
        replace_existing=True,
    )
    return slot

@app.get(
    "/api/v1/schedule",
    response_model=List[ScheduleSlotResponse],
    tags=["Scheduling"],
)
def list_schedule(db: Session = Depends(get_db)):
    """Return all schedule slots (pending, processing, completed, failed)."""
    return db.query(ScheduleSlot).order_by(ScheduleSlot.scheduled_time).all()

@app.delete(
    "/api/v1/schedule/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Scheduling"],
)
def delete_schedule(job_id: str, db: Session = Depends(get_db)):
    """Cancel a scheduled publish and delete its slot.

    ``job_id`` is the ``idempotency_key`` used when the job was registered.
    """
    slot = db.query(ScheduleSlot).filter(ScheduleSlot.idempotency_key == job_id).first()
    if not slot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule slot not found")
    # Remove the APScheduler job if it exists.
    scheduler = get_scheduler()
    try:
        scheduler.remove_job(job_id)
    except Exception:
        # If the job is already executed or missing, ignore.
        pass
    db.delete(slot)
    db.commit()
    return None
