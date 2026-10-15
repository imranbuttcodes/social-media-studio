"""
Job runner for APScheduler – executes a publish at the scheduled time.

The logic mirrors the on‑demand ``POST /api/v1/variants/{id}/publish``
endpoint (Phase 4) but is invoked by the background scheduler.  It:
Loads the variant and verifies it is still ``approved``.
Re‑creates the idempotency key (``{variant_id}_{scheduled_time}``).
Checks for an existing successful ``PublishAttempt`` – if found, the job
   exits early (idempotent behaviour).
Creates a ``ScheduleSlot`` if one does not already exist (this can happen
   if the scheduler lost the row for any reason).
Calls the appropriate publisher adapter via ``get_publisher``.
Persists a ``PublishAttempt`` record (the "evidence" of the publish).
Updates the variant status to ``published`` on success, or leaves it as
   ``approved`` on failure so a reviewer can retry.

All database interactions use a fresh ``SessionLocal`` from ``app.database``
so the job can run independently of any request‑scoped session.
"""

import json
import asyncio

from datetime import datetime
from typing import List

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Variant, ScheduleSlot, PublishAttempt
from app.publishers.factory import get_publisher
from app.publishers.base import PublishError
from app.schemas import validate_platform_constraints


def _load_hashtags(variant: Variant) -> List[str]:
    """Decode the JSON‑encoded ``hashtags`` column safely.

    The column may be ``NULL`` or contain malformed JSON – in those cases we
    simply return an empty list so the adapter receives a well‑formed value.
    """
    try:
        return json.loads(variant.hashtags) if variant.hashtags else []
    except (json.JSONDecodeError, TypeError):
        return []


def run_publish_job(variant_id: str, scheduled_iso: str) -> None:
    """APScheduler entry point for a scheduled publish.

    Args:
        variant_id:   UUID of the ``Variant`` to publish.
        scheduled_iso: ISO‑8601 string (UTC) indicating the time the job was
                       originally scheduled for.  It is used to rebuild the
                       ``idempotency_key`` so that repeated executions are
                       recognised as duplicates.
    """
    db: Session = SessionLocal()
    try:

        # Load variant and ensure it is still approvable.

        variant = db.query(Variant).filter(Variant.id == variant_id).first()
        if not variant:
            # Variant has been deleted – nothing to do.
            return
        if variant.status != "approved":
            # Only approved variants may be published.
            return

        # Re‑create the idempotency key used when the slot was created.

        try:
            scheduled_dt = datetime.fromisoformat(scheduled_iso)
        except ValueError:
            # Bad datetime – abort the job silently (scheduler will log).
            return
        idempotency_key = f"{variant_id}_{scheduled_dt.strftime('%Y%m%dT%H%M%S')}"

        # Retrieve (or create) the ScheduleSlot for this run.

        slot = (
            db.query(ScheduleSlot)
            .filter(ScheduleSlot.variant_id == variant_id)
            .filter(ScheduleSlot.idempotency_key == idempotency_key)
            .first()
        )
        if not slot:
            slot = ScheduleSlot(
                variant_id=variant_id,
                scheduled_time=scheduled_dt,
                idempotency_key=idempotency_key,
                status="processing",
            )
            db.add(slot)
            db.commit()
            db.refresh(slot)

        
        # Idempotency guard – if a successful attempt already exists,
        #    we stop here to avoid duplicate posts.
        
        successful = (
            db.query(PublishAttempt)
            .filter(PublishAttempt.slot_id == slot.id)
            .filter(PublishAttempt.status == "success")
            .first()
        )
        if successful:
            return

        # Parse hashtags and invoke the appropriate publisher.

        hashtags = _load_hashtags(variant)
        adapter = get_publisher(variant.platform)

        try:
            # Ensure the content still satisfies platform constraints.
            validate_platform_constraints(variant.platform, variant.content, hashtags)
            adapter_response = asyncio.run(
                                adapter.publish(
                                content=variant.content,
                                hashtags=hashtags,
                                idempotency_key=idempotency_key,
                            )
                        )
            attempt_status = "success"
            response_json = json.dumps(adapter_response)
            # Mark slot completed and variant as published.
            slot.status = "completed"
            variant.status = "published"
        except (PublishError, ValueError) as exc:
            # Any validation or adapter failure is recorded as a failed attempt.
            attempt_status = "failed"
            response_json = json.dumps({"error": str(exc)})
            slot.status = "failed"
            # Keep the variant in ``approved`` so a reviewer can retry later.

        # Persist the PublishAttempt (the evidence record).

        attempt = PublishAttempt(
            slot_id=slot.id,
            adapter_name=adapter.adapter_name,
            status=attempt_status,
            response_data=response_json,
        )
        db.add(attempt)
        db.commit()
        db.refresh(attempt)
    finally:
        db.close()
