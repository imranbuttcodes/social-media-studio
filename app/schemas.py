from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, model_validator


# --- Platform Constraint Definitions ---
PLATFORM_CONSTRAINTS = {
    "x": {
        "max_length": 280,
        "min_hashtags": 1,
        "max_hashtags": 3,
        "description": "Short, punchy update for X (Twitter)"
    },
    "linkedin": {
        "max_length": 3000,
        "min_hashtags": 3,
        "max_hashtags": 10,
        "description": "Professional, in-depth thought leadership post (expanded hashtag allowance)"
    },
    "discord": {
        "max_length": 2000,
        "min_hashtags": 0,
        "max_hashtags": 2,
        "description": "Community announcement with direct link"
    },
    "telegram": {
        "max_length": 4096,
        "min_hashtags": 0,
        "max_hashtags": 3,
        "description": "Telegram channel announcement"
    }
}


def validate_platform_constraints(platform: str, content: str, hashtags: List[str]):
    """
    Validates a variant against its platform constraint profile.
    Raises ValueError detailing the exact rule broken if validation fails.
    """
    platform = platform.lower()
    if platform not in PLATFORM_CONSTRAINTS:
        raise ValueError(f"Unsupported platform '{platform}'. Supported platforms: {list(PLATFORM_CONSTRAINTS.keys())}")

    profile = PLATFORM_CONSTRAINTS[platform]
    
    # Length enforcement
    total_length = len(content)
    if total_length > profile["max_length"]:
        raise ValueError(
            f"Content length {total_length} exceeds {platform.upper()} limit of {profile['max_length']} characters"
        )
    if total_length < 10:
        raise ValueError(f"Content too short ({total_length} characters). Minimum 10 characters required.")

    # Hashtag count enforcement
    hashtag_count = len(hashtags)
    if hashtag_count < profile["min_hashtags"]:
        raise ValueError(
            f"{platform.upper()} requires at least {profile['min_hashtags']} hashtag(s), but {hashtag_count} were provided"
        )
    if hashtag_count > profile["max_hashtags"]:
        raise ValueError(
            f"{platform.upper()} allows at most {profile['max_hashtags']} hashtag(s), but {hashtag_count} were provided"
        )


# --- Request & Response Schemas ---

class PostCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=255, description="Title of the article")
    content: Optional[str] = Field(None, description="Markdown body of the article")
    source_url: Optional[str] = Field(None, description="URL to scrape/fetch article from")

    @model_validator(mode="after")
    def check_content_or_url(self):
        if not self.content and not self.source_url:
            raise ValueError("Either 'content' (Markdown) or 'source_url' must be provided.")
        return self


class PostResponse(BaseModel):
    id: str
    title: str
    content: str
    source_url: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class VariantCreateManual(BaseModel):
    """Used when manually proposing or editing a platform variant."""
    platform: Literal["x", "linkedin", "discord", "telegram"]
    content: str
    hashtags: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_rules(self):
        validate_platform_constraints(self.platform, self.content, self.hashtags)
        return self


class VariantResponse(BaseModel):
    id: str
    post_id: str
    platform: str
    content: str
    hashtags: Optional[str] = None
    status: str
    review_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VariantReviewUpdate(BaseModel):
    status: Literal["approved", "rejected", "draft"]
    review_notes: Optional[str] = None


class ScheduleRequest(BaseModel):
    scheduled_time: datetime = Field(..., description="ISO datetime to publish")
    idempotency_key: Optional[str] = Field(None, description="Unique key for deduplication")


class ScheduleSlotResponse(BaseModel):
    id: str
    variant_id: str
    scheduled_time: datetime
    idempotency_key: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
