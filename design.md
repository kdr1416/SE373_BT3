# Flight Booking Agent --- Design Specification

> **Scope:** M0 design for a mock flight-booking agent.\
> **Principle:** Design the workflow and safety boundaries first;
> implementation comes after the design is accepted.

------------------------------------------------------------------------

## 0.1 Domain Design

### Câu 1 --- Agent phải làm được gì?

Agent phải:

1.  Nhận yêu cầu đặt vé từ người dùng.
2.  Trích xuất các thông tin/ràng buộc từ yêu cầu: route, ngày bay, số
    hành khách, cabin class, budget, airline preference...
3.  Tìm kiếm các chuyến bay phù hợp và sử dụng tools khi cần.
4.  Kiểm tra thông tin và tình trạng ghế trước khi booking.
5.  Thực hiện booking khi đủ điều kiện và đạt yêu cầu xác nhận của người
    dùng.

**Goal:**

-   Có một booking đã `confirmed` và thỏa các constraints đã được user
    chấp thuận; hoặc
-   Kết thúc với một terminal outcome phù hợp như `CANCELLED`,
    `REJECTED`, hoặc `HANDED_OFF` khi không thể tiếp tục an toàn.

### Câu 2 --- Constraints là gì?

Constraints là các dữ liệu/ràng buộc dùng để xác định flight có phù hợp
với yêu cầu hay không:

-   `budget_min` / `budget_max`
-   `passengers`
-   `origin`
-   `destination`
-   `cabin_class`
-   `airline`
-   ngày/giờ bay nếu user yêu cầu
-   các preference khác nếu được hỗ trợ

#### Cabin class policy

`economy` là **soft constraint**:

-   Nếu Economy có sẵn → ưu tiên/chọn Economy.
-   Nếu không có Economy nhưng có Business → **không tự động đổi**, phải
    hỏi user.
-   Chỉ sau khi user đồng ý đổi sang Business thì Business mới trở thành
    lựa chọn hợp lệ.

### Câu 3 --- Khi nào agent phải từ chối?

Agent **reject** khi yêu cầu nằm ngoài capability/scope đã thiết kế hoặc
không thể thực hiện bằng workflow hiện tại.

Ví dụ:

-   User yêu cầu vé **khứ hồi** trong khi hệ thống hiện chỉ hỗ trợ một
    chiều.
-   User yêu cầu một chức năng không thuộc flight-booking scope.
-   User yêu cầu một hành động mà agent không được phép thực hiện và
    không có handoff path phù hợp.

**Không coi mọi trường hợp "không tìm thấy vé" là rejection.** Nếu còn
khả năng hỏi user về phương án khác, agent nên clarification trước.

### Câu 4 --- Khi nào agent handoff cho human?

Handoff khi agent hiểu yêu cầu nhưng không nên/không thể tự hoàn tất một
cách an toàn, ví dụ:

-   Refund hoặc xử lý yêu cầu ngoài capability của agent.
-   Tool/backend gặp lỗi lặp lại và không thể tự recover.
-   Confidence quá thấp sau các bước clarification/replanning hợp lý.
-   Phát hiện conflict cần quyết định nghiệp vụ mà agent không có
    authority để tự quyết.

**User confirmation cho booking không phải là handoff.** Đây là một
**HITL approval gate do harness kiểm soát** trong workflow.

### Câu 5 --- "Done" nghĩa là gì?

Booking chỉ được coi là `DONE` khi đồng thời thỏa:

``` text
user_approved == true
AND
booking.status == "confirmed"
AND
booking satisfies accepted constraints
```

Có `booking_id` là bằng chứng booking tồn tại, nhưng **không tự nó đủ để
kết luận DONE**.

Nếu user hủy yêu cầu thì đó là `CANCELLED`, **không phải DONE**.

------------------------------------------------------------------------

## 0.2 Mock Data

Mock data dùng YAML hợp lệ như sau:

