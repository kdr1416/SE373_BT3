"""
Layer 2: Completion Checker
Checks if task is DONE by code, not by asking LLM.
"""


class CompletionChecker:
    def check(self, task: dict, agent_output: dict) -> tuple[bool, str]:
        """
        Returns (is_complete, reason).

        Completion criteria:
        DONE = user_approved AND booking.status == "confirmed"
               AND booking satisfies constraints (total price <= budget, passengers match, route matches).
        """
        # 1. Check user approval
        if not agent_output.get("user_approved"):
            return (False, "User did not approve the booking.")

        # 2. Check booking exists and is a valid dictionary
        booking = agent_output.get("booking")
        if not booking or not isinstance(booking, dict):
            return (False, "No booking information found.")

        # 3. Check status == "confirmed"
        if booking.get("status") != "confirmed":
            return (False, f"Booking is not confirmed (got '{booking.get('status')}').")

        # 4. Check booking_id exists
        if not booking.get("booking_id"):
            return (False, "Booking ID is missing.")

        # 5. Check passenger count matches task if specified
        if "passengers" in task and booking.get("passengers") is not None:
            if booking.get("passengers") != task["passengers"]:
                return (
                    False,
                    f"Booked passengers ({booking.get('passengers')}) does not match task ({task['passengers']}).",
                )

        # 6. Check route matches task (strictly enforced)
        req_origin = task.get("origin")
        if req_origin:
            if not booking.get("origin"):
                return (False, "Booking origin is missing.")
            if booking["origin"] != req_origin:
                return (
                    False,
                    f"Booking origin '{booking['origin']}' does not match task origin '{req_origin}'.",
                )

        req_destination = task.get("destination")
        if req_destination:
            if not booking.get("destination"):
                return (False, "Booking destination is missing.")
            if booking["destination"] != req_destination:
                return (
                    False,
                    f"Booking destination '{booking['destination']}' does not match task destination '{req_destination}'.",
                )

        # 7. Check price within budget (comparing TOTAL price)
        total_price = booking.get("total_price", booking.get("price", 0))
        max_budget = task.get("max_budget")
        if max_budget is not None and total_price > max_budget:
            return (False, f"Booking total price {total_price} exceeds budget {max_budget}.")

        return (True, "OK")