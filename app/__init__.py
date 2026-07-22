from flask import Flask, session
from flask_login import current_user
from flask_migrate import Migrate

from . import config
from .admin import bp as admin_bp
from .ask import bp as ask_bp
from .auth import bp as auth_bp, init_login
from .models import Category, LoginSession, User, db, now
from .routes import bp as main_bp

LAST_SEEN_UPDATE_INTERVAL_SECONDS = 60

migrate = Migrate()

# Matches the subfolder names under Google Drive > Shared with me > Full Domestic Videos
DEFAULT_CATEGORIES = [
    "Apprentice On Boarding",
    "Meter Box Upgrade",
    "Earthing",
    "IXL Installation",
    "Lighting",
    "Testing",
    "3 Phase",
    "Generator",
    "CCTV",
    "Tesla",
    "Toyota",
]


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.secret_key()
    app.config["SQLALCHEMY_DATABASE_URI"] = config.database_url()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = None  # video streaming can be large

    db.init_app(app)
    migrate.init_app(app, db)
    init_login(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(ask_bp)

    @app.before_request
    def _touch_login_session():
        if not current_user.is_authenticated:
            return
        login_session_id = session.get("login_session_id")
        if not login_session_id:
            return
        login_session = db.session.get(LoginSession, login_session_id)
        if not login_session or login_session.ended_at is not None:
            return
        if (now() - login_session.last_seen_at).total_seconds() > LAST_SEEN_UPDATE_INTERVAL_SECONDS:
            login_session.last_seen_at = now()
            db.session.commit()

    # Schema is owned by Alembic migrations (see migrations/), not created here — this
    # keeps `flask db ...` commands safe to run against a database with no tables yet.
    # Row seeding is a separate, explicit step: run `flask seed` after `flask db upgrade`
    # (both are already chained into run.sh for local dev).
    @app.cli.command("seed")
    def seed_command():
        """Seed default categories and the admin account (idempotent)."""
        _seed_categories()
        _seed_admin()
        print("Seed complete.")

    return app


def _seed_categories():
    if Category.query.count() > 0:
        return
    for i, name in enumerate(DEFAULT_CATEGORIES):
        db.session.add(Category(name=name, sort_order=i))
    db.session.commit()


def _seed_admin():
    seed = config.admin_seed()
    if User.query.filter_by(username=seed["username"]).first():
        return
    admin = User(name=seed["name"], username=seed["username"], role="admin")
    admin.set_password(seed["password"])
    db.session.add(admin)
    db.session.commit()
