"""
Test Plan-then-Execute agent.
Uses the exact same 6 scenarios as M3 for apples-to-apples comparison.
"""
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.harness.agent_harness import AgentHarness
from src.agents.plan_execute_agent import PlanExecuteAgent
from src.tools.flight_tools import check_availability, reset_db


@pytest.fixture(autouse=True)
def setup_db():
    reset_db()
    yield
    reset_db()


@pytest.fixture
def agent():
    harness = AgentHarness()
    return PlanExecuteAgent(harness)


def test_scenario_1_valid_booking(agent):
    """User books HAN-SGN, 2 pax, budget 5M → should succeed."""
    user_input = "Book me a flight from Hanoi to Saigon for 2 people"
    task = {
        "origin": "HAN",
        "destination": "SGN",
        "passengers": 2,
        "max_budget": 5000000,
        "user_approved": True,  # Explicit approval required
    }

    result = agent.run(user_input, task)

    print("\n=== Plan-Execute Scenario 1 ===")
    print(json.dumps(result, indent=2, default=str))

    assert result["status"] == "DONE"
    assert result["harness_checks"]["completed"] is True
    assert result["harness_checks"]["task_input_valid"] is True
    assert result["metrics"]["tool_calls_count"] > 0
    assert any(p["tool"] == "book_flight" and p["allowed"] for p in result["harness_checks"]["permissions"])


def test_scenario_2_over_budget(agent):
    """User books business QH205, budget 2M → should be blocked."""
    user_input = "Book me flight QH205 from Hanoi to Saigon for 1 person"
    task = {
        "origin": "HAN",
        "destination": "SGN",
        "passengers": 1,
        "max_budget": 2000000,
        "user_approved": True,
    }

    result = agent.run(user_input, task)

    print("\n=== Plan-Execute Scenario 2 ===")
    print(json.dumps(result, indent=2, default=str))

    assert result["status"] in ["PERMISSION_DENIED", "INCOMPLETE"]
    assert result["harness_checks"]["completed"] is False
    book_checks = [p for p in result["harness_checks"]["permissions"] if p["tool"] == "book_flight"]
    if book_checks:
        assert any(not p["allowed"] for p in book_checks)


def test_scenario_3_no_flights(agent):
    """User searches HAN-XYZ → should handoff or clarify."""
    user_input = "Find me a flight from Hanoi to XYZ for 1 person"
    task = {"origin": "HAN", "destination": "XYZ", "passengers": 1, "max_budget": 5000000}

    result = agent.run(user_input, task)

    print("\n=== Plan-Execute Scenario 3 ===")
    print(json.dumps(result, indent=2, default=str))

    assert result["status"] in ["HANDED_OFF", "INCOMPLETE"]
    assert result["harness_checks"]["completed"] is False


def test_scenario_4_sold_out(agent):
    """User books FD643 (sold out) → should fail gracefully."""
    user_input = "Book flight FD643 from Hanoi to Don Mueang for 1 person"
    task = {"origin": "HAN", "destination": "DMK", "passengers": 1, "max_budget": 5000000}

    result = agent.run(user_input, task)

    print("\n=== Plan-Execute Scenario 4 ===")
    print(json.dumps(result, indent=2, default=str))

    assert result["status"] in ["PERMISSION_DENIED", "INCOMPLETE", "HANDED_OFF"]
    assert result["harness_checks"]["completed"] is False


def test_scenario_5_wrong_passengers(agent):
    """User books 5 people (max 4) → should be blocked at validate input."""
    user_input = "Book a flight from Hanoi to Saigon for 5 people"
    task = {"origin": "HAN", "destination": "SGN", "passengers": 5, "max_budget": 10000000}

    result = agent.run(user_input, task)

    print("\n=== Plan-Execute Scenario 5 ===")
    print(json.dumps(result, indent=2, default=str))

    assert result["status"] == "REJECTED"
    assert result["harness_checks"]["task_input_valid"] is False
    assert "Passengers exceed max allowed" in result["output"]
    assert result["metrics"]["tool_calls_count"] == 0


def test_book_flight_blocked_does_not_execute(agent):
    """Adversarial test: Over-budget book_flight KHÔNG được thực thi (Approach A guard)."""
    # Before
    before = json.loads(check_availability.invoke({"flight_id": "QH205"}))

    user_input = "Book QH205 for 1 person"
    task = {
        "origin": "HAN",
        "destination": "SGN",
        "passengers": 1,
        "max_budget": 2000000,
        "user_approved": True,
    }
    result = agent.run(user_input, task)

    # After
    after = json.loads(check_availability.invoke({"flight_id": "QH205"}))

    assert before["seats_left"] == after["seats_left"], (
        "Seats changed → tool executed despite harness block!"
    )
    assert len(agent.blocked_calls) > 0, (
        "Approach A guard was never triggered — agent might not have called book_flight!"
    )
    assert any(b["tool"] == "book_flight" for b in agent.blocked_calls)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
