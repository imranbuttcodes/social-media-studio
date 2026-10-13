"""
Abstract base for all publisher adapters.

Every platform adapter (mock or real) must inherit from SocialPublisher and
implement the `publish` coroutine.  The adapter is responsible for:
  - Communicating with the external platform (or simulating it for mocks).
  - Returning a dict with at minimum:
      {
          "platform_message_id": str,   # ID assigned by the platform
          "preview_url": str,           # Direct link to the published content
          "adapter": str,               # Name of this adapter, e.g. "mock_x"
      }
  - Raising an exception (PublishError) on any unrecoverable failure so that
    the calling code can record a failed PublishAttempt.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class PublishError(Exception):
    """Raised by an adapter when publishing fails unrecoverably."""


class SocialPublisher(ABC):
    """
    Abstract base class that every platform adapter must implement.

    Attributes:
        adapter_name (str): Human-readable identifier stored in PublishAttempt rows.
    """

    # Subclasses must override this with a unique identifier, e.g. "mock_x".
    adapter_name: str = "base"

    @abstractmethod
    async def publish(
        self,
        content: str,
        hashtags: list[str],
        idempotency_key: str,
    ) -> Dict[str, Any]:
        """
        Publish content to the target platform.

        Args:
            content:          The text body to publish.
            hashtags:         List of hashtag strings (without '#' prefix).
            idempotency_key:  Unique key for this publish attempt.
                              Adapters may optionally forward this to the platform.

        Returns:
            A dict describing the successful outcome.  Must include at minimum:
            {
                "platform_message_id": str,
                "preview_url": str,
                "adapter": str,
            }

        Raises:
            PublishError: On any unrecoverable failure.
        """