``` yaml
routes:
  HAN-SGN:
    - id: "VN123"
      airline: "Vietnam Airlines"
      origin: "HAN"
      destination: "SGN"
      departure: "2026-10-10T08:00"
      arrival: "2026-10-10T10:15"
      class: "economy"
      price: 1200000
      monetary_unit: "VND"
      seats: 45

    - id: "VJ181"
      airline: "Vietjet Air"
      origin: "HAN"
      destination: "SGN"
      departure: "2026-10-10T13:30"
      arrival: "2026-10-10T15:45"
      class: "economy"
      price: 890000
      monetary_unit: "VND"
      seats: 12

    - id: "QH205"
      airline: "Bamboo Airways"
      origin: "HAN"
      destination: "SGN"
      departure: "2026-10-10T18:00"
      arrival: "2026-10-10T20:15"
      class: "business"
      price: 3450000
      monetary_unit: "VND"
      seats: 4

  HAN-BKK:
    - id: "VN611"
      airline: "Vietnam Airlines"
      origin: "HAN"
      destination: "BKK"
      departure: "2026-10-11T09:15"
      arrival: "2026-10-11T11:15"
      class: "economy"
      price: 2150000
      monetary_unit: "VND"
      seats: 28

    - id: "TG561"
      airline: "Thai Airways"
      origin: "HAN"
      destination: "BKK"
      departure: "2026-10-11T10:35"
      arrival: "2026-10-11T12:35"
      class: "business"
      price: 5200000
      monetary_unit: "VND"
      seats: 6

    - id: "FD643"
      airline: "AirAsia"
      origin: "HAN"
      destination: "DMK"
      departure: "2026-10-11T19:00"
      arrival: "2026-10-11T20:50"
      class: "economy"
      price: 1450000
      monetary_unit: "VND"
      seats: 0

  SGN-BKK:
    - id: "VN603"
      airline: "Vietnam Airlines"
      origin: "SGN"
      destination: "BKK"
      departure: "2026-10-12T16:55"
      arrival: "2026-10-12T18:30"
      class: "economy"
      price: 1850000
      monetary_unit: "VND"
      seats: 15

    - id: "VJ801"
      airline: "Vietjet Air"
      origin: "SGN"
      destination: "BKK"
      departure: "2026-10-12T08:30"
      arrival: "2026-10-12T10:05"
      class: "economy"
      price: 1100000
      monetary_unit: "VND"
      seats: 32

    - id: "TG557"
      airline: "Thai Airways"
      origin: "SGN"
      destination: "BKK"
      departure: "2026-10-12T14:10"
      arrival: "2026-10-12T15:40"
      class: "business"
      price: 4900000
      monetary_unit: "VND"
      seats: 8
```

### Edge cases bắt buộc

1.  **Route không tồn tại**

    Ví dụ:

    ``` text
    HAN-DAD
    ```

    Không có key tương ứng trong `routes`. Tool phải trả kết quả
    lỗi/empty result theo contract; agent không được tự tạo flight.

2.  **Seats \< passengers**

    Ví dụ user yêu cầu `passengers = 16` nhưng chọn `VN603` có
    `seats = 15`.

    Kết quả validation:

    ``` text
    seats (15) < passengers (16)
    → INVALID
    → không được gọi/tiếp tục booking cho flight này
    ```

3.  **Sold out**

    `FD643` có `seats = 0`.

    → Không được chọn để booking.

4.  **Business vượt budget**

    `QH205` có giá `3,450,000 VND`.

    Nếu user yêu cầu Business nhưng `budget_max = 2,000,000`:

    → Không tự ý bỏ budget hoặc đổi cabin. Đây là constraint conflict
    cần clarification.

------------------------------------------------------------------------

## 0.3 State Design

### Nguyên tắc

Tách **Graph State** khỏi **Harness State**.

-   **Graph State:** dữ liệu workflow mà agent cần đọc/cập nhật.
-   **Harness State:** dữ liệu kiểm soát an toàn, authorization,
    approval và completion; **không cho LLM tự sửa**.

### 0.3.1 Graph State

Ví dụ schema:

``` python
from operator import add
from typing import Annotated, TypedDict

class GraphState(TypedDict):
    task: str
    plan: list[str]
    is_replan_needed: bool
    current_step: int

    user_input: str

    results: Annotated[list, add]
    tickets: list[FlightTicket]

    data_valid: bool
    validation_errors: Annotated[list, add]
```

