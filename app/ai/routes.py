from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user

from app.ai.service import chat


ai = Blueprint(
    "ai",
    __name__,
    url_prefix="/api/ai"
)


@ai.route("/chat", methods=["POST"])
@login_required
def ai_chat():

    try:
        data = request.get_json(silent=True) or {}

        message = data.get("message", "").strip()

        if not message:
            return jsonify({
                "success": False,
                "error": "Message is required."
            }), 400

        if len(message) > 4000:
            return jsonify({
                "success": False,
                "error": "Message is too long."
            }), 400

        answer = chat(
            current_user,
            message
        )

        return jsonify({
            "success": True,
            "answer": answer
        })

    except Exception as exc:

        current_app.logger.exception(
            "MFUKO AI error"
        )

        return jsonify({
            "success": False,
            "error": (
                "MFUKO AI is temporarily unavailable. "
                "Please try again."
            )
        }), 500