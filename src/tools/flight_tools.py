import copy
import json
from pathlib import Path
import yaml
from langchain.tools import tool
import uuid

# Load YAML 1 lần duy nhất khi import module
DATA_PATH = Path(__file__).parent.parent / "data" / "flights.yaml"
with open(DATA_PATH, "r", encoding="utf-8") as f:
    _RAW_DB = yaml.safe_load(f)["routes"]

FLIGHTS_DB = copy.deepcopy(_RAW_DB)


def reset_db():
    """Reset mutable in-memory database using deepcopy (no repeated disk I/O)."""
    global FLIGHTS_DB
    FLIGHTS_DB = copy.deepcopy(_RAW_DB)


@tool
def search_flights(origin: str, destination: str) -> str:
    """
    Search for flights between two airports.

    Args:
        origin: IATA code of origin airport (e.g., "HAN").
        destination: IATA code of destination airport (e.g., "SGN").

    Returns:
        JSON string containing list of flights. Each flight has:
        id, airline, departure, arrival, class, price, seats.
        Returns JSON with error key if route not found.
    """
    # TODO: build route key from origin + destination
    origin = origin.upper().strip()
    destination = destination.upper().strip()
    route_key = f"{origin}-{destination}"

    matching_routes = FLIGHTS_DB.get(route_key, [])

    # Filter strictly by destination and origin
    matching_routes = [
        f for f in matching_routes
        if f.get("origin") == origin and f.get("destination") == destination
    ]

    # TODO: lookup in FLIGHTS_DB
    # TODO: handle route not found
    if not matching_routes:
        return json.dumps({"error": "No flights found for the specified route."})

    # TODO: return JSON string
    return json.dumps(matching_routes)


@tool
def get_flight_details(flight_id: str) -> str:
    """
    Get details of a specific flight by its ID.

    Args:
        flight_id: ID of the flight (e.g., "VN123").

    Returns:
        JSON string containing flight details. Returns JSON with error key if flight not found.
    """
    # TODO: lookup flight by ID in FLIGHTS_DB
    for _, flights in FLIGHTS_DB.items():
        for flight in flights:
            if flight["id"] == flight_id:
                return json.dumps(flight)
    # TODO: handle flight not found
    return json.dumps({"error": "Flight not found."})


@tool
def check_availability(flight_id: str) -> str:
    """
    Check seat availability for a specific flight by its ID.

    Args:
        flight_id: ID of the flight (e.g., "VN123").

    Returns:
        JSON string containing seat availability. Returns JSON with error key if flight not found.
    """
    for _, flights in FLIGHTS_DB.items():
        for flight in flights:
            if flight["id"] == flight_id:
                if flight["seats"] > 0:
                    return json.dumps({"status": "available", "seats_left": flight["seats"]})
                return json.dumps({"status": "sold_out", "seats_left": 0})
    return json.dumps({"error": "Flight not found."})


@tool
def book_flight(flight_id: str, passenger_name: str, passengers: int) -> str:
    """
    Book a flight for passengers.

    IMPORTANT:
    - price in mock data is PER-PASSENGER.
    - total_price = flight.price * passengers.
    - This tool is DEFENSIVE: it re-validates seats >= passengers.
    - No rollback: booking is treated as atomic. If fail, no partial state.

    Args:
        flight_id: Flight identifier (e.g., "VN123").
        passenger_name: Name of lead passenger.
        passengers: Number of passengers (must be > 0).

    Returns:
        JSON with booking_id, status, passenger_name, passengers, total_price.
        Returns JSON with error key if booking fails.
    """
    # TODO 1: validate passengers > 0
    if passengers <= 0:
        return json.dumps({"error": "Number of passengers must be greater than zero."})
    # TODO 2: find flight by flight_id
    flight = None
    for _, flights in FLIGHTS_DB.items():
        for f in flights:
            if f["id"] == flight_id:
                flight = f
                break
        if flight:
            break
    # TODO 3: if not found → error
    if not flight:
        return json.dumps({"error": "Flight not found."})
    # TODO 4: check seats >= passengers (defensive)
    if flight["seats"] < passengers:
        return json.dumps({"error": "Not enough seats available."})
    # TODO 5: if not → error
    # TODO 6: generate booking_id
    booking_id = f"Booking_{uuid.uuid4()}"
    # TODO 7: calculate total_price
    total_price = flight["price"] * passengers
    flight["seats"] -= passengers
    # TODO 8: return JSON
    return json.dumps({
        "booking_id": booking_id,
        "flight_id": flight_id,
        "origin": flight["origin"],
        "destination": flight["destination"],
        "status": "confirmed",
        "passenger_name": passenger_name,
        "passengers": passengers,
        "total_price": total_price,
        "seats_left": flight["seats"]
    })
