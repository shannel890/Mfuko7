from flask import Blueprint, request, jsonify, current_app, session
from flask_login import login_required, current_user

from app.ai.service import (
    chat,
    confirm_rent_payment,
)


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
        conversation_id = data.get("conversation_id")

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

        # ---------------------------------------------------------
        # Explicit M-Pesa payment confirmation
        # ---------------------------------------------------------
        pending_payment = session.get("pending_rent_payment")

        confirmation_words = {
            "yes",
            "yes please",
            "confirm",
            "confirmed",
            "proceed",
            "go ahead",
            "pay",
            "make the payment",
        }

        if pending_payment and message.lower() in confirmation_words:
            result = confirm_rent_payment(current_user)

            return jsonify({
                "success": result.get("success", False),
                "conversation_id": conversation_id,
                "answer": result.get("message"),
                "payment": result,
            })

        # ---------------------------------------------------------
        # Normal AI conversation
        # ---------------------------------------------------------
        result = chat(
            current_user,
            message,
            conversation_id=conversation_id,
        )

        return jsonify({
            "success": True,
            "conversation_id": result["conversation_id"],
            "answer": result["answer"],
        })

    except Exception:

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