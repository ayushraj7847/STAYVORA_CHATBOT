from typing import TypedDict, List, Dict, Any


class ChatState(TypedDict, total=False):

    session_id: str

    user_message: str

    history: List[Dict[str, str]]

    response: str

    booking: Dict[str, Any]