"""Upload Shorts/compilations to your channel via OAuth2, with a pre-publish
license re-check and a circuit breaker since uploads run fully automatically
with no human review step."""

import logging

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from app.config import DRY_RUN, YOUTUBE_OAUTH_TOKEN_FILE
from app.db import PipelineState, Upload, get_session
from app.youtube_search import reverify_license

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
STRIKE_INDICATORS = ("suspend", "terminat", "forbidden", "blocked")


def is_paused() -> tuple:
    session = get_session()
    try:
        state = session.query(PipelineState).first()
        return bool(state and state.paused), (state.pause_reason if state else "")
    finally:
        session.close()


def pause_pipeline(reason: str):
    session = get_session()
    try:
        state = session.query(PipelineState).first()
        state.paused = True
        state.pause_reason = reason
        session.commit()
        logger.error("Circuit breaker tripped: %s", reason)
    finally:
        session.close()


def _youtube_client():
    credentials = Credentials.from_authorized_user_file(YOUTUBE_OAUTH_TOKEN_FILE, SCOPES)
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
    return build("youtube", "v3", credentials=credentials)


def publish_video(file_path: str, metadata: dict, candidates, kind: str,
                   run_id=None, privacy_status="private") -> "Upload":
    """Upload one finished video. Always re-checks every source license
    immediately before publishing, and respects the dry-run/pause flags."""
    session = get_session()
    upload_row = Upload(
        run_id=run_id,
        kind=kind,
        title=metadata["title"],
        description=metadata["description"],
        source_candidate_ids=",".join(str(c.id) for c in candidates),
        privacy_status=privacy_status,
        dry_run=DRY_RUN,
        status="pending",
    )
    session.add(upload_row)
    session.commit()

    paused, reason = is_paused()
    if paused:
        upload_row.status = "skipped"
        upload_row.error = f"Pipeline paused: {reason}"
        session.commit()
        session.close()
        return upload_row

    for candidate in candidates:
        if not reverify_license(candidate.video_id):
            upload_row.status = "skipped"
            upload_row.error = f"License no longer CC for source {candidate.video_id}; aborting publish."
            session.commit()
            session.close()
            return upload_row

    if DRY_RUN:
        logger.info("[DRY RUN] Would upload %r (%s): %s", metadata["title"], kind, file_path)
        upload_row.status = "uploaded"
        upload_row.youtube_video_id = "DRY_RUN"
        session.commit()
        session.close()
        return upload_row

    try:
        youtube = _youtube_client()
        body = {
            "snippet": {
                "title": metadata["title"],
                "description": metadata["description"],
                "tags": metadata.get("tags", []),
                "categoryId": metadata.get("category_id", "24"),
            },
            "status": {"privacyStatus": privacy_status, "selfDeclaredMadeForKids": False},
        }
        media = MediaFileUpload(file_path, mimetype="video/mp4", resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            _, response = request.next_chunk()

        upload_row.youtube_video_id = response["id"]
        upload_row.status = "uploaded"
        session.commit()
        logger.info("Uploaded %s -> https://youtu.be/%s", metadata["title"], response["id"])
    except HttpError as exc:
        error_text = str(exc).lower()
        upload_row.status = "failed"
        upload_row.error = str(exc)
        session.commit()
        if any(indicator in error_text for indicator in STRIKE_INDICATORS):
            pause_pipeline(f"YouTube API returned a possible account restriction: {exc}")
        logger.error("Upload failed: %s", exc)
    finally:
        session.close()

    return upload_row
