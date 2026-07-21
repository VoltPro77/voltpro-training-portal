"""Set the display order of videos within a category.

Usage:
    python scripts/set_video_order.py "Meter Box Upgrade" \\
        "Preparing Meter Box" \\
        "Set Up Meter Box" \\
        "Set Up Meter Box For Overhead Supply Upgrade" \\
        "Meterbox Upgrade PART 2" \\
        "Meterbox Upgrade PART 3"

Lists the titles in the exact order they should appear (first = shows first). Any video
in the category not listed keeps its existing position, sorted after the listed ones.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.models import Category, Video, db  # noqa: E402


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)

    category_name, titles = sys.argv[1], sys.argv[2:]

    app = create_app()
    with app.app_context():
        category = Category.query.filter_by(name=category_name).first()
        if not category:
            raise SystemExit(f"Unknown category '{category_name}'")

        videos_by_title = {v.title: v for v in category.videos}
        missing = [t for t in titles if t not in videos_by_title]
        if missing:
            raise SystemExit(f"No video(s) titled: {missing}")

        for i, title in enumerate(titles):
            videos_by_title[title].sort_order = i

        db.session.commit()

        print(f"Order set for '{category_name}':")
        for v in sorted(category.videos, key=lambda v: (v.sort_order, v.title)):
            print(f"  {v.sort_order:>3}  {v.title}")


if __name__ == "__main__":
    main()
