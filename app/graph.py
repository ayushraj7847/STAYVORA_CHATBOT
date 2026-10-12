import re
from langgraph.graph import (
    StateGraph,
    START,
    END,
)
from .state import ChatState
from .gemini import generate_reply
from .stayvora_api import (
    search_hotels,
    get_hotel_rooms,
    get_available_room_numbers,
    parse_date,
    create_whatsapp_booking,
)
# ===============================
# PARSE DATES
# ===============================
def parse_dates(message):
    if not message:
        return None
    message = message.strip()
    pattern = (
        r"(\d{1,2}[-/]\d{1,2}[-/]\d{4})"
        r"\s*(?:to|-)\s*"
        r"(\d{1,2}[-/]\d{1,2}[-/]\d{4})"
    )
    match = re.search(
        pattern,
        message,
        re.IGNORECASE,
    )
    if not match:
        return None
    check_in = parse_date(
        match.group(1)
    )
    check_out = parse_date(
        match.group(2)
    )
    if not check_in or not check_out:
        return None
    # Checkout must be after check-in
    if check_out <= check_in:
        return None
    return {
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat(),
    }
# ===============================
# GET NUMBER
# ===============================
def get_number(message):
    match = re.search(
        r"\b([1-9][0-9]?)\b",
        message,
    )
    if not match:
        return None
    return int(match.group(1))
# ===============================
# GET ACTUAL ROOM NUMBER
# ===============================
def get_room_number_from_message(
    message
):
    # Supports:
    # 101
    # room 101
    # Room Number 101
    match = re.search(
        r"(?:room\s*(?:number)?\s*)?(\d{2,5})\b",
        message,
        re.IGNORECASE,
    )
    if not match:
        return None
    return str(
        match.group(1)
    )
# ===============================
# FORMAT HOTELS
# ===============================
def format_hotels(
    hotels
):
    if not hotels:
        return (
            "Sorry, I could not find any "
            "properties for those dates."
        )
    lines = [
        "I found these Stayvora properties:\n"
    ]
    for index, hotel in enumerate(
        hotels[:5],
        start=1,
    ):
        name = hotel.get(
            "name",
            "Stayvora Property",
        )
        rating = hotel.get(
            "rating",
            "N/A",
        )
        price = hotel.get(
            "cheapestPrice",
            "N/A",
        )
        lines.append(
            f"{index}. {name}\n"
            f"   Rating: {rating}/5\n"
            f"   Starting from: ₹{price}/night"
        )
    lines.append(
        "\nReply with the property number."
    )
    return "\n".join(lines)
# ===============================
# FORMAT ROOMS
# ===============================
def format_rooms(
    rooms,
    check_in,
    check_out,
):
    room_options = []
    lines = [
        "Available rooms:\n"
    ]
    for room in rooms:
        available_numbers = (
            get_available_room_numbers(
                room,
                check_in,
                check_out,
            )
        )
        # Skip room type if no actual
        # room number is available
        if not available_numbers:
            continue
        room_name = (
            room.get("title")
            or room.get("name")
            or "Room"
        )
        price = room.get(
            "price",
            room.get(
                "cheapestPrice",
                "N/A",
            ),
        )
        lines.append(
            f"🛏 {room_name}"
        )
        for item in available_numbers:
            room_number = str(
                item.get(
                    "number",
                    "",
                )
            ).strip()
            if not room_number:
                continue
            lines.append(
                f"   • Room {room_number}"
                f" — ₹{price}/night"
            )
            raw_room_number = item.get("raw")
            room_number_id = (
                str(raw_room_number.get("_id"))
                if isinstance(raw_room_number, dict)
                and raw_room_number.get("_id") is not None
                else None
            )
            room_options.append(
                {
                    "room": room,
                    "room_number": room_number,
                    "room_number_id": room_number_id,
                    "price": price,
                }
            )
        lines.append("")
    # No actual available room number
    if not room_options:
        return (
            "Sorry, no rooms are available "
            "for those dates."
        ), []
    lines.append(
        "Reply with the room number.\n"
        "Example: 101"
    )
    return (
        "\n".join(lines),
        room_options,
    )
