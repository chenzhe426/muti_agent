# 对话要点总结

## 1. 项目整体架构

- **多智能体 RAG 客户支持系统**，使用 LangChain + LangGraph
- **数据层**：SQLite（事务）、Qdrant（向量检索）、Neo4j（知识图谱/规则）
- **没有前端**，纯 CLI 交互，已新增 FastAPI + SSE 流式前端

## 2. 工具系统

- 工具使用 `@tool` 装饰器基于 LangChain 定义
- 工具分两类：
  - **safe_tools**：直接执行（查询、搜索）
  - **sensitive_tools**：需用户审批（预订、改签、退票等写操作）
- 通过 `interrupt_before` 配置实现敏感操作中断

## 3. 多智能体设计

- 1 个 **Primary Assistant**（主控，只做搜索+委托）
- 4 个 **Specialized Assistants**（航班、酒店、租车、短途旅行）
- 使用 **Chain of Responsibility** 模式：委托 → 执行 → CompleteOrEscalate 交回
- 工具绑定通过 `llm.bind_tools(tools_list)` 实现

## 4. LangGraph Runtime

- **静态定义**：在 graph.py 中用 `add_node()`、`add_edge()` 定义状态图
- **Runtime 执行**：调用 `graph.stream()` 时，LangGraph Runtime 自动按图执行
- **无需外部监控进程**，Runtime 是 LangGraph 库的内嵌执行循环
- 执行流程：读取 state → 确定下一节点 → 执行节点 → 更新 state → 检查中断 → 循环

## 5. 上下文管理

- **State 结构**：`messages`（对话历史）、`user_info`（乘客航班）、`dialog_state`（当前助理）
- **上下文注入**：Prompt 中用 `{user_info}`、`{messages}`、`{time}` 占位符
- **记忆机制**：`MemorySaver` checkpointer，基于 `thread_id` 恢复会话
- **局限**：MemorySaver 是内存存储（重启丢失）、user_info 只在会话开始查一次

## 6. ReAct vs CoT vs Plan-and-Execute

| 范式 | 流程 | 实现方式 |
|------|------|---------|
| **ReAct** | Thought → Action → Observe → 循环 | Prompt 模板引导格式 |
| **CoT** | 先推理完整路径，最后执行 | Prompt 指令（"Think step by step"） |
| **Plan-and-Execute** | 显式输出计划，再按计划执行 | Prompt 中要求输出计划步骤 |

**关键**：ReAct/CoT 是概念/范式，不是库，靠 **LLM Prompt** 实现。

## 7. LangGraph 中的 ReAct

- **tools_condition** 是 LangGraph 内置路由，判断是否需要执行工具
- 不是显式叫 "ReAct"，但循环结构是 ReAct 模式
- 每次 Assistant 节点被调用 = 一次 Thought
- 每次 tool 执行 = Action + Observe
- ToolMessage 返回后，Assistant 节点再次被调用继续推理

## 8. Neo4j 知识图谱（已新增）

- **节点**：TicketType（票种）、MembershipLevel（会员等级）、Rule、Condition、Benefit、Exception
- **关系**：HAS_REFUND_RULE、HAS_RESCHEDULE_RULE、ENABLES、TRIGGERS 等
- **工具**：`lookup_refund_rules`、`lookup_reschedule_rules`、`lookup_membership_benefits`、`check_flight_exception`
- **注意**：工具已创建但**尚未挂载到任何 Assistant**

## 9. 新增文件

```
customer_support_chat/app/
├── api.py                          # FastAPI SSE 流式服务
├── templates/
│   └── index.html                  # Web 聊天前端
└── services/
    ├── neo4j/
    │   ├── connection.py           # Neo4j 连接管理
    │   └── rules_graph.py         # 规则知识图谱
    └── tools/
        └── rules_lookup.py        # 规则查询工具
```

## 10. 待完善项

- Neo4j 规则查询工具尚未加入 `primary_assistant_tools`
- MemorySaver 可考虑换用 PostgreSQL/Redis 实现持久化
- 对话超过 10 轮后 token 消耗大，建议加消息摘要机制
