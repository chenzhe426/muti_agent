import os
import shutil
import sqlite3
from datetime import datetime
import pandas as pd
import requests
from customer_support_chat.app.core.settings import get_settings
from customer_support_chat.app.core.logger import logger
from qdrant_client import QdrantClient
from customer_support_chat.app.core.settings import get_settings
from typing import List, Dict, Callable

from langchain_core.messages import ToolMessage
from customer_support_chat.app.core.state import State

settings = get_settings()

def init_metadata_db():
    """Initialize metadata database with user info, subscriptions, permissions, and memory tables."""
    metadata_db = settings.METADATA_DB_PATH
    metadata_dir = os.path.dirname(metadata_db)

    if not os.path.exists(metadata_dir):
        os.makedirs(metadata_dir)

    conn = sqlite3.connect(metadata_db)
    cursor = conn.cursor()

    # Create users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            passenger_id PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            membership_tier TEXT DEFAULT 'bronze'
        )
    """)

    # Create user_subscriptions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_subscriptions (
            passenger_id TEXT NOT NULL,
            module TEXT NOT NULL,
            subscribed INTEGER DEFAULT 1,
            subscribed_at TEXT,
            PRIMARY KEY (passenger_id, module)
        )
    """)

    # Create user_permissions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_permissions (
            passenger_id TEXT NOT NULL,
            permission TEXT NOT NULL,
            value TEXT,
            PRIMARY KEY (passenger_id, permission)
        )
    """)

    # Create session_archive table (短期记忆归档)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS session_archive (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            passenger_id TEXT NOT NULL,
            thread_id TEXT NOT NULL,
            state_data TEXT NOT NULL,
            message_count INTEGER DEFAULT 0,
            archived_at TEXT NOT NULL,
            session_summary TEXT
        )
    """)

    # Create user_preferences table (长期记忆 - 用户偏好)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            passenger_id TEXT NOT NULL,
            preference_key TEXT NOT NULL,
            preference_value TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (passenger_id, preference_key)
        )
    """)

    # Create user_activities table (长期记忆 - 业务活动)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            passenger_id TEXT NOT NULL,
            activity_type TEXT NOT NULL,
            entity_id TEXT,
            details TEXT,
            occurred_at TEXT NOT NULL
        )
    """)

    # Create conversation_summaries table (长期记忆 - 对话摘要)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversation_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            passenger_id TEXT NOT NULL,
            thread_id TEXT NOT NULL,
            summary TEXT NOT NULL,
            domain TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # Create indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_session_archive_passenger
        ON session_archive(passenger_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_activities_passenger
        ON user_activities(passenger_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversation_summaries_passenger
        ON conversation_summaries(passenger_id)
    """)

    # Insert default user if not exists
    default_passenger_id = "5102 899977"
    cursor.execute("SELECT COUNT(*) FROM users WHERE passenger_id = ?", (default_passenger_id,))
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO users (passenger_id, name, email, phone, membership_tier)
            VALUES (?, ?, ?, ?, ?)
        """, (default_passenger_id, "John Doe", "john@example.com", "+1-555-0123", "gold"))

        # Default subscriptions
        modules = ['flights', 'hotels', 'car_rentals', 'excursions']
        for module in modules:
            cursor.execute("""
                INSERT INTO user_subscriptions (passenger_id, module, subscribed, subscribed_at)
                VALUES (?, ?, 1, ?)
            """, (default_passenger_id, module, datetime.now().isoformat()))

        # Default permissions
        permissions = [
            ('can_cancel', 'true'),
            ('can_reschedule', 'true'),
            ('max_free_changes', '2'),
        ]
        for perm, val in permissions:
            cursor.execute("""
                INSERT INTO user_permissions (passenger_id, permission, value)
                VALUES (?, ?, ?)
            """, (default_passenger_id, perm, val))

    conn.commit()
    conn.close()


def create_entry_node(assistant_name: str, new_dialog_state: str) -> Callable:
    # Map dialog_state to domain for long-term memory filtering
    domain_mapping = {
        "update_flight": "flights",
        "book_car_rental": "cars",
        "book_hotel": "hotels",
        "book_excursion": "excursions",
    }

    def entry_node(state: State) -> dict:
        tool_call_id = state["messages"][-1].tool_calls[0]["id"]

        # Extract relevant long-term memory for this domain
        domain = domain_mapping.get(new_dialog_state, "")
        long_term = state.get("long_term_memory", {})
        relevant_memory = long_term.get(domain, {}) if domain else {}

        # Format relevant memory for context
        memory_context = ""
        if relevant_memory:
            if "activities" in relevant_memory:
                activities = relevant_memory["activities"]
                if activities:
                    memory_context += "\n\nRecent activities:\n"
                    for a in activities[:5]:
                        memory_context += f"- {a.get('activity_type')}: {a.get('details', {})}\n"
            if "summaries" in relevant_memory:
                summaries = relevant_memory["summaries"]
                if summaries:
                    memory_context += "\n\nConversation summaries:\n"
                    for s in summaries[:3]:
                        memory_context += f"- [{s.get('domain')}]: {s.get('summary')}\n"
            if "preferences" in relevant_memory:
                prefs = relevant_memory["preferences"]
                if prefs:
                    memory_context += "\n\nUser preferences:\n"
                    for k, v in prefs.items():
                        memory_context += f"- {k}: {v}\n"

        return {
            "messages": [
                ToolMessage(
                    content=(
                        f"The assistant is now the {assistant_name}. Reflect on the above conversation between the host assistant and the user. "
                        f"The user's intent is unsatisfied. Use the provided tools to assist the user. Remember, you are {assistant_name}, "
                        "and the booking, update, or other action is not complete until after you have successfully invoked the appropriate tool. "
                        "If the user changes their mind or needs help for other tasks, call the CompleteOrEscalate function to let the primary host assistant take control. "
                        "Do not mention who you are—just act as the proxy for the assistant."
                        f"{memory_context}"
                    ),
                    tool_call_id=tool_call_id,
                )
            ],
            "dialog_state": new_dialog_state,
        }
    return entry_node


def download_and_prepare_db():
    settings = get_settings()
    db_file = settings.SQLITE_DB_PATH
    db_dir = os.path.dirname(db_file)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
    db_url = "https://storage.googleapis.com/benchmarks-artifacts/travel-db/travel2.sqlite"
    if not os.path.exists(db_file):
        response = requests.get(db_url)
        response.raise_for_status()
        with open(db_file, "wb") as f:
            f.write(response.content)
        update_dates(db_file)
    # Add passenger_id columns to business tables
    add_passenger_id_columns()
    # Initialize metadata database
    init_metadata_db()

def add_passenger_id_columns():
    """Add passenger_id column to business tables that track user bookings."""
    db_file = settings.SQLITE_DB_PATH
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    # Get all table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]

    # Tables that need passenger_id
    tables_with_bookings = ['hotels', 'car_rentals', 'trip_recommendations']

    for table in tables_with_bookings:
        if table in tables:
            # Check if passenger_id column exists
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [col[1] for col in cursor.fetchall()]
            if 'passenger_id' not in columns:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN passenger_id TEXT")
                print(f"Added passenger_id column to {table}")

    conn.commit()
    conn.close()

def update_dates(db_file):
    backup_file = db_file + '.backup'
    if not os.path.exists(backup_file):
        shutil.copy(db_file, backup_file)

    conn = sqlite3.connect(db_file)

    tables = pd.read_sql(
        "SELECT name FROM sqlite_master WHERE type='table';", conn
    ).name.tolist()
    tdf = {}
    for t in tables:
        tdf[t] = pd.read_sql(f"SELECT * from {t}", conn)

    example_time = pd.to_datetime(
        tdf["flights"]["actual_departure"].replace("\\N", pd.NaT)
    ).max()
    current_time = pd.to_datetime("now").tz_localize(example_time.tz)
    time_diff = current_time - example_time

    tdf["bookings"]["book_date"] = (
        pd.to_datetime(tdf["bookings"]["book_date"].replace("\\N", pd.NaT), utc=True)
        + time_diff
    )

    datetime_columns = [
        "scheduled_departure",
        "scheduled_arrival",
        "actual_departure",
        "actual_arrival",
    ]
    for column in datetime_columns:
        tdf["flights"][column] = (
            pd.to_datetime(tdf["flights"][column].replace("\\N", pd.NaT)) + time_diff
        )

    for table_name, df in tdf.items():
        df.to_sql(table_name, conn, if_exists="replace", index=False)

    conn.commit()
    conn.close()

def handle_tool_error(state) -> dict:
    error = state.get("error")
    tool_calls = state["messages"][-1].tool_calls
    return {
        "messages": [
            {
                "type": "tool",
                "content": f"Error: {repr(error)}\nPlease fix your mistakes.",
                "tool_call_id": tc["id"],
            }
            for tc in tool_calls
        ]
    }

def create_tool_node_with_fallback(tools: list):
    from langchain_core.messages import ToolMessage
    from langchain_core.runnables import RunnableLambda
    from langgraph.prebuilt import ToolNode

    return ToolNode(tools).with_fallbacks(
        [RunnableLambda(handle_tool_error)], exception_key="error"
    )

def get_qdrant_client():
    settings = get_settings()
    try:
        client = QdrantClient(url=settings.QDRANT_URL)
        # Test the connection
        client.get_collections()
        return client
    except Exception as e:
        logger.error(f"Failed to connect to Qdrant server at {settings.QDRANT_URL}. Error: {str(e)}")
        raise

def flight_info_to_string(flight_info: List[Dict]) -> str:
    info_lines = [] 
    i = 0
    for flight in flight_info:
        i += 1
        line = (
            f"Ticket [{i}]:\n"
            f"Ticket Number: {flight['ticket_no']}\n"
            f"Booking Reference: {flight['book_ref']}\n"
            f"Flight ID: {flight['flight_id']}\n"
            f"Flight Number: {flight['flight_no']}\n"
            f"Departure: {flight['departure_airport']} at {flight['scheduled_departure']}\n"
            f"Arrival: {flight['arrival_airport']} at {flight['scheduled_arrival']}\n"
            f"Seat: {flight['seat_no']}\n"
            f"Fare Class: {flight['fare_conditions']}\n"
            f"\n\n"
        )
        info_lines.append(line)

    info_lines = f"User current booked flight(s) details:\n" + "\n".join(info_lines)

    return "\n".join(info_lines)

def fetch_user_metadata(passenger_id: str) -> dict:
    """Fetch lightweight user metadata from metadata database."""
    metadata_db = settings.METADATA_DB_PATH

    if not os.path.exists(metadata_db):
        return {}

    conn = sqlite3.connect(metadata_db)
    cursor = conn.cursor()

    # Fetch user info
    cursor.execute("""
        SELECT passenger_id, name, email, phone, membership_tier
        FROM users WHERE passenger_id = ?
    """, (passenger_id,))
    user_row = cursor.fetchone()

    if not user_row:
        conn.close()
        return {}

    user_info = {
        "passenger_id": user_row[0],
        "name": user_row[1],
        "email": user_row[2],
        "phone": user_row[3],
        "membership_tier": user_row[4],
    }

    # Fetch subscriptions
    cursor.execute("""
        SELECT module, subscribed FROM user_subscriptions WHERE passenger_id = ?
    """, (passenger_id,))
    subs_rows = cursor.fetchall()
    subscriptions = {row[0]: bool(row[1]) for row in subs_rows}

    # Fetch permissions
    cursor.execute("""
        SELECT permission, value FROM user_permissions WHERE passenger_id = ?
    """, (passenger_id,))
    perms_rows = cursor.fetchall()
    permissions = {row[0]: row[1] for row in perms_rows}

    conn.close()

    return {
        "user_info": user_info,
        "subscriptions": subscriptions,
        "permissions": permissions,
    }

def metadata_to_string(metadata: dict) -> str:
    """Convert metadata dict to formatted string for prompt."""
    if not metadata:
        return "No user metadata available."

    user = metadata.get("user_info", {})
    subs = metadata.get("subscriptions", {})
    perms = metadata.get("permissions", {})

    lines = [
        "=== User Metadata ===",
        f"Passenger ID: {user.get('passenger_id', 'N/A')}",
        f"Name: {user.get('name', 'N/A')}",
        f"Email: {user.get('email', 'N/A')}",
        f"Phone: {user.get('phone', 'N/A')}",
        f"Membership Tier: {user.get('membership_tier', 'bronze').upper()}",
        "",
        "=== Active Subscriptions ===",
    ]

    for module, active in subs.items():
        status = "Active" if active else "Inactive"
        lines.append(f"  - {module}: {status}")

    lines.extend([
        "",
        "=== Permissions ===",
    ])

    for perm, value in perms.items():
        lines.append(f"  - {perm}: {value}")

    return "\n".join(lines)