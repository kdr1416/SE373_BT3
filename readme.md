# Flight Booking Agent — Agentic AI Benchmark System

A multi-pattern AI agent system for flight booking built with **LangChain**, **LangGraph**, and a **4-Layer Safety Harness**. The system benchmarks and evaluates three prominent agent orchestration paradigms:
1. **ReAct Agent** (Step-by-step emergent reasoning and tool invocation)
2. **Plan-then-Execute Agent** (LangGraph-based upfront planning with deterministic execution)
3. **Hybrid Agent** (LangGraph global planning with autonomous Mini-ReAct executors per step)

---

## 🏗️ System Architecture

The architecture enforces a strict **Fail-Closed 4-Layer Agent Harness**:
- **Layer 1: Input Validation** (`validate_task_input`) — Validates passenger count ($1 \le pax \le 4$), IATA codes, and routes before invoking LLMs.
- **Layer 2: Completion Checker** (`CompletionChecker`) — Validates output criteria, budget limits, user approval, and database state.
- **Layer 3: Permission Checker (Approach A)** (`safe_book_flight`) — Pre-execution guard intercepting state-mutating actions before execution.
- **Layer 4: Handoff Manager** (`HandoffManager`) — Detects out-of-scope requests, empty searches, or repeated failures and escalates gracefully.

---

## 📁 Project Structure

```
flight-booking-agent/
├── src/
│   ├── agents/
│   │   ├── react_agent.py          # Milestone 3: ReAct Pattern
│   │   ├── plan_execute_agent.py   # Milestone 4: Plan-then-Execute
│   │   └── hybrid_agent.py         # Milestone 5: Hybrid Agent
│   ├── harness/                    # Milestone 2: 4-Layer Harness
│   │   ├── agent_harness.py
│   │   ├── constraints_loader.py
│   │   ├── completion_checker.py
│   │   ├── permission_checker.py
│   │   └── handoff_manager.py
│   ├── tools/                      # Milestone 1: SQLite Mock Tools
│   │   └── flight_tools.py
│   └── data/
│       ├── flights.yaml
│       └── constraints.yaml
├── evaluation/                     # Milestone 6: Benchmark Suite
│   ├── run_evaluation.py
│   └── metrics.py
├── reports/
│   ├── evaluation.md               # Final Evaluation Report (8 Sections)
│   └── raw_results.json            # Benchmark Raw Results Data
├── tests/                          # 49 Pytest Unit & Integration Tests
│   ├── test_tools.py
│   ├── test_harness.py
│   ├── test_react_agent.py
│   ├── test_plan_execute_agent.py
│   └── test_hybrid_agent.py
├── design.md                       # Milestone 0: Architecture Design Document
├── requirements.txt
├── .env.example
├── .gitignore
└── readme.md
```

---

## 🚀 Setup & Installation

### 1. Create and Activate Virtual Environment

```bash
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install Dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Copy `.env.example` to `.env` and fill in your API credentials:

```bash
cp .env.example .env
```

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=http://localhost:20128/v1   # Or provider endpoint
MODEL_NAME=gemini/gemini-3.5-flash-lite
```

---

## 🧪 Running Tests

Run the complete test suite across all 5 modules:

```bash
pytest tests/ -v
```

Run test suite for a specific agent pattern:

```bash
pytest tests/test_react_agent.py -v
pytest tests/test_plan_execute_agent.py -v
pytest tests/test_hybrid_agent.py -v
```

---

## 📊 Running Benchmark Evaluation (Milestone 6)

Execute the standardized benchmark across all 6 scenarios ($N = 3$ runs per pattern):

```bash
python evaluation/run_evaluation.py --runs 3
```

Results and statistical summaries will be automatically saved to:
- Raw benchmark data: `reports/raw_results.json`
- Comprehensive evaluation report: `reports/evaluation.md`

---

## 📄 License & Attribution
Course Project: Agentic AI — University of Information Technology (UIT).
Author: Nguyen Duong Quat Tuan (24521934).