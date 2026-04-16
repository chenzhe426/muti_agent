# Multi-Agent RAG Customer Support System

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.12+-green.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2.19-orange.svg)](https://langchain-ai.github.io/langgraph/)

## 项目简介

这是一个基于 **LangGraph + LangChain** 构建的智能客服系统，提供多轮对话式支持。系统使用多代理架构处理航班预订、酒店、租车、游览等业务。

**演示视频**: [YouTube 演示](https://youtu.be/mPBYvSJuN8Q?si=TGmtyp-XK5O5xQV7)

![系统架构](./graphs/multi-agent-rag-system-graph.png)

---

## 核心技术栈

| 类别 | 技术 |
|------|------|
| **编排框架** | LangGraph 0.2.19 |
| **LLM** | OpenAI GPT-4 / vLLM (本地) / Ollama |
| **向量数据库** | Qdrant |
| **状态存储** | Redis / MemorySaver |
| **图数据库** | Neo4j |
| **Web 框架** | FastAPI + asyncio + SSE |
| **容器编排** | Docker Compose |

---

## 系统架构

### 多代理架构

```
用户输入
    │
    ▼
fetch_user_info (获取用户元数据)
    │
    ▼
Primary Assistant (路由 + 记忆管理)
    │
    ├── 检测工具调用 ──→ primary_assistant_tools
    │
    └── 路由判断 ──┬─→ enter_update_flight ──→ Flight Booking
                   ├─→ enter_book_car_rental ──→ Car Rental
                   ├─→ enter_book_hotel ──→ Hotel Booking
                   └─→ enter_book_excursion ──→ Excursion

专用助手完成后 ──→ CompleteOrEscalate ──→ 返回 Primary Assistant
```

### 状态分区机制

- **thread_id**: 状态分区的唯一 key，不同 thread_id 状态完全隔离
- **passenger_id**: 业务标识，用于用户画像查询，不参与状态分区

### 敏感操作中断

敏感操作（预订/取消）会触发 interrupt，等待用户审批：

```
敏感工具调用 → interrupt_before → 用户审批 (/chat/approve) → 继续执行
```

---

## 三层记忆系统

| 层级 | 存储 | 说明 |
|------|------|------|
| **短期记忆** | State.messages | 当前对话，自动累积 |
| **会话归档** | session_archive 表 | 超过 20 轮归档到 SQLite |
| **长期记忆** | user_preferences/activities/summaries 表 | 用户偏好、跨会话知识 |

---

## Neo4j 知识图谱

Neo4j 用于存储业务规则知识图谱：

- **退票规则**: 不同舱位、不同时间的退票手续费
- **改签规则**: 改签费用计算
- **会员权益**: 银卡/金卡/白金卡的优惠政策
- **例外情况**: 航班取消、延误等特殊处理

```
TicketType ──HAS_REFUND_RULE──▶ Rule ──APPLIES_IF──▶ Condition
MembershipLevel ──ENABLES──▶ Benefit
Exception ──TRIGGERS──▶ Rule
```

---

## 异步并发机制

### asyncio 协程模型

```
事件循环 (单线程)
┌─────────────────────────────────────────────────────────┐
│  请求A (t1) ──→ astream() ──→ 挂起 (等待 I/O) ──────┐│
│  请求B (t2) ──→ astream() ──→ 挂起 (等待 I/O) ──┐ ││
│  请求C (t3) ──→ astream() ──→ 挂起 (等待 I/O)─┐ │ ││
│         ◄─────── 事件循环调度切换 ────────────── │ │ ││
│  请求A 唤醒 ──→ yield event ──→ 推送 SSE        │ │ ││
│  请求B 唤醒 ──→ yield event ──→ 推送 SSE          │ ││
└─────────────────────────────────────────────────────────┘
```

**关键优势**:
- **高并发**: 单进程可处理 10,000+ 并发协程
- **低开销**: 协程切换 ~微秒级
- **无 GIL**: asyncio 在 I/O 等待时切换，不受 GIL 限制

---

## 分布式部署架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           生产环境                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   用户 ──→ Nginx (80) ──→ API Workers (8000) ──→ Redis (6379)            │
│                          │                                    │              │
│                          │                            LangGraph State        │
│                          │                            (thread_id 隔离)      │
│                          │                                                    │
│                          └──→ Qdrant (6333)                                │
│                                    │                                        │
│                                    ↓                                        │
│                          Nginx (8002) ──→ vLLM 集群                       │
│                                         ├── vLLM-1 (GPU 1)                 │
│                                         ├── vLLM-2 (GPU 2)                 │
│                                         └── vLLM-3 (GPU 3)                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 快速开始

### 环境要求

- Python 3.12+
- [Poetry](https://python-poetry.org/docs/#installation)
- Docker 和 Docker Compose
- OpenAI API Key 或 vLLM

### 本地安装

1. **克隆仓库**
```bash
git clone https://github.com/chenzhe426/muti_agent.git
cd muti_agent
```

2. **创建环境变量文件**
```bash
cp .dev.env .env
```

3. **编辑 .env 文件**
```bash
OPENAI_API_KEY="your_openai_api_key"
LLM_PROVIDER="openai"  # 或 "vllm", "ollama"
```

4. **安装依赖**
```bash
poetry install
```

5. **启动向量数据库**
```bash
docker compose up qdrant -d
```

6. **生成向量索引**
```bash
poetry run python vectorizer/app/main.py
```

7. **启动聊天服务 (CLI 模式)**
```bash
poetry run python ./customer_support_chat/app/main.py
```

### 启动 Web 服务 (SSE 流式)

```bash
poetry run python -m uvicorn customer_support_chat.app.api:app --reload --port 8000
```

访问 http://localhost:8000

---

## 项目结构

```
├── customer_support_chat/              # 主聊天服务
│   └── app/
│       ├── api.py                     # FastAPI 服务端点 (SSE 流式)
│       ├── graph.py                   # LangGraph 状态机定义
│       ├── core/
│       │   ├── state.py               # State 定义
│       │   └── settings.py            # 配置管理
│       └── services/
│           ├── assistants/             # 5 个助手
│           │   ├── assistant_base.py   # 基类
│           │   ├── primary_assistant.py # 主路由助手
│           │   ├── flight_booking_assistant.py
│           │   ├── car_rental_assistant.py
│           │   ├── hotel_booking_assistant.py
│           │   └── excursion_assistant.py
│           ├── tools/                 # 领域工具
│           ├── vectordb/              # 向量数据库工具
│           └── neo4j/                 # Neo4j 知识图谱
│
├── vectorizer/                        # 向量化服务
│   └── app/
│       ├── main.py                   # Embeddings 生成入口
│       └── vectordb/vectordb.py      # Qdrant 集成
│
├── docker-compose.yml                 # Docker 编排配置
├── nginx.conf                        # API 负载均衡配置
└── pyproject.toml                    # Poetry 依赖
```

---

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 聊天前端 HTML |
| `/health` | GET | 健康检查 |
| `/chat/stream` | POST | SSE 流式聊天 |
| `/chat/approve` | POST | 审批敏感操作 |
| `/chat/history/{thread_id}` | GET | 获取对话历史 |

---

## 技术亮点

1. **Multi-Agent 架构**: 5 个专业化助手协同工作，职责清晰分离
2. **状态机编排**: LangGraph 提供强大的状态管理和流程控制
3. **分布式状态**: Redis Checkpointer 支持多 Worker 共享状态
4. **向量检索**: Qdrant 实现语义搜索，提升召回效果
5. **知识图谱**: Neo4j 存储复杂业务规则，支持多条件推理
6. **三层记忆**: 短期记忆 + 会话归档 + 长期记忆，实现跨会话上下文
7. **异步流式**: SSE 实现实时响应，支持中断恢复
8. **敏感操作审批**: interrupt 机制确保关键操作需用户确认

---

## License

MIT License
