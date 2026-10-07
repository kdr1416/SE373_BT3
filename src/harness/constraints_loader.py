"""
Layer 1: Constraints Loader
Loads constraints from YAML as DATA, not hardcoded.
"""
from pathlib import Path
from typing import Optional
import yaml

CONSTRAINTS_PATH = Path(__file__).parent.parent / "data" / "constraints.yaml"


class ConstraintsLoader:
    def __init__(self, path: Path = CONSTRAINTS_PATH):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            self._data = data if isinstance(data, dict) else {}

        booking_limits = self._data.get("booking_limits") or {}
        self._max_passengers = booking_limits.get("max_passengers_per_booking")
        self._max_budget = booking_limits.get("max_budget_vnd")
        self._allowed_airlines = self._data.get("allowed_airlines", [])
        self._cabin_policy = self._data.get("cabin_class", {})

        tools_cfg = self._data.get("tools") or {}
        self._read_only_tools = tools_cfg.get(
            "read_only", ["search_flights", "get_flight_details", "check_availability"]
        )
        self._requires_approval_tools = tools_cfg.get(
            "requires_approval", ["book_flight"]
        )

    def get_max_passengers(self) -> Optional[int]:
        """Return max passengers per booking."""
        return self._max_passengers

    def get_max_budget(self) -> Optional[int]:
        """Return max budget in VND."""
        return self._max_budget

    def get_allowed_airlines(self) -> list[str]:
        """Return list of allowed airlines."""
        return self._allowed_airlines

    def get_cabin_policy(self) -> dict:
        """Return cabin class policy."""
        return self._cabin_policy

    def get_read_only_tools(self) -> list[str]:
        """Return list of read-only tools loaded from constraints YAML."""
        return self._read_only_tools

    def get_requires_approval_tools(self) -> list[str]:
        """Return list of tools that require approval loaded from constraints YAML."""
        return self._requires_approval_tools