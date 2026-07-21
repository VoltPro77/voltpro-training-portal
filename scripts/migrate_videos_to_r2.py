"""One-time migration: upload all locally-stored videos to the Cloudflare R2 bucket,
using each Video's existing storage_key so no database changes are needed — once this
runs, switching the live app's STORAGE_BACKEND to "r2" just works.

Uses R2Storage directly regardless of the local .env STORAGE_BACKEND setting (which stays
"local" for local dev — this script targets R2 specifically for the production migration).

Usage:
    python scripts/migrate_videos_to_r2.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.models import Video  # noqa: E402
from app.storage import LocalStorage, R2Storage  # noqa: E402


def main():
    app = create_app()
    with app.app_context():
        local = LocalStorage()
        r2 = R2Storage()

        videos = Video.query.filter(Video.storage_key.isnot(None)).order_by(Video.id).all()
        print(f"{len(videos)} videos to migrate.")

        for i, video in enumerate(videos, 1):
            local_path = local.local_path_for(video.storage_key)
            if not local_path.exists():
                print(f"[{i}/{len(videos)}] SKIP (local file missing): {video.title}")
                continue

            size_mb = local_path.stat().st_size / (1024 * 1024)
            print(f"[{i}/{len(videos)}] Uploading {video.title} ({size_mb:.0f}MB) ...")
            r2.save_file(local_path, video.storage_key)
            print(f"    done -> {video.storage_key}")

        print("Migration complete.")


if __name__ == "__main__":
    main()
