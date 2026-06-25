"""Trend discovery.

Pulls *real* trending signals (YouTube's own trending chart + Google Trends)
rather than asking an AI model to invent topics from scratch -- that's what
caused the prototype to "discover" first-run movie titles. The free-tier AI
call here is only used to normalize/clean the raw signals into short search
phrases, never to generate topics on its own.
"""

import logging

from googleapiclient.discovery import build
from pytrends.request import TrendReq

from app.config import GEMINI_API_KEY, GEMINI_MODEL, MAX_KEYWORDS_PER_RUN, YOUTUBE_API_KEY
from app.db import Keyword, get_session

logger = logging.getLogger(__name__)


def get_youtube_trending_titles(region_code="US", max_results=15):
    """Real trending video titles from YouTube's own 'most popular' chart."""
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    response = (
        youtube.videos()
        .list(part="snippet", chart="mostPopular", regionCode=region_code, maxResults=max_results)
        .execute()
    )
    return [item["snippet"]["title"] for item in response.get("items", [])]


def get_google_trends(geo="US"):
    """Real-time trending search terms from Google Trends."""
    try:
        pytrends = TrendReq(hl="en-US", tz=360)
        df = pytrends.trending_searches(pn="united_states" if geo == "US" else geo)
        return df[0].tolist()
    except Exception as exc:  # pytrends scrapes a public endpoint and can break
        logger.warning("Google Trends fetch failed: %s", exc)
        return []


def normalize_with_ai(raw_signals):
    """Turn raw trending titles/terms into short, generic YouTube search phrases.

    Uses Google's free-tier Gemini API. Falls back to naive truncation if no
    API key is configured or the call fails, so the pipeline never silently
    invents content on its own.
    """
    raw_signals = [s for s in raw_signals if s][:30]
    if not raw_signals:
        return []

    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set; falling back to raw signals as keywords.")
        return raw_signals[:MAX_KEYWORDS_PER_RUN]

    try:
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        prompt = (
            "Here are raw trending video titles and search terms:\n"
            + "\n".join(f"- {s}" for s in raw_signals)
            + "\n\nCluster these into at most "
            + str(MAX_KEYWORDS_PER_RUN)
            + " short, generic topic phrases suitable as YouTube search queries "
            "(e.g. event names, general subjects, public figures, sports, news topics). "
            "Do NOT output movie/show/song titles or anything that is clearly a copyrighted "
            "work's proper name. Return ONLY a comma-separated list, nothing else."
        )
        response = model.generate_content(prompt)
        text = response.text.strip()
        phrases = [p.strip() for p in text.split(",") if p.strip()]
        return phrases[:MAX_KEYWORDS_PER_RUN]
    except Exception as exc:
        logger.warning("Gemini normalization failed (%s); falling back to raw signals.", exc)
        return raw_signals[:MAX_KEYWORDS_PER_RUN]


def discover_keywords(run_id=None):
    """Fetch trending signals, normalize them, and persist as Keyword rows."""
    youtube_titles = get_youtube_trending_titles()
    google_terms = get_google_trends()
    raw_signals = google_terms + youtube_titles

    phrases = normalize_with_ai(raw_signals)

    session = get_session()
    try:
        for phrase in phrases:
            session.add(Keyword(run_id=run_id, phrase=phrase, source="trend_discovery"))
        session.commit()
    finally:
        session.close()

    logger.info("Discovered %d keywords: %s", len(phrases), phrases)
    return phrases


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(discover_keywords())
