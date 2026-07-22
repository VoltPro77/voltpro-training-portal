"""Link an external YouTube video into the catalogue — no download/hosting, just a
reference (youtube_id) plus a transcript fetched from YouTube's own public captions, used
the same way as hosted-video transcripts to power quiz generation.

Usage:
    python scripts/add_youtube_video.py \
      --youtube-id cuBRzCNptlo \
      --title "How to Bend Conduit" \
      --category "IXL Installation" \
      --channel "Electrical How To"
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.models import Category, Video, db  # noqa: E402


def fetch_transcript(youtube_id):
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

    api = YouTubeTranscriptApi()
    try:
        transcript = api.fetch(youtube_id)
    except (TranscriptsDisabled, NoTranscriptFound) as exc:
        raise SystemExit(f"No captions available for {youtube_id}: {exc}")
    return " ".join(seg.text for seg in transcript)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--youtube-id", required=True, help="YouTube video ID (from the watch?v= URL)")
    parser.add_argument("--title", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--channel", required=True, help="Source channel name, for attribution")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        category = Category.query.filter_by(name=args.category).first()
        if not category:
            raise SystemExit(
                f"Unknown category '{args.category}'. Known categories: "
                + ", ".join(c.name for c in Category.query.all())
            )

        print(f"Fetching transcript for {args.youtube_id} ...")
        transcript = fetch_transcript(args.youtube_id)
        print(f"  {len(transcript)} chars")

        video = Video.query.filter_by(youtube_id=args.youtube_id).first()
        if not video:
            video = Video(youtube_id=args.youtube_id)
            db.session.add(video)

        video.category_id = category.id
        video.title = args.title
        video.source_channel = args.channel
        video.transcript_text = transcript
        db.session.commit()
        print(f"Video record id={video.id} ready: {args.title}")


if __name__ == "__main__":
    main()
