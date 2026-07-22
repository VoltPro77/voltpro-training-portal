from datetime import datetime, timezone

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


def now():
    # Naive UTC, not aware — matches what SQLite/Postgres hand back after a round-trip
    # through a plain (non-timezone) DateTime column, so a freshly computed now() can be
    # safely subtracted from a value just loaded from the DB (see LoginSession).
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="staff")  # "admin" or "staff"
    created_at = db.Column(db.DateTime, default=now)
    last_login_at = db.Column(db.DateTime, nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"


class LoginSession(db.Model):
    """One row per login. last_seen_at is refreshed periodically while the user is
    active (see app before_request hook) since most users never hit an explicit
    logout — it's the best available proxy for when the session actually ended.
    """

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    started_at = db.Column(db.DateTime, default=now)
    last_seen_at = db.Column(db.DateTime, default=now)
    ended_at = db.Column(db.DateTime, nullable=True)  # set on explicit logout

    user = db.relationship("User", backref="login_sessions")

    @property
    def duration_seconds(self):
        end = self.ended_at or self.last_seen_at
        return max(0, int((end - self.started_at).total_seconds()))


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    sort_order = db.Column(db.Integer, default=0)

    videos = db.relationship(
        "Video", backref="category", order_by="Video.sort_order, Video.title"
    )


class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    subheading = db.Column(db.String(120), nullable=True)  # groups videos within a category, e.g. a Drive subfolder name
    sort_order = db.Column(db.Integer, default=0)  # lower shows first within a category; ties break by title
    storage_key = db.Column(db.String(500), nullable=True)  # set once ingested (hosted videos)
    youtube_id = db.Column(db.String(20), nullable=True)  # set instead of storage_key for linked YouTube videos
    source_channel = db.Column(db.String(120), nullable=True)  # attribution for linked videos, e.g. "Electrical How To"
    duration_seconds = db.Column(db.Integer, nullable=True)
    drive_source_id = db.Column(db.String(100), nullable=True)
    transcript_text = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=now)

    comments = db.relationship(
        "Comment", backref="video", cascade="all, delete-orphan", order_by="Comment.created_at"
    )
    quiz_questions = db.relationship(
        "QuizQuestion", backref="video", cascade="all, delete-orphan"
    )

    @property
    def is_ready(self):
        return bool(self.storage_key) or bool(self.youtube_id)

    @property
    def is_external(self):
        return bool(self.youtube_id)

    @property
    def has_quiz(self):
        return len(self.quiz_questions) > 0


class WatchProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey("video.id"), nullable=False)
    seconds_watched = db.Column(db.Integer, default=0)
    percent_complete = db.Column(db.Float, default=0.0)
    completed_at = db.Column(db.DateTime, nullable=True)
    last_watched_at = db.Column(db.DateTime, default=now, onupdate=now)

    user = db.relationship("User")
    video = db.relationship("Video")

    __table_args__ = (db.UniqueConstraint("user_id", "video_id", name="uq_user_video"),)


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey("video.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("comment.id"), nullable=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=now)

    user = db.relationship("User")
    replies = db.relationship("Comment", backref=db.backref("parent", remote_side=[id]))


class QuizQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey("video.id"), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    choices_json = db.Column(db.Text, nullable=False)  # JSON list of choice strings
    correct_index = db.Column(db.Integer, nullable=False)
    sort_order = db.Column(db.Integer, default=0)

    attempts = db.relationship("QuizAttempt", backref="question", cascade="all, delete-orphan")


class QuizAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("quiz_question.id"), nullable=False)
    selected_index = db.Column(db.Integer, nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False)
    attempted_at = db.Column(db.DateTime, default=now)

    user = db.relationship("User")


class RegulationChunk(db.Model):
    """One page of extracted regulation-document text (AS/NZS 3000, AS/NZS 3008, etc.),
    used as retrieval context for 'Ask the Regs'.

    Populated by scripts/extract_regulations.py — never exposed directly to staff, only
    used server-side to ground AI-generated answers with citations.
    """

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(120), nullable=False, index=True)  # e.g. "AS/NZS 3000:2018"
    printed_page = db.Column(db.Integer, nullable=False, index=True)
    text = db.Column(db.Text, nullable=False)


class RegulationQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    citations = db.Column(db.Text, nullable=True)  # JSON list of {"source": ..., "page": ...}
    created_at = db.Column(db.DateTime, default=now)

    user = db.relationship("User")

    @property
    def formatted_citations(self):
        """e.g. 'AS/NZS 3000:2018 p.278, 282 · AS/NZS 3008.1.1:2017 Section 3 p.12'"""
        if not self.citations:
            return ""
        import json as _json

        by_source = {}
        for c in _json.loads(self.citations):
            by_source.setdefault(c["source"], []).append(str(c["page"]))
        return " · ".join(f"{source} p.{', '.join(pages)}" for source, pages in by_source.items())
