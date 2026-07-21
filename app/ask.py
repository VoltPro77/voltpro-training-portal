import json

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from . import config
from .models import RegulationQuestion, db
from .regs import answer_question

bp = Blueprint("ask", __name__)

# Source documents indexed for Ask the Regs, also linked directly for staff to view/download.
DOCUMENTS = [
    {"label": "AS/NZS 3000:2018 — Wiring Rules", "key": "documents/AS-NZS-3000-2018.pdf"},
    {
        "label": "AS/NZS 3008.1.1:2017 Section 3 — Current-carrying capacity",
        "key": "documents/AS-NZS-3008.1.1-2017-Section-3.pdf",
    },
]


def _document_links():
    base_url = config.r2_config()["public_base_url"].rstrip("/")
    return [{"label": d["label"], "url": f"{base_url}/{d['key']}"} for d in DOCUMENTS]


@bp.route("/ask")
@login_required
def ask_page():
    recent = RegulationQuestion.query.order_by(RegulationQuestion.created_at.desc()).limit(50).all()
    return render_template("ask.html", recent=recent, documents=_document_links())


@bp.route("/api/ask", methods=["POST"])
@login_required
def api_ask():
    question_text = (request.get_json(force=True).get("question") or "").strip()
    if not question_text:
        return jsonify({"error": "empty question"}), 400

    try:
        result = answer_question(question_text)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 503

    citations = result.get("citations", [])
    record = RegulationQuestion(
        user_id=current_user.id,
        question=question_text,
        answer=result["answer"],
        citations=json.dumps(citations),
    )
    db.session.add(record)
    db.session.commit()

    return jsonify(
        {
            "id": record.id,
            "question": record.question,
            "answer": record.answer,
            "citations": citations,
            "user_name": current_user.name,
            "created_at": record.created_at.isoformat(),
        }
    )
