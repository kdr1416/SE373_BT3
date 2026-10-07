"""
Agent Harness - orchestrates all 4 layers.
"""
from typing import Optional
from .constraints_loader import ConstraintsLoader
from .completion_checker import CompletionChecker
from .permission_checker import PermissionChecker
from .handoff_manager import HandoffManager


class AgentHarness:
    def __init__(self):
        self.constraints = ConstraintsLoader()
        self.completion = CompletionChecker()
        self.permission = PermissionChecker(self.constraints)
        self.handoff = HandoffManager()

    def validate_task_input(self, task: dict) -> tuple[bool, str]:
        """Layer 1 validation: task inputs meet constraints."""
        # 1. Check passenger count
        passengers = task.get("passengers", 1)
        if passengers <= 0:
            return (False, "Passengers must be greater than zero.")
        max_passengers = self.constraints.get_max_passengers()
        if max_passengers is not None and passengers > max_passengers:
            return (False, "Passengers exceed max allowed.")

        # 2. Check budget limit if specified
        max_budget = self.constraints.get_max_budget()
        task_budget = task.get("max_budget")
        if task_budget is not None and max_budget is not None and task_budget > max_budget:
            return (False, "Budget exceeds max allowed.")

        # 3. Check airline if specified
        airline = task.get("airline")
        allowed_airlines = self.constraints.get_allowed_airlines()
        if airline and allowed_airlines and airline not in allowed_airlines:
            return (False, "Airline not allowed.")

        # 4. Check route format (3-letter IATA codes and distinct airports)
        origin = task.get("origin")
        destination = task.get("destination")
        if not origin or not destination:
            return (False, "Origin and destination are required.")
        if not (isinstance(origin, str) and len(origin.strip()) == 3 and origin.strip().isalpha()):
            return (False, "Origin must be a 3-letter IATA code.")
        if not (isinstance(destination, str) and len(destination.strip()) == 3 and destination.strip().isalpha()):
            return (False, "Destination must be a 3-letter IATA code.")
        if origin.strip().upper() == destination.strip().upper():
            return (False, "Origin and destination cannot be the same.")

        return (True, "Task inputs are valid.")

    def check_tool_call(
        self, tool_name: str, params: dict, task_budget: Optional[int] = None
    ) -> tuple[bool, str]:
        """Layer 3: delegate to permission checker."""
        return self.permission.can_call_tool(tool_name, params, task_budget=task_budget)

    def check_completion(self, task: dict, output: dict) -> tuple[bool, str]:
        """Layer 2: delegate to completion checker."""
        return self.completion.check(task, output)

    def check_handoff(self, state: dict) -> tuple[bool, str]:
        """Layer 4: delegate to handoff manager."""
        return self.handoff.should_handoff(state)