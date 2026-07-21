from flask import Blueprint, flash, redirect, render_template, request, url_for

from .auth import admin_required
from .models import (
    Comment,
    QuizAttempt,
    QuizQuestion,
    RegulationQuestion,
    User,
    Video,
    WatchProgress,
    db,
)

bp = Blueprint("admin", __name__, url_prefix="/admin")


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
    return render_template("admin_staff.html", staff=all_staff)


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
