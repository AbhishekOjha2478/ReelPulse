"""Scrubs API keys out of text before it's persisted to the DB or rendered
into the public static dashboard.

Several Google API client/requests exceptions embed the full request URL
-- including ?key=<API_KEY> -- in their string representation. GitHub
Actions' own log redaction only masks the *exact* configured secret value
when printed to the workflow console; it does nothing for values written
into files (like the SQLite DB or the static dashboard HTML), which is
exactly how a key ended up committed and caught by GitHub's push
protection. This module is the backstop for that.
"""

import re

from app.config import GEMINI_API_KEY, YOUTUBE_API_KEY

_KEY_PARAM_RE = re.compile(r"([?&]key=)[^&\s'\"]+")


def redact_secrets(text: str) -> str:
    if not text:
        return text

    text = _KEY_PARAM_RE.sub(r"\1***", text)

    for secret in (GEMINI_API_KEY, YOUTUBE_API_KEY):
        if secret:
            text = text.replace(secret, "***")

    return text
