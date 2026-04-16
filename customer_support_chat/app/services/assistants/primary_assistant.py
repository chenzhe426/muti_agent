from datetime import datetime
import json
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from customer_support_chat.app.core.settings import get_settings
import sqlite3
import os
from customer_support_chat.app.services.assistants.assistant_base import Assistant, llm
from customer_support_chat.app.core.state import State
from pydantic import BaseModel, Field

settings = get_settings()

@tool
def update_user_metadata(
    passenger_id: str,
    action: str,
    module: str = None,
    permission: str = None,
    value: str = None,
) -> str:
    """Update user metadata after business operations.
    Use this to sync metadata with business database changes.

    Actions:
    - 'subscribe': Add or update module subscription
    - 'unsubscribe': Remove module subscription
    - 'update_permission': Update a permission value
    """
    metadata_db = settings.METADATA_DB_PATH

    if not os.path.exists(metadata_db):
        return "Metadata database not found."

    conn = sqlite3.connect(metadata_db)
    cursor = conn.cursor()

    if action == "subscribe" and module:
        cursor.execute("""
            INSERT OR REPLACE INTO user_subscriptions (passenger_id, module, subscribed, subscribed_at)
            VALUES (?, ?, 1, ?)
        """, (passenger_id, module, datetime.now().isoformat()))
        result = f"Subscribed {passenger_id} to {module}"

    elif action == "unsubscribe" and module:
        cursor.execute("""
            UPDATE user_subscriptions SET subscribed = 0 WHERE passenger_id = ? AND module = ?
        """, (passenger_id, module))
        result = f"Unsubscribed {passenger_id} from {module}"

    elif action == "update_permission" and permission and value:
        cursor.execute("""
            INSERT OR REPLACE INTO user_permissions (passenger_id, permission, value)
            VALUES (?, ?, ?)
        """, (passenger_id, permission, value))
        result = f"Updated {permission} = {value} for {passenger_id}"

    else:
        conn.close()
        return f"Invalid action or missing parameters. Action: {action}, Module: {module}, Permission: {permission}"

    conn.commit()
    conn.close()
    return result

@tool
def archive_session_messages(
    passenger_id: str,
    thread_id: str,
    state_data: dict,
) -> str:
    """Archive full state to session archive (短期记忆 -> 会话库).
    Call this when messages exceed the window size (e.g., 20 turns) or session ends.
    Saves complete state including messages, dialog_state, long_term_memory, etc.
    """
    metadata_db = settings.METADATA_DB_PATH

    if not os.path.exists(metadata_db):
        return "Metadata database not found."

    conn = sqlite3.connect(metadata_db)
    cursor = conn.cursor()

    # Convert full state to JSON string
    state_json = json.dumps(state_data, ensure_ascii=False, default=str)

    # Extract message count
    messages = state_data.get("messages", [])
    message_count = len(messages)

    cursor.execute("""
        INSERT INTO session_archive (passenger_id, thread_id, messages, message_count, archived_at)
        VALUES (?, ?, ?, ?, ?)
    """, (passenger_id, thread_id, state_json, message_count, datetime.now().isoformat()))

    conn.commit()
    conn.close()

    return f"Archived full state ({message_count} messages) for thread {thread_id}"

@tool
def load_session_archive(
    passenger_id: str,
    thread_id: str = None,
    limit: int = 5,
) -> str:
    """Load archived state from session archive (会话库 -> 短期记忆).
    If thread_id is provided, load that specific session; otherwise load recent sessions.
    Returns full state data that can be used to restore conversation context.
    """
    metadata_db = settings.METADATA_DB_PATH

    if not os.path.exists(metadata_db):
        return "Metadata database not found."

    conn = sqlite3.connect(metadata_db)
    cursor = conn.cursor()

    if thread_id:
        cursor.execute("""
            SELECT thread_id, state_data, message_count, archived_at, session_summary
            FROM session_archive
            WHERE passenger_id = ? AND thread_id = ?
            ORDER BY archived_at DESC
            LIMIT ?
        """, (passenger_id, thread_id, limit))
    else:
        cursor.execute("""
            SELECT thread_id, state_data, message_count, archived_at, session_summary
            FROM session_archive
            WHERE passenger_id = ?
            ORDER BY archived_at DESC
            LIMIT ?
        """, (passenger_id, limit))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return "No archived sessions found."

    results = []
    for row in rows:
        thread_id, state_json, count, archived_at, summary = row
        results.append({
            "thread_id": thread_id,
            "message_count": count,
            "archived_at": archived_at,
            "summary": summary or "No summary",
            "state_data": json.loads(state_json)
        })

    return json.dumps(results, ensure_ascii=False, indent=2)

@tool
def load_long_term_memory(
    passenger_id: str,
    domain: str = None,
) -> str:
    """Load user's long-term memory including preferences, activities, and summaries.
    If domain is provided, only load memory for that domain (flights, hotels, cars, excursions).
    """
    metadata_db = settings.METADATA_DB_PATH

    if not os.path.exists(metadata_db):
        return "Metadata database not found."

    conn = sqlite3.connect(metadata_db)
    cursor = conn.cursor()

    result = {}

    # Load preferences
    cursor.execute("""
        SELECT preference_key, preference_value, updated_at
        FROM user_preferences
        WHERE passenger_id = ?
    """, (passenger_id,))
    prefs = {row[0]: row[1] for row in cursor.fetchall()}
    if prefs:
        result["preferences"] = prefs

    # Load recent activities (grouped by domain if specified)
    if domain:
        cursor.execute("""
            SELECT id, activity_type, entity_id, details, occurred_at
            FROM user_activities
            WHERE passenger_id = ? AND activity_type LIKE ?
            ORDER BY occurred_at DESC
            LIMIT 20
        """, (passenger_id, f"%{domain}%"))
    else:
        cursor.execute("""
            SELECT id, activity_type, entity_id, details, occurred_at
            FROM user_activities
            WHERE passenger_id = ?
            ORDER BY occurred_at DESC
            LIMIT 20
        """, (passenger_id,))

    activities = []
    for row in cursor.fetchall():
        activities.append({
            "id": row[0],
            "activity_type": row[1],
            "entity_id": row[2],
            "details": json.loads(row[3]) if row[3] else {},
            "occurred_at": row[4]
        })
    if activities:
        result["activities"] = activities

    # Load conversation summaries
    if domain:
        cursor.execute("""
            SELECT id, thread_id, summary, domain, created_at
            FROM conversation_summaries
            WHERE passenger_id = ? AND domain = ?
            ORDER BY created_at DESC
            LIMIT 10
        """, (passenger_id, domain))
    else:
        cursor.execute("""
            SELECT id, thread_id, summary, domain, created_at
            FROM conversation_summaries
            WHERE passenger_id = ?
            ORDER BY created_at DESC
            LIMIT 10
        """, (passenger_id,))

    summaries = []
    for row in cursor.fetchall():
        summaries.append({
            "id": row[0],
            "thread_id": row[1],
            "summary": row[2],
            "domain": row[3],
            "created_at": row[4]
        })
    if summaries:
        result["summaries"] = summaries

    conn.close()

    if not result:
        return "No long-term memory found."

    return json.dumps(result, ensure_ascii=False, indent=2)

@tool
def save_to_long_term_memory(
    passenger_id: str,
    thread_id: str,
    memory_type: str,
    domain: str = None,
    summary: str = None,
    preference_key: str = None,
    preference_value: str = None,
    activity_type: str = None,
    activity_details: dict = None,
) -> str:
    """Save extracted knowledge to long-term memory (提炼 -> 长期记忆).
    Memory types: 'preference', 'activity', 'summary'
    """
    metadata_db = settings.METADATA_DB_PATH

    if not os.path.exists(metadata_db):
        return "Metadata database not found."

    conn = sqlite3.connect(metadata_db)
    cursor = conn.cursor()

    result = ""

    if memory_type == "preference" and preference_key and preference_value:
        cursor.execute("""
            INSERT OR REPLACE INTO user_preferences (passenger_id, preference_key, preference_value, updated_at)
            VALUES (?, ?, ?, ?)
        """, (passenger_id, preference_key, preference_value, datetime.now().isoformat()))
        result = f"Saved preference: {preference_key} = {preference_value}"

    elif memory_type == "activity" and activity_type:
        details_json = json.dumps(activity_details or {})
        cursor.execute("""
            INSERT INTO user_activities (passenger_id, activity_type, details, occurred_at)
            VALUES (?, ?, ?, ?)
        """, (passenger_id, activity_type, details_json, datetime.now().isoformat()))
        result = f"Saved activity: {activity_type}"

    elif memory_type == "summary" and summary:
        cursor.execute("""
            INSERT INTO conversation_summaries (passenger_id, thread_id, summary, domain, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (passenger_id, thread_id, summary, domain, datetime.now().isoformat()))
        result = f"Saved summary: {summary[:50]}..."

    else:
        conn.close()
        return f"Invalid parameters. memory_type={memory_type}"

    conn.commit()
    conn.close()

    return result

@tool
def compact_messages() -> str:
    """Compact current messages to keep only recent turns.
    This should be called after archiving messages.
    Returns instructions for the graph to truncate messages.
    """
    return "__COMPACT_MESSAGES__"

# Define task delegation tools
class ToFlightBookingAssistant(BaseModel):
    """Transfers work to a specialized assistant to handle flight updates and cancellations."""
    request: str = Field(description="Any necessary follow-up questions the update flight assistant should clarify before proceeding.")

class ToBookCarRental(BaseModel):
    """Transfers work to a specialized assistant to handle car rental bookings."""
    location: str = Field(description="The location where the user wants to rent a car.")
    start_date: str = Field(description="The start date of the car rental.")
    end_date: str = Field(description="The end date of the car rental.")
    request: str = Field(description="Any additional information or requests from the user regarding the car rental.")

class ToHotelBookingAssistant(BaseModel):
    """Transfers work to a specialized assistant to handle hotel bookings."""
    location: str = Field(description="The location where the user wants to book a hotel.")
    checkin_date: str = Field(description="The check-in date for the hotel.")
    checkout_date: str = Field(description="The check-out date for the hotel.")
    request: str = Field(description="Any additional information or requests from the user regarding the hotel booking.")

class ToBookExcursion(BaseModel):
    """Transfers work to a specialized assistant to handle trip recommendation and other excursion bookings."""
    location: str = Field(description="The location where the user wants to book a recommended trip.")
    request: str = Field(description="Any additional information or requests from the user regarding the trip recommendation.")

# Primary assistant prompt
primary_assistant_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a helpful customer support assistant for Swiss Airlines. "
            "Your primary role is to route customer requests to specialized assistants and manage memory. "
            "\n\n=== MEMORY ARCHITECTURE ==="
            "\nThis system uses a 3-layer memory architecture:"
            "\n1. SHORT-TERM (state.messages): Current conversation, auto-incremented"
            "\n2. SESSION ARCHIVE (session_archive table): Archived when >20 turns or session ends"
            "\n3. LONG-TERM (user_preferences/activities/summaries): Extracted knowledge for cross-session reuse"
            "\n\n=== MEMORY MANAGEMENT RULES ==="
            "\n1. When messages exceed 20 turns, call archive_session_messages to archive"
            "\n2. When user asks about history (e.g., 'what did I book last time'), call load_long_term_memory"
            "\n3. When extracting preferences/knowledge during conversation, call save_to_long_term_memory"
            "\n4. When a specialized assistant completes, call update_user_metadata to sync"
            "\n5. After archiving, use compact_messages to keep only recent turns"
            "\n\n=== ROUTING ==="
            "\nRoute to specialized assistants for: flight changes, hotel bookings, car rentals, excursions. "
            "Only specialized assistants can modify business data."
            "\n\nCurrent user info:\n{user_info}"
            "\n\nCurrent time: {time}.",
        ),
        ("placeholder", "{messages}"),
    ]
).partial(time=datetime.now())

# Primary assistant tools
primary_assistant_tools = [
    update_user_metadata,
    archive_session_messages,
    load_session_archive,
    load_long_term_memory,
    save_to_long_term_memory,
    ToFlightBookingAssistant,
    ToBookCarRental,
    ToHotelBookingAssistant,
    ToBookExcursion,
]

# Create the primary assistant runnable
primary_assistant_runnable = primary_assistant_prompt | llm.bind_tools(primary_assistant_tools)

# Instantiate the primary assistant
primary_assistant = Assistant(primary_assistant_runnable)