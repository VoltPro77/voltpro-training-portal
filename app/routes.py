import json
from datetime import datetime, timezone

from flask import Blueprint, abort, jsonify, render_template, request, send_from_directory
from flask_login import current_user, login_required

from . import config
from .models import Category, Comment, QuizAttempt, QuizQuestion, Video, WatchProgress, db
from .quiz import generate_quiz
from .storage import get_storage

bp = Blueprint("main", __name__)

COMPLETE_THRESHOLD = 0.9  # 90% watched counts as "completed" and unlocks the quiz


def _video_url(video):
    if video.is_external:
        return None
    storage = get_storage()
    return storage.url_for(video.storage_key)


@bp.route("/")
@login_required
def catalog():
    categories = Category.query.order_by(Category.sort_order, Category.name).all()
    progress_by_video = {
        p.video_id: p
        for p in WatchProgress.query.filter_by(user_id=current_user.id).all()
    }
    return render_template(
        "catalog.html", categories=categories, progress_by_video=progress_by_video
    )


@bp.route("/video/<int:video_id>")
@login_required
def video_detail(video_id):
    video = db.session.get(Video, video_id)
    if not video or not video.is_ready:
        abort(404)

    progress = WatchProgress.query.filter_by(
        user_id=current_user.id, video_id=video_id
    ).first()

    top_comments = [c for c in video.comments if c.parent_id is None]

    quiz_unlocked = bool(progress and progress.percent_complete >= COMPLETE_THRESHOLD)

    return render_template(
        "video.html",
        video=video,
        video_url=_video_url(video),
        progress=progress,
        comments=top_comments,
        quiz_unlocked=quiz_unlocked,
    )


@bp.route("/media/<path:key>")
@login_required
def serve_video(key):
    storage = get_storage()
    if storage.backend_name != "local":
        abort(404)
    return send_from_directory(storage.root, key)


@bp.route("/api/progress", methods=["POST"])
@login_required
def api_progress():
    data = request.get_json(force=True)
    video_id = data.get("video_id")
    seconds_watched = int(data.get("seconds_watched", 0))
    duration = float(data.get("duration") or 0)

    video = db.session.get(Video, video_id)
    if not video:
        return jsonify({"error": "not found"}), 404

    progress = WatchProgress.query.filter_by(
        user_id=current_user.id, video_id=video_id
    ).first()
    if not progress:
        progress = WatchProgress(user_id=current_user.id, video_id=video_id)
        db.session.add(progress)

    percent = min(1.0, seconds_watched / duration) if duration else 0
    progress.seconds_watched = max(progress.seconds_watched or 0, seconds_watched)
    progress.percent_complete = max(progress.percent_complete or 0, percent)
    if progress.percent_complete >= COMPLETE_THRESHOLD and not progress.completed_at:
        progress.completed_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify(
        {
            "percent_complete": progress.percent_complete,
            "completed": progress.completed_at is not None,
        }
    )


@bp.route("/api/videos/<int:video_id>/comments", methods=["POST"])
@login_required
def post_comment(video_id):
    video = db.session.get(Video, video_id)
    if not video:
        return jsonify({"error": "not found"}), 404

    data = request.get_json(force=True)
    body = (data.get("body") or "").strip()
    parent_id = data.get("parent_id")
    if not body:
        return jsonify({"error": "empty comment"}), 400

    comment = Comment(
        video_id=video_id, user_id=current_user.id, body=body, parent_id=parent_id
    )
    db.session.add(comment)
    db.session.commit()

    return jsonify(
        {
            "id": comment.id,
            "body": comment.body,
            "user_name": current_user.name,
            "created_at": comment.created_at.isoformat(),
            "parent_id": comment.parent_id,
        }
    )


@bp.route("/video/<int:video_id>/quiz")
@login_required
def quiz_page(video_id):
    video = db.session.get(Video, video_id)
    if not video:
        abort(404)

    progress = WatchProgress.query.filter_by(
        user_id=current_user.id, video_id=video_id
    ).first()
    if not progress or progress.percent_complete < COMPLETE_THRESHOLD:
        abort(403)

    if not video.has_quiz:
        if not video.transcript_text:
            return render_template("quiz_unavailable.html", video=video)
        try:
            questions = generate_quiz(video.transcript_text)
        except Exception as exc:
            return render_template("quiz_unavailable.html", video=video, error=str(exc))
        for i, q in enumerate(questions):
            db.session.add(
                QuizQuestion(
                    video_id=video.id,
                    question_text=q["question"],
                    choices_json=json.dumps(q["choices"]),
                    correct_index=q["correct_index"],
                    sort_order=i,
                )
            )
        db.session.commit()

    questions = QuizQuestion.query.filter_by(video_id=video.id).order_by(
        QuizQuestion.sort_order
    ).all()
    questions_view = [
        {"id": q.id, "question": q.question_text, "choices": json.loads(q.choices_json)}
        for q in questions
    ]
    return render_template("quiz.html", video=video, questions=questions_view)


@bp.route("/video/<int:video_id>/quiz/submit", methods=["POST"])
@login_required
def quiz_submit(video_id):
    video = db.session.get(Video, video_id)
    if not video:
        abort(404)

    answers = request.get_json(force=True).get("answers", {})  # {question_id: selected_index}
    questions = QuizQuestion.query.filter_by(video_id=video.id).all()

    results = []
    correct_count = 0
    for q in questions:
        selected = answers.get(str(q.id))
        is_correct = selected is not None and int(selected) == q.correct_index
        if is_correct:
            correct_count += 1
        db.session.add(
            QuizAttempt(
                user_id=current_user.id,
                question_id=q.id,
                selected_index=selected if selected is not None else -1,
                is_correct=is_correct,
            )
        )
        results.append(
            {
                "question_id": q.id,
                "correct_index": q.correct_index,
                "selected_index": selected,
                "is_correct": is_correct,
            }
        )
    db.session.commit()

    return jsonify(
        {
            "score": correct_count,
            "total": len(questions),
            "results": results,
        }
    )
