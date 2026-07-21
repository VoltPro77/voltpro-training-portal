"""Convert a downloaded source video to MP4, store it, and register it in the DB.

Usage:
    python scripts/ingest_video.py \
        --source "/path/to/Some Video.wmv" \
        --category "Earthing" \
        --title "Continuity Of Main Earthing Conductor" \
        --drive-id 1KTpsTo7p2m1xG025gd2djNYvNogVmBlX

This is step 2 of the ingestion pipeline. Step 1 (downloading the source file out of
Google Drive) happens separately via an authenticated browser session, since the Drive
MCP connector's download tool base64-encodes file content inline and is only practical
for small files — not the multi-hundred-MB training videos in this library.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.models import Category, Video, db  # noqa: E402
from app.storage import get_storage  # noqa: E402


def slugify(text):
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def probe_duration(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def convert_to_mp4(source_path, dest_path):
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source_path),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(dest_path),
        ],
        check=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="Path to the downloaded .wmv file")
    parser.add_argument("--category", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--drive-id", required=True)
    parser.add_argument("--keep-source", action="store_true", help="Don't delete the source file after conversion")
    args = parser.parse_args()

    source_path = Path(args.source).expanduser().resolve()
    if not source_path.exists():
        raise SystemExit(f"Source file not found: {source_path}")

    app = create_app()
    with app.app_context():
        category = Category.query.filter_by(name=args.category).first()
        if not category:
            raise SystemExit(
                f"Unknown category '{args.category}'. Known categories: "
                + ", ".join(c.name for c in Category.query.all())
            )

        category_slug = slugify(category.name)
        title_slug = slugify(args.title)
        storage_key = f"{category_slug}/{title_slug}.mp4"

        tmp_mp4 = source_path.with_suffix(".converted.mp4")
        print(f"Converting {source_path.name} -> {tmp_mp4.name} ...")
        convert_to_mp4(source_path, tmp_mp4)

        duration = probe_duration(tmp_mp4)
        print(f"Duration: {duration:.1f}s")

        storage = get_storage()
        storage.save_file(tmp_mp4, storage_key)
        print(f"Stored at key: {storage_key} (backend={storage.backend_name})")

        video = Video.query.filter_by(drive_source_id=args.drive_id).first()
        if not video:
            video = Video(drive_source_id=args.drive_id)
            db.session.add(video)

        video.category_id = category.id
        video.title = args.title
        video.storage_key = storage_key
        video.duration_seconds = int(duration)
        db.session.commit()
        print(f"Video record id={video.id} ready.")

        tmp_mp4.unlink(missing_ok=True)
        if not args.keep_source:
            source_path.unlink(missing_ok=True)
            print(f"Deleted source file {source_path}")


if __name__ == "__main__":
    main()
