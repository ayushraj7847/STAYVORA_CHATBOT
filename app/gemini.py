import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is missing in .env")

client = genai.Client(api_key=GEMINI_API_KEY)


SYSTEM_PROMPT = """
You are Stayvora's booking assistant.

Rules:
- Reply in English.
- Be friendly and concise.
- Help users search properties and book stays.
- Never invent hotels, rooms, prices, dates, or booking IDs.
- Use real Stayvora data when available.
- Ask for missing booking information one step at a time.
- Never say a booking is confirmed unless the backend confirms it.
"""


def generate_reply(user_message: str, history: list[dict[str, str]]) -> str:

    history_text = ""

    for item in history[-10:]:
        role = item.get("role", "user")
        content = item.get("content", "")
        history_text += f"{role.upper()}: {content}\n"

    prompt = f"""
{SYSTEM_PROMPT}

Conversation history:
{history_text}

USER:
{user_message}

ASSISTANT:
"""

    models = [
        "gemini-3.8-flash",
        "gemini-3.7-flash",
    ]

    last_error = None

    for model_name in models:

        for attempt in range(3):

            try:

                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        automatic_function_calling={
                            "disable": True
                        }
                    ),
                )

                return response.text or "Sorry, I could not generate a response."

            except Exception as error:

                last_error = error

                print(
                    f"GEMINI ERROR | model={model_name} | attempt={attempt + 1}:",
                    error,
                )

                error_text = str(error)

                if "503" not in error_text and "UNAVAILABLE" not in error_text:
                    break

                time.sleep(2 ** attempt)

    print("GEMINI FINAL ERROR:", last_error)

    return "Sorry, I am having trouble right now. Please try again."