### Ý nghĩa các field

  -------------------------------------------------------------------------------------------
  Field                 Type                           Update strategy   Ý nghĩa
  --------------------- ------------------------------ ----------------- --------------------
  `task`                `str`                          replace           Task hiện tại

  `plan`                `list[str]`                    replace           Kế hoạch hiện tại

  `is_replan_needed`    `bool`                         replace           Có cần lập lại plan
                                                                         không

  `current_step`        `int`                          replace           Bước hiện tại

  `user_input`          `str`                          replace           Yêu cầu user

  `results`             `Annotated[list, add]`   add               Tích lũy tool/flight
                                                                         results trong run

  `tickets`             `list[FlightTicket]`           replace           Candidate/selected
                                                                         flight objects hiện
                                                                         tại

  `data_valid`          `bool`                         replace           Kết quả validation
                                                                         hiện tại

  `validation_errors`   `Annotated[list, add]`    add               Tích lũy validation
                                                                         errors trong run
  -------------------------------------------------------------------------------------------

> `Annotated[list, add]` dùng reducer `add` để tích lũy list update thay
> vì ghi đè list hiện tại.

### 0.3.2 Harness State

Các field sau thuộc harness, không thuộc LLM-controlled graph state:

``` text
auth_passed
user_approved
is_completed
cancelled
needs_handoff
handoff_reason
```

Harness chịu trách nhiệm:

-   kiểm tra permission trước action nhạy cảm;
-   kiểm soát user approval;
-   xác định completion bằng code;
-   ghi nhận cancellation;
-   quyết định/ghi nhận handoff;
-   ngăn LLM tự sửa các safety flags.

**Đặc biệt:** `user_approved`, `auth_passed` và `is_completed` không
được để LLM tự đặt thành `true`.

------------------------------------------------------------------------

## 0.4 Tool Interface Design

### 1. `search_flights(origin: str, destination: str) -> str`

**Purpose:** Tìm danh sách chuyến bay giữa hai mã sân bay IATA.

**Returns:** JSON list gồm thông tin cơ bản như `flight_id`, `airline`,
`departure`, `price`, `class`, `seats` nếu có.

**Edge cases:**

-   route không tồn tại → empty result/error;
-   không có flight phù hợp → empty result;
-   không được tự sinh flight ngoài mock data.

### 2. `get_flight_details(flight_id: str) -> str`

**Purpose:** Tra cứu thông tin chi tiết của một flight cụ thể.

**Returns:** JSON gồm flight ID, airline, origin/destination,
departure/arrival, cabin class, baggage và policy nếu mock data hỗ trợ.

### 3. `check_availability(flight_id: str) -> str`

**Purpose:** Kiểm tra số ghế còn lại.

**Returns:** JSON như:

``` json
{
  "status": "available",
  "seats_left": 12
}
```

hoặc:

``` json
{
  "status": "sold_out",
  "seats_left": 0
}
```

**Validation:** `seats_left >= passengers` là điều kiện cần trước
booking.

### 4. `book_flight(flight_id: str, passenger_name: str, passengers: int) -> str`

**Purpose:** Thực hiện booking sau khi flight đã được kiểm tra và user
đã approve.

**Returns:** JSON success gồm:

``` json
{
  "booking_id": "...",
  "status": "confirmed",
  "passenger_name": "...",
  "passengers": 2,
  "total_price": 2400000
}
```

hoặc error nếu booking fail.

**Permission:** `book_flight` là action nhạy cảm và phải qua harness
authorization/approval gate.

------------------------------------------------------------------------

## 0.5 Test Cases Design

### Test Case 7 --- Round-trip unsupported

**Yêu cầu:**

> "Đặt cho tôi vé máy bay khứ hồi từ ĐN đến TPHCM."

**Kỳ vọng:**

``` text
REJECT
```

**Justification:**

Workflow hiện tại chỉ hỗ trợ booking một chiều. Round-trip là capability
chưa được cài đặt, nên agent không thể thực hiện yêu cầu một cách đúng
đắn. Đây là **out-of-scope capability**, không phải trường hợp chỉ thiếu
thông tin.

------------------------------------------------------------------------

### Test Case 8 --- Business vượt budget

**Yêu cầu:**

> "Tôi muốn vé Business, budget tối đa 2M."

Mock flight:

``` text
QH205
class = business
price = 3.45M VND
```

**Kỳ vọng:**

``` text
CLARIFICATION
```

Agent phải báo Business hiện có vượt budget và hỏi user muốn:

-   tăng budget; hoặc
-   đổi sang Economy.

Agent **không được tự ý** book Business 3.45M và cũng không được tự ý
đổi sang Economy.

------------------------------------------------------------------------

