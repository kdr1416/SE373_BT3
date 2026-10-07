"""
Hybrid Agent using LangGraph + Mini ReAct Executor.
Combines high-level Plan-then-Execute orchestration with dynamic ReAct Mini-Agent per step.
No regex fallback masking: Mini-agent is strictly required to execute every step.
"""
import json
import os
import re
from typing import TypedDict, Annotated, Optional
from operator import add
from dotenv import load_dotenv

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import HumanMessage

from src.harness.agent_harness import AgentHarness
from src.tools.flight_tools import (
    search_flights,
    get_flight_details,
    check_availability,
    book_flight,
)


class HybridState(TypedDict):
    """
    Graph state for Hybrid Agent pattern.
    - Results, tool calls, and blocked calls accumulate across mini-agent steps using add reducer.
    - High-level plan and step index are updated dynamically.
    """
    # Inputs
    user_input: str
    task: dict

    # Planner
    plan: list[str]
    current_step: int

    # Executor outputs
    step_messages: list
    results: Annotated[list[dict], add]
    tool_calls: Annotated[list[dict], add]
    blocked_calls: Annotated[list[dict], add]

    # Booking & Status
    booking: Optional[dict]
    llm_invocations: int
    status: str
    final_output: str
    search_empty: bool
    tool_errors: int
    is_out_of_scope: bool


