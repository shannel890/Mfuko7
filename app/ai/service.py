import json
import os

from google import genai
from google.genai import types
from flask import session
from app.extensions import db
from app.models import AIConversation, AIMessage

from app.ai.prompts import SYSTEM_PROMPT
from app.ai.tools import (
    get_rent_balance,
    get_current_invoice,
    get_my_property_info,
    get_payment_history,
    get_lease_details,
    get_maintenance_requests,
    get_landlord_info,
    create_maintenance_request,
    get_tenant_account_summary,
    get_payment_instructions,
    initiate_rent_payment,
    get_financial_summary,
    prepare_rent_payment as prepare_rent_payment_tool_impl,
    search_properties,
)


client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.8-flash",
)


def get_rent_balance_tool(user):
    return get_rent_balance(user)


def get_current_invoice_tool(user):
    return get_current_invoice(user)

def get_payment_history_tool(user, limit=10):
    return get_payment_history(
        user,
        limit=limit,
    )
def get_my_property_info_tool(user):
    return get_my_property_info(user)

def get_lease_details_tool(user):
    return get_lease_details(user)

def get_landlord_info_tool(user):
    return get_landlord_info(user)

def get_tenant_account_summary_tool(user):
    return get_tenant_account_summary(user)

def get_financial_summary_tool(user):
    return get_financial_summary(user)

def get_payment_instructions_tool(user):
    return get_payment_instructions(user)

def initiate_rent_payment_tool(user, amount, confirmed=False):
    return initiate_rent_payment(
        user,
        amount=amount,
        confirmed=confirmed,
    )
def prepare_rent_payment_tool(user, amount):
    result = prepare_rent_payment_tool_impl(user, amount)

    if result.get("success"):
        prepare_rent_payment(user, amount)

    return result

def create_maintenance_request_tool(
    user,
    title,
    description,
):
    return create_maintenance_request(
        user,
        title=title,
        description=description,
    )


def search_properties_tool(
    county=None,
    property_type=None,
    max_rent=None,
    bedrooms=None,
):
    return search_properties(
        county=county,
        property_type=property_type,
        max_rent=max_rent,
        bedrooms=bedrooms,
    )

def prepare_rent_payment(user, amount):
    """
    Store a pending rent payment in the authenticated user's session.
    Does not initiate M-Pesa.
    """
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {
            "success": False,
            "message": "Please provide a valid payment amount."
        }

    if amount <= 0:
        return {
            "success": False,
            "message": "Payment amount must be greater than zero."
        }

    session["pending_rent_payment"] = {
        "amount": amount,
        "user_id": user.id,
    }

    return {
        "success": True,
        "amount": amount,
        "message": (
            f"You're about to initiate an M-Pesa payment of "
            f"Ksh {amount:,.2f}. Please confirm if you want to proceed."
        ),
    }


def confirm_rent_payment(user):
    """
    Execute a previously prepared rent payment after explicit confirmation.
    """
    pending = session.get("pending_rent_payment")

    if not pending:
        return {
            "success": False,
            "message": "There is no pending rent payment to confirm."
        }

    if pending.get("user_id") != user.id:
        session.pop("pending_rent_payment", None)

        return {
            "success": False,
            "message": "The pending payment does not belong to this account."
        }

    amount = pending.get("amount")

    result = initiate_rent_payment(
        user,
        amount=amount,
        confirmed=True,
    )

    if result.get("success"):
        session.pop("pending_rent_payment", None)

    return result


