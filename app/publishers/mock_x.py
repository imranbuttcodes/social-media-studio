"""
Mock X (Twitter) Publisher Adapter.

Simulates posting a tweet to X.  No external HTTP calls are made;
all responses are deterministic and safe to run in tests and CI.

Platform constraints enforced (from PLATFORM_CONSTRAINTS):
  - Max character length  : 280
  - Min hashtags          : 1
  - Max hashtags          : 3

The adapter pre-validates constraints before "publishing" so that an invalid
variant never produces a success record in the DB.
"""

import uuid
from typing import Dict, Any

from app.publishers.base import SocialPublisher, PublishError
from app.schemas import validate_platform_constraints


class MockXPublisher(SocialPublisher):
    """Mock adapter for X (formerly Twitter). No real API calls are made."""

    adapter_name = "mock_x"

    async def publish(
        self,
        content: str,
        hashtags: list[str],
        idempotency_key: str,
    ) -> Dict[str, Any]:
        """
        Validates the content against X constraints and simulates a successful post.

        Args:
            content:         Tweet body (must be ≤ 280 characters).
            hashtags:        List of hashtag strings (1–3 tags required for X).
            idempotency_key: Unique key for this attempt (stored in PublishAttempt).

        Returns:
            dict with platform_message_id, preview_url, and adapter name.

        Raises:
            PublishError: If content violates X platform constraints.
        """
        # --- Pre-publish constraint validation ---
        try:
            validate_platform_constraints("x", content, hashtags)
        except ValueError as exc:
            raise PublishError(f"[mock_x] Constraint violation: {exc}") from exc

        # --- Simulate a successful tweet post ---
        mock_message_id = f"mock-tweet-{uuid.uuid4().hex[:10]}"
        return {
            "platform_message_id": mock_message_id,
            "preview_url": f"https://x.com/mock_user/status/{mock_message_id}",
            "adapter": self.adapter_name,
            "idempotency_key": idempotency_key,
            "character_count": len(content),
            "hashtag_count": len(hashtags),
        }
