import json

from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from .models import RegulationQuestion, db
from .regs import answer_question

bp = Blueprint("ask", __name__)


@bp.route("/ask")
@login_required
def ask_page():
    recent = RegulationQuestion.query.order_by(RegulationQuestion.created_at.desc()).limit(50).all()
    return render_template("ask.html", recent=recent)


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