TOOLS = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="get_rent_balance",
                description=(
                    "Get the authenticated tenant's rent information, "
                    "current invoice and confirmed payment total."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={},
                ),
            ),
            types.FunctionDeclaration(
                name="get_current_invoice",
                description=(
                    "Get the authenticated tenant's latest rental invoice, "
                    "including invoice number, issue date, total amount, "
                    "amount due, status, and description."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={},
                ),
            ),
            types.FunctionDeclaration(
                name="get_payment_history",
                description=(
                    "Get payment history belonging to the authenticated tenant."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "limit": types.Schema(
                            type=types.Type.INTEGER,
                            description=(
                                "Maximum number of payments to return. "
                                "Use a value between 1 and 20."
                            ),
                        )
                    },
                ),
            ),
            types.FunctionDeclaration(
                name="search_properties",
                description=(
                    "Search available vacant rental units by county, "
                    "property type, maximum rent, or bedrooms."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "county": types.Schema(
                            type=types.Type.STRING,
                            nullable=True,
                        ),
                        "property_type": types.Schema(
                            type=types.Type.STRING,
                            nullable=True,
                        ),
                        "max_rent": types.Schema(
                            type=types.Type.NUMBER,
                            nullable=True,
                        ),
                        "bedrooms": types.Schema(
                            type=types.Type.INTEGER,
                            nullable=True,
                        ),
                    },
                ),
            ),
            types.FunctionDeclaration(
                name="get_maintenance_requests",
                description=(
                    "Get maintenance requests belonging to the authenticated tenant."
                    "including their status and details."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "limit": types.Schema(
                            type=types.Type.INTEGER,
                            description=(
                                "Maximum number of maintenance requests to return. "
                                "Use a value between 1 and 20."
                            ),
                        )
                    },
                ),
            ),
            types.FunctionDeclaration(
                name="create_maintenance_request",
                description=(
                    "Create a maintenance request for the authenticated tenant. "
                    "Use this only when the tenant clearly asks to report or submit "
                    "a maintenance issue."
                ),
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "title": types.Schema(
                            type=types.Type.STRING,
                            description="Short title describing the maintenance issue.",
                        ),
                        "description": types.Schema(
                            type=types.Type.STRING,
                            description="Detailed description of the maintenance issue.",
                        ),
                    },
                    required=["title", "description"],
                ),
            ),
            types.FunctionDeclaration(
                name="get_my_property_info",
                description=(
                    "Get the authenticated tenant's current property, unit, rent, "
                    "bedroom, bathroom, property address, and lease information."
                ),
                parameters=types.Schema(
                    type="OBJECT",
                    properties={},
                ),
            ),
            types.FunctionDeclaration(
                name="get_lease_details",
                description=(
                    "Get the authenticated tenant's lease dates, monthly rent, "
                    "rent due day, grace period, and tenant status."
                ),
                parameters=types.Schema(
                    type="OBJECT",
                    properties={},
                ),
            ),
            types.FunctionDeclaration(
                name="get_landlord_info",
                description=(
                    "Get the authenticated tenant's landlord or property manager "
                    "name, email address, and phone number."
                ),
                parameters=types.Schema(
                    type="OBJECT",
                    properties={},
                ),
            ),
            types.FunctionDeclaration(
                name="get_tenant_account_summary",
                description=(
                    "Get a consolidated summary of the authenticated tenant's "
                    "property, unit, rent, lease, landlord, rent balance, and "
                    "recent maintenance requests."
                ),
                parameters=types.Schema(
                    type="OBJECT",
                    properties={},
                ),
            ),
            types.FunctionDeclaration(
                name="get_financial_summary",
                description=(
                    "Get a consolidated financial summary for the authenticated tenant, "
                    "including monthly rent, current rent balance, total confirmed "
                    "payments, latest payment, and recent payment history."
                ),
                parameters=types.Schema(
                    type="OBJECT",
                    properties={},
                ),
            ),
            types.FunctionDeclaration(
                name="get_payment_instructions",
                description=(
                    "Get the authenticated tenant's property-specific payment "
                    "instructions, including payment method, PayBill number, and fees."
                ),
                parameters=types.Schema(
                    type="OBJECT",
                    properties={},
                ),
            ),
            types.FunctionDeclaration(
                name="prepare_rent_payment",
                description="Prepare an M-Pesa rent payment and ask the tenant for explicit confirmation. Never initiates the payment.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "amount": types.Schema(
                            type=types.Type.NUMBER,
                            description="The amount of rent the tenant wants to pay in Kenyan shillings."
                        )
                    },
                    required=["amount"],
                ),
            ),
        ]
    )
]


