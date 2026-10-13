"""
Publisher Factory.

Resolves the correct SocialPublisher adapter for a given platform name.

Usage:
    from app.publishers.factory import get_publisher

    adapter = get_publisher("x")          # → MockXPublisher instance
    adapter = get_publisher("linkedin")   # → MockLinkedInPublisher instance
    adapter = get_publisher("discord")    # → MockDiscordPublisher instance

Design decision:
    Right now every platform maps to a *mock* adapter because we have no
    real credentials wired up yet.  In a future phase, this factory can be
    updated to return real adapters (e.g. TweetAdapter, LinkedInOAuthAdapter)
    simply by changing the mapping — zero changes required in the API layer.
"""

from app.publishers.base import SocialPublisher
from app.publishers.mock_x import MockXPublisher
from app.publishers.mock_linkedin import MockLinkedInPublisher
from app.publishers.mock_discord import MockDiscordPublisher


# Registry: platform name → adapter class
# To swap a mock for a real adapter, change the value here only.
_ADAPTER_REGISTRY: dict[str, type[SocialPublisher]] = {
    "x":        MockXPublisher,
    "linkedin": MockLinkedInPublisher,
    "discord":  MockDiscordPublisher,
}


def get_publisher(platform: str) -> SocialPublisher:
    """
    Returns an instantiated publisher adapter for the requested platform.

    Args:
        platform: Lowercase platform name (e.g. "x", "linkedin", "discord").

    Returns:
        A concrete SocialPublisher instance ready to call `.publish(...)` on.

    Raises:
        ValueError: If the platform has no registered adapter.
    """
    platform = platform.lower()
    adapter_class = _ADAPTER_REGISTRY.get(platform)
    if adapter_class is None:
        supported = sorted(_ADAPTER_REGISTRY.keys())
        raise ValueError(
            f"No publisher adapter registered for platform '{platform}'. "
            f"Supported platforms: {supported}"
        )
    return adapter_class()
