from flask import Blueprint, flash, redirect, render_template, request, url_for

from .auth import admin_required
from .models import (
    Category,
    Comment,
    LoginSession,
    QuizAttempt,
    QuizQuestion,
    RegulationQuestion,
    User,
    Video,
    WatchProgress,
    db,
)

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _format_duration(seconds):
    if seconds is None:
        return "—"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m"
    return f"{secs}s"


@bp.route("/")
@admin_required
def dashboard():
    staff = User.query.filter_by(role="staff").order_by(User.name).all()
    videos = (
        Video.query.filter(Video.storage_key.isnot(None))
        .order_by(Video.category_id, Video.sort_order, Video.title)
        .all()
    )

    progress_lookup = {
        (p.user_id, p.video_id): p for p in WatchProgress.query.all()
    }

    # per-user quiz average, based on their most recent attempt per question
    quiz_scores = {}
    for u in staff:
        attempts = (
            QuizAttempt.query.filter_by(user_id=u.id)
            .order_by(QuizAttempt.attempted_at.desc())
            .all()
        )
        seen_questions = set()
        correct = 0
        total = 0
        for a in attempts:
            if a.question_id in seen_questions:
                continue
            seen_questions.add(a.question_id)
            total += 1
            if a.is_correct:
                correct += 1
        quiz_scores[u.id] = f"{correct}/{total}" if total else "—"

    return render_template(
        "admin_dashboard.html",
        staff=staff,
        videos=videos,
        progress_lookup=progress_lookup,
        quiz_scores=quiz_scores,
    )


@bp.route("/staff", methods=["GET", "POST"])
@admin_required
def staff():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "").strip()

        if not (name and username and password):
            flash("Name, username, and password are all required.", "error")
        elif User.query.filter_by(username=username).first():
            flash(f"Username '{username}' is already taken.", "error")
        else:
            user = User(name=name, username=username, role="staff")
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash(f"Added staff account for {name}.", "success")
        return redirect(url_for("admin.staff"))

    all_staff = User.query.filter_by(role="staff").order_by(User.name).all()

    last_session_duration = {}
    for u in all_staff:
        last_session = (
            LoginSession.query.filter_by(user_id=u.id)
            .order_by(LoginSession.started_at.desc())
            .first()
        )
        last_session_duration[u.id] = _format_duration(
            last_session.duration_seconds if last_session else None
        )

    return render_template(
        "admin_staff.html", staff=all_staff, last_session_duration=last_session_duration
    )


@bp.route("/staff/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete_staff(user_id):
    user = db.session.get(User, user_id)
    if user and user.role == "staff":
        db.session.delete(user)
        db.session.commit()
        flash(f"Removed {user.name}.", "success")
    return redirect(url_for("admin.staff"))


@bp.route("/questions")
@admin_required
def questions():
    all_questions = (
        RegulationQuestion.query.order_by(RegulationQuestion.created_at.desc()).all()
    )
    return render_template("admin_questions.html", questions=all_questions)


@bp.route("/videos")
@admin_required
def videos():
    staff_count = User.query.filter_by(role="staff").count()

    completed_counts = dict(
        db.session.query(WatchProgress.video_id, db.func.count(WatchProgress.id))
        .filter(WatchProgress.completed_at.isnot(None))
        .group_by(WatchProgress.video_id)
        .all()
    )

    categories = Category.query.order_by(Category.sort_order).all()
    video_stats = {}
    for category in categories:
        for video in category.videos:
            if not video.is_ready:
                continue
            completed = completed_counts.get(video.id, 0)
            video_stats[video.id] = {
                "completed": completed,
                "pct": round(completed / staff_count * 100) if staff_count else 0,
            }

    return render_template(
        "admin_videos.html",
        categories=categories,
        video_stats=video_stats,
        staff_count=staff_count,
    )


@bp.route("/videos/<int:video_id>/toggle-priority", methods=["POST"])
@admin_required
def toggle_priority(video_id):
    video = db.session.get(Video, video_id)
    if video:
        video.is_priority = not video.is_priority
        db.session.commit()
    return redirect(url_for("admin.videos"))


@bp.route("/quiz-insights")
@admin_required
def quiz_insights():
    rows = (
        db.session.query(
            QuizQuestion,
            db.func.count(QuizAttempt.id).label("attempts"),
            db.func.sum(db.case((QuizAttempt.is_correct.is_(False), 1), else_=0)).label("misses"),
        )
        .join(QuizAttempt, QuizAttempt.question_id == QuizQuestion.id)
        .group_by(QuizQuestion.id)
        .having(db.func.count(QuizAttempt.id) > 0)
        .all()
    )

    insights = []
    for question, attempts, misses in rows:
        insights.append(
            {
                "question": question,
                "video": question.video,
                "attempts": attempts,
                "misses": misses,
                "miss_rate": round(misses / attempts * 100) if attempts else 0,
            }
        )
    insights.sort(key=lambda r: (-r["miss_rate"], -r["attempts"]))

    return render_template("admin_quiz_insights.html", insights=insights)
