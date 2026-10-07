"""
Layer 3: Permission Checker
Blocks dangerous actions BEFORE they happen.
"""
import json
from typing import Optional
from .constraints_loader import ConstraintsLoader
from src.tools.flight_tools import get_flight_details


class PermissionChecker:
    def __init__(self, constraints: ConstraintsLoader):
        self.constraints = constraints

    def can_call_tool(
        self, tool_name: str, params: dict, task_budget: Optional[int] = None
    ) -> tuple[bool, str]:
        """
        Returns (allowed, reason).

        Rules:
        - read-only tools: loaded from YAML, always allowed
        - book_flight: lookup flight info via flight_id, then validate constraints
          (budget checked against min(global_limit, task_budget))
        """
        # 1. Check read-only whitelist loaded from YAML (Data-driven)
        if tool_name in self.constraints.get_read_only_tools():
            return (True, "Read-only tool, allowed.")

        # 2. Check sensitive tools (requires approval & constraint check)
        if tool_name in self.constraints.get_requires_approval_tools() or tool_name in ["book_flight", "safe_book_flight"]:
            flight_id = params.get("flight_id")
            passengers = params.get("passengers", 0)

            if not flight_id:
                return (False, "Missing flight_id in booking parameters.")

            if passengers <= 0:
                return (False, "Number of passengers must be greater than zero.")

            # Lookup actual flight details from database using flight_id
            flight_raw = get_flight_details.invoke({"flight_id": flight_id})
            flight_data = json.loads(flight_raw)

            if "error" in flight_data:
                return (False, f"Flight '{flight_id}' not found.")

            price_per_passenger = flight_data.get("price", 0)
            airline = flight_data.get("airline", "")
            seats_left = flight_data.get("seats", 0)

            # Check passengers limit
            max_passengers = self.constraints.get_max_passengers()
            if max_passengers is not None and passengers > max_passengers:
                return (False, f"Passengers {passengers} exceed max allowed {max_passengers}.")

            # Check seat availability
            if passengers > seats_left:
                return (False, f"Not enough seats available ({seats_left} seats left).")

            # Check budget limit (comparing TOTAL price against BOTH global limit and task budget)
            global_budget = self.constraints.get_max_budget()
            effective_budget = (
                min(global_budget, task_budget)
                if (global_budget is not None and task_budget is not None)
                else (task_budget if task_budget is not None else global_budget)
            )
            total_price = price_per_passenger * passengers
            if effective_budget is not None and total_price > effective_budget:
                return (False, f"Total price {total_price} exceeds budget {effective_budget}.")

            # Check allowed airlines
            allowed_airlines = self.constraints.get_allowed_airlines()
            if allowed_airlines and airline not in allowed_airlines:
                return (False, f"Airline '{airline}' is not allowed.")

            return (True, "Booking parameters within constraints.")

        return (False, f"Tool '{tool_name}' not recognized or not permitted.")