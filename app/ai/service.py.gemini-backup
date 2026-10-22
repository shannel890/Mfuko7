import json
import os

from google import genai
from google.genai import types

from app.ai.prompts import SYSTEM_PROMPT
from app.ai.tools import (
    get_rent_balance,
    get_payment_history,
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


def get_payment_history_tool(user, limit=10):
    return get_payment_history(
        user,
        limit=limit,
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
        ]
    )
]


def execute_tool(name, arguments, user):

    if name == "get_rent_balance":
        return get_rent_balance_tool(user)

    if name == "get_payment_history":
        return get_payment_history_tool(
            user,
            limit=arguments.get("limit", 10),
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


def chat(user, message):
    """
    Send a user message to MFUKO AI and handle Gemini tool calls.
    """

    if not os.getenv("GEMINI_API_KEY"):
        raise RuntimeError(
            "GEMINI_API_KEY is not configured."
        )

    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part(text=message)
            ],
        )
    ]

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
                            function_calls.append(part.function_call)

        if not function_calls:
            return response.text

        contents.append(response.candidates[0].content)

        tool_parts = []

        for call in function_calls:

            arguments = dict(call.args or {})

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