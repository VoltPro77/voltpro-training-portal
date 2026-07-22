"""One-off batch run: link the curated set of "All Electrical" (@allelectricalau)
YouTube videos discovered on 2026-07-22. See add_youtube_video.py for the underlying
single-video logic this reuses.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.models import Category, Video, db  # noqa: E402
from scripts.add_youtube_video import fetch_transcript  # noqa: E402

CHANNEL = "All Electrical"

VIDEOS = [
    # (youtube_id, title, category)
    ("ZLwNfjYqH3k", "How To Remove A Downlight", "Lighting"),
    ("QbxNqqJbPdQ", "How To Install A LED Downlight 2024: Start To Finish", "Lighting"),
    ("Mg4vzxtketQ", "How To Wire A Plug Base For Downlights", "Lighting"),
    ("Tz17C7T7kdI", "How To Install A Dimmer Switch For Your Lights 2025", "Lighting"),
    ("lLL5PIBWrSQ", "Easy Upgrade For More Outlets/Sockets/Powerpoints", "Switches & Outlets"),
    ("K4dqCkQ1AT0", "Replacing An Architrave Switch", "Switches & Outlets"),
    ("EXBW9j0uv0Y", "How To Wire A Single Switch And Add A Light", "Switches & Outlets"),
    ("O2DF6VPfmNg", "How To Wire A 2 Way Light Switch Explained", "Switches & Outlets"),
    ("hI4NKghIXXU", "Two Way Switching With Power At The Switch", "Switches & Outlets"),
    ("CWeDLVPESh8", "Two Way Switching With Power At Light", "Switches & Outlets"),
    ("GierTOMYB5A", "How To Change A Power Outlet/Socket 2024", "Switches & Outlets"),
    ("KB5vWc4v4ew", "How To Install A USB Outlet", "Switches & Outlets"),
    ("2FyAuJzqjfI", "How To Test A Powerpoint/Outlet Before Disconnecting", "Testing"),
    ("d6QMkfs7Pn0", "Strip Electrical Wire (How To Guide)", "Tools & Equipment"),
    ("XfR_gxZrC40", "Making An Extension Lead/Cord Or Repair", "Tools & Equipment"),
    ("OqDV-I8MnC0", "How Is Your House Wired Australia/NZ 2025", "Apprentice On Boarding"),
    ("oC4FgrUq14I", "Emergency Power Restoration: Quick Fixes For Sudden Power Outages", "Apprentice On Boarding"),
]


def main():
    app = create_app()
    with app.app_context():
        category_ids = {c.name: c.id for c in Category.query.all()}
        ok, failed = [], []
        for youtube_id, title, category_name in VIDEOS:
            category_id = category_ids.get(category_name)
            if not category_id:
                print(f"SKIP {title}: unknown category {category_name}")
                failed.append((youtube_id, title, "unknown category"))
                continue

            transcript = None
            try:
                print(f"Fetching transcript for {youtube_id} ({title}) ...")
                transcript = fetch_transcript(youtube_id)
            except SystemExit as exc:
                print(f"  no transcript available: {exc}")
            except Exception as exc:
                print(f"  transcript fetch error (will backfill later): {exc}")

            try:
                video = Video.query.filter_by(youtube_id=youtube_id).first()
                if not video:
                    video = Video(youtube_id=youtube_id)
                    db.session.add(video)
                video.category_id = category_id
                video.title = title
                video.source_channel = CHANNEL
                if transcript:
                    video.transcript_text = transcript
                db.session.commit()
                print(f"  OK id={video.id} (transcript: {'yes, ' + str(len(transcript)) + ' chars' if transcript else 'PENDING'})")
                ok.append(title if transcript else f"{title} (transcript pending)")
            except Exception as exc:
                db.session.rollback()
                print(f"  FAILED: {exc}")
                failed.append((youtube_id, title, str(exc)))

        print(f"\n{len(ok)} added, {len(failed)} failed")
        if failed:
            for yid, title, reason in failed:
                print(f"  - {title} ({yid}): {reason}")


if __name__ == "__main__":
    main()