# ===============================
# CHAT NODE
# ===============================
def chat_node(
    state: ChatState
):
    message = (
        state.get(
            "user_message",
            "",
        )
        .strip()
    )
    history = state.get(
        "history",
        [],
    )
    booking = state.get(
        "booking",
        {},
    ).copy()
    stage = booking.get(
        "stage",
        "start",
    )
    # ===============================
    # START
    # ===============================
    if stage == "start":
        booking["stage"] = (
            "await_city"
        )
        response = (
            "Hello! Welcome to Stayvora. "
            "Where are you planning to travel?"
        )
    # ===============================
    # CITY
    # ===============================
    elif stage == "await_city":
        city = message.strip()
        if not city:
            response = (
                "Please tell me the city "
                "you want to visit."
            )
        else:
            booking["city"] = city
            booking["stage"] = (
                "await_dates"
            )
            response = (
                f"{city.title()} sounds like "
                "a great trip!\n\n"
                "What dates are you planning "
                "to check in and check out?\n\n"
                "Example: "
                "07-10-2026 to 08-10-2026"
            )
    # ===============================
    # DATES
    # ===============================
    elif stage == "await_dates":
        dates = parse_dates(
            message
        )
        if not dates:
            response = (
                "Please send your check-in "
                "and check-out dates like:\n\n"
                "07-10-2026 to 08-10-2026"
            )
        else:
            booking.update(
                dates
            )
            try:
                hotels = search_hotels(
                    booking["city"],
                    limit=10,
                )
                # Highest rating first
                hotels = sorted(
                    hotels,
                    key=lambda item: float(
                        item.get(
                            "rating"
                        ) or 0
                    ),
                    reverse=True,
                )
                booking["hotels"] = (
                    hotels[:5]
                )
                if not booking["hotels"]:
                    booking["stage"] = (
                        "await_city"
                    )
                    response = (
                        "I could not find any "
                        "Stayvora properties in "
                        f"{booking['city'].title()}.\n\n"
                        "Please enter another city."
                    )
                else:
                    booking["stage"] = (
                        "await_hotel"
                    )
                    response = format_hotels(
                        booking["hotels"]
                    )
            except Exception as error:
                print(
                    "HOTEL FETCH ERROR:",
                    error,
                )
                response = (
                    "I am having trouble "
                    "getting Stayvora properties "
                    "right now. Please try again."
                )
    # ===============================
    # HOTEL / PROPERTY SELECTION
    # ===============================
    elif stage == "await_hotel":
        selected_number = get_number(
            message
        )
        hotels = booking.get(
            "hotels",
            [],
        )
        if (
            not selected_number
            or selected_number < 1
            or selected_number > len(hotels)
        ):
            response = (
                "Please reply with a valid "
                "property number.\n\n"
                f"Choose between 1 and "
                f"{len(hotels)}."
            )
        else:
            hotel = hotels[
                selected_number - 1
            ]
            booking["hotel"] = hotel
            # ===============================
            # PROPERTY TYPE
            # ===============================
            property_type = str(
                hotel.get(
                    "type",
                    "",
                )
            ).strip().lower()
            # ===============================
            # DIRECT BOOKING PROPERTY TYPES
            # ===============================
            direct_booking_types = [
                "apartment",
                "apartments",
                "flat",
                "flats",
                "villa",
                "villas",
                "resort",
                "resorts",
                "cottage",
                "cottages",
            ]
            # ===============================
            # APARTMENT / FLAT / VILLA / RESORT
            # NO ROOM SELECTION
            # ===============================
            if property_type in direct_booking_types:
                # Clear any old room state
                # from previous booking flow
                booking.pop(
                    "room_options",
                    None,
                )
                booking.pop(
                    "rooms",
                    None,
                )
                booking.pop(
                    "room",
                    None,
                )
                booking.pop(
                    "room_number",
                    None,
                )
                booking.pop(
                    "room_price",
                    None,
                )
                booking["stage"] = (
                    "await_guest_name"
                )
                response = (
                    "Great choice! ✅\n\n"
                    f"🏨 {hotel.get('name', 'Property')}\n"
                    f"🏠 Property Type: "
                    f"{hotel.get('type', 'Property').title()}\n"
                    f"📍 {hotel.get('city', booking.get('city', ''))}\n"
                    f"📅 {booking.get('check_in')} "
                    f"to {booking.get('check_out')}\n"
                    f"💰 Starting from: "
                    f"₹{hotel.get('cheapestPrice', 'N/A')}/night\n\n"
                    "This property does not require "
                    "room selection.\n\n"
                    "Please send the guest's full name."
                )
            # ===============================
            # HOTEL / HOSTEL
            # ROOM BASED PROPERTY
            # ===============================
            else:
                try:
                    rooms = get_hotel_rooms(
                        hotel
                    )
                    check_in = parse_date(
                        booking.get(
                            "check_in"
                        )
                    )
                    check_out = parse_date(
                        booking.get(
                            "check_out"
                        )
                    )
                    room_text, room_options = (
                        format_rooms(
                            rooms,
                            check_in,
                            check_out,
                        )
                    )
                    # No actual room number available
                    if not room_options:
                        booking["stage"] = (
                            "await_hotel"
                        )
                        response = (
                            f"{hotel.get('name', 'Property')} "
                            "does not have available rooms "
                            "for your selected dates.\n\n"
                            "Please choose another property."
                        )
                    else:
                        booking["room_options"] = (
                            room_options
                        )
                        # Keep previous key too
                        # so existing flow does not break
                        booking["rooms"] = (
                            room_options
                        )
                        booking["stage"] = (
                            "await_room_number"
                        )
                        response = (
                            f"{hotel.get('name', 'Property')}"
                            f"\n\n"
                            f"{room_text}"
                        )
                except Exception as error:
                    print(
                        "ROOM FETCH ERROR:",
                        error,
                    )
                    booking["stage"] = (
                        "await_hotel"
                    )
                    response = (
                        "I could not fetch the rooms "
                        "for this property.\n\n"
                        "Please choose another property."
                    )
    # ===============================
    # ACTUAL ROOM NUMBER SELECTION
    # ===============================
    elif stage == "await_room_number":
        selected_room_number = (
            get_room_number_from_message(
                message
            )
        )
        room_options = booking.get(
            "room_options",
            [],
        )
        if not selected_room_number:
            response = (
                "Please send the actual "
                "room number.\n\n"
                "Example: 101"
            )
        else:
            selected_room = None
            for item in room_options:
                stored_room_number = str(
                    item.get(
                        "room_number",
                        "",
                    )
                ).strip()
                if (
                    stored_room_number
                    == selected_room_number
                ):
                    selected_room = item
                    break
            if not selected_room:
                available_numbers = []
                for item in room_options:
                    number = str(
                        item.get(
                            "room_number",
                            "",
                        )
                    ).strip()
                    if number:
                        available_numbers.append(
                            number
                        )
                if available_numbers:
                    response = (
                        "That room is not available "
                        "for your selected dates.\n\n"
                        "Available room numbers:\n"
                        + ", ".join(
                            available_numbers
                        )
                    )
                else:
                    response = (
                        "No available room numbers "
                        "were found.\n\n"
                        "Please choose another property."
                    )
            else:
                room = selected_room[
                    "room"
                ]
                room_number = (
                    selected_room[
                        "room_number"
                    ]
                )
                booking["room"] = room
                booking["room_number"] = (
                    room_number
                )
                booking["room_price"] = (
                    selected_room.get(
                        "price",
                        "N/A",
                    )
                )
                booking["room_number_id"] = selected_room.get(
                    "room_number_id"
                )
                booking["stage"] = (
                    "await_guest_name"
                )
                room_name = (
                    room.get("title")
                    or room.get("name")
                    or "Room"
                )
                response = (
                    "Great choice! ✅\n\n"
                    f"🏨 {booking.get('hotel', {}).get('name', 'Property')}\n"
                    f"🛏 {room_name}\n"
                    f"🚪 Room Number: {room_number}\n"
                    f"💰 ₹{selected_room.get('price', 'N/A')}/night\n"
                    f"📅 {booking.get('check_in')} "
                    f"to {booking.get('check_out')}\n\n"
                    "Please send the guest's "
                    "full name."
                )
    # ===============================
    # NAME
    # ===============================
    elif stage == "await_guest_name":
        if not message:
            response = (
                "Please send the guest's "
                "full name."
            )
        else:
            booking["guest_name"] = (
                message
            )
            booking["stage"] = (
                "await_guest_email"
            )
            response = (
                "Thanks! Please send your "
                "email address."
            )
    # ===============================
    # EMAIL
    # ===============================
    elif stage == "await_guest_email":
        if (
            "@" not in message
            or "." not in message.split("@")[-1]
        ):
            response = (
                "Please send a valid email "
                "address."
            )
        else:
            booking["guest_email"] = (
                message
            )
            hotel = booking.get(
                "hotel",
                {},
            )
            room = booking.get(
                "room",
                {},
            )
            property_type = str(
                hotel.get(
                    "type",
                    "",
                )
            ).strip().lower()
            direct_booking_types = [
                "apartment",
                "apartments",
                "flat",
                "flats",
                "villa",
                "villas",
                "resort",
                "resorts",
                "cottage",
                "cottages",
            ]
            # ===============================
            # DIRECT PROPERTY CONFIRMATION
            # ===============================
            if (
                property_type
                in direct_booking_types
            ):
                response = (
                    "Please confirm your booking:\n\n"
                    f"🏨 {hotel.get('name', 'Property')}\n"
                    f"🏠 Property Type: "
                    f"{hotel.get('type', 'Property').title()}\n"
                    f"📍 {hotel.get('city', booking.get('city', ''))}\n"
                    f"📅 {booking.get('check_in')} "
                    f"to {booking.get('check_out')}\n"
                    f"💰 ₹{hotel.get('cheapestPrice', 'N/A')}/night\n"
                    f"👤 {booking.get('guest_name')}\n"
                    f"📧 {booking.get('guest_email')}\n\n"
                    "Reply YES to confirm."
                )
            # ===============================
            # ROOM PROPERTY CONFIRMATION
            # ===============================
            else:
                room_name = (
                    room.get("title")
                    or room.get("name")
                    or "Room"
                )
                room_number = booking.get(
                    "room_number",
                    "N/A",
                )
                room_price = booking.get(
                    "room_price",
                    "N/A",
                )
                response = (
                    "Please confirm your booking:\n\n"
                    f"🏨 {hotel.get('name', 'Property')}\n"
                    f"🛏 {room_name}\n"
                    f"🚪 Room: {room_number}\n"
                    f"💰 ₹{room_price}/night\n"
                    f"📅 {booking.get('check_in')} "
                    f"to {booking.get('check_out')}\n"
                    f"👤 {booking.get('guest_name')}\n"
                    f"📧 {booking.get('guest_email')}\n\n"
                    "Reply YES to confirm."
                )
            booking["stage"] = (
                "await_confirmation"
            )
    # ===============================
    # CONFIRMATION
    # ===============================
    elif stage == "await_confirmation":
        if message.strip().lower() in {
            "yes",
            "y",
            "confirm",
            "confirmed",
        }:
            try:
                hotel = booking.get("hotel") or {}
                hotel_id = str(hotel.get("_id") or "").strip()
                if not hotel_id:
                    raise RuntimeError("Selected property ID is missing")

                session_id = str(
                    state.get("session_id")
                    or state.get("phone_number")
                    or booking.get("whatsapp_number")
                    or ""
                ).strip()
                if not session_id:
                    raise RuntimeError(
                        "WhatsApp number/session_id is missing from graph state"
                    )

                guest_name = str(booking.get("guest_name") or "").strip()
                guest_email = str(booking.get("guest_email") or "").strip()
                check_in = booking.get("check_in")
                check_out = booking.get("check_out")
                if not guest_name or not guest_email:
                    raise RuntimeError("Guest name or email is missing")
                if not check_in or not check_out:
                    raise RuntimeError("Check-in or check-out date is missing")

                payload = {
                    "whatsappNumber": session_id,
                    "guestName": guest_name,
                    "guestEmail": guest_email,
                    "hotelId": hotel_id,
                    "checkIn": check_in,
                    "checkOut": check_out,
                    "roomNumberId": booking.get("room_number_id"),
                }

                property_type = str(hotel.get("type", "")).strip().lower()
                direct_booking_types = {
                    "apartment",
                    "apartments",
                    "flat",
                    "flats",
                    "resort",
                    "resorts",
                    "villa",
                    "villas",
                    "cottage",
                    "cottages",
                }
                is_direct_booking = property_type in direct_booking_types

                # Hotel and hostel bookings require the selected room-number ID.
                if not is_direct_booking and not payload["roomNumberId"]:
                    raise RuntimeError(
                        "Selected room number ID is missing. Please select a room again."
                    )

                # The backend response confirms whether the booking was saved.
                saved_booking = create_whatsapp_booking(payload)
                booking_id = str(saved_booking["_id"])
                booking["booking_id"] = booking_id
                booking["stage"] = "booking_completed"

                response = (
                    "🎉 Booking Confirmed!\n\n"
                    f"🏨 {hotel.get('name', 'Property')}\n"
                    f"📅 {check_in} to {check_out}\n"
                    f"💰 Total: ₹{saved_booking.get('totalPrice', 0)}\n"
                    f"✅ Status: {saved_booking.get('status', 'Confirmed')}\n\n"
                    f"🧾 Booking ID: {booking_id}\n\n"
                    "Thank you for booking with Stayvora!"
                )
            except Exception as error:
                print("WHATSAPP BOOKING CREATE ERROR:", error)
                booking["stage"] = "await_confirmation"
                response = (
                    "Sorry, I couldn't complete your booking right now. "
                    "Your booking has not been confirmed by the chatbot.\n\n"
                    "Please check the booking service and try sending YES again."
                )
        else:
            response = (
                "No problem. Reply YES when "
                "you want to confirm the booking."
            )

    # ===============================
    # BOOKING COMPLETED
    # ===============================
    elif stage == "booking_completed":
        response = (
            "✅ Your booking is already confirmed.\n\n"
            f"Booking ID: {booking.get('booking_id', 'N/A')}\n\n"
            "Thank you for booking with Stayvora!"
        )

    # ===============================
    # GENERAL CHAT
    # ===============================
    else:
        response = generate_reply(
            message,
            history,
        )
    # ===============================
    # HISTORY
    # ===============================
    updated_history = (
        history
        + [
            {
                "role": "user",
                "content": message,
            },
            {
                "role": "assistant",
                "content": response,
            },
        ]
    )
    # ===============================
    # RETURN STATE
    # ===============================
    return {
        "response": response,
        "history": updated_history,
        "booking": booking,
    }
# ===============================
# LANGGRAPH
# ===============================
graph_builder = StateGraph(
    ChatState
)
graph_builder.add_node(
    "chat",
    chat_node,
)
graph_builder.add_edge(
    START,
    "chat",
)
graph_builder.add_edge(
    "chat",
    END,
)
chat_graph = graph_builder.compile()
