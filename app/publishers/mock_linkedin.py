"""
Mock LinkedIn Publisher Adapter.

Simulates publishing a thought-leadership post on LinkedIn.
No external HTTP calls are made; responses are deterministic.

Platform constraints enforced (from PLATFORM_CONSTRAINTS):
  - Max character length  : 3000
  - Min hashtags          : 3
  - Max hashtags          : 10
"""

import uuid
from typing import Dict, Any

from app.publishers.base import SocialPublisher, PublishError
from app.schemas import validate_platform_constraints


class MockLinkedInPublisher(SocialPublisher):
    """Mock adapter for LinkedIn. No real API calls are made."""

    adapter_name = "mock_linkedin"

    async def publish(
        self,
        content: str,
        hashtags: list[str],
        idempotency_key: str,
    ) -> Dict[str, Any]:
        """
        Validates the content against LinkedIn constraints and simulates a post.

        Args:
            content:         Post body (must be ≤ 3000 characters).
            hashtags:        List of hashtag strings (3–10 tags required for LinkedIn).
            idempotency_key: Unique key for this attempt.

        Returns:
            dict with platform_message_id, preview_url, and adapter name.

        Raises:
            PublishError: If content violates LinkedIn platform constraints.
        """
        # --- Pre-publish constraint validation ---
        try:
            validate_platform_constraints("linkedin", content, hashtags)
        except ValueError as exc:
            raise PublishError(f"[mock_linkedin] Constraint violation: {exc}") from exc

        # --- Simulate a successful LinkedIn post ---
        mock_message_id = f"mock-li-{uuid.uuid4().hex[:10]}"
        return {
            "platform_message_id": mock_message_id,
            "preview_url": f"https://www.linkedin.com/feed/update/{mock_message_id}/",
            "adapter": self.adapter_name,
            "idempotency_key": idempotency_key,
            "character_count": len(content),
            "hashtag_count": len(hashtags),
        }
