"""One-off batch run: link the curated set of new "Electrical How To" YouTube
videos discovered on 2026-07-22. See add_youtube_video.py for the underlying
single-video logic this reuses.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.models import Category, Video, db  # noqa: E402
from scripts.add_youtube_video import fetch_transcript  # noqa: E402

CHANNEL = "Electrical How To"

VIDEOS = [
    # (youtube_id, title, category)
    ("67e70gXJZFw", "How to be a GREAT Electrical Apprentice | 13 TIPS to Help", "Apprentice On Boarding"),
    ("p7PFNw7iddk", "Explanation of a Timber Structure", "Apprentice On Boarding"),
    ("JTuDLstCnl4", "Electrical Isolation Procedure | Lock Out Tag Out", "Apprentice On Boarding"),
    ("4ZvFKBNu0MQ", "Flush Mount Switchboards: Clipsal vs Hager", "Meter Box Upgrade"),
    ("cuBRzCNptlo", "How to Bend Conduit", "IXL Installation"),
    ("Rj7NmdS9lIg", "Wiring Coach Lights In Arbor", "Lighting"),
    ("Dn_NeERHURE", "How an RCD Works", "Testing"),
    ("RyKL9OTtW5M", "Setting Up Trailing Lead to the Insulation Resistance Tester", "Testing"),
    ("caM-rh4hyrs", "M.E.N. System (Main Earthing System Explanation)", "Earthing"),
    ("Y7eSiJmPJvw", "EVNEX E2 Plus Smart Charger Installation | Full Installation", "EV Chargers"),
    ("6InCEpNvNYU", "EV Charger Questions Sparkies Keep Asking | Rapid Fire Q&A with Evnex", "EV Chargers"),
    ("Sa5WTnbMI04", "Before You Install an EV Charger, Watch This", "EV Chargers"),
    ("3lY6QjbYhc8", "What Sparkies Should Ask Before Installing An EV Charger", "EV Chargers"),
    ("aP1_kPRWatk", "Don't Use The Wrong CT Cable On EV Chargers", "EV Chargers"),
    ("5Gt1mPaWQ3U", "The Most Common EV Charger CT Wiring Mistakes", "EV Chargers"),
    ("XBIq7pRV6T4", "The RIGHT Circuit Protection For EV Chargers", "EV Chargers"),
    ("4C989tBgpTc", "What's in Ken's Tool Bag?", "Tools & Equipment"),
    ("GZa8JdtmBBA", "Insert and Remove HILTI Masonry Drill Bit", "Tools & Equipment"),
    ("i6VEQauHZWQ", "Set Up Electrical Cable Drums on Cable Stand", "Tools & Equipment"),
    ("3bhXFhg9rXU", "Remove Dynabolts from Brick Work", "Tools & Equipment"),
    ("NWrCVId9-T4", "How To Remove A Roofing Nail", "Tools & Equipment"),
    ("b--qbs0jQ20", "Hilti Vacuum VC 40-U And Grinder DCH-EX 300", "Tools & Equipment"),
    ("iGHBD9hEagE", "Vessel Electric Screwdriver Modification", "Tools & Equipment"),
    ("uCpPLjXe5ko", "Grinding Cutting Wheels", "Tools & Equipment"),
    ("l5UDbSMdpxY", "Wera Tool Check Plus 1 | Small Kit, Serious Quality", "Tools & Equipment"),
]


def main():
    app = create_app()
    with app.app_context():
        # Plain ints, not ORM objects — avoids expired-instance lazy-refresh
        # triggering autoflush of a half-populated Video row mid-loop.
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