## 0.6 Constraints, Completion, Permission & Failure Policy

### 0.6.1 Constraints

Constraints được lưu riêng trong file `.yml`.

Ví dụ:

``` yaml
cabin_class:
  preferred: economy
  negotiable: true
  fallback_options:
    - business
  auto_switch: false
  require_user_confirmation_for_change: true
```

### 0.6.2 Completion vs Cancellation

**Completion check** chỉ kiểm tra liệu workflow đã đạt điều kiện thành
công hay chưa.

``` text
DONE =
    user_approved
    AND booking.status == "confirmed"
    AND booking satisfies accepted constraints
```

**Cancellation** là một terminal outcome khác:

``` text
User cancels
    ↓
CANCELLED
```

Cancellation **không phải completion** và không phải rejection.

Ví dụ:

``` text
No matching flight
    ↓
Ask user for alternative / cancellation
    ↓
User chooses cancel
    ↓
CANCELLED
```

### 0.6.3 Permission check

Các action nhạy cảm như:

``` text
book_flight
```

phải qua permission/approval của harness.

Các tool read-only như:

``` text
search_flights
get_flight_details
check_availability
```

được cấp quyền cho agent vì không trực tiếp tạo side effect booking.

### 0.6.4 Completion check vs Permission check

-   **Completion check:** output cuối cùng có đạt yêu cầu và exit
    criteria không?
-   **Permission check:** agent có được phép thực hiện action/tool đó
    không?

Hai check này độc lập.

Ví dụ:

``` text
user_approved = true
BUT
booking API failed
→ permission OK
→ completion FAIL
→ chưa DONE
```

Hoặc:

``` text
booking API có thể chạy
BUT
user chưa approve
→ permission/approval FAIL
→ không được book
```

### 0.6.5 Failure / Handoff policy

Có thể handoff khi:

-   tool/backend lỗi lặp lại;
-   confidence quá thấp;
-   conflict nghiệp vụ không thể giải quyết bằng clarification;
-   yêu cầu vượt capability nhưng có human path.

Nếu chỉ không tìm thấy flight, agent nên **clarify alternative trước**,
không handoff ngay.

------------------------------------------------------------------------

## 0.7 Trả lời các câu hỏi thiết kế

### Q1 --- Nếu agent search HAN-SGN và không có flight thì làm gì?

Không tự coi đây là completion hay handoff.

Agent nên:

1.  thông báo không tìm thấy flight phù hợp;
2.  hỏi user có muốn đổi ngày, route, cabin hoặc constraint phù hợp
    không;
3.  nếu user chọn hủy → `CANCELLED`;
4.  nếu agent không thể tiếp tục sau các phương án hợp lý → có thể
    handoff/reject tùy nguyên nhân.

### Q2 --- Tại sao `results` cần reducer `add`?

Vì nhiều node/tool calls có thể tạo ra các kết quả khác nhau trong cùng
một run. Ta cần giữ các kết quả trước để đối chiếu, thay vì mỗi update
ghi đè kết quả cũ.

### Q3 --- Tool nào phải qua permission check?

`book_flight` phải qua permission/approval vì đây là action có side
effect và có thể tạo nghĩa vụ thanh toán/booking.

Các tool read-only không cần cùng mức approval.

### Q4 --- Sự khác biệt giữa completion check và permission check?

-   Completion: kiểm tra **đã đạt mục tiêu chưa**.
-   Permission: kiểm tra **có được phép thực hiện action chưa**.

### Q5 --- Nếu agent book vé thành công nhưng giá vượt budget thì lỗi của ai?

Thiết kế đúng phải **ngăn trường hợp này trước booking** bằng constraint
validation và completion/safety verification.

Nếu vẫn xảy ra, đây là **safety/invariant violation của hệ
thống/harness**, vì harness phải bảo đảm side-effect không được thực
hiện nếu constraint bắt buộc chưa được thỏa mãn.

------------------------------------------------------------------------

## 0.8 Decision Summary

