"""Manual control surface for the pause/resume/blocklist circuit breaker.

There's no live dashboard server to click buttons on (GitHub Pages is
static), so this script is invoked instead via the "Pipeline Control"
GitHub Actions workflow (Actions tab -> Run workflow), which commits the
resulting state change back to data/pipeline.db.
"""

import argparse

from app.db import BlockedChannel, PipelineState, get_session, init_db


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True, choices=["pause", "resume", "block"])
    parser.add_argument("--reason", default="")
    parser.add_argument("--channel-id", default="")
    args = parser.parse_args()

    init_db()
    session = get_session()
    try:
        if args.action == "pause":
            state = session.query(PipelineState).first()
            state.paused = True
            state.pause_reason = args.reason or "Manually paused via control workflow"
            session.commit()
            print("Pipeline paused.")
        elif args.action == "resume":
            state = session.query(PipelineState).first()
            state.paused = False
            state.pause_reason = ""
            session.commit()
            print("Pipeline resumed.")
        elif args.action == "block":
            if not args.channel_id:
                raise SystemExit("--channel-id is required for action=block")
            if not session.query(BlockedChannel).filter_by(channel_id=args.channel_id).first():
                session.add(BlockedChannel(channel_id=args.channel_id, reason=args.reason))
                session.commit()
            print(f"Blocked channel {args.channel_id}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
