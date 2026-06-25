"""End-to-end pipeline: trend discovery -> CC search -> download -> edit ->
publish. Runs once per invocation -- scheduling itself is handled externally
by the GitHub Actions cron in .github/workflows/pipeline.yml, since this
process runs on an ephemeral runner rather than a long-lived VM. Fully
automatic (no manual approval step), relying on the license re-checks and
circuit breaker built into youtube_search.py / publisher.py for safety
instead.
"""

import datetime
import logging
import shutil

from app.config import DEFAULT_PRIVACY_STATUS, MAX_KEYWORDS_PER_RUN, TEMP_DIR
from app.db import Candidate, RunLog, get_session, init_db
from app.downloader import LicenseRevokedError, download_video
from app.editor import build_compilation, build_short
from app.metadata import build_compilation_metadata, build_short_metadata
from app.publisher import is_paused, publish_video
from app.trends import discover_keywords
from app.youtube_search import select_candidates_for_run

logger = logging.getLogger(__name__)


def run_pipeline():
    paused, reason = is_paused()
    if paused:
        logger.warning("Pipeline is paused (%s); skipping this run.", reason)
        return

    session = get_session()
    run = RunLog(status="running")
    session.add(run)
    session.commit()
    run_id = run.id
    session.close()

    quota_used = 0
    try:
        keywords = discover_keywords(run_id=run_id)[:MAX_KEYWORDS_PER_RUN]
        if not keywords:
            _finish_run(run_id, "completed", quota_used, "No keywords discovered.")
            return

        candidates = select_candidates_for_run(keywords, per_keyword=2, total_limit=6)
        quota_used += len(keywords) * 100  # search.list cost
        if not candidates:
            _finish_run(run_id, "completed", quota_used, "No usable CC candidates found.")
            return

        downloaded_paths = {}
        usable_candidates = []
        for candidate in candidates:
            try:
                downloaded_paths[candidate.video_id] = download_video(candidate.video_id)
                usable_candidates.append(candidate)
            except LicenseRevokedError as exc:
                logger.warning(str(exc))
            except Exception as exc:
                logger.error("Download failed for %s: %s", candidate.video_id, exc)

        if not usable_candidates:
            _finish_run(run_id, "completed", quota_used, "All candidates failed to download.")
            return

        short_candidate = max(usable_candidates, key=lambda c: c.view_count)
        compilation_candidates = usable_candidates[:5]

        short_path = build_short(short_candidate, downloaded_paths[short_candidate.video_id])
        compilation_path = build_compilation(
            [(c, downloaded_paths[c.video_id]) for c in compilation_candidates]
        )

        topic = keywords[0] if keywords else "Trending"
        short_meta = build_short_metadata(short_candidate, topic)
        compilation_meta = build_compilation_metadata(compilation_candidates, topic)

        publish_video(
            short_path, short_meta, [short_candidate], kind="short",
            run_id=run_id, privacy_status=DEFAULT_PRIVACY_STATUS,
        )
        publish_video(
            compilation_path, compilation_meta, compilation_candidates, kind="compilation",
            run_id=run_id, privacy_status=DEFAULT_PRIVACY_STATUS,
        )

        _mark_used([short_candidate] + compilation_candidates)
        _finish_run(run_id, "completed", quota_used, "OK")
    except Exception as exc:
        logger.exception("Pipeline run %s failed", run_id)
        _finish_run(run_id, "failed", quota_used, str(exc))
    finally:
        _cleanup_temp()


def _mark_used(candidates):
    session = get_session()
    try:
        ids = [c.id for c in candidates]
        session.query(Candidate).filter(Candidate.id.in_(ids)).update(
            {"used": True}, synchronize_session=False
        )
        session.commit()
    finally:
        session.close()


def _finish_run(run_id, status, quota_used, notes):
    session = get_session()
    try:
        run = session.query(RunLog).get(run_id)
        run.status = status
        run.quota_units_used = quota_used
        run.notes = notes
        run.finished_at = datetime.datetime.utcnow()
        session.commit()
    finally:
        session.close()
    logger.info("Run %s finished: %s (%s)", run_id, status, notes)


def _cleanup_temp():
    for child in TEMP_DIR.iterdir():
        try:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink()
        except OSError:
            pass


def main():
    logging.basicConfig(level=logging.INFO)
    init_db()
    run_pipeline()

    from app.static_dashboard import render

    render()


if __name__ == "__main__":
    main()
