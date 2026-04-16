from vectorizer.app.vectordb.vectordb import VectorDB
from customer_support_chat.app.core.settings import get_settings
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
import sqlite3
from typing import Optional, List, Dict

settings = get_settings()
db = settings.SQLITE_DB_PATH
excursions_vectordb = VectorDB(table_name="trip_recommendations", collection_name="excursions_collection")

@tool
def search_trip_recommendations(
    query: str,
    limit: int = 2,
) -> List[Dict]:
    """Search for trip recommendations based on a natural language query."""
    search_results = excursions_vectordb.search(query, limit=limit)

    recommendations = []
    for result in search_results:
        payload = result.payload
        recommendations.append({
            "id": payload["id"],
            "name": payload["name"],
            "location": payload["location"],
            "keywords": payload["keywords"],
            "details": payload["details"],
            "booked": payload["booked"],
            "chunk": payload["content"],
            "similarity": result.score,
        })
    return recommendations

@tool
def get_user_excursions(*, config: RunnableConfig) -> List[Dict]:
    """Get all excursion bookings for the current user."""
    configuration = config.get("configurable", {})
    passenger_id = configuration.get("passenger_id", None)
    if not passenger_id:
        raise ValueError("No passenger ID configured.")

    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, location, keywords, details
        FROM trip_recommendations
        WHERE passenger_id = ? AND booked = 1
    """, (passenger_id,))
    rows = cursor.fetchall()
    column_names = [column[0] for column in cursor.description]
    results = [dict(zip(column_names, row)) for row in rows]

    cursor.close()
    conn.close()
    return results

@tool
def book_excursion(recommendation_id: int, *, config: RunnableConfig) -> str:
    """Book an excursion by its ID for the current user."""
    configuration = config.get("configurable", {})
    passenger_id = configuration.get("passenger_id", None)
    if not passenger_id:
        raise ValueError("No passenger ID configured.")

    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE trip_recommendations SET booked = 1, passenger_id = ? WHERE id = ?",
        (passenger_id, recommendation_id)
    )
    conn.commit()

    if cursor.rowcount > 0:
        conn.close()
        return f"Excursion {recommendation_id} successfully booked for passenger {passenger_id}."
    else:
        conn.close()
        return f"No excursion found with ID {recommendation_id}."

@tool
def update_excursion(recommendation_id: int, details: str, *, config: RunnableConfig) -> str:
    """Update an excursion's details by its ID."""
    configuration = config.get("configurable", {})
    passenger_id = configuration.get("passenger_id", None)
    if not passenger_id:
        raise ValueError("No passenger ID configured.")

    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    # Check ownership
    cursor.execute("SELECT passenger_id FROM trip_recommendations WHERE id = ?", (recommendation_id,))
    row = cursor.fetchone()
    if not row or row[0] != passenger_id:
        conn.close()
        return f"Excursion {recommendation_id} not found or not booked by this user."

    cursor.execute(
        "UPDATE trip_recommendations SET details = ? WHERE id = ?",
        (details, recommendation_id),
    )
    conn.commit()
    conn.close()
    return f"Excursion {recommendation_id} successfully updated."

@tool
def cancel_excursion(recommendation_id: int, *, config: RunnableConfig) -> str:
    """Cancel an excursion by its ID."""
    configuration = config.get("configurable", {})
    passenger_id = configuration.get("passenger_id", None)
    if not passenger_id:
        raise ValueError("No passenger ID configured.")

    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    # Check ownership
    cursor.execute("SELECT passenger_id FROM trip_recommendations WHERE id = ?", (recommendation_id,))
    row = cursor.fetchone()
    if not row or row[0] != passenger_id:
        conn.close()
        return f"Excursion {recommendation_id} not found or not booked by this user."

    cursor.execute(
        "UPDATE trip_recommendations SET booked = 0, passenger_id = NULL WHERE id = ?",
        (recommendation_id,)
    )
    conn.commit()
    conn.close()
    return f"Excursion {recommendation_id} successfully cancelled."
