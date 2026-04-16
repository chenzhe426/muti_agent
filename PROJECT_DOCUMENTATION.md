# Multi-Agent RAG Customer Support System
## 完整技术文档

---

## 目录

1. [系统概述](#1-系统概述)
2. [系统架构](#2-系统架构)
3. [技术栈](#3-技术栈)
4. [项目结构](#4-项目结构)
5. [数据层](#5-数据层)
6. [多智能体设计](#6-多智能体设计)
7. [完整请求链路](#7-完整请求链路)
8. [上下文管理机制](#8-上下文管理机制)
9. [记忆与状态持久化](#9-记忆与状态持久化)
10. [工具系统详解](#10-工具系统详解)
11. [图架构与路由逻辑](#11-图架构与路由逻辑)
12. [流式输出实现](#12-流式输出实现)
13. [Neo4j 知识图谱](#13-neo4j-知识图谱)
14. [API 接口说明](#14-api-接口说明)
15. [启动与配置](#15-启动与配置)

---

## 1. 系统概述

### 1.1 项目简介

本项目是一个**多智能体检索增强生成（RAG）客户支持系统**，用于处理旅游相关的客户咨询和业务办理，包括：

- 航班查询、预订、改签、退票
- 酒店查询、预订、修改、取消
- 汽车租赁查询、预订、修改、取消
- 短途旅行/活动推荐和预订

### 1.2 核心特性

| 特性 | 描述 |
|------|------|
| 多智能体架构 | 1个主控Agent + 4个专业Agent，采用Chain of Responsibility模式 |
| RAG检索增强 | Qdrant向量数据库存储语义索引，支持自然语言查询 |
| 知识图谱推理 | Neo4j存储退改签规则、会员权益等结构化知识 |
| 敏感操作审批 | 预订/改签等操作需用户二次确认 |
| 流式输出 | SSE实现实时流式响应 |
| 会话记忆 | 基于thread_id的跨请求状态保持 |

---

## 2. 系统架构

### 2.1 整体架构图

```
                                    ┌─────────────────────────────────────────┐
                                    │            Frontend (HTML/JS)            │
                                    │         http://localhost:8000           │
                                    └──────────────────┬──────────────────────┘
                                                       │ HTTP/SSE
                                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              FastAPI Server (api.py)                                │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                           /chat/stream (POST)                                │   │
│  │  - 接收用户消息 + thread_id                                                  │   │
│  │  - 调用 multi_agentic_graph.stream() 流式处理                                │   │
│  │  - SSE推送消息到前端                                                         │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────────────────┐   │
│  │                           /chat/approve (POST)                                │   │
│  │  - 接收用户对敏感操作的审批/拒绝                                              │   │
│  │  - 继续/中断 LangGraph 执行                                                   │   │
│  └─────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────┬──────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                        LangGraph State Machine (graph.py)                            │
│                                                                                     │
│   ┌──────────────┐    ┌───────────────────┐    ┌──────────────────────────┐      │
│   │fetch_user_info│───▶│  primary_assistant │◀───│ primary_assistant_tools │      │
│   │  (SQLite)    │    │                   │    └──────────────────────────┘      │
│   └──────────────┘    └─────────┬─────────┘                                     │
│                                  │                                                 │
│                    ┌─────────────┼─────────────┬─────────────┬─────────────┐     │
│                    ▼             ▼             ▼             ▼             │     │
│           ┌──────────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │     │
│           │enter_update  │ │enter_book │ │enter_book │ │enter_book │      │     │
│           │   _flight   │ │ _car_rent │ │  _hotel   │ │_excursion │      │     │
│           └──────┬───────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘      │     │
│                  ▼              ▼             ▼             ▼              │     │
│           ┌──────────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │     │
│           │update_flight │ │book_car  │ │book_hotel│ │book_exc  │       │     │
│           │              │ │ _rental  │ │          │ │ ursion   │       │     │
│           └──────┬───────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘      │     │
│                  │              │             │             │              │     │
│    ┌─────────────┴──────────────┴─────────────┴─────────────┴─────────────┐│     │
│    │              tools_condition 路由 + interrupt_before                  ││     │
│    │  ┌─────────────────┐    ┌─────────────────┐                        ││     │
│    │  │  *_safe_tools   │    │*_sensitive_tools│ (需用户审批)            ││     │
│    │  │   (直接执行)     │    │   (执行前中断)   │                        ││     │
│    │  └─────────────────┘    └─────────────────┘                        ││     │
│    └──────────────────────────────────────────────────────────────────────┘│     │
│                                                                                     │
│   ┌─────────────────────────────────────────────────────────────────────────────┐   │
│   │                    MemorySaver (checkpointer)                              │   │
│   │  - thread_id 作为会话标识                                                   │   │
│   │  - 持久化 State (messages, user_info, dialog_state)                        │   │
│   └─────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────┬──────────────────────────────────────────┘
                                       │
            ┌──────────────────────────┼──────────────────────────┐
            │                          │                          │
            ▼                          ▼                          ▼
     ┌─────────────┐           ┌─────────────┐           ┌─────────────┐
     │   SQLite    │           │   Qdrant     │           │   Neo4j     │
     │  (事务数据)  │           │  (向量检索)   │           │  (知识图谱)  │
     │  订单/用户   │           │  FAQ/政策    │           │  退改签规则  │
     └─────────────┘           │  航班/酒店   │           └─────────────┘
                               └─────────────┘
```

### 2.2 数据流方向

```
用户输入 → API → MemorySaver恢复State → fetch_user_info → primary_assistant
                                                              │
                                              ┌───────────────┼───────────────┐
                                              ▼               ▼               ▼
                                          搜索/查询      委托专业助理      结束
                                              │               │
                                    ┌─────────┴─────────┐     │
                                    ▼                   ▼     ▼
                                Qdrant向量检索      SQLite查询   specialized assistant
                                                                        │
                                                            ┌───────────┴───────────┐
                                                            ▼                       ▼
                                                    safe_tools执行          sensitive_tools中断
                                                            │                       │
                                                            ▼              等待用户审批 (y/n)
                                                         返回结果              │
                                                                            ▼
                                                                     SQLite写操作
                                                                            │
                                                                            ▼
                                                                   返回结果给用户
```

---

## 3. 技术栈

| 类别 | 技术 | 用途 |
|------|------|------|
| **LLM框架** | LangChain + LangGraph | 智能体编排、状态机 |
| **语言模型** | OpenAI GPT-4 | 对话生成 |
| **向量数据库** | Qdrant | 语义搜索、FAQ/政策检索 |
| **关系数据库** | SQLite | 事务数据（订单、用户、预订） |
| **知识图谱** | Neo4j | 退改签规则、会员权益 |
| **API框架** | FastAPI | REST API + SSE流式输出 |
| **前端** | 原生HTML/CSS/JS | 无需构建的轻量前端 |
| **观察性** | LangSmith | 调用链追踪 |

---

## 4. 项目结构

```
multi-agent-rag-customer-support/
├── README.md                          # 主文档
├── PROJECT_DOCUMENTATION.md           # 本文档
├── pyproject.toml                     # 依赖管理
├── .env / .dev.env                    # 环境变量
│
├── vectorizer/                        # 向量生成服务（一次性初始化）
│   └── app/
│       ├── main.py                    # 向量化入口
│       ├── vectordb/
│       │   ├── vectordb.py            # Qdrant客户端封装
│       │   ├── chunkenizer.py         # 文本分块
│       │   └── utils.py
│       ├── embeddings/
│       │   └── embedding_generator.py # OpenAI embedding
│       └── core/
│           └── settings.py
│
└── customer_support_chat/             # 主聊天服务
    └── app/
        ├── api.py                     # FastAPI服务器（新增）
        ├── main.py                     # CLI入口
        ├── graph.py                    # LangGraph状态机定义
        ├── core/
        │   ├── state.py               # State类型定义
        │   ├── settings.py            # 配置管理
        │   └── logger.py               # 日志
        ├── templates/
        │   └── index.html             # Web前端
        └── services/
            ├── assistants/
            │   ├── assistant_base.py   # Agent基类 + CompleteOrEscalate
            │   ├── primary_assistant.py # 主控Agent
            │   ├── flight_booking_assistant.py
            │   ├── hotel_booking_assistant.py
            │   ├── car_rental_assistant.py
            │   └── excursion_assistant.py
            ├── tools/
            │   ├── flights.py          # 航班相关工具
            │   ├── hotels.py           # 酒店相关工具
            │   ├── cars.py             # 租车相关工具
            │   ├── excursions.py       # 短途旅行工具
            │   ├── lookup.py           # FAQ/Policy查询
            │   └── rules_lookup.py     # Neo4j规则查询（新增）
            ├── utils.py                # 辅助函数
            └── neo4j/                  # Neo4j模块（新增）
                ├── connection.py        # 连接管理
                └── rules_graph.py      # 规则知识图谱
```

---

## 5. 数据层

### 5.1 SQLite 事务数据库

**路径**: `customer_support_chat/data/travel2.sqlite`

**数据源**: [LangGraph Travel DB Benchmark](https://storage.googleapis.com/benchmarks-artifacts/travel-db)

**表结构**:

| 表名 | 说明 |
|------|------|
| `tickets` | 机票订单（ticket_no, passenger_id, book_ref） |
| `ticket_flights` | 机票-航班关联（ticket_no, flight_id, fare_conditions） |
| `flights` | 航班信息（flight_id, flight_no, 起飞/到达机场, 时刻, 状态） |
| `boarding_passes` | 登机牌（ticket_no, flight_id, seat_no） |
| `bookings` | 预订记录 |
| `hotels` | 酒店数据 |
| `car_rentals` | 租车数据 |
| `trip_recommendations` | 短途旅行/活动数据 |

### 5.2 Qdrant 向量数据库

**用途**: 语义搜索，存储可检索的知识库

**Collections**:

| Collection | 数据来源 | 用途 |
|------------|---------|------|
| `flights_collection` | SQLite flights表 | 航班信息语义检索 |
| `hotels_collection` | SQLite hotels表 | 酒店信息语义检索 |
| `car_rentals_collection` | SQLite car_rentals表 | 租车信息语义检索 |
| `excursions_collection` | SQLite trip_recommendations表 | 短途旅行语义检索 |
| `faq_collection` | Swiss FAQ Markdown | 公司政策/常见问题 |

**向量模型**: `text-embedding-ada-002` (OpenAI)
**向量维度**: 1536
**距离度量**: Cosine

### 5.3 Neo4j 知识图谱

**用途**: 结构化规则存储与推理

**节点类型**:

| 节点类型 | 示例 |
|---------|------|
| `TicketType` | ECO(经济舱), BUS(商务舱), FST(头等舱), DIS(特价票) |
| `MembershipLevel` | REG(普通), SIL(银卡), GLD(金卡), PLT(白金) |
| `FlightType` | DOM(国内), INT(国际), SPC(特价), CHT(包机) |
| `Rule` | 退票规则、改签规则 |
| `Condition` | 起飞前24小时外、起飞前4小时内 |
| `Benefit` | 退票费减免25%、免费改签 |
| `Exception` | 航班取消、延误超2小时 |

**关系类型**:

| 关系 | 说明 |
|------|------|
| `(TicketType)-[:HAS_REFUND_RULE]->(Rule)` | 票种有某退票规则 |
| `(TicketType)-[:HAS_RESCHEDULE_RULE]->(Rule)` | 票种有某改签规则 |
| `(Rule)-[:APPLIES_IF]->(Condition)` | 规则适用条件 |
| `(MembershipLevel)-[:ENABLES]->(Benefit)` | 会员享有某权益 |
| `(Exception)-[:TRIGGERS]->(Rule)` | 例外触发某规则 |

---

## 6. 多智能体设计

### 6.1 智能体概述

| 智能体 | 角色 | 工具范围 |
|--------|------|---------|
| `primary_assistant` | 主控/入口 | 搜索 + 委托 |
| `update_flight` | 航班改签/退票 | 航班工具 |
| `book_hotel` | 酒店预订 | 酒店工具 |
| `book_car_rental` | 租车预订 | 租车工具 |
| `book_excursion` | 短途旅行 | 短途旅行工具 |

### 6.2 委托模式 (Chain of Responsibility)

```
用户请求
    │
    ▼
┌─────────────────────┐
│  primary_assistant  │ ◀── 系统入口
│  (只做搜索+委托)     │
└──────────┬──────────┘
           │
           │ 识别到需要专业化服务
           ▼
┌──────────────────────────────────────────┐
│        4个专业助理 (Specialized)          │
│  ┌────────────────────────────────────┐  │
│  │ update_flight    → 航班改签/退票    │  │
│  │ book_hotel       → 酒店预订        │  │
│  │ book_car_rental  → 租车预订        │  │
│  │ book_excursion   → 短途旅行        │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
           │
           │ 任务完成或需要更高级别帮助
           ▼
┌─────────────────────┐
│  CompleteOrEscalate │ ◀── 归还控制权
└─────────────────────┘
```

### 6.3 主控Agent Prompt

```python
primary_assistant_prompt = ChatPromptTemplate.from_messages([
    ("system", """
        You are a helpful customer support assistant for Swiss Airlines.
        Your primary role is to search for flight information and company
        policies to answer customer queries.

        If a customer requests to update or cancel a flight, book a car
        rental, book a hotel, or get trip recommendations, delegate the
        task to the appropriate specialized assistant by invoking the
        corresponding tool.

        You are not able to make these types of changes yourself.
        Only the specialized assistants are given permission to do this.

        The user is not aware of the different specialized assistants,
        so do not mention them; just quietly delegate through function calls.

        Provide detailed information to the customer, and always double-check
        the database before concluding that information is unavailable.

        Current user flight information:
        <Flights>{user_info}</Flights>

        Current time: {time}.
    """),
    ("placeholder", "{messages}"),
])
```

### 6.4 专业助理Prompt模式

```python
specialized_prompt = ChatPromptTemplate.from_messages([
    ("system", """
        You are a specialized assistant for handling [业务范围].
        The primary assistant delegates work to you whenever the user needs
        help with [具体任务].

        Confirm the details with the customer before executing write operations.
        Remember that a booking isn't completed until after the relevant tool
        has successfully been used.

        If you need more information or the customer changes their mind,
        escalate the task back to the main assistant.

        Current user flight information:
        <Flights>{user_info}</Flights>

        Current time: {time}.
    """),
    ("placeholder", "{messages}"),
])
```

### 6.5 CompleteOrEscalate 机制

```python
class CompleteOrEscalate(BaseModel):
    """标记当前任务完成或升级控制权"""
    cancel: bool = True      # 是否取消任务
    reason: str             # 原因说明
```

**使用场景**:
- 专业助理完成任务后，交回控制权
- 专业助理遇到不属于自己的任务时（如用户问天气）
- 专业助理无法继续时

---

## 7. 完整请求链路

### 7.1 请求生命周期

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          阶段1: 请求初始化                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. 用户发送消息到 /chat/stream                                               │
│     POST /chat/stream                                                        │
│     Body: {                                                                  │
│       "message": "我想改签到明天的航班",                                       │
│       "passenger_id": "5102 899977",                                        │
│       "thread_id": null  // 首次为null，后续传入                             │
│     }                                                                        │
│                                                                              │
│  2. API生成或使用thread_id                                                   │
│     thread_id = request.thread_id or str(uuid.uuid4())                       │
│                                                                              │
│  3. 构建config配置                                                           │
│     config = {                                                               │
│       "configurable": {                                                       │
│         "passenger_id": "5102 899977",                                       │
│         "thread_id": "abc-123-def-456"                                       │
│       }                                                                      │
│     }                                                                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          阶段2: 图执行                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  4. 调用 graph.stream()                                                      │
│     events = multi_agentic_graph.stream(                                      │
│       {"messages": [("user", "我想改签到明天的航班")]},                       │
│       config,                                                                │
│       stream_mode="values"                                                   │
│     )                                                                        │
│                                                                              │
│  5. MemorySaver恢复State                                                     │
│     - 根据thread_id从内存存储中恢复                                            │
│     - State = {messages: [...], user_info: "...", dialog_state: [...]}       │
│     - 新消息追加到messages                                                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     阶段3: 节点执行顺序                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 节点1: fetch_user_info                                              │    │
│  │                                                                      │    │
│  │ 输入: State (无user_info)                                            │    │
│  │ 处理:                                                                │    │
│  │   flight_info = fetch_user_flight_information.invoke(                 │    │
│  │     input={},                                                        │    │
│  │     config={"configurable": {"passenger_id": "5102 899977"}}         │    │
│  │   )                                                                  │    │
│  │   user_info_str = flight_info_to_string(flight_info)                 │    │
│  │                                                                      │    │
│  │ 输出: {"user_info": "User current booked flight(s) details:\n..."}  │    │
│  │                                                                      │    │
│  │ 数据源: SQLite tickets, ticket_flights, flights表                    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 节点2: primary_assistant                                             │    │
│  │                                                                      │    │
│  │ 输入:                                                                │    │
│  │   - State.messages (历史+当前用户消息)                                │    │
│  │   - State.user_info (刚获取的航班信息)                               │    │
│  │   - State.time (当前时间)                                           │    │
│  │                                                                      │    │
│  │ Prompt填充后:                                                        │    │
│  │   "You are a helpful customer support assistant..."                  │    │
│  │   "Current user flight information:"                                │    │
│  │   "<Flights>" + user_info + "</Flights>"                            │    │
│  │   "Current time: 2026-04-12 14:30:00."                              │    │
│  │   "{messages}" (对话历史)                                            │    │
│  │                                                                      │    │
│  │ LLM推理结果:                                                         │    │
│  │   - ToolCalls: [{"name": "ToFlightBookingAssistant",                 │    │
│  │                  "args": {"request": "用户想改签，请确认详情"}}]     │    │
│  │                                                                      │    │
│  │ 输出: {"messages": AIMessage(tool_calls=[...])}                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 节点3: enter_update_flight (入口节点)                               │    │
│  │                                                                      │    │
│  │ 作用: 创建委托消息，切换dialog_state                                  │    │
│  │                                                                      │    │
│  │ 输出: {"messages": [ToolMessage(content="The assistant is now the   │    │
│  │               Flight Updates & Booking Assistant...")],               │    │
│  │        "dialog_state": "update_flight"}                              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 节点4: update_flight (FlightBookingAssistant)                       │    │
│  │                                                                      │    │
│  │ 输入:                                                                │    │
│  │   - State.messages (含委托ToolMessage)                               │    │
│  │   - State.user_info                                                  │    │
│  │   - State.dialog_state = "update_flight"                            │    │
│  │                                                                      │    │
│  │ Prompt:                                                              │    │
│  │   "You are a specialized assistant for handling flight updates..."    │    │
│  │   "Current user flight information: <Flights>{user_info}</Flights>"  │    │
│  │                                                                      │    │
│  │ LLM推理: 识别用户意图 → search_flights 查询可选航班                   │    │
│  │                                                                      │    │
│  │ 输出: {"messages": AIMessage(content="找到以下航班可供选择...")}      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 路由: route_update_flight()                                         │    │
│  │                                                                      │    │
│  │ 判断逻辑:                                                            │    │
│  │   1. tools_condition(state) → 是否需要工具?                           │    │
│  │   2. 检查tool_calls[0].name是否在safe_tools列表中?                   │    │
│  │   3. 是 → 路由到 update_flight_safe_tools                           │    │
│  │   4. 否 → 路由到 update_flight_sensitive_tools                      │    │
│  │   5. tool是CompleteOrEscalate → 路由回primary_assistant             │    │
│  │                                                                      │    │
│  │ 本例: search_flights是safe → update_flight_safe_tools               │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 节点5: update_flight_safe_tools                                     │    │
│  │                                                                      │    │
│  │ 执行: search_flights.invoke({"query": "明天航班", "limit": 2})       │    │
│  │                                                                      │    │
│  │ 内部调用Qdrant:                                                      │    │
│  │   1. 生成查询向量 (text-embedding-ada-002)                           │    │
│  │   2. Qdrant.similarity_search(collection, query_vector, limit=2)     │    │
│  │   3. 返回Top-K相关文档                                               │    │
│  │                                                                      │    │
│  │ 输出: ToolMessage(content="Flight FE123 available...")              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 返回 update_flight 节点                                              │    │
│  │                                                                      │    │
│  │ LLM整合工具返回结果，生成自然语言回复                                 │    │
│  │                                                                      │    │
│  │ 用户选择航班后，LLM调用 update_ticket_to_new_flight                  │    │
│  │                                                                      │    │
│  │ 判断: update_ticket_to_new_flight 是 sensitive                      │    │
│  │ → 路由到 update_flight_sensitive_tools                              │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ 节点6: update_flight_sensitive_tools (中断点)                        │    │
│  │                                                                      │    │
│  │ 触发 interrupt_before                                                │    │
│  │ → 执行暂停，等待用户审批                                              │    │
│  │                                                                      │    │
│  │ API返回给前端:                                                       │    │
│  │   {"event": "interrupt", "data": {"requires_approval": true}}       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          阶段4: 用户审批                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  7. 前端弹出确认对话框                                                       │
│     "确认将机票改签到航班 FE123 吗？"                                          │
│                                                                              │
│  8. 用户点击"确认"或"取消"                                                   │
│                                                                              │
│  9. 前端调用 /chat/approve                                                  │
│     POST /chat/approve                                                       │
│     Body: {                                                                  │
│       "thread_id": "abc-123-def-456",                                        │
│       "approved": true,     // 或 false                                     │
│       "feedback": ""         // 用户反馈（拒绝时填写）                        │
│     }                                                                        │
│                                                                              │
│  10. API处理:                                                               │
│      if approved:                                                            │
│        result = multi_agentic_graph.invoke(None, config)                      │
│        // 继续执行pending的工具调用                                           │
│      else:                                                                   │
│        result = multi_agentic_graph.invoke({                                 │
│          "messages": [ToolMessage(content="API call denied by user...")]     │
│        }, config)                                                            │
│        // 向LLM传达拒绝原因，让其重新推理                                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          阶段5: 结果返回                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  11. 工具执行结果返回给Assistant                                             │
│      ToolMessage(content="Ticket successfully updated to flight FE123")       │
│                                                                              │
│  12. Assistant生成最终回复                                                   │
│      "您的机票已成功改签至航班 FE123，明天上午10点起飞..."                      │
│                                                                              │
│  13. 消息追加到State                                                        │
│      messages += [user_msg, ai_msg, tool_msg...]                            │
│                                                                              │
│  14. MemorySaver持久化State                                                │
│      thread_id: "abc-123-def-456" → 存储完整State                           │
│                                                                              │
│  15. SSE流式返回前端                                                        │
│      event: message → data: {"type": "AIMessage", "content": "您的机票..."}  │
│      event: done → data: {"thread_id": "abc-123-def-456"}                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 8. 上下文管理机制

### 8.1 上下文组成

| 上下文字段 | 来源 | 更新时机 | 内容 |
|-----------|------|---------|------|
| `messages` | State + 用户输入 | 每次对话 | 完整对话历史 |
| `user_info` | SQLite查询 | 每次请求开始 | 用户航班信息 |
| `time` | datetime.now() | 每次请求 | 当前时间 |
| `dialog_state` | 各节点设置 | 委托/完成时 | 当前所在助理 |

### 8.2 上下文注入点

```
┌─────────────────────────────────────────────────────────────┐
│                   Prompt 模板中的上下文注入                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  primary_assistant_prompt = ChatPromptTemplate.from_messages│
│  ([                                                              │
│      ("system", """                                            │
│          ...                                                   │
│          Current user flight information:                     │
│          <Flights>{user_info}</Flights>  ←─── State.user_info │
│          Current time: {time}.           ←─── datetime.now()  │
│      """),                                                     │
│      ("placeholder", "{messages}"),  ←─── State.messages     │
│  ])                                                             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 8.3 上下文补全流程

```
用户输入: "我想改签"
    │
    ▼
┌─────────────────────────┐
│ messages = [            │
│   user("我想改签")       │
│ ]                       │
│ (之前的历史消息由        │
│  MemorySaver恢复)        │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ fetch_user_info 节点     │
│ → 查询SQLite             │
│ → user_info = "Ticket 1:│
│   Flight FE123, NYC→LA"  │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│ primary_assistant       │
│                         │
│ Prompt填充:              │
│ {user_info} = 航班信息   │
│ {time} = 当前时间        │
│ {messages} = 历史+当前  │
│                         │
│ LLM看到完整上下文:       │
│ - 用户有1张机票 FE123    │
│ - 出发地NYC，目的地LA    │
│ - 用户想改签             │
└──────────┬──────────────┘
           │
           ▼
    正确理解用户意图
```

### 8.4 上下文限制与问题

| 问题 | 说明 | 影响 |
|------|------|------|
| **user_info只查一次** | 在fetch_user_info节点获取，之后不更新 | 改签后用户信息不会自动刷新 |
| **消息无限增长** | messages只有追加，没有压缩/摘要 | 对话越长，上下文越多，token消耗越大 |
| **无历史语义检索** | 历史消息只做堆叠，不做语义召回 | 无法主动关联多轮前的相关信息 |
| **passenger_id固定** | 配置中写死，无登录态 | 无法支持多用户 |

---

## 9. 记忆与状态持久化

### 9.1 MemorySaver机制

```python
# graph.py
from langgraph.checkpoint.memory import MemorySaver

# 创建内存检查点
memory = MemorySaver()

# 编译图时启用
multi_agentic_graph = builder.compile(
    checkpointer=memory,
    interrupt_before=sensitive_nodes,
)
```

### 9.2 状态恢复流程

```
首次请求:
  thread_id = "new-uuid"
  MemorySaver无数据 → State = {messages: [], user_info: "", dialog_state: []}
  │
  ▼
  graph.stream({"messages": [user_msg]}, config)
  │
  ▼
  响应返回，State持久化
  MemorySaver["new-uuid"] = State

第二次请求 (同一thread_id):
  thread_id = "new-uuid"
  │
  ▼
  MemorySaver["new-uuid"] → 恢复State
  │
  ▼
  graph.stream({"messages": [user_msg2]}, config)
  // State.messages已包含历史 [user_msg, ai_msg, tool_msg, user_msg2]
```

### 9.3 状态结构

```python
class State(TypedDict):
    # 消息历史，自动通过add_messages累加
    messages: Annotated[list[AnyMessage], add_messages]

    # 用户航班信息，由fetch_user_info节点填充
    user_info: str

    # 对话状态栈，用于追踪当前所在助理
    dialog_state: Annotated[
        list[
            Literal[
                "assistant",           # 主控
                "update_flight",       # 航班改签
                "book_car_rental",     # 租车
                "book_hotel",          # 酒店
                "book_excursion",      # 短途旅行
            ]
        ],
        update_dialog_stack,  # push/pop操作
    ]
```

### 9.4 dialog_state管理

```python
def update_dialog_stack(left: list[str], right: Optional[str]) -> list[str]:
    """Push or pop the dialog state stack."""
    if right is None:
        return left                           # 无操作
    if right == "pop":
        return left[:-1]                     # 弹出
    return left + [right]                   # 压入
```

**使用场景**:
- 进入专业助理时 → `dialog_state + [新状态]`
- CompleteOrEscalate时 → `dialog_state + ["assistant"]`

### 9.5 记忆的局限性

| 特性 | 当前实现 | 问题 |
|------|---------|------|
| 存储位置 | 内存 (MemorySaver) | **服务重启后丢失** |
| 会话隔离 | thread_id | 正确 |
| 并发安全 | 无 | 同一thread_id并发请求可能冲突 |
| 持久化 | 无自动持久化 | 需切换到PostgreSQL/Redis |

---

## 10. 工具系统详解

### 10.1 工具分类总表

| 工具名 | 类型 | 数据源 | 说明 |
|--------|------|--------|------|
| `search_flights` | safe | Qdrant | 语义搜索航班 |
| `search_hotels` | safe | Qdrant | 语义搜索酒店 |
| `search_car_rentals` | safe | Qdrant | 语义搜索租车 |
| `search_trip_recommendations` | safe | Qdrant | 语义搜索短途旅行 |
| `search_faq` | safe | Qdrant | 语义搜索FAQ |
| `lookup_policy` | safe | Qdrant | 查询公司政策 |
| `fetch_user_flight_information` | safe | SQLite | 获取用户航班 |
| `update_ticket_to_new_flight` | **sensitive** | SQLite | 改签（需审批） |
| `cancel_ticket` | **sensitive** | SQLite | 退票（需审批） |
| `book_hotel` | **sensitive** | SQLite | 订酒店（需审批） |
| `update_hotel` | **sensitive** | SQLite | 改酒店（需审批） |
| `cancel_hotel` | **sensitive** | SQLite | 取消酒店（需审批） |
| `book_car_rental` | **sensitive** | SQLite | 订租车（需审批） |
| `update_car_rental` | **sensitive** | SQLite | 改租车（需审批） |
| `cancel_car_rental` | **sensitive** | SQLite | 取消租车（需审批） |
| `book_excursion` | **sensitive** | SQLite | 订短途旅行（需审批） |
| `update_excursion` | **sensitive** | SQLite | 改短途旅行（需审批） |
| `cancel_excursion` | **sensitive** | SQLite | 取消短途旅行（需审批） |
| `lookup_refund_rules` | safe | Neo4j | 查询退票规则 |
| `lookup_reschedule_rules` | safe | Neo4j | 查询改签规则 |
| `lookup_membership_benefits` | safe | Neo4j | 查询会员权益 |
| `check_flight_exception` | safe | Neo4j | 检查例外情况 |

### 10.2 工具定义示例

```python
# flights.py
@tool
def update_ticket_to_new_flight(
    ticket_no: str,
    new_flight_id: int,
    *, config: RunnableConfig
) -> str:
    """Update the user's ticket to a new valid flight."""
    configuration = config.get("configurable", {})
    passenger_id = configuration.get("passenger_id", None)

    # 1. 验证机票属于该乘客
    conn = sqlite3.connect(db)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM tickets WHERE ticket_no = ? AND passenger_id = ?",
        (ticket_no, passenger_id),
    )
    ticket = cursor.fetchone()
    if not ticket:
        return f"Ticket {ticket_no} not found for passenger {passenger_id}."

    # 2. 执行改签
    cursor.execute(
        "UPDATE ticket_flights SET flight_id = ? WHERE ticket_no = ?",
        (new_flight_id, ticket_no),
    )
    conn.commit()
    conn.close()

    return f"Ticket {ticket_no} successfully updated to flight {new_flight_id}."
```

### 10.3 Qdrant语义搜索流程

```python
# flights.py
flights_vectordb = VectorDB(table_name="flights", collection_name="flights_collection")

@tool
def search_flights(query: str, limit: int = 2) -> List[Dict]:
    # 1. 向量化查询
    search_results = flights_vectordb.search(query, limit=limit)

    # 2. 解析结果
    flights = []
    for result in search_results:
        payload = result.payload
        flights.append({
            "flight_id": payload["flight_id"],
            "flight_no": payload["flight_no"],
            "departure_airport": payload["departure_airport"],
            ...
        })
    return flights
```

**VectorDB.search内部**:
```python
# vectordb.py
def search(self, query, limit=2, with_payload=True):
    # 1. 用OpenAI生成查询向量
    query_vector = generate_embedding(query)

    # 2. Qdrant余弦相似度搜索
    search_result = self.client.search(
        collection_name=self.collection_name,
        query_vector=query_vector,
        limit=limit,
        with_payload=with_payload
    )

    return search_result  # 返回 ScoredPoint 列表
```

### 10.4 Safe vs Sensitive 工具

```
┌────────────────────────────────────────────────────────────┐
│                    Safe Tools (直接执行)                   │
├────────────────────────────────────────────────────────────┤
│  - search_flights / hotels / cars / excursions           │
│  - search_faq / lookup_policy                             │
│  - fetch_user_flight_information                         │
│                                                            │
│  流程:                                                     │
│  LLM调用 → tool_node执行 → 返回ToolMessage → 继续         │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│               Sensitive Tools (执行前中断)                  │
├────────────────────────────────────────────────────────────┤
│  - update_ticket_to_new_flight (改签)                     │
│  - cancel_ticket (退票)                                   │
│  - book_*/update_*/cancel_* (所有预订类操作)             │
│                                                            │
│  流程:                                                     │
│  LLM调用 → interrupt_before中断 → 等待用户审批            │
│           ↓                                                │
│    用户批准 → 执行 → 返回ToolMessage                       │
│    用户拒绝 → 返回拒绝原因 → LLM重新推理                   │
└────────────────────────────────────────────────────────────┘
```

### 10.5 委托工具 (Transfer Tools)

```python
# primary_assistant.py
class ToFlightBookingAssistant(BaseModel):
    """Transfers work to a specialized assistant to handle flight updates."""
    request: str = Field(description="Follow-up questions for the flight assistant.")

class ToBookCarRental(BaseModel):
    """Transfers work to a specialized assistant to handle car rental."""
    location: str
    start_date: str
    end_date: str
    request: str
```

这些是**BaseModel类型**，不是@tool，但LLM通过bind_tools绑定后可以调用，实现委托。

---

## 11. 图架构与路由逻辑

### 11.1 节点定义 (graph.py)

```python
builder = StateGraph(State)

# 入口节点
builder.add_node("fetch_user_info", user_info)

# 专业助理节点
builder.add_node("enter_update_flight", create_entry_node("Flight Updates...", "update_flight"))
builder.add_node("update_flight", flight_booking_assistant)
builder.add_node("enter_book_car_rental", create_entry_node("Car Rental...", "book_car_rental"))
builder.add_node("book_car_rental", car_rental_assistant)
builder.add_node("enter_book_hotel", create_entry_node("Hotel...", "book_hotel"))
builder.add_node("book_hotel", hotel_booking_assistant)
builder.add_node("enter_book_excursion", create_entry_node("Excursion...", "book_excursion"))
builder.add_node("book_excursion", excursion_assistant)

# 主控节点
builder.add_node("primary_assistant", primary_assistant)

# 工具节点
builder.add_node("update_flight_safe_tools", create_tool_node_with_fallback(update_flight_safe_tools))
builder.add_node("update_flight_sensitive_tools", create_tool_node_with_fallback(update_flight_sensitive_tools))
# ... 同理其他3个助理
```

### 11.2 边定义

```python
# 基本边 (顺序执行)
builder.add_edge(START, "fetch_user_info")
builder.add_edge("fetch_user_info", "primary_assistant")

# 专业助理入口
builder.add_edge("enter_update_flight", "update_flight")
builder.add_edge("enter_book_car_rental", "book_car_rental")
builder.add_edge("enter_book_hotel", "book_hotel")
builder.add_edge("enter_book_excursion", "book_excursion")

# 工具节点返回
builder.add_edge("update_flight_safe_tools", "update_flight")
builder.add_edge("update_flight_sensitive_tools", "update_flight")
# ... 同理其他助理
```

### 11.3 条件路由

```python
# primary_assistant的路由
def route_primary_assistant(state: State) -> Literal[...]:
    route = tools_condition(state)  # LangGraph内置判断

    if route == END:
        return END

    tool_calls = state["messages"][-1].tool_calls
    if tool_calls:
        tool_name = tool_calls[0]["name"]
        if tool_name == "ToFlightBookingAssistant":
            return "enter_update_flight"
        elif tool_name == "ToBookCarRental":
            return "enter_book_car_rental"
        elif tool_name == "ToHotelBookingAssistant":
            return "enter_book_hotel"
        elif tool_name == "ToBookExcursion":
            return "enter_book_excursion"
        else:
            return "primary_assistant_tools"  # 未知工具 → 主控工具节点

    return "primary_assistant"  # 无工具调用 → 继续主控

builder.add_conditional_edges(
    "primary_assistant",
    route_primary_assistant,
    {
        "enter_update_flight": "enter_update_flight",
        "enter_book_car_rental": "enter_book_car_rental",
        "enter_book_hotel": "enter_book_hotel",
        "enter_book_excursion": "enter_book_excursion",
        "primary_assistant_tools": "primary_assistant_tools",
        END: END,
    },
)

# 专业助理的路由
def route_update_flight(state: State) -> Literal[...]:
    route = tools_condition(state)
    if route == END:
        return END

    tool_calls = state["messages"][-1].tool_calls
    did_cancel = any(tc["name"] == "CompleteOrEscalate" for tc in tool_calls)
    if did_cancel:
        return "primary_assistant"  # 交回控制权

    safe_toolnames = [t.name for t in update_flight_safe_tools]
    if all(tc["name"] in safe_toolnames for tc in tool_calls):
        return "update_flight_safe_tools"

    return "update_flight_sensitive_tools"  # 敏感工具 → 中断

builder.add_conditional_edges("update_flight", route_update_flight)
```

### 11.4 完整路由图

```
START
  │
  ▼
fetch_user_info
  │
  ▼
primary_assistant ──────────────────────────────────────────────────┐
  │                                                                  │
  │ tools_condition路由:                                             │
  │   ├─ END (无工具调用) ─────────────────────────────────────── END │
  │   │                                                              │
  │   ├─ ToFlightBookingAssistant ──→ enter_update_flight          │
  │   │                                 │                            │
  │   ├─ ToBookCarRental ──────────────→ enter_book_car_rental      │
  │   │                                 │                            │
  │   ├─ ToHotelBookingAssistant ──────→ enter_book_hotel           │
  │   │                                 │                            │
  │   ├─ ToBookExcursion ──────────────→ enter_book_excursion       │
  │   │                                 │                            │
  │   └─ 其他工具 ──────────────────────→ primary_assistant_tools     │
  │                                       │                            │
  │                                       ▼                            │
  │                              primary_assistant                     │
  │                                                                  │
  ├─ enter_update_flight ──→ update_flight ──route─→ ┐                │
  │                                                  │                │
  ├─ enter_book_car_rental ──→ book_car_rental ─route─→ ┤             │
  │                                                  │                │
  ├─ enter_book_hotel ──→ book_hotel ───────route─→ ┤              │
  │                                                  │                │
  └─ enter_book_excursion ──→ book_excursion ───route─→ ┘            │
                                                                  │
  route判断:                                                       │
    ├─ CompleteOrEscalate ────────────────────────────→ primary_assistant
    │                                                           │
    ├─ safe_tools ────────────────────────────────────→ *_safe_tools
    │                                                           │
    └─ sensitive_tools ──────────────────────────────────→ *_sensitive_tools
                                                                    │
                                                                    ▼
                                                       interrupt_before = True
                                                       (暂停，等待用户审批)
```

### 11.5 中断点配置

```python
# 定义哪些节点需要中断
interrupt_nodes = [
    "update_flight_sensitive_tools",
    "book_car_rental_sensitive_tools",
    "book_hotel_sensitive_tools",
    "book_excursion_sensitive_tools",
]

# 编译时设置
multi_agentic_graph = builder.compile(
    checkpointer=memory,
    interrupt_before=interrupt_nodes,  # 执行前中断
)
```

---

## 12. 流式输出实现

### 12.1 SSE流式API

```python
# api.py
@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """SSE流式聊天接口"""

    async def event_generator():
        printed_message_ids = set()

        # 1. 流式执行图
        events = multi_agentic_graph.stream(
            {"messages": [("user", request.message)]},
            config,
            stream_mode="values"
        )

        # 2. 逐事件推送
        for event in events:
            messages = event.get("messages", [])
            for message in messages:
                if message.id not in printed_message_ids:
                    yield f"event: message\ndata: {json.dumps({
                        "type": type(message).__name__,
                        "content": message.content,
                        "id": message.id
                    })}\n\n"
                    printed_message_ids.add(message.id)

        # 3. 检查中断
        snapshot = multi_agentic_graph.get_state(config)
        if snapshot.next:
            yield f"event: interrupt\ndata: {json.dumps({'requires_approval': True})}\n\n"

        # 4. 结束
        yield f"event: done\ndata: {json.dumps({'thread_id': thread_id})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )
```

### 12.2 SSE事件类型

| 事件 | 说明 | 前端处理 |
|------|------|---------|
| `message` | 新消息 | 追加到聊天框 |
| `interrupt` | 敏感操作需审批 | 弹出确认对话框 |
| `done` | 结束 | 完成当前对话 |
| `error` | 错误 | 显示错误信息 |

### 12.3 前端SSE处理

```javascript
// index.html
const response = await fetch('/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, thread_id })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value);
    for (const line of chunk.split('\n')) {
        if (!line.startsWith('data:')) continue;
        const data = JSON.parse(line.slice(5));

        if (data.type === 'AIMessage') {
            // 流式显示AI回复
            assistantMsg.textContent += data.content;
        } else if (data.type === 'ToolMessage') {
            // 显示工具调用结果
            addMessage(data.content, 'tool');
        } else if (data.event === 'interrupt') {
            // 显示审批对话框
            approvalModal.classList.add('active');
        }
    }
}
```

---

## 13. Neo4j 知识图谱

### 13.1 初始化

```bash
# 启动Neo4j
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:5.25.0

# 初始化知识图谱
python -c "from customer_support_chat.app.services.neo4j import initialize_knowledge_graph; initialize_knowledge_graph()"
```

### 13.2 知识图谱内容

**票种节点**:
```cypher
MERGE (t:TicketType {name: 'Economy', code: 'ECO'})
MERGE (t:TicketType {name: 'Business', code: 'BUS'})
MERGE (t:TicketType {name: 'FirstClass', code: 'FST'})
MERGE (t:TicketType {name: 'Discount', code: 'DIS'})
```

**退票规则**:
```cypher
// 经济舱 - 起飞前24小时外免费退票
MATCH (t:TicketType {code: 'ECO'})
MERGE (t)-[:HAS_REFUND_RULE]->(r:Rule {
    id: 'REFUND_ECO_24H',
    type: 'refund',
    refundable: true,
    penalty_rate: 0.0
})
MERGE (r)-[:APPLIES_IF]->(c:Condition {
    id: 'TIME_BEFORE_24H',
    name: '起飞前24小时外'
})
```

**会员权益**:
```cypher
// 金卡会员: 退票费减免25%，改签免费
MATCH (m:MembershipLevel {code: 'GLD'})
MERGE (m)-[:ENABLES]->(b:Benefit {
    id: 'BEN_GLD_REFUND',
    type: 'refund_discount',
    discount_rate: 0.25
})
```

### 13.3 规则查询示例

```python
# 查询经济舱退票规则
lookup_refund_rules("ECO")

# 返回:
# === 退票规则 (ECO) ===
# 规则: 经济舱24小时外退票规则
#   说明: 经济舱机票，起飞前24小时外申请退票，免收退票费
#   退票: 可退票
#   手续费: 免费
#   条件: 起飞前24小时外
```

---

## 14. API 接口说明

### 14.1 端点总览

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 聊天前端HTML |
| `/chat/stream` | POST | 流式聊天 (SSE) |
| `/chat/approve` | POST | 审批敏感操作 |
| `/chat/history/{thread_id}` | GET | 获取会话历史 |

### 14.2 POST /chat/stream

**请求**:
```json
{
    "message": "我想改签到明天的航班",
    "passenger_id": "5102 899977",
    "thread_id": null
}
```

**响应**: SSE流
```
event: message
data: {"type": "AIMessage", "content": "好的，让我查一下您现在的航班信息...", "id": "msg-001"}

event: message
data: {"type": "ToolMessage", "content": "Ticket 1: Flight FE123...", "id": "msg-002"}

event: interrupt
data: {"requires_approval": true}

event: done
data: {"thread_id": "abc-123-def-456"}
```

### 14.3 POST /chat/approve

**请求**:
```json
{
    "thread_id": "abc-123-def-456",
    "approved": true,
    "feedback": ""
}
```

**响应**:
```json
{
    "status": "approved",
    "messages": [
        {"type": "AIMessage", "content": "改签成功！"},
        {"type": "ToolMessage", "content": "Ticket updated."}
    ]
}
```

---

## 15. 启动与配置

### 15.1 环境变量

```bash
# .env 文件
OPENAI_API_KEY="sk-..."
LANGCHAIN_API_KEY="langchain-..."  # 可选

NEO4J_URI="bolt://localhost:7687"
NEO4J_USER="neo4j"
NEO4J_PASSWORD="password"

QDRANT_URL="http://localhost:6333"
SQLITE_DB_PATH="./customer_support_chat/data/travel2.sqlite"
```

### 15.2 启动顺序

```bash
# 1. 安装依赖
poetry install
poetry add neo4j fastapi uvicorn sse-starlette

# 2. 生成向量索引 (一次性)
poetry run python vectorizer/app/main.py

# 3. 启动Qdrant
docker compose up qdrant -d

# 4. (可选) 初始化Neo4j知识图谱
python -c "from customer_support_chat.app.services.neo4j import initialize_knowledge_graph; initialize_knowledge_graph()"

# 5. 启动聊天服务
poetry run python -m uvicorn customer_support_chat.app.api:app --reload --port 8000
```

### 15.3 访问

- Web前端: http://localhost:8000
- Qdrant Dashboard: http://localhost:6333/dashboard

---

## 附录A: 完整State流程示例

```
初始State:
{
    "messages": [],
    "user_info": "",
    "dialog_state": []
}

fetch_user_info后:
{
    "messages": [],
    "user_info": "User current booked flight(s) details:\nTicket [1]:\nTicket Number: 0005435210023\n...",
    "dialog_state": []
}

用户输入"我想改签"后:
{
    "messages": [HumanMessage("我想改签")],
    "user_info": "...",
    "dialog_state": []
}

primary_assistant调用ToFlightBookingAssistant后:
{
    "messages": [
        HumanMessage("我想改签"),
        AIMessage(content="...", tool_calls=[{"name": "ToFlightBookingAssistant", ...}])
    ],
    "user_info": "...",
    "dialog_state": ["assistant"]  // 主控
}

enter_update_flight后:
{
    "messages": [..., ToolMessage("The assistant is now the Flight Updates...")],
    "user_info": "...",
    "dialog_state": ["assistant", "update_flight"]  // 切换到航班助理
}

search_flights执行后:
{
    "messages": [..., ToolMessage("Flight FE123 available...")],
    "user_info": "...",
    "dialog_state": ["assistant", "update_flight"]
}

update_ticket_to_new_flight触发中断:
→ 对话暂停，等待用户审批
```

---

## 附录B: Token消耗说明

| 对话轮次 | messages长度 | 预估Token | 说明 |
|---------|-------------|----------|------|
| 1 | 4 | ~500 | 初始加载user_info |
| 5 | 20 | ~2500 | 5轮对话 |
| 10 | 40 | ~5000 | 10轮对话 |
| 20 | 80 | ~10000 | 20轮对话 |

**建议**: 当对话超过10轮时，应考虑实现消息摘要或历史检索机制。

---

文档版本: v1.0
最后更新: 2026-04-12
