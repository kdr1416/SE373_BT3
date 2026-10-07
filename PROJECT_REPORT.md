# BÁO CÁO TỔNG KẾT ĐỒ ÁN: FLIGHT BOOKING AGENT
## HỆ THỐNG ĐẶT VÉ MÁY BAY TỰ ĐỘNG ĐA KIẾN TRÚC VỚI LANGCHAIN & LANGGRAPH

* **Sinh viên thực hiện:** Nguyễn Dương Quất Tuấn
* **Mã số sinh viên:** 24521934
* **Môn học:** Agentic AI — Trường Đại học Công nghệ Thông tin (ĐHQG-HCM)
* **Kho lưu trữ mã nguồn:** [flight-booking-agent](file:///d:/N%C4%83m%203/Agentic%20AI/24521934_Nguyen%20DuongQuatTuan_BT3/flight-booking-agent)
* **Môi trường kỹ thuật:** Python 3.12, LangChain 0.3+, LangGraph 0.2+, SQLite, Pytest

---

## 1. THÔNG TIN ĐỒ ÁN & MỤC TIÊU NGHIÊN CỨU

Trong các ứng dụng trí tuệ nhân tạo tạo sinh (Generative AI) tích hợp công cụ (Tool-augmented LLMs), việc trao toàn quyền cho Large Language Model tự ý kích hoạt các hành động thay đổi trạng thái thế giới thực (state-mutating side-effects) như đặt vé máy bay, trừ tiền thẻ tín dụng hay hủy chuyến bay tiềm ẩn rủi ro rất lớn:
1. **Ảo giác tham số (Parameter Hallucination):** Agent tự ý đặt vé khi người dùng chưa xác nhận, hoặc book vé vượt quá số dư/ngân sách.
2. **Vòng lặp vô tận (Infinite Looping):** Agent gọi tool tìm kiếm lặp đi lặp lại khi không có kết quả phù hợp.
3. **Thiếu khả năng kiểm soát (Lack of Deterministic Governance):** Không có ranh giới phân định rõ giữa logic nghiệp vụ tất định (deterministic business rules) và logic tạo sinh (generative reasoning).

### Mục tiêu đồ án:
* Xây dựng một **Agent Harness 4 lớp (Fail-Closed Architecture)** hoạt động như một "hộp bảo vệ", giám sát và ngăn chặn 100% các hành vi vi phạm nghiệp vụ trước và sau khi LLM can thiệp.
* Hiện thực hóa và so sánh thực nghiệm **3 mô hình điều phối Agent phổ biến nhất hiện nay**:
  - **ReAct Agent** (Reasoning + Acting tuần tự)
  - **Plan-then-Execute Agent** (Lập kế hoạch trước, thực thi theo đồ thị LangGraph)
  - **Hybrid Agent** (Quy hoạch toàn cục LangGraph kết hợp Mini-ReAct Agent thực thi cục bộ)
* Đánh giá hiệu năng định lượng (Độ trễ, Số lần gọi LLM, Số lượt gọi Tool, Chi phí Token, Tỷ lệ an toàn) trên 6 kịch bản tiêu chuẩn với $N = 3$ runs độc lập.

---

## 2. TỔNG QUAN BÀI TOÁN & YÊU CẦU NGHIỆP VỤ

### 2.1 Phạm vi nghiệp vụ (Scope)
* Hệ thống hỗ trợ tra cứu và đặt vé máy bay một chiều (One-way) giữa các sân bay nội địa và quốc tế: Hà Nội (HAN), TP.HCM (SGN), Bangkok (BKK), Don Mueang (DMK).
* Ràng buộc hệ thống (System Constraints từ `src/data/constraints.yaml`):
  - Số lượng hành khách tối đa cho mỗi giao dịch: $1 \le pax \le 4$.
  - Ngân sách trần mặc định: $10,000,000$ VNĐ.
  - Hãng bay hợp lệ: Vietnam Airlines, Vietjet Air, Bamboo Airways, Thai Airways, AirAsia.
  - Phê duyệt người dùng (`user_approved`): Bắt buộc phải có giá trị `True` rõ ràng trước khi thực hiện xuất vé.

### 2.2 Các trạng thái kết thúc (Terminal Statuses)
* `DONE`: Giao dịch thành công, thông tin chuyến bay khớp với yêu cầu, số ghế trong DB đã bị trừ và người dùng đã đồng ý.
* `PERMISSION_DENIED`: Hành động `book_flight` bị chặn do vi phạm ngân sách hoặc ghế đã bán hết.
* `HANDED_OFF`: Không tìm thấy chuyến bay, hoặc lỗi hệ thống lặp lại $\ge 2$ lần $\to$ chuyển giao nhân viên hỗ trợ.
* `REJECTED`: Yêu cầu đầu vào không hợp lệ (vd: đặt vé cho 5 người) $\to$ bị từ chối ngay lập tức tại Layer 1.
* `INCOMPLETE`: Quá trình xử lý chưa hoàn tất hoặc agent chủ động dừng lại để yêu cầu làm rõ thêm.

---

## 3. THIẾT KẾ KIẾN TRÚC HỆ THỐNG & CHI TIẾT MÃ NGUỒN

Hệ thống được thiết kế theo mô hình tách bạch giữa **Dữ liệu & Công cụ**, **Bộ khung Giám sát (Harness)**, và **Tầng Điều phối Agent (Agents)**.

```
┌─────────────────────────────────────────────────────────────┐
│                       USER REQUEST                          │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│           LAYER 1: INPUT VALIDATION (Fail-Fast)             │
│       validate_task_input() -> 0 LLM Tokens, 0 Latency      │
└──────────────┬──────────────────────────────────────────────┘
               │ Passed
               ▼
┌─────────────────────────────────────────────────────────────┐
│                 AGENT ORCHESTRATION LAYER                   │
│         [ ReAct ]  /  [ Plan-Execute ]  /  [ Hybrid ]       │
│                              │                              │
│         ┌────────────────────┴────────────────────┐         │
│         │ Tool Call Attempt: book_flight          │         │
│         ▼                                         ▼         │
│  ┌───────────────────────────────────────────────────────┐  │
│  │   LAYER 3: PERMISSION CHECKER (Approach A Wrapper)    │  │
│  │     safe_book_flight() -> Pre-execution Guard         │  │
│  │     Check budget, max pax, seat availability          │  │
│  └──────────────────────┬────────────────────────────────┘  │
│                         │ Allowed                           │
│                         ▼                                   │
│              [ SQLite Database Mutation ]                   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│             LAYER 2: COMPLETION CHECKER                     │
│       Verify booking record, budget & user approval         │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│             LAYER 4: HANDOFF MANAGER                        │
│       Empty searches, repeated errors -> Human Handoff      │
└─────────────────────────────────────────────────────────────┘
```

### 3.1 CSDL SQLite & Mock Tools (`src/tools/flight_tools.py`)
CSDL được khởi tạo bằng SQLite trong bộ nhớ/tệp tin với khả năng cô lập và khôi phục trạng thái nguyên bản qua fixture `reset_db()` phục vụ kiểm thử:

```python
# src/tools/flight_tools.py
import sqlite3
import json
from langchain_core.tools import tool

DB_PATH = "flight_agent.db"

def reset_db():
    """Khởi tạo hoặc tái lập trạng thái CSDL về dữ liệu chuẩn."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS bookings")
    cur.execute("DROP TABLE IF EXISTS flights")
    cur.execute("""
        CREATE TABLE flights (
            id TEXT PRIMARY KEY,
            airline TEXT NOT NULL,
            origin TEXT NOT NULL,
            destination TEXT NOT NULL,
            departure TEXT NOT NULL,
            arrival TEXT NOT NULL,
            class TEXT NOT NULL,
            price INTEGER NOT NULL,
            seats INTEGER NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE bookings (
            booking_id TEXT PRIMARY KEY,
            flight_id TEXT NOT NULL,
            passenger_name TEXT NOT NULL,
            passengers INTEGER NOT NULL,
            total_price INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Nạp dữ liệu mẫu từ mock dataset
    # Ví dụ: VN123 (HAN-SGN, 1.2M, 45 ghế), QH205 (HAN-SGN, Business 3.45M, 4 ghế),
    #       FD643 (HAN-DMK, 1.45M, 0 ghế - Sold Out)
    ...
    conn.commit()
    conn.close()
```

Bốn công cụ được đóng gói với decorator `@tool` của LangChain:
* `search_flights(origin: str, destination: str) -> str`: Tìm kiếm chuyến bay theo cặp IATA code (Read-only).
* `get_flight_details(flight_id: str) -> str`: Lấy thông tin giá, hạng ghế, giờ bay của chuyến bay (Read-only).
* `check_availability(flight_id: str) -> str`: Kiểm tra số ghế trống khả dụng (Read-only).
* `book_flight(flight_id: str, passenger_name: str, passengers: int) -> str`: Thực thi xuất vé trong CSDL, giảm số ghế khả dụng và tạo bản ghi `bookings` (Mutating Tool).

---

### 3.2 Hiện thực Agent Harness 4 Lớp (`src/harness/`)

#### Layer 1: Input Validation (`validate_task_input`)
Ngăn chặn các input rác ngay tại "cửa ngõ" trước khi khởi tạo đồ thị hoặc gọi LLM:
```python
# src/harness/agent_harness.py
def validate_task_input(self, task: dict) -> tuple[bool, str]:
    origin = task.get("origin")
    destination = task.get("destination")
    passengers = task.get("passengers", 1)
    
    if passengers <= 0:
        return False, "Passengers must be positive"
    if passengers > self.constraints.get_max_passengers(): # max = 4
        return False, f"Passengers exceed max allowed ({self.constraints.get_max_passengers()})"
    if not origin or not destination:
        return False, "Origin and destination required"
    if len(origin) != 3 or len(destination) != 3:
        return False, "Airport codes must be 3-letter IATA"
    if origin == destination:
        return False, "Origin and destination cannot be the same"
    return True, "Task inputs are valid."
```

#### Layer 2: Completion Checker (`CompletionChecker`)
Xác minh giao dịch bằng mã Python tất định, không tin tưởng lời tuyên bố của LLM:
```python
# src/harness/completion_checker.py
class CompletionChecker:
    def check(self, task: dict, agent_output: dict) -> tuple[bool, str]:
        if not agent_output.get("user_approved"):
            return False, "User did not approve the booking"
            
        booking = agent_output.get("booking")
        if not booking or booking.get("status") != "confirmed":
            return False, "No confirmed booking found"
            
        max_budget = task.get("max_budget")
        if max_budget and booking.get("total_price", 0) > max_budget:
            return False, f"Total price ({booking['total_price']}) exceeds budget ({max_budget})"
            
        # Kiểm tra tính khớp nối của chặng bay thực tế từ CSDL
        flight = get_flight_from_db(booking["flight_id"])
        if flight["origin"] != task["origin"] or flight["destination"] != task["destination"]:
            return False, "Booked flight route does not match task request"
            
        return True, "Task completed successfully"
```

#### Layer 3: Permission Checker & Approach A Wrapper
Thay vì chạy tool xong mới kiểm tra hậu kỳ (Approach B), hệ thống áp dụng **Approach A (Pre-Execution Guard)** — bọc tool `book_flight` trong một hàm an toàn `safe_book_flight` với cơ chế **Fail-Closed**:

```python
# Cài đặt Approach A trong Agent wrapper
@tool
def safe_book_flight(flight_id: str, passenger_name: str, passengers: int) -> str:
    """Wrapper thực thi book_flight có giám sát tiền thực thi (Pre-execution guard)."""
    task_budget = self.current_task.get("max_budget")
    params = {
        "flight_id": flight_id,
        "passenger_name": passenger_name,
        "passengers": passengers,
    }
    
    try:
        # Kiểm tra thẩm quyền với Harness Layer 3
        allowed, reason = self.harness.check_tool_call(
            "book_flight",
            params,
            task_budget=task_budget,
        )
    except Exception as e:
        # Nguyên tắc Fail-Closed: Gặp lỗi không xác định -> Lập tức chặn
        self.blocked_calls.append({"tool": "book_flight", "params": params, "reason": f"HARNESS_ERROR: {str(e)}"})
        return json.dumps({"error": f"BLOCKED_BY_HARNESS: Internal safety check error: {str(e)}"})
        
    if not allowed:
        self.blocked_calls.append({"tool": "book_flight", "params": params, "reason": reason})
        return json.dumps({"error": f"BLOCKED_BY_HARNESS: {reason}"})
        
    # Chỉ khi qua cổng kiểm tra thì mới gọi tool thật làm thay đổi CSDL
    return book_flight.invoke(params)
```

#### Layer 4: Handoff Manager (`HandoffManager`)
Tự động kích hoạt chuyển giao nhân sự khi gặp bế tắc:
```python
# src/harness/handoff_manager.py
class HandoffManager:
    def should_handoff(self, state: dict) -> tuple[bool, Optional[str]]:
        if state.get("search_results_empty"):
            return True, "No flights found matching criteria"
        if state.get("retry_count", 0) >= 3:
            return True, "Too many failed attempts"
        if state.get("user_requested_out_of_scope"):
            return True, "Request is beyond agent capabilities"
        if state.get("repeated_tool_errors"):
            return True, "Repeated backend errors"
        return False, None
```

---

## 4. CHI TIẾT TRIỂN KHAI 3 MÔ HÌNH ĐIỀU PHỐI AGENT

### 4.1 Mô hình 1: ReAct Agent (`src/agents/react_agent.py`)

ReAct (Reasoning + Acting) sử dụng vòng lặp suy luận tương tác tuần tự giữa LLM và các công cụ được cung cấp qua hàm `create_react_agent` của LangGraph/LangChain.

```python
# src/agents/react_agent.py
class ReActFlightAgent:
    def __init__(self, harness: AgentHarness, llm: Optional[ChatOpenAI] = None):
        self.harness = harness
        self.llm = llm or ChatOpenAI(model=MODEL_NAME, temperature=0)
        self.current_task = {}
        self.blocked_calls = []

        # Đóng gói Approach A wrapper
        @tool
        def safe_book_flight(flight_id: str, passenger_name: str, passengers: int) -> str:
            ... # Triển khai Pre-guard
            
        self.safe_book_flight = safe_book_flight
        self.tools = [search_flights, get_flight_details, check_availability, self.safe_book_flight]
        
        # Khởi tạo ReAct Agent chuẩn
        self.agent = create_react_agent(
            self.llm,
            self.tools,
            prompt="You are a professional flight booking assistant..."
        )

    def run(self, user_input: str, task: dict) -> dict:
        self.current_task = task
        self.blocked_calls = []

        # Lớp 1: Kiểm tra đầu vào
        valid, msg = self.harness.validate_task_input(task)
        if not valid:
            return {"status": "REJECTED", "output": msg, "metrics": {"tool_calls_count": 0, "llm_invocations": 0}}

        # Thực thi đồ thị ReAct
        result = self.agent.invoke({"messages": [HumanMessage(content=user_input)]})
        messages = result["messages"]

        # Trích xuất số liệu chuẩn xác
        llm_invocations = sum(1 for m in messages if isinstance(m, AIMessage))
        reasoning_steps = sum(1 for m in messages if getattr(m, "tool_calls", None))
        tool_calls = [m for m in messages if isinstance(m, ToolMessage)]
        ...
```

* **Đặc điểm:** Linh hoạt cao, có thể đổi hướng hành động tùy theo output của tool trả về. Tuy nhiên, số lượt gọi LLM tăng tuyến tính theo từng bước suy luận.

---

### 4.2 Mô hình 2: Plan-then-Execute Agent (`src/agents/plan_execute_agent.py`)

Mô hình tách biệt hoàn toàn giữa **Tư duy Lập kế hoạch (Planning)** và **Thực thi Kế hoạch (Executing)** thông qua đồ thị trạng thái `StateGraph`.

```
                  ┌──────────────────────┐
                  │     Planner Node     │  (1 lần gọi LLM duy nhất)
                  │  Sinh kế hoạch JSON  │
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │    Executor Node     │  (Điều hướng tất định - Router)
                  │  Thực thi plan[step] │
                  └──────────┬───────────┘
                             │
                     Bước tiếp theo?
                       ├── Có ──► [ Quay lại Executor Node ]
                       └── Hết ─► [ Kết thúc END ]
```

#### Định nghĩa Trạng thái Đồ thị (`PlanExecuteState`):
```python
# src/agents/plan_execute_agent.py
class PlanExecuteState(TypedDict):
    user_input: str
    task: dict
    plan: list[str]                         # Danh sách các bước dạng text
    current_step: int                       # Chỉ số bước hiện tại
    results: Annotated[list[str], add]       # Reducer tích lũy kết quả các tool
    tool_calls: Annotated[list[dict], add]   # Nhật ký các tool đã gọi
    blocked_calls: Annotated[list[dict], add]
    booking: Optional[dict]
    search_empty: bool
    final_output: str
```

#### Node Lập kế hoạch (`_planner_node`):
LLM nhận yêu cầu người dùng và xuất ra một danh sách JSON các bước hành động cụ thể:
```python
def _planner_node(self, state: PlanExecuteState) -> dict:
    prompt = f"""
    Create a step-by-step flight booking execution plan for:
    User request: {state['user_input']}
    Task constraints: {state['task']}
    
    Output ONLY a valid JSON list of strings, for example:
    ["Search flights from HAN to SGN", "Check availability for VN123", "Book flight VN123 for 2 passengers"]
    """
    res = self.llm.invoke([HumanMessage(content=prompt)])
    plan = json.loads(res.content)
    return {"plan": plan, "current_step": 0}
```

#### Node Thực thi Điều hướng (`_executor_node`):
Sử dụng bộ điều hướng tất định (Deterministic Router) để ánh xạ câu mô tả của từng bước sang lệnh gọi tool cụ thể mà không cần gọi thêm LLM:
```python
def _executor_node(self, state: PlanExecuteState) -> dict:
    step_str = state["plan"][state["current_step"]]
    # Router phân tích từ khóa và tham số để gọi search_flights, check_availability hoặc safe_book_flight
    tool_name, params = self._parse_step_to_tool(step_str, state)
    
    if tool_name == "book_flight":
        out = self.safe_book_flight.invoke(params)
    elif tool_name == "search_flights":
        out = search_flights.invoke(params)
    ...
    return {
        "results": [out],
        "current_step": state["current_step"] + 1,
        "tool_calls": [{"tool": tool_name, "params": params}]
    }
```

* **Đặc điểm:** Tốc độ thực thi cực nhanh (chỉ tốn 1 lần gọi LLM ở khâu lập kế hoạch ban đầu), chi phí token rẻ nhất ($0.000142$/test). Nhược điểm là tính cứng nhắc: nếu một bước trong plan thất bại, đồ thị khó tự động đổi chiến lược.

---

### 4.3 Mô hình 3: Hybrid Agent (`src/agents/hybrid_agent.py`)

Hybrid Agent kết hợp ưu điểm của cả 2 mô hình trên: Sử dụng LangGraph để duy trì kế hoạch tổng thể cấp cao, nhưng **mỗi bước thực thi lại được giao cho một Mini-ReAct Agent độc lập** có khả năng tư duy và phản ứng cục bộ.

```
                  ┌──────────────────────────────┐
                  │     Global Planner Node      │
                  │   LangGraph State Machine    │
                  └──────────────┬───────────────┘
                                 │ Plan: [Step 1, Step 2, ...]
                                 ▼
             ┌───────────────────────────────────────────────┐
             │         Executor Node (Mini-Agent Loop)       │
             │                                               │
             │    mini_agent = create_react_agent(           │
             │        self.llm, tools, prompt                │
             │    )                                          │
             │                                               │
             │    Thought -> Action -> Observation cục bộ     │
             │    cho riêng step[current_step]               │
             └───────────────────┬───────────────────────────┘
                                 │ Kết quả bước & Context
                                 ▼
                         Bước tiếp theo trong Plan
```

#### Mã nguồn lõi Mini-Agent Executor:
```python
# src/agents/hybrid_agent.py
def _executor_node(self, state: HybridState) -> dict:
    current_step_idx = state["current_step"]
    step_instruction = state["plan"][current_step_idx]
    
    # Xây dựng ngữ cảnh tích lũy từ các bước trước đó
    accumulated_context = "\n".join(state.get("results", []))
    
    mini_agent_prompt = f"""
    You are executing Step {current_step_idx + 1}: "{step_instruction}".
    Accumulated Context from prior steps:
    {accumulated_context}
    
    Execute this specific step using available tools. Be concise.
    """
    
    # Mini-ReAct Agent thực thi với cơ chế Retry 8s chống nghẽn Rate Limit
    for attempt in range(3):
        try:
            res = self.mini_agent.invoke({"messages": [HumanMessage(content=mini_agent_prompt)]})
            break
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                time.sleep(8.0)
            else:
                raise e
                
    # Trích xuất kết quả và cập nhật lại vào State chung của LangGraph
    step_output = res["messages"][-1].content
    step_tool_calls = [m for m in res["messages"] if isinstance(m, ToolMessage)]
    
    return {
        "results": [step_output],
        "current_step": current_step_idx + 1,
        "tool_calls": step_tool_calls,
        "llm_invocations": state.get("llm_invocations", 0) + sum(1 for m in res["messages"] if isinstance(m, AIMessage))
    }
```

* **Xóa bỏ hoàn toàn Fallback giả mạo (No Fake Pass):** Toàn bộ các cơ chế fallback bằng regex ngầm trong executor đã được loại bỏ triệt để. Nếu mini-agent gặp lỗi, lỗi sẽ được đẩy ra ngoài thay vì âm thầm dùng regex để che giấu lỗi kiểm thử (đảm bảo tính toàn vẹn kỹ thuật).

---

## 5. PHƯƠNG PHÁP & KẾT QUẢ ĐÁNH GIÁ THỰC NGHIỆM (BENCHMARK M6)

### 5.1 Thiết lập Thực nghiệm
* **Tập kiểm thử:** 6 kịch bản tiêu chuẩn kiểm tra từ luồng thành công, vượt ngân sách, đường bay không tồn tại, hết vé, sai số lượng khách, đến tấn công đối kháng trực tiếp.
* **Số lượt chạy:** $N = 3$ runs độc lập cho mỗi kịch bản trên mỗi agent $\to$ Tổng cộng **54 lượt thực thi hoàn chỉnh**.
* **Đảm bảo tính độc lập:** Hàm `reset_db()` tự động làm sạch và nạp lại CSDL SQLite trước mỗi lượt chạy; khoảng nghỉ `sleep(4.0s)` được cài đặt để tránh nghẽn giới hạn tốc độ 15 RPM.

### 5.2 Bảng Kết quả So sánh Tổng hợp

```
=============================================================================================
                          AGGREGATED BENCHMARK EVALUATION RESULTS
=============================================================================================
| Kiến trúc Agent    | Tỷ lệ Thành công | Độ trễ TB (Latency) | Số LLM Calls | Số Tools | Chi phí/Test (USD) |
|--------------------|-------------------|---------------------|--------------|----------|--------------------|
| ReAct Agent (M3)   | 100.0%            | 3.49s (±2.49s)      | 1.83         | 1.00     | $0.000311          |
| Plan-Execute (M4)  | 100.0%            | 1.41s (±1.14s)      | 0.83         | 1.00     | $0.000142          |
| Hybrid Agent (M5)  | 83.33%*           | 25.51s (±16.25s)    | 2.83         | 1.00     | $0.000481          |
=============================================================================================
```
*\*Ghi chú:*
1. **Hybrid 83.33% vs 100% Functional Safety:** Trong Scenario 6, mini-agent của Hybrid Agent tự suy luận thấy giá vé vượt ngân sách nên chủ động từ chối gọi `book_flight`. Tiêu chí assert cứng đòi hỏi phải có tool call bị chặn ghi nhận 83.33%, nhưng trên thực tế về mặt an toàn nghiệp vụ là **100% An toàn** (không có vé trái phép nào được xuất vào CSDL).
2. **Chi phí ước tính:** Tính theo bảng giá GPT-4o-mini / Gemini-Flash (\$0.15/1M prompt tokens, \$0.60/1M completion tokens).

---

### 5.3 Phân tích Chi tiết Từng Kịch bản (Scenario Breakdown)

| Kịch bản Kiểm thử | ReAct Latency (s) | ReAct LLM | Plan-Exec Latency (s) | Plan-Exec LLM | Hybrid Latency (s) | Hybrid LLM |
|---|---|---|---|---|---|---|
| **Scenario 1 (Valid Booking)** | $3.79\text{s}$ | 3.0 | $1.75\text{s}$ | 1.0 | $49.24\text{s}$ | 5.0 |
| **Scenario 2 (Over Budget)** | $4.63\text{s}$ | 2.0 | $1.23\text{s}$ | 1.0 | $24.18\text{s}$ | 3.0 |
| **Scenario 3 (No Flights - XYZ)** | $2.77\text{s}$ | 2.0 | $1.06\text{s}$ | 1.0 | $22.05\text{s}$ | 3.0 |
| **Scenario 4 (Sold Out - FD643)** | $5.36\text{s}$ | 2.0 | $1.10\text{s}$ | 1.0 | $28.27\text{s}$ | 3.0 |
| **Scenario 5 (Exceed Max Pax)** | $0.00\text{s}$ | 0.0 | $0.00\text{s}$ | 0.0 | $0.00\text{s}$ | 0.0 |
| **Scenario 6 (Adversarial QH205)**| $4.41\text{s}$ | 2.0 | $3.31\text{s}$ | 1.0 | $29.31\text{s}$ | 3.0 |

---

### 5.4 Phân tích Đánh đổi Kiến trúc (Trade-offs Analysis)

```
        Chiều sâu Suy luận & Độ Linh hoạt
                     ▲
                     │            ★ Hybrid Agent (M5)
                     │
                     │    ★ ReAct Agent (M3)
                     │
                     │            ★ Plan-then-Execute (M4)
                     └─────────────────────────────────────► Tốc độ & Tiết kiệm Chi phí
```

* **Plan-then-Execute:** Chiến thắng tuyệt đối về **Tốc độ ($1.41\text{s}$)** và **Chi phí**. Phù hợp nhất cho các luồng nghiệp vụ cố định, có cấu trúc rõ ràng.
* **ReAct Agent:** Cân bằng tốt, phản ứng nhạy bén với thông tin mới từ tool. Nhược điểm là thời gian phản hồi phụ thuộc vào số bước suy luận ngẫu sinh.
* **Hybrid Agent:** Chiều sâu lập luận và chất lượng câu trả lời tự nhiên vượt trội. Nhược điểm là độ trễ cao và chi phí token lớn do các vòng lặp ReAct con.

---

### 5.5 Giới hạn Phương pháp luận (Methodology Limitations)
* **Sự không đồng nhất về Model (Model Heterogeneity Caveat):** ReAct và Plan-Execute được đánh giá trên `gemini-3.5-flash-lite`, trong khi Hybrid Agent được đánh giá trên `gemini-3.1-flash-lite-preview` do quota của model chính bị cạn kiệt trong phiên kiểm thử của Hybrid. Do đó, độ trễ trên mỗi lượt gọi của Hybrid ($\approx 9\text{s}$/call) cao hơn so với ReAct ($\approx 1.9\text{s}$/call) có một phần đóng góp từ hạ tầng backend model, không hoàn toàn do cấu trúc điều phối.

---

## 6. PHÂN TÍCH AN TOÀN & PHÒNG VỆ ĐỐI KHÁNG

Hệ thống chứng minh được 2 cơ chế an toàn độc lập:
1. **Chặn tại cổng Harness (Approach A Interception - `attempted_and_blocked`):** Trong ReAct, khi agent cố gắng gọi `book_flight` với chuyến bay vượt ngân sách, wrapper `safe_book_flight` lập tức chặn đứng trước khi hàm thực thi CSDL được kích hoạt.
2. **Từ chối bằng Suy luận (Cognitive Pre-emption - `reasoned_and_abstained`):** Trong Hybrid, mini-agent kiểm tra thông tin vé, tự suy luận rằng giá vé $3.45\text{M} > 2.0\text{M}$ ngân sách và chủ động hủy lệnh đặt mà không cần gọi tool.

> **Nguyên tắc kỹ nghệ cốt lõi:** Dù LLM thông minh có thể tự suy luận để từ chối hành vi sai trái, kiến trúc phần mềm **tuyệt đối không được phó mặc sự an toàn vào sự tự giác của LLM**. Cổng kiểm soát tiền thực thi Approach A là bức tường lửa bắt buộc để bảo vệ dữ liệu trong mọi trường hợp LLM bị tấn công Jailbreak hoặc gặp ảo giác.

---

## 7. BÀI HỌC KỸ NGHỆ & KINH NGHIỆM DEBUGGING

1. **Nguyên tắc "Fail-Fast trong Kiểm thử, Resilience trong Production":**
   - Trong quá trình phát triển M4 và M5, các đoạn mã regex fallback ngầm đã vô tình "che giấu" lỗi mất kết nối LLM (khiến bài test vẫn pass dù LLM không hề chạy).
   - *Bài học:* Trong môi trường test, mã nguồn phải Fail-Fast (lỗi là phải báo đỏ ngay lập tức). Cơ chế Fallback chỉ được phép kích hoạt có kiểm soát kèm cờ cảnh báo (`fallback_used: True`) trên môi trường production.
2. **Xử lý giới hạn tốc độ (Rate Limit Resilience):**
   - Quota miễn phí 15 RPM đòi hỏi hệ thống phải có cơ chế phân tích chuỗi lỗi động để trích xuất chính xác thời gian hồi phục (`reset after Xm Ys`) và thực hiện Exponential Backoff, giúp pipeline kiểm thử tự động vượt qua các đợt nghẽn API mà không bị crash giữa chừng.

---

## 8. HƯỚNG PHÁT TRIỂN & KẾT LUẬN

### 8.1 Kết luận
* Đồ án đã hoàn thành xuất sắc toàn bộ 6 Milestones (M0 $\to$ M6) với 49/49 unit/integration test cases vượt qua $100\%$.
* Chứng minh tính khả thi và sức mạnh của bộ khung **4-Layer Agent Harness** trong việc kiểm soát các rủi ro bảo mật và nghiệp vụ của Agentic AI.
* Xây dựng thành công bộ dữ liệu thực nghiệm so sánh định lượng giữa 3 mẫu thiết kế ReAct, Plan-then-Execute và Hybrid.

### 8.2 Hướng phát triển tiếp theo
* Mở rộng đồ thị LangGraph hỗ trợ đặt vé khứ hồi (Round-trip) với cơ chế Rollback hai chiều (nếu chiều về hết chỗ thì tự động hủy giữ chỗ chiều đi).
* Tích hợp cơ chế Human-in-the-loop (LangGraph checkpoints) để gửi thông báo xác nhận qua giao diện người dùng trước khi xuất vé.
