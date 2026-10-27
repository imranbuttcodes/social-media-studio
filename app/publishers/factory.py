"""
Publisher Factory.

Resolves the correct SocialPublisher adapter for a given platform name.

Usage:
    from app.publishers.factory import get_publisher

    adapter = get_publisher("x")        # → MockXPublisher
    adapter = get_publisher("linkedin") # → MockLinkedInPublisher
    adapter = get_publisher("discord")  # → MockDiscordPublisher
    adapter = get_publisher("telegram") # → MockDiscordPublisher

Design decision:
    All platforms use mock adapters. X and LinkedIn avoid paid API tiers by design.
    Discord and Telegram mocks simulate real delivery with deterministic responses.
    Swapping to a real adapter in a future phase requires changing this factory only —
    zero changes needed in any endpoint or job runner.
"""

from app.publishers.base import SocialPublisher
from app.publishers.mock_x import MockXPublisher
from app.publishers.mock_linkedin import MockLinkedInPublisher
from app.publishers.mock_discord import MockDiscordPublisher


def get_publisher(platform: str) -> SocialPublisher:
    """
    Returns an instantiated mock publisher adapter for the requested platform.

    Args:
        platform: Lowercase platform name ("x", "linkedin", "discord", "telegram").

    Returns:
        A concrete SocialPublisher instance ready to call `.publish(...)` on.

    Raises:
        ValueError: If the platform has no registered adapter.
    """
    platform = platform.lower()

    if platform == "x":
        return MockXPublisher()

    if platform == "linkedin":
        return MockLinkedInPublisher()

    if platform in ("discord", "telegram"):
        return MockDiscordPublisher()

    supported = ["x", "linkedin", "discord", "telegram"]
    raise ValueError(
        f"No publisher adapter registered for platform '{platform}'. "
        f"Supported platforms: {supported}"
    )
