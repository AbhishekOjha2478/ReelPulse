"""Download verified-CC source videos only. Never call this directly with a
video that hasn't passed youtube_search.reverify_license() first."""

import logging
import os

import yt_dlp

from app.config import TEMP_DIR, YT_COOKIES_FILE
from app.youtube_search import reverify_license

logger = logging.getLogger(__name__)


class LicenseRevokedError(Exception):
    pass


def download_video(video_id: str) -> str:
    if not reverify_license(video_id):
        raise LicenseRevokedError(
            f"{video_id} is no longer a public Creative Commons video; skipping download."
        )

    video_url = f"https://www.youtube.com/watch?v={video_id}"
    out_dir = TEMP_DIR / video_id
    out_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        "outtmpl": str(out_dir / "source.%(ext)s"),
        # Falls all the way back to plain "best" (whatever single combined
        # format is available) if the preferred split video+audio streams
        # at <=1080p aren't offered for a given video.
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "noprogress": True,
        # Deliberately NOT forcing player_client: an earlier run with yt-dlp's
        # default multi-client set + cookies cleared the bot-check (only formats
        # were missing), whereas forcing web-only reintroduced it. We keep the
        # defaults and let the bgutil PO-token provider (server on :4416,
        # started in the workflow) supply the proof-of-origin tokens that fill
        # in the otherwise-missing web formats.
    }
    if YT_COOKIES_FILE:
        ydl_opts["cookiefile"] = YT_COOKIES_FILE
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        filename = ydl.prepare_filename(info)
        filename = os.path.splitext(filename)[0] + ".mp4"

    logger.info("Downloaded %s -> %s", video_id, filename)
    return filename


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    print(download_video(sys.argv[1]))