Các quyết định M0 đã chốt:

  ----------------------------------------------------------------------------------------
  Decision                            Chọn
  ----------------------------------- ----------------------------------------------------
  Booking confirmation                HITL

  Approval authority                  Harness

  Cabin constraint                    Soft / negotiable

  Economy available                   Chọn Economy

  Economy unavailable                 Hỏi user trước khi đổi Business

  Round-trip                          Reject vì unsupported

  Business \> budget                  Clarification

  Validation location                 Sau mỗi tool call

  `results` reducer                   `Annotated[list, add]`

  `validation_errors` reducer         `Annotated[list, add]`

  Validation scope                    Validate toàn bộ tool output/candidate set

  Completion                          `approved AND confirmed AND constraints satisfied`

  Cancellation                        Terminal `CANCELLED`, không phải `DONE`

  `book_flight` permission            Harness-controlled

  Graph state                         Không chứa safety/approval flags

  Harness state                       Chứa authorization, approval, completion,
                                      cancellation, handoff
  ----------------------------------------------------------------------------------------

------------------------------------------------------------------------

## 0.9 Mock User Behavior

Harness phải giả lập user response một cách **deterministic**, để test
case có thể reproducible.

### Input của mock user

Mỗi test case định nghĩa sẵn response cho các loại câu hỏi mà agent có
thể hỏi:

``` yaml
mock_user:
  confirmations:
    booking: true
    constraint_change: false

  clarifications:
    cabin_class: "business"
    budget_max: 3500000

  cancellation: false
```

### Behavior rules

1.  Khi agent yêu cầu **booking confirmation**, harness trả về giá trị
    `confirmations.booking`.
2.  Khi agent hỏi có đổi Economy → Business hay không, harness trả về
    `confirmations.constraint_change`.
3.  Khi agent yêu cầu clarification về constraint, harness trả về giá
    trị tương ứng trong `clarifications`.
4.  Nếu test case yêu cầu user cancel, harness trả `cancellation: true`
    và kết thúc run bằng `CANCELLED`.
5.  Mock user **không tự thay đổi Graph State** và không tự gọi tool.
6.  Response phải deterministic theo test case; cùng input + cùng mock
    behavior phải cho cùng expected outcome.

### Ví dụ Case B --- Không có Economy

``` text
Agent:
"Không có Economy. Bạn có muốn Business không?"

Mock user:
NO

→ Agent không được book Business
→ workflow không được tự ý đổi cabin
```

Nếu mock user trả `YES`:

``` text
→ constraint được user chấp thuận thay đổi
→ agent có thể tiếp tục tìm/booking Business
→ vẫn phải qua booking approval gate nếu chưa được approval cho side effect
```

------------------------------------------------------------------------

## 0.10 Reducer Strategy

### Mục tiêu

`validation_errors` sử dụng:

``` python
Annotated[list, add]
```

để tích lũy lỗi trong **một test run**.

Ví dụ:

``` text
Tool Call 1
  → error_1, error_2

Tool Call 2
  → error_3

State:
validation_errors = [
  error_1,
  error_2,
  error_3
]
```

### Reset giữa các test case

Mỗi test case phải bắt đầu bằng **một Graph State mới**:

``` python
initial_state = {
    ...
    "validation_errors": [],
    "results": [],
}
```

Không reuse state của test case trước.

Flow:

``` text
Test Case 1
    ↓
Fresh Graph State
    ↓
validation_errors = []
    ↓
run
    ↓
errors accumulate
    ↓
END

Test Case 2
    ↓
Fresh Graph State
    ↓
validation_errors = []
    ↓
run
```

### Quy tắc

-   `add` chỉ có hiệu lực trong phạm vi **một run**.
-   Không dùng reducer `add` như cơ chế lưu lỗi xuyên test cases.
-   Harness phải khởi tạo state mới hoặc clear state trước mỗi test
    case.
-   Không được để lỗi từ Test Case N xuất hiện trong Test Case N+1.
-   Nếu một validation cycle mới trong cùng run cần bắt đầu với danh
    sách lỗi rỗng, phải thực hiện reset explicitly theo workflow design
    thay vì dựa vào reducer `add`.

### Validation location

Validation được thực hiện **sau mỗi tool call**:

``` text
LLM
 ↓
Tool Call
 ↓
Tool Output
 ↓
Validate entire tool output / candidate set
 ↓
Valid → continue
Invalid → record validation_errors + replan/skip/reject as appropriate
```

Ví dụ:

``` text
search_flights()
    ↓
5 candidate flights
    ↓
validate ALL 5
    ↓
3 invalid
    ↓
validation_errors += 3 errors
```

------------------------------------------------------------------------

# End of M0 Design
