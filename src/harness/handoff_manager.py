"""
Layer 4: Handoff Manager
Determines when agent should escalate to human.
"""
from datetime import datetime, timezone


class HandoffManager:
    def should_handoff(self, state: dict) -> tuple[bool, str]:
        """
        Returns (needs_handoff, reason).

        Triggers:
        - search results empty after clarification
        - confidence too low (mock: use retry count > threshold)
        - user requests out-of-scope action (refund, round-trip)
        - repeated tool errors
        """
        if state.get("search_results_empty"):
            return (True, "Search results empty after clarification.")
        if state.get("retry_count", 0) > 3:
            return (True, "Confidence too low after multiple retries.")
        if state.get("user_requested_out_of_scope"):
            return (True, "User requested an out-of-scope action.")
        if state.get("repeated_tool_errors"):
            return (True, "Repeated tool errors occurred.")
        return (False, "No handoff required.")

    def create_handoff_record(self, state: dict, reason: str) -> dict:
        """Create structured handoff payload with current UTC timestamp."""
        return {
            "handoff_reason": reason,
            "state_snapshot": state,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }