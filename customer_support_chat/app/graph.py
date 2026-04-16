from typing import Literal
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import tools_condition
from langchain_core.runnables import RunnableConfig

from customer_support_chat.app.core.state import State
from customer_support_chat.app.core.settings import get_settings
from customer_support_chat.app.services.utils import (
  create_tool_node_with_fallback,
  create_entry_node,
  fetch_user_metadata,
  metadata_to_string,
)
from customer_support_chat.app.services.assistants.assistant_base import (
  Assistant,
  CompleteOrEscalate,
  llm,
)
from customer_support_chat.app.services.assistants.primary_assistant import (
  primary_assistant,
  primary_assistant_tools,
  update_user_metadata,
  ToFlightBookingAssistant,
  ToBookCarRental,
  ToHotelBookingAssistant,
  ToBookExcursion,
)
from customer_support_chat.app.services.assistants.flight_booking_assistant import (
  flight_booking_assistant,
  update_flight_safe_tools,
  update_flight_sensitive_tools,
)
from customer_support_chat.app.services.assistants.car_rental_assistant import (
  car_rental_assistant,
  book_car_rental_safe_tools,
  book_car_rental_sensitive_tools,
)
from customer_support_chat.app.services.assistants.hotel_booking_assistant import (
  hotel_booking_assistant,
  book_hotel_safe_tools,
  book_hotel_sensitive_tools,
)
from customer_support_chat.app.services.assistants.excursion_assistant import (
  excursion_assistant,
  book_excursion_safe_tools,
  book_excursion_sensitive_tools,
)

settings = get_settings()

# Initialize the graph
builder = StateGraph(State)

def user_info(state: State, config: RunnableConfig):
    passenger_id = config.get("configurable", {}).get("passenger_id")
    thread_id = config.get("configurable", {}).get("thread_id", "default")
    metadata = fetch_user_metadata(passenger_id)
    metadata_str = metadata_to_string(metadata)
    return {
        "user_info": metadata_str,
        "session_id": thread_id,
        "long_term_memory": {}
    }

builder.add_node("fetch_user_info", user_info)
builder.add_edge(START, "fetch_user_info")

def handle_message_compaction(state: State, config: RunnableConfig) -> dict:
    """Handle compact_messages tool result - truncate messages to keep only recent turns."""
    last_message = state["messages"][-1]
    if hasattr(last_message, 'content') and last_message.content == "__COMPACT_MESSAGES__":
        # Keep only last 10 messages
        return {"messages": state["messages"][-10:]}
    return {}

builder.add_node("handle_compaction", handle_message_compaction)

# Primary Assistant
builder.add_node("primary_assistant", primary_assistant)
builder.add_node(
  "primary_assistant_tools", create_tool_node_with_fallback(primary_assistant_tools)
)
builder.add_edge("fetch_user_info", "primary_assistant")

# Flight Booking Assistant
builder.add_node(
  "enter_update_flight",
  create_entry_node("Flight Updates & Booking Assistant", "update_flight"),
)
builder.add_node("update_flight", flight_booking_assistant)
builder.add_edge("enter_update_flight", "update_flight")
builder.add_node(
  "update_flight_safe_tools",
  create_tool_node_with_fallback(update_flight_safe_tools),
)
builder.add_node(
  "update_flight_sensitive_tools",
  create_tool_node_with_fallback(update_flight_sensitive_tools),
)

def route_update_flight(state: State) -> Literal[
  "update_flight_safe_tools",
  "update_flight_sensitive_tools",
  "primary_assistant",
  "__end__",
]:
  route = tools_condition(state)
  if route == END:
      return END
  tool_calls = state["messages"][-1].tool_calls
  did_cancel = any(tc["name"] == CompleteOrEscalate.__name__ for tc in tool_calls)
  if did_cancel:
      return "primary_assistant"
  safe_toolnames = [t.name for t in update_flight_safe_tools]
  if all(tc["name"] in safe_toolnames for tc in tool_calls):
      return "update_flight_safe_tools"
  return "update_flight_sensitive_tools"

builder.add_edge("update_flight_safe_tools", "update_flight")
builder.add_edge("update_flight_sensitive_tools", "update_flight")
builder.add_conditional_edges("update_flight", route_update_flight)

# Car Rental Assistant
builder.add_node(
  "enter_book_car_rental",
  create_entry_node("Car Rental Assistant", "book_car_rental"),
)
builder.add_node("book_car_rental", car_rental_assistant)
builder.add_edge("enter_book_car_rental", "book_car_rental")
builder.add_node(
  "book_car_rental_safe_tools",
  create_tool_node_with_fallback(book_car_rental_safe_tools),
)
builder.add_node(
  "book_car_rental_sensitive_tools",
  create_tool_node_with_fallback(book_car_rental_sensitive_tools),
)

def route_book_car_rental(state: State) -> Literal[
  "book_car_rental_safe_tools",
  "book_car_rental_sensitive_tools",
  "primary_assistant",
  "__end__",
]:
  route = tools_condition(state)
  if route == END:
      return END
  tool_calls = state["messages"][-1].tool_calls
  did_cancel = any(tc["name"] == CompleteOrEscalate.__name__ for tc in tool_calls)
  if did_cancel:
      return "primary_assistant"
  safe_toolnames = [t.name for t in book_car_rental_safe_tools]
  if all(tc["name"] in safe_toolnames for tc in tool_calls):
      return "book_car_rental_safe_tools"
  return "book_car_rental_sensitive_tools"

builder.add_edge("book_car_rental_safe_tools", "book_car_rental")
builder.add_edge("book_car_rental_sensitive_tools", "book_car_rental")
builder.add_conditional_edges("book_car_rental", route_book_car_rental)

# Hotel Booking Assistant
builder.add_node(
  "enter_book_hotel",
  create_entry_node("Hotel Booking Assistant", "book_hotel"),
)
builder.add_node("book_hotel", hotel_booking_assistant)
builder.add_edge("enter_book_hotel", "book_hotel")
builder.add_node(
  "book_hotel_safe_tools",
  create_tool_node_with_fallback(book_hotel_safe_tools),
)
builder.add_node(
  "book_hotel_sensitive_tools",
  create_tool_node_with_fallback(book_hotel_sensitive_tools),
)

def route_book_hotel(state: State) -> Literal[
  "book_hotel_safe_tools",
  "book_hotel_sensitive_tools",
  "primary_assistant",
  "__end__",
]:
  route = tools_condition(state)
  if route == END:
      return END
  tool_calls = state["messages"][-1].tool_calls
  did_cancel = any(tc["name"] == CompleteOrEscalate.__name__ for tc in tool_calls)
  if did_cancel:
      return "primary_assistant"
  safe_toolnames = [t.name for t in book_hotel_safe_tools]
  if all(tc["name"] in safe_toolnames for tc in tool_calls):
      return "book_hotel_safe_tools"
  return "book_hotel_sensitive_tools"

builder.add_edge("book_hotel_safe_tools", "book_hotel")
builder.add_edge("book_hotel_sensitive_tools", "book_hotel")
builder.add_conditional_edges("book_hotel", route_book_hotel)

# Excursion Assistant
builder.add_node(
  "enter_book_excursion",
  create_entry_node("Trip Recommendation Assistant", "book_excursion"),
)
builder.add_node("book_excursion", excursion_assistant)
builder.add_edge("enter_book_excursion", "book_excursion")
builder.add_node(
  "book_excursion_safe_tools",
  create_tool_node_with_fallback(book_excursion_safe_tools),
)
builder.add_node(
  "book_excursion_sensitive_tools",
  create_tool_node_with_fallback(book_excursion_sensitive_tools),
)

def route_book_excursion(state: State) -> Literal[
  "book_excursion_safe_tools",
  "book_excursion_sensitive_tools",
  "primary_assistant",
  "__end__",
]:
  route = tools_condition(state)
  if route == END:
      return END
  tool_calls = state["messages"][-1].tool_calls
  did_cancel = any(tc["name"] == CompleteOrEscalate.__name__ for tc in tool_calls)
  if did_cancel:
      return "primary_assistant"
  safe_toolnames = [t.name for t in book_excursion_safe_tools]
  if all(tc["name"] in safe_toolnames for tc in tool_calls):
      return "book_excursion_safe_tools"
  return "book_excursion_sensitive_tools"

builder.add_edge("book_excursion_safe_tools", "book_excursion")
builder.add_edge("book_excursion_sensitive_tools", "book_excursion")
builder.add_conditional_edges("book_excursion", route_book_excursion)

def route_primary_assistant(state: State) -> Literal[
  "primary_assistant_tools",
  "handle_compaction",
  "enter_update_flight",
  "enter_book_car_rental",
  "enter_book_hotel",
  "enter_book_excursion",
  "__end__",
]:
  route = tools_condition(state)
  if route == END:
      return END
  tool_calls = state["messages"][-1].tool_calls
  if tool_calls:
      tool_name = tool_calls[0]["name"]
      if tool_name == ToFlightBookingAssistant.__name__:
          return "enter_update_flight"
      elif tool_name == ToBookCarRental.__name__:
          return "enter_book_car_rental"
      elif tool_name == ToHotelBookingAssistant.__name__:
          return "enter_book_hotel"
      elif tool_name == ToBookExcursion.__name__:
          return "enter_book_excursion"
      elif tool_name == "compact_messages":
          return "handle_compaction"
      else:
          return "primary_assistant_tools"
  return "primary_assistant"

builder.add_conditional_edges(
  "primary_assistant",
  route_primary_assistant,
  {
      "enter_update_flight": "enter_update_flight",
      "enter_book_car_rental": "enter_book_car_rental",
      "enter_book_hotel": "enter_book_hotel",
      "enter_book_excursion": "enter_book_excursion",
      "handle_compaction": "handle_compaction",
      "primary_assistant_tools": "primary_assistant_tools",
      END: END,
  },
)

builder.add_edge("handle_compaction", "primary_assistant")
builder.add_edge("primary_assistant_tools", "primary_assistant")

# Compile the graph with interrupts
interrupt_nodes = [
  "update_flight_sensitive_tools",
  "book_car_rental_sensitive_tools",
  "book_hotel_sensitive_tools",
  "book_excursion_sensitive_tools",
]

# 根据配置选择 Checkpointer 类型
def create_checkpointer():
    """创建状态持久化器，支持 memory 和 redis"""
    checkpointer_type = settings.CHECKPOINTER_TYPE.lower()

    if checkpointer_type == "redis":
        try:
            from langgraph.checkpoint.redis import RedisSaver
            import redis as redis_client

            # 创建 Redis 连接池
            redis_conn = redis_client.from_url(
                settings.REDIS_URL,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                decode_responses=False,
            )

            # 创建 RedisSaver
            checkpointer = RedisSaver(
                redis_conn,
                thread_count=settings.REDIS_THREAD_COUNT,
            )

            print(f"[Graph] Using Redis checkpointer: {settings.REDIS_URL}")
            return checkpointer

        except ImportError:
            print("[Graph] Redis saver not available, falling back to MemorySaver")
            return MemorySaver()
        except Exception as e:
            print(f"[Graph] Failed to connect to Redis: {e}, falling back to MemorySaver")
            return MemorySaver()
    else:
        print("[Graph] Using MemorySaver checkpointer")
        return MemorySaver()

checkpointer = create_checkpointer()

multi_agentic_graph = builder.compile(
  checkpointer=checkpointer,
  interrupt_before=interrupt_nodes,
)