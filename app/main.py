from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from uuid import uuid4

from twilio.twiml.messaging_response import MessagingResponse

from .graph import chat_graph


app = FastAPI(
    title="Stayvora Chatbot API",
    version="1.0.0",
)


# ===============================
# CORS
# ===============================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ===============================
# STORE CHAT SESSIONS
# ===============================

sessions = {}


# ===============================
# NORMAL CHAT REQUEST
# ===============================

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


# ===============================
# ROOT
# ===============================

@app.get("/")
def root():
    return {
        "success": True,
        "message": "Stayvora Chatbot API is running",
    }


# ===============================
# HEALTH
# ===============================

@app.get("/health")
def health():
    return {
        "success": True,
        "status": "healthy",
    }


# ===============================
# NORMAL CHAT
# ===============================

@app.post("/chat")
def chat(request: ChatRequest):

    session_id = (
        request.session_id
        or str(uuid4())
    )

    session = sessions.get(
        session_id,
        {
            "history": [],
            "booking": {},
        },
    )

    # Send the existing session to LangGraph
    result = chat_graph.invoke({
        "user_message": request.message,
        "history": session.get("history", []),
        "booking": session.get("booking", {}),
        "session_id": session_id,
    })

    # Save history and booking state
    sessions[session_id] = {
        "history": result.get("history", []),
        "booking": result.get("booking", {}),
    }

    return {
        "success": True,
        "session_id": session_id,
        "message": result.get("response", ""),
        "booking": result.get("booking", {}),
    }


# ===============================
# WHATSAPP WEBHOOK
# ===============================

@app.post("/whatsapp")
async def whatsapp(request: Request):

    try:
        # Read Twilio WhatsApp form data
        form = await request.form()

        incoming_message = str(
            form.get("Body") or ""
        ).strip()

        whatsapp_number = str(
            form.get("From") or ""
        ).strip()

        # ===============================
        # CHECK MESSAGE
        # ===============================

        if not incoming_message:
            response = MessagingResponse()

            response.message(
                "Sorry, I could not read your message."
            )

            return Response(
                content=str(response),
                media_type="application/xml",
            )

        # ===============================
        # SESSION ID
        # ===============================

        session_id = (
            whatsapp_number
            or str(uuid4())
        )

        # ===============================
        # GET EXISTING SESSION
        # ===============================

        session = sessions.get(
            session_id,
            {
                "history": [],
                "booking": {},
            },
        )

        # ===============================
        # SEND MESSAGE TO LANGGRAPH
        # ===============================

        result = chat_graph.invoke({
            "user_message": incoming_message,
            "history": session.get("history", []),
            "booking": session.get("booking", {}),
            "session_id": session_id,
        })

        # ===============================
        # SAVE SESSION
        # ===============================

        sessions[session_id] = {
            "history": result.get("history", []),
            "booking": result.get("booking", {}),
        }

        # ===============================
        # GET BOT RESPONSE
        # ===============================

        bot_message = result.get(
            "response",
            "Sorry, something went wrong.",
        )

        # ===============================
        # CREATE TWILIO RESPONSE
        # ===============================

        response = MessagingResponse()

        response.message(bot_message)

        # ===============================
        # RETURN XML
        # ===============================

        return Response(
            content=str(response),
            media_type="application/xml",
        )

    except Exception as error:
        print(
            "WHATSAPP WEBHOOK ERROR:",
            error,
        )

        response = MessagingResponse()

        response.message(
            "Sorry, something went wrong. Please try again."
        )

        return Response(
            content=str(response),
            media_type="application/xml",
        )