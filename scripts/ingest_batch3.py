"""Batch version of ingest_video.py for the 98-video Drive haul (see
drive_manifest_batch3.py) — converts each downloaded .wmv to MP4, stores it, and
registers/updates the Video row with its category + subheading. Transcription is a
separate pass (run transcribe_videos.py after this), same as the normal pipeline.

Usage:
    python scripts/ingest_batch3.py [--downloads-dir ~/Downloads] [--keep-source]
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
from scripts.drive_manifest_batch3 import MANIFEST  # noqa: E402


def slugify(text):
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def probe_duration(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def convert_to_mp4(source_path, dest_path):
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(source_path),
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
            str(dest_path),
        ],
        check=True,
        capture_output=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--downloads-dir", default="~/Downloads")
    parser.add_argument("--keep-source", action="store_true")
    args = parser.parse_args()

    downloads_dir = Path(args.downloads_dir).expanduser()

    app = create_app()
    with app.app_context():
        category_ids = {c.name: c.id for c in Category.query.all()}
        existing_by_drive_id = {
            v.drive_source_id: v for v in Video.query.filter(Video.drive_source_id.isnot(None)).all()
        }
        storage = get_storage()

        ok, failed, skipped = 0, [], 0
        for i, (drive_id, filename, category_name, subheading) in enumerate(MANIFEST, 1):
            existing = existing_by_drive_id.get(drive_id)
            if existing and existing.storage_key:
                print(f"[{i}/{len(MANIFEST)}] SKIP (already ingested): {filename}")
                skipped += 1
                continue

            source_path = downloads_dir / filename
            if not source_path.exists():
                print(f"[{i}/{len(MANIFEST)}] FAIL (source missing): {filename}")
                failed.append(filename)
                continue

            category_id = category_ids.get(category_name)
            if not category_id:
                print(f"[{i}/{len(MANIFEST)}] FAIL (unknown category {category_name}): {filename}")
                failed.append(filename)
                continue

            try:
                title = Path(filename).stem
                category_slug = slugify(category_name)
                title_slug = slugify(title)
                storage_key = f"{category_slug}/{title_slug}.mp4"

                tmp_mp4 = source_path.with_suffix(".converted.mp4")
                print(f"[{i}/{len(MANIFEST)}] Converting: {filename} ...")
                convert_to_mp4(source_path, tmp_mp4)
                duration = probe_duration(tmp_mp4)

                storage.save_file(tmp_mp4, storage_key)

                video = existing or Video(drive_source_id=drive_id)
                video.category_id = category_id
                video.title = title
                video.subheading = subheading
                video.storage_key = storage_key
                video.duration_seconds = int(duration)
                if not existing:
                    db.session.add(video)
                db.session.commit()

                tmp_mp4.unlink(missing_ok=True)
                if not args.keep_source:
                    source_path.unlink(missing_ok=True)

                print(f"    OK id={video.id} ({duration:.0f}s)")
                ok += 1
            except Exception as exc:
                db.session.rollback()
                print(f"    FAILED: {exc}")
                failed.append(filename)

        print(f"\n{ok} ingested, {skipped} already done, {len(failed)} failed")
        if failed:
            for f in failed:
                print(f"  - {f}")


if __name__ == "__main__":
    main()
