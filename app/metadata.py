"""Title/description generation with mandatory CC BY attribution.

YouTube's reused Creative Commons license (the one selectable via the Studio
license dropdown) is effectively CC BY 3.0: reuse is allowed, but the
re-user must credit the original creator. This module makes sure that
credit is never optional or missing from generated metadata.
"""

from app.config import CHANNEL_BRAND_NAME


def _attribution_block(candidates) -> str:
    lines = ["Sources (Creative Commons - CC BY):"]
    for c in candidates:
        lines.append(f"- \"{c.title}\" by {c.channel_title}: {c.video_url}")
    lines.append("")
    lines.append(
        "These clips are used under YouTube's Creative Commons (CC BY) license. "
        "Edits made: trimmed to highlight segments, recompiled, captioned/branded."
    )
    return "\n".join(lines)


def build_short_metadata(candidate, topic_keyword: str) -> dict:
    title = f"{topic_keyword} - {candidate.title}"[:95] + " #Shorts"
    description = (
        f"{candidate.title} (clip)\n\n"
        f"{_attribution_block([candidate])}\n\n"
        f"{CHANNEL_BRAND_NAME}\n#Shorts"
    )
    return {
        "title": title[:100],
        "description": description,
        "tags": [topic_keyword, "shorts"],
        "category_id": "24",  # Entertainment
    }


def build_compilation_metadata(candidates, topic_keyword: str) -> dict:
    title = f"{topic_keyword}: Top Creative Commons Clips"[:100]
    description = (
        f"A compilation of trending Creative Commons-licensed clips about {topic_keyword}.\n\n"
        f"{_attribution_block(candidates)}\n\n"
        f"{CHANNEL_BRAND_NAME}"
    )
    return {
        "title": title,
        "description": description,
        "tags": [topic_keyword, "compilation"],
        "category_id": "24",
    }
