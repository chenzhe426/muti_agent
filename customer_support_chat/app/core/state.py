from typing import Annotated, Literal, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import AnyMessage, add_messages

def update_dialog_stack(left: list[str], right: Optional[str]) -> list[str]:
    """Push or pop the dialog state stack."""
    if right is None:
        return left
    if right == "pop":
        return left[:-1]
    return left + [right]

def merge_long_term(left: dict, right: dict) -> dict:
    """Merge long-term memory updates."""
    if left is None:
        left = {}
    if right is None:
        return left
    # Merge by domain keys
    for key, value in right.items():
        if key in left:
            # For lists, extend; for dicts, merge
            if isinstance(left[key], list) and isinstance(value, list):
                left[key] = left[key] + value
            elif isinstance(left[key], dict) and isinstance(value, dict):
                left[key].update(value)
            else:
                left[key] = value
        else:
            left[key] = value
    return left

class State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    user_info: str
    dialog_state: Annotated[
        list[
            Literal[
                "assistant",
                "update_flight",
                "book_car_rental",
                "book_hotel",
                "book_excursion",
            ]
        ],
        update_dialog_stack,
    ]
    session_id: str
    long_term_memory: Annotated[dict, merge_long_term]