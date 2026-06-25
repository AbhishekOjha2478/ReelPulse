"""Renders the audit-trail dashboard to static HTML for GitHub Pages.

There's no long-lived server in the GitHub Actions deployment model (each
run is a fresh, ephemeral runner), so the dashboard can't be a live FastAPI
app. Instead, every pipeline run re-renders these static pages from the
SQLite state and the workflow commits docs/ back to the repo, which GitHub
Pages serves directly. Pause/resume/blocklist controls live in the separate
"Pipeline Control" manual workflow (control_cli.py) since static HTML can't
handle POST requests.
"""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app.config import BASE_DIR, YOUTUBE_DAILY_QUOTA_BUDGET
from app.db import BlockedChannel, Candidate, PipelineState, RunLog, Upload, get_session

DOCS_DIR = BASE_DIR / "docs"
TEMPLATES_DIR = Path(__file__).parent / "static_templates"

_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)


def render():
    DOCS_DIR.mkdir(exist_ok=True)
    (DOCS_DIR / "runs").mkdir(exist_ok=True)

    session = get_session()
    try:
        runs = session.query(RunLog).order_by(RunLog.id.desc()).limit(30).all()
        uploads = session.query(Upload).order_by(Upload.id.desc()).limit(30).all()
        state = session.query(PipelineState).first()
        blocked = session.query(BlockedChannel).order_by(BlockedChannel.id.desc()).all()
        quota_used = sum(r.quota_units_used or 0 for r in runs)

        index_html = _env.get_template("index.html").render(
            runs=runs,
            uploads=uploads,
            paused=bool(state and state.paused),
            pause_reason=state.pause_reason if state else "",
            blocked=blocked,
            quota_used=quota_used,
            quota_budget=YOUTUBE_DAILY_QUOTA_BUDGET,
        )
        (DOCS_DIR / "index.html").write_text(index_html, encoding="utf-8")

        detail_template = _env.get_template("run_detail.html")
        for run in runs:
            run_uploads = [u for u in uploads if u.run_id == run.id]
            candidate_ids = set()
            for u in run_uploads:
                if u.source_candidate_ids:
                    candidate_ids.update(int(i) for i in u.source_candidate_ids.split(",") if i)
            candidates = (
                session.query(Candidate).filter(Candidate.id.in_(candidate_ids)).all()
                if candidate_ids
                else []
            )
            run_html = detail_template.render(run=run, uploads=run_uploads, candidates=candidates)
            (DOCS_DIR / "runs" / f"{run.id}.html").write_text(run_html, encoding="utf-8")
    finally:
        session.close()


if __name__ == "__main__":
    render()
