"""Retry transcript fetch for YouTube-linked videos that don't have one yet
(e.g. added while YouTube was rate-limiting this IP). Safe to re-run anytime —
only touches videos with youtube_id set and transcript_text still empty.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.models import Video, db  # noqa: E402
from scripts.add_youtube_video import fetch_transcript  # noqa: E402


def main():
    app = create_app()
    with app.app_context():
        pending = Video.query.filter(
            Video.youtube_id.isnot(None), Video.transcript_text.is_(None)
        ).all()
        if not pending:
            print("Nothing pending — all YouTube videos already have transcripts.")
            return

        print(f"{len(pending)} video(s) pending a transcript.")
        done, still_pending = [], []
        for video in pending:
            try:
                print(f"Fetching transcript for {video.youtube_id} ({video.title}) ...")
                transcript = fetch_transcript(video.youtube_id)
                video.transcript_text = transcript
                db.session.commit()
                print(f"  OK ({len(transcript)} chars)")
                done.append(video.title)
            except SystemExit as exc:
                db.session.rollback()
                print(f"  no captions available: {exc}")
                still_pending.append((video.title, "no captions"))
            except Exception as exc:
                db.session.rollback()
                print(f"  still failing: {exc}")
                still_pending.append((video.title, str(exc)[:120]))

        print(f"\n{len(done)} backfilled, {len(still_pending)} still pending")
        for title, reason in still_pending:
            print(f"  - {title}: {reason}")


if __name__ == "__main__":
    main()
