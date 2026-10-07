"""
ReAct Agent using LangChain create_agent.
Integrates with AgentHarness for permission + completion checks.
"""
import json
import os
from typing import Optional
from dotenv import load_dotenv

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from src.harness.agent_harness import AgentHarness
from src.tools.flight_tools import (
    search_flights,
    get_flight_details,
    check_availability,
    book_flight,
)


class ReActFlightAgent:
    def __init__(self, harness: AgentHarness, llm: Optional[ChatOpenAI] = None):
        load_dotenv()
        self.harness = harness
        self.current_task: dict = {}
        self.blocked_calls: list[dict] = []

        if llm:
            self.llm = llm
        else:
            raw_model = os.getenv("MODEL_NAME", "gpt-4o-mini")
            # Sanitize model name if it contains comments or suffixes like (low)
            model = raw_model.split("(")[0].strip() if "(" in raw_model else raw_model.strip()
            base_url = os.getenv("OPENAI_BASE_URL") or None
            api_key = os.getenv("OPENAI_API_KEY") or None
            self.llm = ChatOpenAI(
                model=model,
                temperature=0,
                base_url=base_url,
                api_key=api_key,
            )

        # Approach A: Wrap book_flight with pre-execution harness check
        @tool
        def safe_book_flight(flight_id: str, passenger_name: str, passengers: int) -> str:
            """
            Book a flight with harness pre-execution guard.
            Validates permissions BEFORE executing actual booking.
            """
            task_budget = self.current_task.get("max_budget")
            params = {
                "flight_id": flight_id,
                "passenger_name": passenger_name,
                "passengers": passengers,
            }
            try:
                allowed, reason = self.harness.check_tool_call(
                    "book_flight",
                    params,
                    task_budget=task_budget,
                )
            except Exception as e:
                err_msg = f"Security check exception: {str(e)}"
                self.blocked_calls.append({
                    "tool": "book_flight",
                    "args": params,
                    "allowed": False,
                    "reason": err_msg,
                })
                return json.dumps({"error": f"BLOCKED_BY_HARNESS: {err_msg}"})

            if not allowed:
                self.blocked_calls.append({
                    "tool": "book_flight",
                    "args": params,
                    "allowed": False,
                    "reason": reason,
                })
                return json.dumps({"error": f"BLOCKED_BY_HARNESS: {reason}"})

            return book_flight.invoke(params)

        self.safe_book_flight = safe_book_flight
        self.tools = [search_flights, get_flight_details, check_availability, safe_book_flight]

        system_prompt = (
            "You are a helpful and reliable flight booking assistant.\n"
            "Rules you must strictly follow:\n"
            "1. Only one-way flights are supported. If the user requests round-trip, inform them it is not supported.\n"
            "2. When the user asks to book a flight for a route (e.g. Hanoi to Saigon), search flights using search_flights, then immediately select the best available flight within budget and book it using safe_book_flight.\n"
            "3. If a specific flight ID (such as QH205, FD643) is requested by the user, you may check availability or call safe_book_flight.\n"
            "4. When calling safe_book_flight, use passenger_name='Lead Passenger' unless specified, and the number of passengers requested.\n"
            "5. If a tool returns an error or blocked message, do not attempt unauthorized retries; report the error clearly."
        )

        self.agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=system_prompt,
        )

    def run(self, user_input: str, task: dict) -> dict:
        """
        Run agent with harness integration.

        Args:
            user_input: Natural language request
            task: Structured task (origin, destination, passengers, max_budget)

        Returns:
            dict with: status, output, harness_checks, metrics
        """
        self.current_task = task
        self.blocked_calls = []

        # TODO 1: validate task input via harness
        is_valid, validation_msg = self.harness.validate_task_input(task)
        if not is_valid:
            return {
                "status": "REJECTED",
                "output": validation_msg,
                "harness_checks": {
                    "task_input_valid": False,
                    "task_input_reason": validation_msg,
                },
                "metrics": {
                    "tool_calls_count": 0,
                    "llm_invocations": 0,
                    "reasoning_steps": 0,
                },
            }

        # TODO 1: Check early out-of-scope intents
        user_lower = user_input.lower()
        is_out_of_scope = any(
            kw in user_lower for kw in ["round-trip", "khứ hồi", "refund", "hoàn vé", "đổi vé"]
        )

        # TODO 2: run agent
        result = self.agent.invoke({"messages": [HumanMessage(content=user_input)]})
        messages = result.get("messages", [])
        final_output = messages[-1].content if messages else "No response generated."

        # TODO 3: extract tool calls from agent result
        tool_calls = []
        booking_data = None
        search_empty = False
        tool_errors = 0

        for msg in messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append({"name": tc["name"], "args": tc["args"]})

            if getattr(msg, "type", None) == "tool":
                try:
                    content_json = json.loads(msg.content)
                    if isinstance(content_json, dict):
                        if "booking_id" in content_json:
                            booking_data = content_json
                        if "error" in content_json:
                            tool_errors += 1
                            err_str = str(content_json.get("error", ""))
                            if "No flights found" in err_str:
                                search_empty = True
                    elif isinstance(content_json, list) and len(content_json) == 0:
                        search_empty = True
                except Exception:
                    pass

        # TODO 4: audit each tool call via harness permission
        permission_checks = []
        all_permissions_allowed = True
        for tc in tool_calls:
            check_name = "book_flight" if tc["name"] in ["safe_book_flight", "book_flight"] else tc["name"]
            allowed, reason = self.harness.check_tool_call(
                check_name, tc["args"], task_budget=task.get("max_budget")
            )
            permission_checks.append({
                "tool": check_name,
                "args": tc["args"],
                "allowed": allowed,
                "reason": reason,
            })
            if not allowed:
                all_permissions_allowed = False

        if self.blocked_calls:
            all_permissions_allowed = False

        # TODO 5: check completion via harness
        agent_output = {
            "user_approved": task.get("user_approved"),
            "booking": booking_data,
        }
        is_completed, completion_reason = self.harness.check_completion(task, agent_output)

        # TODO 6: check handoff via harness
        handoff_state = {
            "search_results_empty": search_empty,
            "retry_count": len(tool_calls),
            "user_requested_out_of_scope": is_out_of_scope,
            "repeated_tool_errors": tool_errors >= 2,
        }
        needs_handoff, handoff_reason = self.harness.check_handoff(handoff_state)

        # TODO 7: return structured result
        if needs_handoff:
            status = "HANDED_OFF"
        elif not all_permissions_allowed:
            status = "PERMISSION_DENIED"
        elif is_completed:
            status = "DONE"
        elif is_out_of_scope:
            status = "REJECTED"
        else:
            status = "INCOMPLETE"

        metrics = {
            "tool_calls_count": len(tool_calls),
            "llm_invocations": sum(1 for m in messages if getattr(m, "type", None) == "ai"),
            "reasoning_steps": sum(1 for m in messages if hasattr(m, "tool_calls") and m.tool_calls),
        }

        return {
            "status": status,
            "output": final_output,
            "harness_checks": {
                "task_input_valid": True,
                "permissions": permission_checks,
                "completed": is_completed,
                "completion_reason": completion_reason,
                "needs_handoff": needs_handoff,
                "handoff_reason": handoff_reason,
            },
            "metrics": metrics,
        }