class HybridAgent:
    def __init__(self, harness: AgentHarness, llm: Optional[ChatOpenAI] = None):
        load_dotenv()
        self.harness = harness
        self.current_task: dict = {}
        self.blocked_calls: list[dict] = []

        if llm:
            self.llm = llm
        else:
            raw_model = os.getenv("MODEL_NAME", "gpt-4o-mini")
            model = raw_model.split("(")[0].strip() if "(" in raw_model else raw_model.strip()
            base_url = os.getenv("OPENAI_BASE_URL") or None
            api_key = os.getenv("OPENAI_API_KEY") or None
            self.llm = ChatOpenAI(
                model=model,
                temperature=0,
                base_url=base_url,
                api_key=api_key,
                timeout=30,
                max_retries=2,
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

        # Mini ReAct Agent system prompt
        mini_agent_system_prompt = (
            "You are a helpful flight booking mini-agent executing a specific step in an overall plan.\n"
            "Rules you must strictly follow:\n"
            "1. Focus only on executing the assigned step using the available tools.\n"
            "2. Read previous context carefully to choose the best available flight matching the user's budget.\n"
            "3. When booking, call safe_book_flight with passenger_name='Lead Passenger' unless specified.\n"
            "4. If a flight has 0 seats left or is sold out, inform clearly and do not attempt to book it.\n"
            "5. If a tool reports an error or is blocked, do not attempt unauthorized retries; report clearly in natural language."
        )

        self.mini_agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=mini_agent_system_prompt,
        )

        self.graph = self._build_graph()

    def _planner_node(self, state: HybridState) -> dict:
        """
        High-level Planner: LLM breaks user goal into 1-2 distinct actionable steps.
        """
        user_input = state["user_input"]
        task = state["task"]

        # Check early out of scope
        user_lower = user_input.lower()
        if any(kw in user_lower for kw in ["round-trip", "khứ hồi", "refund", "hoàn vé", "đổi vé"]):
            return {
                "plan": ["Reject out-of-scope request"],
                "current_step": 0,
                "is_out_of_scope": True,
                "final_output": "Out-of-scope request: Only one-way flights are supported.",
                "llm_invocations": state.get("llm_invocations", 0),
            }

        plan: list[str] = []
        origin = task.get("origin", "HAN")
        destination = task.get("destination", "SGN")
        passengers = task.get("passengers", 1)

        planner_prompt = (
            f"You are a flight travel planner.\n"
            f"User request: '{user_input}'\n"
            f"Task details: Origin={origin}, Destination={destination}, Passengers={passengers}, Budget={task.get('max_budget')}\n"
            f"Generate a concise 1-2 step execution plan as a JSON list of strings.\n"
            f"Guidelines:\n"
            f"- If user explicitly asks to book a specific flight (e.g. 'Book QH205 for 1 person' or 'Book flight FD643'), generate: [\"Book flight <flight_id> for {passengers} passengers\"]\n"
            f"- If user asks to search or book for a route (e.g. 'Book a flight from Hanoi to Saigon'), generate 2 steps: [\"Search flights from {origin} to {destination} for {passengers} passengers within budget\", \"Book the best available flight\"]\n"
            f"Respond ONLY with a valid JSON array of strings."
        )

        llm_called = 0
        try:
            response = self.llm.invoke([HumanMessage(content=planner_prompt)])
            llm_called = 1
            content = response.content.strip()
            match = re.search(r"\[.*\]", content, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, list) and len(parsed) > 0:
                    plan = [str(s) for s in parsed]
        except Exception:
            pass

        if not plan:
            flight_match = re.search(r"\b(QH205|FD643|VN123|VJ181)\b", user_input, re.IGNORECASE)
            if flight_match:
                fid = flight_match.group(1).upper()
                plan = [f"Book flight {fid} for {passengers} passengers"]
            else:
                plan = [
                    f"Search flights from {origin} to {destination} for {passengers} passengers within budget",
                    f"Book the best available flight for {passengers} passengers",
                ]

        return {
            "plan": plan,
            "current_step": 0,
            "llm_invocations": state.get("llm_invocations", 0) + llm_called,
        }

    def _executor_node(self, state: HybridState) -> dict:
        """
        Executor Node: Runs a MINI REACT AGENT for the current step.
        No regex fallback masking.
        """
        if state.get("is_out_of_scope"):
            return {
                "current_step": state["current_step"] + 1,
                "final_output": "Out-of-scope request: Only one-way flights are supported.",
            }

        step_idx = state["current_step"]
        if step_idx >= len(state["plan"]):
            return {"current_step": step_idx + 1}

        step_desc = state["plan"][step_idx]
        task = state["task"]
        self.current_task = task
        # NOTE: self.blocked_calls is NOT wiped here; it preserves blocks across steps

        # Context passing (Approach A: serialize previous step results into prompt)
        context_data = [r.get("output", r) for r in state.get("results", [])]
        context_str = json.dumps(context_data, default=str) if context_data else "None"

        mini_agent_prompt = (
            f"Overall Goal: {state['user_input']}\n"
            f"Task Constraints: Origin={task.get('origin')}, Destination={task.get('destination')}, "
            f"Passengers={task.get('passengers', 1)}, Max Budget={task.get('max_budget')}\n"
            f"Previous Step Outputs: {context_str}\n"
            f"CURRENT STEP TO EXECUTE: '{step_desc}'\n"
            f"Execute this step using the available tools."
        )

        # Invoke Mini ReAct Agent directly (with rate-limit retry on quota limit)
        import time
        mini_messages = []
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                res = self.mini_agent.invoke({"messages": [HumanMessage(content=mini_agent_prompt)]})
                mini_messages = res.get("messages", [])
                break
            except Exception as e:
                err_str = str(e)
                if ("429" in err_str or "503" in err_str or "Quota exceeded" in err_str or "RESOURCE_EXHAUSTED" in err_str) and attempt < max_attempts - 1:
                    time.sleep(8)
                    continue
                raise e

        step_tool_calls: list[dict] = []
        booking = state.get("booking")
        search_empty = state.get("search_empty", False)
        tool_errors = state.get("tool_errors", 0)
        final_output = mini_messages[-1].content if mini_messages else ""

        # Extract tool calls & booking data from Mini Agent execution
        for msg in mini_messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    step_tool_calls.append({"name": tc["name"], "args": tc["args"]})

            if getattr(msg, "type", None) == "tool":
                try:
                    content_json = json.loads(msg.content)
                    if isinstance(content_json, dict):
                        if "booking_id" in content_json:
                            booking = content_json
                        if "error" in content_json:
                            tool_errors += 1
                            err_str = str(content_json.get("error", ""))
                            if "No flights found" in err_str:
                                search_empty = True
                    elif isinstance(content_json, list) and len(content_json) == 0:
                        search_empty = True
                except Exception:
                    pass

        step_blocked_calls = list(self.blocked_calls)
        step_llm_invocations = sum(1 for m in mini_messages if getattr(m, "type", None) == "ai")

        return {
            "current_step": step_idx + 1,
            "step_messages": mini_messages,
            "results": [{"step": step_desc, "output": final_output}],
            "tool_calls": step_tool_calls,
            "blocked_calls": step_blocked_calls,
            "booking": booking,
            "search_empty": search_empty,
            "tool_errors": tool_errors,
            "final_output": final_output,
            "llm_invocations": state.get("llm_invocations", 0) + step_llm_invocations,
        }

    def _should_continue(self, state: HybridState) -> str:
        """
        Conditional edge: stop early if blocked, out-of-scope, empty search, or sold out.
        """
        if state.get("is_out_of_scope"):
            return "done"
        if state.get("blocked_calls"):
            return "done"
        if state.get("search_empty"):
            return "done"
        # Stop early if previous step revealed flight is sold out (0 seats left)
        for res in state.get("results", []):
            out_str = str(res.get("output", ""))
            if "0 seats" in out_str or "sold out" in out_str.lower():
                return "done"
        if state["current_step"] < len(state["plan"]):
            return "continue"
        return "done"

    def _build_graph(self):
        graph = StateGraph(HybridState)
        graph.add_node("planner", self._planner_node)
        graph.add_node("executor", self._executor_node)

        graph.set_entry_point("planner")
        graph.add_edge("planner", "executor")
        graph.add_conditional_edges(
            "executor",
            self._should_continue,
            {
                "continue": "executor",
                "done": END,
            }
        )
        return graph.compile()

    def run(self, user_input: str, task: dict) -> dict:
        """
        Run agent with harness integration.
        """
        self.current_task = task
        self.blocked_calls = []

        # Layer 1: Validate task input
        is_valid, validation_msg = self.harness.validate_task_input(task)
        if not is_valid:
            return {
                "status": "REJECTED",
                "output": validation_msg,
                "plan": [],
                "harness_checks": {
                    "task_input_valid": False,
                    "task_input_reason": validation_msg,
                },
                "metrics": {
                    "tool_calls_count": 0,
                    "llm_invocations": 0,
                    "plan_steps_count": 0,
                    "steps_executed": 0,
                },
            }

        # Initialize graph state
        initial_state: HybridState = {
            "user_input": user_input,
            "task": task,
            "plan": [],
            "current_step": 0,
            "step_messages": [],
            "results": [],
            "blocked_calls": [],
            "tool_calls": [],
            "booking": None,
            "status": "INCOMPLETE",
            "final_output": "",
            "search_empty": False,
            "tool_errors": 0,
            "is_out_of_scope": False,
            "llm_invocations": 0,
        }

        # Invoke LangGraph Hybrid workflow
        final_state = self.graph.invoke(initial_state)

        # Layer 3: Audit tool call permissions via Harness
        permission_checks = []
        all_permissions_allowed = True
        for tc in final_state.get("tool_calls", []):
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

        if final_state.get("blocked_calls"):
            all_permissions_allowed = False

        # Layer 2: Completion check
        agent_output = {
            "user_approved": task.get("user_approved"),
            "booking": final_state.get("booking"),
        }
        is_completed, completion_reason = self.harness.check_completion(task, agent_output)

        # Layer 4: Handoff check
        handoff_state = {
            "search_results_empty": final_state.get("search_empty", False),
            "retry_count": len(final_state.get("tool_calls", [])),
            "user_requested_out_of_scope": final_state.get("is_out_of_scope", False),
            "repeated_tool_errors": final_state.get("tool_errors", 0) >= 2,
        }
        needs_handoff, handoff_reason = self.harness.check_handoff(handoff_state)

        # Final Status determination
        if needs_handoff:
            status = "HANDED_OFF"
        elif not all_permissions_allowed:
            status = "PERMISSION_DENIED"
        elif is_completed:
            status = "DONE"
        elif final_state.get("is_out_of_scope", False):
            status = "REJECTED"
        else:
            status = "INCOMPLETE"

        tool_calls = final_state.get("tool_calls", [])
        plan = final_state.get("plan", [])
        steps_executed = final_state.get("current_step", 0)

        metrics = {
            "tool_calls_count": len(tool_calls),
            "llm_invocations": final_state.get("llm_invocations", 0),
            "plan_steps_count": len(plan),
            "steps_executed": steps_executed,
        }

        # Expose blocked_calls attribute for adversarial tests
        self.blocked_calls = final_state.get("blocked_calls", [])

        return {
            "status": status,
            "output": final_state.get("final_output", ""),
            "plan": plan,
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
