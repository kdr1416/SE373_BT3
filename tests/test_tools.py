"""
Test suite for flight_tools.

Run: python tests/test_tools.py
"""
import json
import sys
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from src.tools.flight_tools import (
    search_flights,
    get_flight_details,
    check_availability,
    book_flight,
    reset_db,
)


@pytest.fixture(autouse=True)
def reset_database():
    """Reset database state before and after each test."""
    reset_db()
    yield
    reset_db()


# ============ SEARCH FLIGHTS ============
def test_search_valid_route():
    """Test 1: valid route HAN-SGN."""
    result = search_flights.invoke({"origin": "HAN", "destination": "SGN"})
    assert "VN123" in result
    parsed = json.loads(result)
    assert isinstance(parsed, list)
    assert len(parsed) == 3


def test_search_invalid_route():
    """Test 2: invalid route HAN-XYZ."""
    result = search_flights.invoke({"origin": "HAN", "destination": "XYZ"})
    parsed = json.loads(result)
    assert "error" in parsed


def test_search_lowercase():
    """Test 3: lowercase input."""
    result = search_flights.invoke({"origin": "han", "destination": "sgn"})
    expected = search_flights.invoke({"origin": "HAN", "destination": "SGN"})
    assert json.loads(result) == json.loads(expected)


def test_search_han_bkk_excludes_dmk():
    """Test 3b: search HAN-BKK strictly excludes flights to DMK and FD643."""
    result = search_flights.invoke({"origin": "HAN", "destination": "BKK"})
    parsed = json.loads(result)
    assert all(f["destination"] == "BKK" for f in parsed)
    assert all(f["id"] != "FD643" for f in parsed)


# ============ GET FLIGHT DETAILS ============
def test_get_details_valid():
    """Test 4: valid flight ID."""
    result = get_flight_details.invoke({"flight_id": "VN123"})
    parsed = json.loads(result)
    assert parsed.get("id") == "VN123"
    assert parsed.get("airline") == "Vietnam Airlines"


def test_get_details_invalid():
    """Test 5: invalid flight ID."""
    result = get_flight_details.invoke({"flight_id": "INVALID_ID"})
    parsed = json.loads(result)
    assert "error" in parsed


# ============ CHECK AVAILABILITY ============
def test_check_available():
    """Test 6: flight with seats > 0."""
    result = check_availability.invoke({"flight_id": "VN123"})
    parsed = json.loads(result)
    assert parsed.get("status") == "available"
    assert parsed.get("seats_left") == 45


def test_check_sold_out():
    """Test 7: flight with seats == 0."""
    result = check_availability.invoke({"flight_id": "FD643"})
    parsed = json.loads(result)
    assert parsed.get("status") == "sold_out"
    assert parsed.get("seats_left") == 0


def test_check_invalid_id():
    """Test 8: invalid flight ID."""
    result = check_availability.invoke({"flight_id": "INVALID_ID"})
    parsed = json.loads(result)
    assert "error" in parsed


# ============ BOOK FLIGHT ============
def test_book_valid():
    """Test 9: happy path."""
    result = book_flight.invoke({
        "flight_id": "VN123",
        "passenger_name": "Nguyen Van A",
        "passengers": 2,
    })
    parsed = json.loads(result)
    assert parsed.get("status") == "confirmed"
    assert "booking_id" in parsed
    assert parsed.get("total_price") == 1200000 * 2


def test_book_zero_passengers():
    """Test 10: passengers = 0."""
    result = book_flight.invoke({
        "flight_id": "VN123",
        "passenger_name": "Nguyen Van A",
        "passengers": 0,
    })
    parsed = json.loads(result)
    assert "error" in parsed


def test_book_negative_passengers():
    """Test 11: passengers = -1."""
    result = book_flight.invoke({
        "flight_id": "VN123",
        "passenger_name": "A",
        "passengers": -1,
    })
    parsed = json.loads(result)
    assert "error" in parsed


def test_book_twice_decrements_seats():
    """Test 12: book 2 lần, seats phải giảm."""
    r1 = book_flight.invoke({
        "flight_id": "VN123",
        "passenger_name": "A",
        "passengers": 2,
    })
    r2 = book_flight.invoke({
        "flight_id": "VN123",
        "passenger_name": "B",
        "passengers": 3,
    })

    p1 = json.loads(r1)
    p2 = json.loads(r2)

    assert p1["seats_left"] == 43   # 45 - 2
    assert p2["seats_left"] == 40   # 43 - 3


def test_book_over_seats():
    """Test 13: passengers > seats."""
    result = book_flight.invoke({
        "flight_id": "QH205",
        "passenger_name": "Nguyen Van A",
        "passengers": 5,
    })
    parsed = json.loads(result)
    assert "error" in parsed


def test_book_invalid_id():
    """Test 14: invalid flight ID."""
    result = book_flight.invoke({
        "flight_id": "INVALID_ID",
        "passenger_name": "Nguyen Van A",
        "passengers": 1,
    })
    parsed = json.loads(result)
    assert "error" in parsed


# ============ RUNNER ============
if __name__ == "__main__":
    tests = [
        test_search_valid_route,
        test_search_invalid_route,
        test_search_lowercase,
        test_search_han_bkk_excludes_dmk,
        test_get_details_valid,
        test_get_details_invalid,
        test_check_available,
        test_check_sold_out,
        test_check_invalid_id,
        test_book_valid,
        test_book_zero_passengers,
        test_book_negative_passengers,
        test_book_twice_decrements_seats,
        test_book_over_seats,
        test_book_invalid_id,
    ]

    passed = 0
    failed = 0
    for t in tests:
        reset_db()
        try:
            t()
            print(f"✅ {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"❌ {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"💥 {t.__name__}: {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")