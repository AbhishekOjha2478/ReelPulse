"""CC-licensed video search with mandatory re-verification.

YouTube's search.list supports filtering by license, but that filter alone
isn't enough to trust: results can be stale, and license status can change
between when a video was indexed and now. Every candidate gets a second,
authoritative check via videos.list(part="status") before it's ever stored
as usable.
"""

import datetime
import logging

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import YOUTUBE_API_KEY
from app.db import BlockedChannel, Candidate, get_session
from app.redact import redact_secrets

logger = logging.getLogger(__name__)

ISO8601_DURATION = __import__("re").compile(
    r"PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?"
)


def _parse_duration(duration: str) -> int:
    match = ISO8601_DURATION.match(duration or "")
    if not match:
        return 0
    parts = match.groupdict()
    hours = int(parts["hours"] or 0)
    minutes = int(parts["minutes"] or 0)
    seconds = int(parts["seconds"] or 0)
    return hours * 3600 + minutes * 60 + seconds


def _youtube_client():
    return build("youtube", "v3", developerKey=YOUTUBE_API_KEY)


def search_cc_candidates(keyword: str, max_results=10):
    """Search YouTube restricted to Creative Commons license, then re-verify."""
    youtube = _youtube_client()

    try:
        search_response = (
            youtube.search()
            .list(
                q=keyword,
                part="snippet",
                type="video",
                videoLicense="creativeCommon",
                videoEmbeddable="true",
                safeSearch="strict",
                maxResults=max_results,
            )
            .execute()
        )
    except HttpError as exc:
        logger.error("YouTube search failed for %r: %s", keyword, redact_secrets(str(exc)))
        return []

    video_ids = [item["id"]["videoId"] for item in search_response.get("items", [])]
    if not video_ids:
        return []

    return _verify_and_store(youtube, video_ids, keyword)


def _verify_and_store(youtube, video_ids, keyword):
    """Authoritative license/metadata check -- the only source of truth used downstream."""
    session = get_session()
    stored = []
    try:
        existing_ids = {
            row.video_id
            for row in session.query(Candidate.video_id)
            .filter(Candidate.video_id.in_(video_ids))
            .all()
        }
        blocked_channel_ids = {row.channel_id for row in session.query(BlockedChannel.channel_id).all()}

        response = (
            youtube.videos()
            .list(part="status,snippet,contentDetails,statistics", id=",".join(video_ids))
            .execute()
        )

        for item in response.get("items", []):
            video_id = item["id"]
            status = item.get("status", {})
            snippet = item.get("snippet", {})
            content_details = item.get("contentDetails", {})
            statistics = item.get("statistics", {})

            license_ = status.get("license", "youtube")
            if license_ != "creativeCommon":
                logger.info("Rejecting %s: license is %r, not creativeCommon", video_id, license_)
                continue
            if status.get("privacyStatus") != "public":
                continue
            if snippet.get("liveBroadcastContent", "none") != "none":
                continue
            if video_id in existing_ids:
                continue
            if snippet.get("channelId") in blocked_channel_ids:
                continue

            candidate = Candidate(
                video_id=video_id,
                keyword=keyword,
                title=snippet.get("title", ""),
                channel_title=snippet.get("channelTitle", ""),
                channel_id=snippet.get("channelId", ""),
                video_url=f"https://www.youtube.com/watch?v={video_id}",
                license=license_,
                license_verified_at=datetime.datetime.utcnow(),
                duration_seconds=_parse_duration(content_details.get("duration", "")),
                view_count=int(statistics.get("viewCount", 0) or 0),
            )
            session.add(candidate)
            stored.append(candidate)

        session.commit()
        for candidate in stored:
            session.refresh(candidate)
    finally:
        session.close()

    return stored


def reverify_license(video_id: str) -> bool:
    """Re-check a single video's license right before it's used (download or publish time)."""
    youtube = _youtube_client()
    try:
        response = youtube.videos().list(part="status", id=video_id).execute()
    except HttpError as exc:
        logger.error("License re-verification failed for %s: %s", video_id, redact_secrets(str(exc)))
        return False

    items = response.get("items", [])
    if not items:
        return False  # video removed/private since we found it

    status = items[0].get("status", {})
    return status.get("license") == "creativeCommon" and status.get("privacyStatus") == "public"


def select_candidates_for_run(keywords, per_keyword=2, total_limit=6):
    """Search every discovered keyword and pick a ranked set of usable candidates."""
    session = get_session()
    try:
        already_used_ids = {row.video_id for row in session.query(Candidate.video_id).filter(Candidate.used == True)}
    finally:
        session.close()

    all_candidates = []
    for keyword in keywords:
        results = search_cc_candidates(keyword, max_results=10)
        results = [c for c in results if c.video_id not in already_used_ids]
        results.sort(key=lambda c: c.view_count, reverse=True)
        all_candidates.extend(results[:per_keyword])

    all_candidates.sort(key=lambda c: c.view_count, reverse=True)
    return all_candidates[:total_limit]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    for c in search_cc_candidates("space exploration"):
        print(c.video_id, c.title, c.license, c.duration_seconds)
