from vectorizer.app.vectordb.vectordb import VectorDB
from customer_support_chat.app.core.settings import get_settings
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
import sqlite3
from typing import List, Dict, Optional, Union
from datetime import datetime, date

settings = get_settings()
db = settings.SQLITE_DB_PATH

cars_vectordb = VectorDB(table_name="car_rentals", collection_name="car_rentals_collection")

@tool
def search_car_rentals(
    query: str,
    limit: int = 2,
) -> List[Dict]:
    """Search for car rentals based on a natural language query."""
    search_results = cars_vectordb.search(query, limit=limit)

    rentals = []
    for result in search_results:
        payload = result.payload
        rentals.append({
            "id": payload["id"],
            "name": payload["name"],
            "location": payload["location"],
            "price_tier": payload["price_tier"],
            "start_date": payload["start_date"],
            "end_date": payload["end_date"],
            "booked": payload["booked"],
            "chunk": payload["content"],
            "similarity": result.score,
        })
    return rentals

@tool
def get_user_car_rentals(*, config: RunnableConfig) -> List[Dict]:
    """Get all car rental bookings for the current user."""
    configuration = config.get("configurable", {})
    passenger_id = configuration.get("passenger_id", None)
    if not passenger_id:
        raise ValueError("No passenger ID configured.")

    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, location, price_tier, start_date, end_date
        FROM car_rentals
        WHERE passenger_id = ? AND booked = 1
    """, (passenger_id,))
    rows = cursor.fetchall()
    column_names = [column[0] for column in cursor.description]
    results = [dict(zip(column_names, row)) for row in rows]

    cursor.close()
    conn.close()
    return results

@tool
def book_car_rental(rental_id: int, *, config: RunnableConfig) -> str:
    """Book a car rental by its ID for the current user."""
    configuration = config.get("configurable", {})
    passenger_id = configuration.get("passenger_id", None)
    if not passenger_id:
        raise ValueError("No passenger ID configured.")

    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE car_rentals SET booked = 1, passenger_id = ? WHERE id = ?",
        (passenger_id, rental_id)
    )
    conn.commit()

    if cursor.rowcount > 0:
        conn.close()
        return f"Car rental {rental_id} successfully booked for passenger {passenger_id}."
    else:
        conn.close()
        return f"No car rental found with ID {rental_id}."

@tool
def update_car_rental(
    rental_id: int,
    start_date: Optional[Union[datetime, date]] = None,
    end_date: Optional[Union[datetime, date]] = None,
    *,
    config: RunnableConfig,
) -> str:
    """Update a car rental's start and end dates by its ID."""
    configuration = config.get("configurable", {})
    passenger_id = configuration.get("passenger_id", None)
    if not passenger_id:
        raise ValueError("No passenger ID configured.")

    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    # Check ownership
    cursor.execute("SELECT passenger_id FROM car_rentals WHERE id = ?", (rental_id,))
    row = cursor.fetchone()
    if not row or row[0] != passenger_id:
        conn.close()
        return f"Car rental {rental_id} not found or not booked by this user."

    if start_date:
        cursor.execute(
            "UPDATE car_rentals SET start_date = ? WHERE id = ?",
            (start_date.strftime('%Y-%m-%d'), rental_id),
        )
    if end_date:
        cursor.execute(
            "UPDATE car_rentals SET end_date = ? WHERE id = ?",
            (end_date.strftime('%Y-%m-%d'), rental_id),
        )

    conn.commit()
    conn.close()
    return f"Car rental {rental_id} successfully updated."

@tool
def cancel_car_rental(rental_id: int, *, config: RunnableConfig) -> str:
    """Cancel a car rental by its ID."""
    configuration = config.get("configurable", {})
    passenger_id = configuration.get("passenger_id", None)
    if not passenger_id:
        raise ValueError("No passenger ID configured.")

    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    # Check ownership
    cursor.execute("SELECT passenger_id FROM car_rentals WHERE id = ?", (rental_id,))
    row = cursor.fetchone()
    if not row or row[0] != passenger_id:
        conn.close()
        return f"Car rental {rental_id} not found or not booked by this user."

    cursor.execute("UPDATE car_rentals SET booked = 0, passenger_id = NULL WHERE id = ?", (rental_id,))
    conn.commit()
    conn.close()
    return f"Car rental {rental_id} successfully cancelled."
