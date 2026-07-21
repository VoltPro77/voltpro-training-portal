"""Pre-generate quizzes for all transcribed videos, via the Claude API (app/quiz.py).

Quizzes normally generate lazily on a staff member's first quiz visit (see
routes.quiz_page), so running this isn't required — but doing it ahead of time means
nobody has to wait on the first click, and lets you sanity-check the questions before
staff see them.

Usage:
    python scripts/generate_quizzes.py                # generate for videos missing a quiz
    python scripts/generate_quizzes.py --video-id 3    # just one video
    python scripts/generate_quizzes.py --force         # regenerate even if a quiz exists
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.models import QuizQuestion, Video, db  # noqa: E402
from app.quiz import generate_quiz  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video-id", type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        query = Video.query.filter(Video.transcript_text.isnot(None))
        if args.video_id:
            query = query.filter(Video.id == args.video_id)
        videos = query.order_by(Video.id).all()

        for i, video in enumerate(videos, 1):
            if video.has_quiz and not args.force:
                print(f"[{i}/{len(videos)}] SKIP (already has quiz): {video.title}")
                continue

            print(f"[{i}/{len(videos)}] Generating quiz: {video.title} ...")
            try:
                questions = generate_quiz(video.transcript_text)
            except Exception as exc:
                print(f"    FAILED: {exc}")
                continue

            if args.force:
                QuizQuestion.query.filter_by(video_id=video.id).delete()

            for j, q in enumerate(questions):
                db.session.add(
                    QuizQuestion(
                        video_id=video.id,
                        question_text=q["question"],
                        choices_json=json.dumps(q["choices"]),
                        correct_index=q["correct_index"],
                        sort_order=j,
                    )
                )
            db.session.commit()
            print(f"    saved {len(questions)} questions")


if __name__ == "__main__":
    main()