def execute_tool(name, arguments, user):

    if name == "get_rent_balance":
        return get_rent_balance_tool(user)

    if name == "get_current_invoice":
        return get_current_invoice_tool(user)
    
    if name == "get_current_invoice":
        return get_current_invoice_tool(user)

    if name == "get_payment_history":
        return get_payment_history_tool(
            user,
            limit=arguments.get("limit", 10),
        )

    if name == "get_maintenance_requests":
        return get_maintenance_requests_tool(
            user,
            limit=arguments.get("limit", 10),
        )

    if name == "create_maintenance_request":
        return create_maintenance_request_tool(
            user,
            title=arguments.get("title"),
            description=arguments.get("description"),
        )
    
    if name == "get_my_property_info":
        return get_my_property_info_tool(user)

    if name == "get_lease_details":
        return get_lease_details_tool(user)

    if name == "get_landlord_info":
        return get_landlord_info_tool(user)

    if name == "get_tenant_account_summary":
        return get_tenant_account_summary_tool(user)
    
    if name == "get_financial_summary":
        return get_financial_summary_tool(user)

    if name == "get_payment_instructions":
        return get_payment_instructions_tool(user)

    if name == "prepare_rent_payment":
        return prepare_rent_payment_tool(
            user,
            amount=arguments.get("amount"),
        )

    if name == "search_properties":
        return search_properties_tool(
            county=arguments.get("county"),
            property_type=arguments.get("property_type"),
            max_rent=arguments.get("max_rent"),
            bedrooms=arguments.get("bedrooms"),
        )

    return {
        "success": False,
        "message": "Unknown tool.",
    }
    


def create_conversation(user, first_message):
    """
    Create a new AI conversation for the authenticated user.
    """

    title = first_message.strip()

    if len(title) > 255:
        title = title[:252] + "..."

    conversation = AIConversation(
        user_id=user.id,
        title=title or "New conversation",
    )

    db.session.add(conversation)
    db.session.flush()

    return conversation


def get_conversation(user, conversation_id):
    """
    Load a conversation belonging to the authenticated user.
    """

    conversation = AIConversation.query.filter_by(
        id=conversation_id,
        user_id=user.id,
    ).first()

    if not conversation:
        raise ValueError(
            "Conversation not found."
        )

    return conversation


def save_message(
    conversation,
    role,
    content,
    tool_name=None,
):
    """
    Persist one AI conversation message.
    """

    message = AIMessage(
        conversation_id=conversation.id,
        role=role,
        content=content,
        tool_name=tool_name,
    )

    db.session.add(message)

    return message


def build_history(conversation):
    """
    Convert stored conversation messages into Gemini contents.
    """

    contents = []

    for message in conversation.messages:

        if message.role == "user":

            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            text=message.content
                        )
                    ],
                )
            )

        elif message.role == "assistant":

            contents.append(
                types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            text=message.content
                        )
                    ],
                )
            )

    return contents


def chat(user, message, conversation_id=None):
    """
    Send a user message to MFUKO AI, preserve conversation history,
    handle Gemini tool calls, and persist the conversation.
    """

    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError(
            "GEMINI_API_KEY is not configured."
        )

    try:

        if conversation_id is None:
            conversation = create_conversation(
                user,
                message,
            )
        else:
            conversation = get_conversation(
                user,
                conversation_id,
            )

        save_message(
            conversation,
            "user",
            message,
        )

        contents = build_history(
            conversation
        )

        while True:

            response = client.models.generate_content(
                model=MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    tools=TOOLS,
                ),
            )

            function_calls = []

            if response.candidates:
                for candidate in response.candidates:
                    if candidate.content and candidate.content.parts:
                        for part in candidate.content.parts:
                            if part.function_call:
                                function_calls.append(
                                    part.function_call
                                )

            if not function_calls:

                answer = response.text or ""

                save_message(
                    conversation,
                    "assistant",
                    answer,
                )

                db.session.commit()

                return {
                    "conversation_id": conversation.id,
                    "answer": answer,
                }

            contents.append(
                response.candidates[0].content
            )

            tool_parts = []

            for call in function_calls:

                arguments = dict(
                    call.args or {}
                )

                result = execute_tool(
                    call.name,
                    arguments,
                    user,
                )

                tool_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=call.name,
                            response=result,
                        )
                    )
                )

            contents.append(
                types.Content(
                    role="user",
                    parts=tool_parts,
                )
            )

    except Exception:
        db.session.rollback()
        raise

def get_maintenance_requests_tool(user, limit=10):
    return get_maintenance_requests(
        user,
        limit=limit,
    )