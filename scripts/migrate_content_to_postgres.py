"""One-time data migration: copy CONTENT (categories, videos, quiz questions, regulation
chunks) from the local SQLite dev database to a production Postgres database.

Deliberately does NOT touch users, watch progress, comments, quiz attempts, or regulation
questions — those should start fresh in production (real staff accounts, real activity),
and re-running this script must never overwrite/duplicate an admin account created with
whatever real credentials were configured on the production host.

Usage:
    python scripts/migrate_content_to_postgres.py "postgresql://user:pass@host/db"
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.models import Category, QuizQuestion, RegulationChunk, Video, db  # noqa: E402


def main():
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    target_url = sys.argv[1]

    # Read everything from local dev DB first.
    local_app = create_app()
    with local_app.app_context():
        categories = Category.query.order_by(Category.sort_order).all()
        categories_data = [
            {"name": c.name, "sort_order": c.sort_order} for c in categories
        ]

        videos_data = []
        for v in Video.query.all():
            videos_data.append(
                {
                    "category_name": v.category.name,
                    "title": v.title,
                    "sort_order": v.sort_order,
                    "storage_key": v.storage_key,
                    "duration_seconds": v.duration_seconds,
                    "drive_source_id": v.drive_source_id,
                    "transcript_text": v.transcript_text,
                    "quiz_questions": [
                        {
                            "question_text": q.question_text,
                            "choices_json": q.choices_json,
                            "correct_index": q.correct_index,
                            "sort_order": q.sort_order,
                        }
                        for q in v.quiz_questions
                    ],
                }
            )

        chunks_data = [
            {"source": c.source, "printed_page": c.printed_page, "text": c.text}
            for c in RegulationChunk.query.all()
        ]

    print(
        f"Read {len(categories_data)} categories, {len(videos_data)} videos "
        f"({sum(len(v['quiz_questions']) for v in videos_data)} quiz questions), "
        f"{len(chunks_data)} regulation chunks from local DB."
    )

    # Write everything to the target (production) DB.
    import os

    os.environ["DATABASE_URL"] = target_url
    target_app = create_app()
    with target_app.app_context():
        existing_categories = {c.name: c for c in Category.query.all()}
        for cat in categories_data:
            if cat["name"] not in existing_categories:
                new_cat = Category(name=cat["name"], sort_order=cat["sort_order"])
                db.session.add(new_cat)
                existing_categories[cat["name"]] = new_cat
        db.session.commit()
        print(f"Categories in place: {len(existing_categories)}")

        existing_videos = {
            v.drive_source_id: v for v in Video.query.filter(Video.drive_source_id.isnot(None)).all()
        }

        video_count = 0
        quiz_count = 0
        for vd in videos_data:
            if vd["drive_source_id"] in existing_videos:
                continue  # already migrated, safe to re-run this script
            video = Video(
                category_id=existing_categories[vd["category_name"]].id,
                title=vd["title"],
                sort_order=vd["sort_order"],
                storage_key=vd["storage_key"],
                duration_seconds=vd["duration_seconds"],
                drive_source_id=vd["drive_source_id"],
                transcript_text=vd["transcript_text"],
            )
            db.session.add(video)
            db.session.flush()  # get video.id before adding quiz questions

            for q in vd["quiz_questions"]:
                db.session.add(
                    QuizQuestion(
                        video_id=video.id,
                        question_text=q["question_text"],
                        choices_json=q["choices_json"],
                        correct_index=q["correct_index"],
                        sort_order=q["sort_order"],
                    )
                )
                quiz_count += 1
            video_count += 1

        db.session.commit()
        print(f"Videos migrated: {video_count}, quiz questions migrated: {quiz_count}")

        existing_chunk_count = RegulationChunk.query.count()
        if existing_chunk_count == 0:
            for c in chunks_data:
                db.session.add(RegulationChunk(**c))
            db.session.commit()
            print(f"Regulation chunks migrated: {len(chunks_data)}")
        else:
            print(f"Regulation chunks already present ({existing_chunk_count}), skipped.")

    print("Content migration complete.")


if __name__ == "__main__":
    main()
