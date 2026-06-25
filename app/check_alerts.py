"""Prints ALERT|<run_id>|<status>|<notes> for the most recent run if it failed
or self-reported a degradation (see trends.py's "DEGRADED:" markers), else
prints OK. The pipeline workflow uses this to decide whether to open a
GitHub Issue -- things the code could auto-fix (like an unavailable AI
model) already got patched at runtime; this is for what it couldn't fix."""

from app.db import RunLog, get_session


def main():
    session = get_session()
    try:
        run = session.query(RunLog).order_by(RunLog.id.desc()).first()
        if not run:
            print("OK")
            return
        notes = run.notes or ""
        if run.status == "failed" or "DEGRADED" in notes:
            # Pipe-delimited and single-line so it survives GITHUB_OUTPUT.
            flat_notes = notes.replace("\n", " ").replace("|", "/")
            print(f"ALERT|{run.id}|{run.status}|{flat_notes}")
        else:
            print("OK")
    finally:
        session.close()


if __name__ == "__main__":
    main()
