"""
Mock Discord Publisher Adapter.

Simulates sending a community announcement to a Discord channel.
No external HTTP calls are made; responses are deterministic.

Platform constraints enforced (from PLATFORM_CONSTRAINTS):
  - Max character length  : 2000
  - Min hashtags          : 0
  - Max hashtags          : 2
"""

import uuid
from typing import Dict, Any

from app.publishers.base import SocialPublisher, PublishError
from app.schemas import validate_platform_constraints


class MockDiscordPublisher(SocialPublisher):
    """Mock adapter for Discord. No real API calls are made."""

    adapter_name = "mock_discord"

    async def publish(
        self,
        content: str,
        hashtags: list[str],
        idempotency_key: str,
    ) -> Dict[str, Any]:
        """
        Validates content against Discord constraints and simulates sending a message.

        Args:
            content:         Message body (must be ≤ 2000 characters).
            hashtags:        List of hashtag strings (0–2 allowed for Discord).
            idempotency_key: Unique key for this attempt.

        Returns:
            dict with platform_message_id, preview_url, and adapter name.

        Raises:
            PublishError: If content violates Discord platform constraints.
        """
        # --- Pre-publish constraint validation ---
        try:
            validate_platform_constraints("discord", content, hashtags)
        except ValueError as exc:
            raise PublishError(f"[mock_discord] Constraint violation: {exc}") from exc

        # --- Simulate a successful Discord message ---
        mock_message_id = f"mock-dc-{uuid.uuid4().hex[:10]}"
        return {
            "platform_message_id": mock_message_id,
            "preview_url": f"https://discord.com/channels/mock_server/mock_channel/{mock_message_id}",
            "adapter": self.adapter_name,
            "idempotency_key": idempotency_key,
            "character_count": len(content),
            "hashtag_count": len(hashtags),
        }
