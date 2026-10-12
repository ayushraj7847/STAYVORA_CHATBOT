import os
from datetime import date, datetime, timedelta

import httpx
from dotenv import load_dotenv


load_dotenv()


BASE_URL = os.getenv(
    "STAYVORA_API_URL",
    "https://stayvora-backend.onrender.com/api",
).rstrip("/")


# ===============================
# API REQUEST
# ===============================

def request_api(
    method,
    path,
    params=None,
    json=None,
):
    url = f"{BASE_URL}{path}"

    with httpx.Client(timeout=20) as client:
        response = client.request(
            method,
            url,
            params=params,
            json=json,
        )

        response.raise_for_status()

        return response.json()


# ===============================
# SEARCH HOTELS
# ===============================

def search_hotels(
    city,
    limit=10,
):
    data = request_api(
        "GET",
        "/hotels",
        params={
            "city": city,
            "limit": limit,
        },
    )

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in [
            "hotels",
            "data",
            "results",
        ]:
            if isinstance(data.get(key), list):
                return data[key]

    return []


# ===============================
# GET ROOM
# ===============================

def get_room(room_id):
    return request_api(
        "GET",
        f"/rooms/{room_id}",
    )


# ===============================
# GET HOTEL ROOMS
# ===============================

def get_hotel_rooms(hotel):
    room_ids = hotel.get(
        "rooms",
        [],
    )

    rooms = []

    for room_id in room_ids:
        try:
            # Support populated room objects too
            if isinstance(room_id, dict):
                room = room_id
            else:
                room = get_room(room_id)

            if room:
                rooms.append(room)

        except Exception as error:
            print(
                "ROOM FETCH ERROR:",
                room_id,
                error,
            )

    return rooms


# ===============================
# PARSE DATE
# ===============================

def parse_date(value):
    if value is None:
        return None

    value = str(value).strip()

    formats = [
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]

    for date_format in formats:
        try:
            return datetime.strptime(
                value[:26],
                date_format,
            ).date()

        except ValueError:
            continue

    return None


# ===============================
# PARSE UNAVAILABLE DATE
# ===============================

def parse_unavailable_date(value):
    if value is None:
        return None

    # Handle Python datetime objects
    if isinstance(value, datetime):
        return value.date()

    # Handle Python date objects
    if isinstance(value, date):
        return value

    # Handle date objects returned in dictionary form
    if isinstance(value, dict):
        value = (
            value.get("date")
            or value.get("$date")
            or value.get("value")
        )

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    # Handle ISO dates, including timestamps ending in Z
    try:
        normalized_value = value.replace(
            "Z",
            "+00:00",
        )

        return datetime.fromisoformat(
            normalized_value
        ).date()

    except ValueError:
        # Try the existing date formats as a fallback
        return parse_date(value)


# ===============================
# GET ROOM NUMBER
# ===============================

def get_room_number_value(
    room_number,
):
    # Example:
    # { number: 101, unavailableDates: [] }

    if isinstance(room_number, dict):
        value = (
            room_number.get("number")
            or room_number.get("roomNumber")
        )

        if value is not None:
            return value

    # Example:
    # 101
    return room_number


# ===============================
# GET UNAVAILABLE DATES
# ===============================

def get_unavailable_dates(
    room_number,
):
    if not isinstance(room_number, dict):
        return []

    return (
        room_number.get(
            "unavailableDates",
            [],
        )
        or []
    )


# ===============================
# CHECK ROOM AVAILABILITY
# ===============================

def is_room_available(
    room_number,
    check_in,
    check_out,
):
    if not check_in or not check_out:
        return True

    unavailable_dates = get_unavailable_dates(
        room_number
    )

    # No blocked dates
    if not unavailable_dates:
        return True

    current_date = check_in

    while current_date < check_out:
        for unavailable in unavailable_dates:
            unavailable_date = parse_unavailable_date(
                unavailable
            )

            if unavailable_date == current_date:
                return False

        current_date += timedelta(days=1)

    return True


# ===============================
# GET ALL ROOM NUMBERS
# ===============================

def get_room_numbers(
    room,
    check_in=None,
    check_out=None,
):
    room_numbers = (
        room.get(
            "roomNumbers",
            [],
        )
        or []
    )

    result = []

    for room_number in room_numbers:
        number = get_room_number_value(
            room_number
        )

        if number is None:
            continue

        available = is_room_available(
            room_number,
            check_in,
            check_out,
        )

        result.append(
            {
                "number": str(number),
                "available": available,
                "raw": room_number,
            }
        )

    return result


# ===============================
# GET AVAILABLE ROOM NUMBERS
# ===============================

def get_available_room_numbers(
    room,
    check_in,
    check_out,
):
    room_numbers = get_room_numbers(
        room,
        check_in,
        check_out,
    )

    return [
        item
        for item in room_numbers
        if item["available"]
    ]


# ===============================
# CREATE WHATSAPP BOOKING
# ===============================

def create_whatsapp_booking(payload):
    secret = os.getenv(
        "STAYVORA_BOOKING_SECRET"
    )

    if not secret:
        raise RuntimeError(
            "STAYVORA_BOOKING_SECRET is missing in .env"
        )

    url = f"{BASE_URL}/bookings/whatsapp"

    headers = {
        "x-whatsapp-booking-secret": secret,
    }

    with httpx.Client(timeout=30) as client:
        response = client.post(
            url,
            json=payload,
            headers=headers,
        )

        try:
            data = response.json()
        except ValueError:
            data = {}

        # Check whether the backend returned an HTTP error
        if not response.is_success:
            if isinstance(data, dict):
                message = data.get(
                    "message",
                    "WhatsApp booking API failed",
                )
            else:
                message = "WhatsApp booking API failed"

            raise RuntimeError(
                f"{response.status_code}: {message}"
            )

        # Ensure the backend returned a valid response
        if not isinstance(data, dict):
            raise RuntimeError(
                "Invalid response from WhatsApp booking API"
            )

        if data.get("success") is not True:
            raise RuntimeError(
                data.get(
                    "message",
                    "Booking was not confirmed",
                )
            )

        booking = data.get("booking")

        if not isinstance(booking, dict):
            raise RuntimeError(
                "Booking API did not return a booking record"
            )

        if not booking.get("_id"):
            raise RuntimeError(
                "Booking ID was not returned"
            )

        # Return only the booking confirmed by the backend
        return booking