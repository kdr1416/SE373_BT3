"""
Test suite for Agent Harness (4 layers) and Integration with Tools.

Run: python tests/test_harness.py
"""
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.harness import (
    AgentHarness,
    ConstraintsLoader,
    CompletionChecker,
    PermissionChecker,
    HandoffManager,
)
from src.tools.flight_tools import book_flight, reset_db


@pytest.fixture(autouse=True)
def setup_db():
    reset_db()
    yield
    reset_db()


# ==========================================
# LAYER 1: ConstraintsLoader & validate_task_input
# ==========================================
def test_constraints_loader_loads_data():
    loader = ConstraintsLoader()
    assert loader.get_max_passengers() == 4
    assert loader.get_max_budget() == 10000000
    assert "Vietnam Airlines" in loader.get_allowed_airlines()
    assert "search_flights" in loader.get_read_only_tools()
    assert "book_flight" in loader.get_requires_approval_tools()


def test_validate_task_input_valid():
    harness = AgentHarness()
    task = {"origin": "HAN", "destination": "SGN", "passengers": 2, "max_budget": 5000000}
    valid, msg = harness.validate_task_input(task)
    assert valid is True
    assert msg == "Task inputs are valid."


def test_validate_task_input_invalid_passengers():
    harness = AgentHarness()
    # <= 0
    v1, _ = harness.validate_task_input({"origin": "HAN", "destination": "SGN", "passengers": 0})
    assert v1 is False

    # > max (4)
    v2, _ = harness.validate_task_input({"origin": "HAN", "destination": "SGN", "passengers": 5})
    assert v2 is False


def test_validate_task_input_invalid_route():
    harness = AgentHarness()
    # same origin and destination
    v1, _ = harness.validate_task_input({"origin": "HAN", "destination": "HAN"})
    assert v1 is False

    # invalid IATA code length
    v2, _ = harness.validate_task_input({"origin": "HANOI", "destination": "SGN"})
    assert v2 is False


# ==========================================
# LAYER 2: CompletionChecker & Integration with actual tool output
# ==========================================
def test_completion_with_real_tool_output():
    """Verify CompletionChecker with ACTUAL output from book_flight."""
    completion_checker = CompletionChecker()
    output = {
        "user_approved": True,
        "booking": json.loads(
            book_flight.invoke({
                "flight_id": "VN123",
                "passenger_name": "A",
                "passengers": 2,
            })
        ),
    }
    task = {"origin": "HAN", "destination": "SGN", "max_budget": 5000000}
    completed, reason = completion_checker.check(task, output)
    assert completed is True, f"Expected True, got {reason}"


def test_completion_fails_if_not_approved():
    completion_checker = CompletionChecker()
    output = {
        "user_approved": False,
        "booking": json.loads(
            book_flight.invoke({
                "flight_id": "VN123",
                "passenger_name": "A",
                "passengers": 1,
            })
        ),
    }
    task = {"origin": "HAN", "destination": "SGN"}
    completed, reason = completion_checker.check(task, output)
    assert completed is False
    assert "User did not approve" in reason


def test_completion_fails_if_budget_exceeded():
    completion_checker = CompletionChecker()
    output = {
        "user_approved": True,
        "booking": json.loads(
            book_flight.invoke({
                "flight_id": "VN123",
                "passenger_name": "A",
                "passengers": 2,
            })
        ),  # total_price = 2400000
    }
    task = {"origin": "HAN", "destination": "SGN", "max_budget": 2000000}
    completed, reason = completion_checker.check(task, output)
    assert completed is False
    assert "exceeds budget" in reason


def test_completion_fails_if_route_mismatch():
    """Agent book sai route → completion phải fail."""
    completion_checker = CompletionChecker()

    # Book VN123 (HAN-SGN) nhưng task yêu cầu HAN-BKK
    output = {
        "user_approved": True,
        "booking": json.loads(
            book_flight.invoke({
                "flight_id": "VN123",
                "passenger_name": "A",
                "passengers": 1,
            })
        ),
    }
    task = {"origin": "HAN", "destination": "BKK", "max_budget": 5000000}

    completed, reason = completion_checker.check(task, output)
    assert completed is False, "Should fail: wrong destination"


# ==========================================
# LAYER 3: PermissionChecker
# ==========================================
def test_permission_read_only_allowed():
    constraints = ConstraintsLoader()
    checker = PermissionChecker(constraints)
    allowed, msg = checker.can_call_tool("search_flights", {"origin": "HAN", "destination": "SGN"})
    assert allowed is True
    assert "Read-only" in msg


def test_permission_book_flight_valid():
    constraints = ConstraintsLoader()
    checker = PermissionChecker(constraints)
    params = {"flight_id": "VN123", "passenger_name": "A", "passengers": 2}
    allowed, msg = checker.can_call_tool("book_flight", params)
    assert allowed is True
    assert "within constraints" in msg


def test_permission_book_flight_exceeds_passengers():
    constraints = ConstraintsLoader()
    checker = PermissionChecker(constraints)
    # max is 4
    params = {"flight_id": "VN123", "passenger_name": "A", "passengers": 5}
    allowed, msg = checker.can_call_tool("book_flight", params)
    assert allowed is False
    assert "exceed max allowed" in msg


def test_permission_book_flight_exceeds_budget():
    constraints = ConstraintsLoader()
    checker = PermissionChecker(constraints)
    # QH205: price = 3450000, 3 passengers = 10350000 > max_budget 10000000
    params = {"flight_id": "QH205", "passenger_name": "A", "passengers": 3}
    allowed, msg = checker.can_call_tool("book_flight", params)
    assert allowed is False
    assert "exceeds budget" in msg


def test_permission_book_flight_not_found():
    constraints = ConstraintsLoader()
    checker = PermissionChecker(constraints)
    params = {"flight_id": "NON_EXISTENT", "passenger_name": "A", "passengers": 1}
    allowed, msg = checker.can_call_tool("book_flight", params)
    assert allowed is False
    assert "not found" in msg


# ==========================================
# LAYER 4: HandoffManager
# ==========================================
def test_handoff_triggers():
    manager = HandoffManager()
    h1, r1 = manager.should_handoff({"search_results_empty": True})
    assert h1 is True

    h2, r2 = manager.should_handoff({"retry_count": 4})
    assert h2 is True

    h3, _ = manager.should_handoff({"retry_count": 1})
    assert h3 is False


def test_handoff_create_record_has_timestamp():
    manager = HandoffManager()
    record = manager.create_handoff_record({"state": "test"}, "Low confidence")
    assert record["handoff_reason"] == "Low confidence"
    assert "timestamp" in record
    assert "T" in record["timestamp"]  # Valid ISO format timestamp


# ==========================================
# RUNNER
# ==========================================
if __name__ == "__main__":
    tests = [
        test_constraints_loader_loads_data,
        test_validate_task_input_valid,
        test_validate_task_input_invalid_passengers,
        test_validate_task_input_invalid_route,
        test_completion_with_real_tool_output,
        test_completion_fails_if_not_approved,
        test_completion_fails_if_budget_exceeded,
        test_completion_fails_if_route_mismatch,
        test_permission_read_only_allowed,
        test_permission_book_flight_valid,
        test_permission_book_flight_exceeds_passengers,
        test_permission_book_flight_exceeds_budget,
        test_permission_book_flight_not_found,
        test_handoff_triggers,
        test_handoff_create_record_has_timestamp,
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
