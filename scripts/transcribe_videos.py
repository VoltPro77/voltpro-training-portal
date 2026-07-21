"""Transcribe ingested videos with faster-whisper (local, free, CPU-bound) and save the
transcript to Video.transcript_text, which powers auto-generated quizzes (see app/quiz.py).

Usage:
    python scripts/transcribe_videos.py                  # transcribe all videos missing a transcript
    python scripts/transcribe_videos.py --video-id 3      # transcribe just one video
    python scripts/transcribe_videos.py --model base.en   # override the default model
    python scripts/transcribe_videos.py --force           # re-transcribe even if a transcript exists
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.models import Video, db  # noqa: E402
from app.storage import get_storage  # noqa: E402

DEFAULT_MODEL = "small.en"


def transcribe(model, local_path):
    segments, info = model.transcribe(str(local_path), beam_size=5, vad_filter=True)
    text_parts = [seg.text.strip() for seg in segments]
    return " ".join(text_parts), info.duration


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-id", type=int, help="Transcribe only this video's id")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="faster-whisper model size")
    parser.add_argument("--force", action="store_true", help="Re-transcribe even if transcript_text is already set")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        storage = get_storage()
        if storage.backend_name != "local":
            raise SystemExit(
                "Transcription currently only supports the local storage backend "
                "(it reads MP4 files directly off disk)."
            )

        query = Video.query.filter(Video.storage_key.isnot(None))
        if args.video_id:
            query = query.filter(Video.id == args.video_id)
        if not args.force:
            query = query.filter(Video.transcript_text.is_(None))
        videos = query.order_by(Video.id).all()

        if not videos:
            print("Nothing to transcribe.")
            return

        print(f"Loading faster-whisper model '{args.model}' (first run downloads it)...")
        from faster_whisper import WhisperModel

        model = WhisperModel(args.model, device="cpu", compute_type="int8")

        for i, video in enumerate(videos, 1):
            local_path = storage.local_path_for(video.storage_key)
            if not local_path.exists():
                print(f"[{i}/{len(videos)}] SKIP (file missing): {video.title}")
                continue

            print(f"[{i}/{len(videos)}] Transcribing: {video.title} ...")
            start = time.time()
            text, duration = transcribe(model, local_path)
            elapsed = time.time() - start
            speed = duration / elapsed if elapsed else 0

            video.transcript_text = text
            db.session.commit()
            print(
                f"    done in {elapsed:.0f}s for {duration:.0f}s of audio "
                f"({speed:.1f}x realtime), {len(text)} chars"
            )


if __name__ == "__main__":
    main()
