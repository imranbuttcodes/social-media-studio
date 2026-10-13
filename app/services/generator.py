import os
import re
import json
import httpx
from bs4 import BeautifulSoup
from typing import Dict, List, Tuple
from app.schemas import validate_platform_constraints


async def fetch_url_content(url: str) -> str:
    """Fetches clean text content from an external blog post URL using BeautifulSoup."""
    headers = {
        "User-Agent": "SocialMediaStudio/1.0 (Polite Campaign Ingestion Bot)"
    }
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        html = response.text
        
        soup = BeautifulSoup(html, "html.parser")
        # Decompose non-article elements
        for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
            element.decompose()
            
        text = soup.get_text(separator="\n", strip=True)
        lines = [line for line in text.splitlines() if line]
        cleaned = "\n\n".join(lines)
        return cleaned or "No readable text content found at URL."


def generate_platform_variants(title: str, content: str) -> List[Dict]:
    """
    Generates platform-tailored variants from stored post content.
    Each variant is validated against the platform's constraint profile.
    """
    # Clean text of Markdown symbols for clean character accounting
    clean_snippet = re.sub(r"[#*`_\[\]]", "", content).strip()
    raw_sentences = [s.strip() for s in clean_snippet.split(".") if len(s.strip()) > 15]
    first_sentence = raw_sentences[0] if raw_sentences else clean_snippet[:120]
    
    variants = []

    # X (Twitter) Variant: Max 280 chars, 1-3 hashtags, punchy hook
    x_hashtags = ["#Tech", "#Insights"]
    x_tags_str = " " + " ".join(x_hashtags)
    max_body_len = 280 - len(x_tags_str) - 5
    
    x_hook = f"{title}: {first_sentence}"
    if len(x_hook) > max_body_len:
        x_hook = x_hook[:max_body_len - 3] + "..."
    
    x_content = f"{x_hook}{x_tags_str}"
    validate_platform_constraints("x", x_content, x_hashtags)
    variants.append({
        "platform": "x",
        "content": x_content,
        "hashtags": json.dumps(x_hashtags)
    })

    #  LinkedIn Variant: Max 3000 chars, 3-5 hashtags, derived from actual post
    li_hashtags = ["#Engineering", "#Leadership", "#Learning", "#Strategy"]
    takeaways = raw_sentences[1:4] if len(raw_sentences) >= 4 else raw_sentences[1:]
    if takeaways:
        points_block = "Key takeaways from the article:\n" + "\n".join(f"• {point}." for point in takeaways)
    else:
        points_block = f"Core focus:\n• {first_sentence}."

    li_content = (
        f"💡 {title}\n\n"
        f"{first_sentence}.\n\n"
        f"{points_block}\n\n"
        f"What is your perspective on this topic?\n\n"
        f"{' '.join(li_hashtags)}"
    )
    validate_platform_constraints("linkedin", li_content, li_hashtags)
    variants.append({
        "platform": "linkedin",
        "content": li_content,
        "hashtags": json.dumps(li_hashtags)
    })

    # 3. Discord / Community Announcement: Max 2000 chars, community tone
    discord_hashtags = ["#announcement"]
    discord_content = (
        f"📢 **New Post: {title}**\n\n"
        f"> {first_sentence}.\n\n"
        f"Check out the full discussion and share your thoughts in the channel!\n"
        f"{' '.join(discord_hashtags)}"
    )
    validate_platform_constraints("discord", discord_content, discord_hashtags)
    variants.append({
        "platform": "discord",
        "content": discord_content,
        "hashtags": json.dumps(discord_hashtags)
    })

    return variants
    