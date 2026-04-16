# tools/rules_lookup.py - Tools for querying booking rules from Neo4j

from langchain_core.tools import tool
from customer_support_chat.app.services.neo4j import (
    get_refund_rules,
    get_reschedule_rules,
    get_membership_benefits,
    check_exception,
)


@tool
def lookup_refund_rules(ticket_type: str) -> str:
    """Look up refund rules for a specific ticket type.

    Args:
        ticket_type: The ticket type code (ECO=经济舱, BUS=商务舱, FST=头等舱, DIS=特价票)

    Returns:
        A formatted string containing all refund rules for the ticket type,
        including conditions and penalty rates.
    """
    rules = get_refund_rules(ticket_type.upper())

    if not rules:
        return f"No refund rules found for ticket type: {ticket_type}"

    result = f"=== 退票规则 ({ticket_type.upper()}) ===\n\n"

    for rule in rules:
        refundable = "可退票" if rule.get("refundable") else "不可退票"
        penalty = f"{rule.get('penalty_rate', 0) * 100:.0f}%手续费" if rule.get("penalty_rate", 0) > 0 else "免费"
        condition = rule.get("condition", "无条件")

        result += f"规则: {rule.get('rule_name', 'N/A')}\n"
        result += f"  说明: {rule.get('description', 'N/A')}\n"
        result += f"  退票: {refundable}\n"
        result += f"  手续费: {penalty}\n"
        result += f"  条件: {condition}\n\n"

    return result


@tool
def lookup_reschedule_rules(ticket_type: str) -> str:
    """Look up reschedule (change flight) rules for a specific ticket type.

    Args:
        ticket_type: The ticket type code (ECO=经济舱, BUS=商务舱, FST=头等舱, DIS=特价票)

    Returns:
        A formatted string containing all reschedule rules for the ticket type,
        including conditions and penalty rates.
    """
    rules = get_reschedule_rules(ticket_type.upper())

    if not rules:
        return f"No reschedule rules found for ticket type: {ticket_type}"

    result = f"=== 改签规则 ({ticket_type.upper()}) ===\n\n"

    for rule in rules:
        changeable = "可改签" if rule.get("changeable") else "不可改签"
        penalty = f"{rule.get('penalty_rate', 0) * 100:.0f}%改签费" if rule.get("penalty_rate", 0) > 0 else "免费"
        condition = rule.get("condition", "无条件")

        result += f"规则: {rule.get('rule_name', 'N/A')}\n"
        result += f"  说明: {rule.get('description', 'N/A')}\n"
        result += f"  改签: {changeable}\n"
        result += f"  改签费: {penalty}\n"
        result += f"  条件: {condition}\n\n"

    return result


@tool
def lookup_membership_benefits(level: str) -> str:
    """Look up benefits for a specific membership level.

    Args:
        level: The membership level code (REG=普通, SIL=银卡, GLD=金卡, PLT=白金)

    Returns:
        A formatted string containing all benefits for the membership level.
    """
    benefits = get_membership_benefits(level.upper())

    if not benefits:
        return f"No benefits found for membership level: {level}"

    result = f"=== 会员权益 ({level.upper()}) ===\n\n"

    for benefit in benefits:
        benefit_type = benefit.get("type", "N/A")
        desc = benefit.get("description", "N/A")

        if benefit_type == "refund_discount":
            rate = benefit.get("discount_rate", 0)
            result += f"退票费减免: {desc} ({rate * 100:.0f}%减免)\n"
        elif benefit_type == "free_change":
            result += f"免费改签: {desc}\n"
        elif benefit_type == "refund_exemption":
            result += f"全额退票: {desc}\n"
        else:
            result += f"{benefit_type}: {desc}\n"

    return result


@tool
def check_flight_exception(exception_type: str) -> str:
    """Check if a specific exception condition applies.

    Args:
        exception_type: The exception type, one of:
            - "航班取消" (Flight Cancelled)
            - "航班延误超过2小时" (Flight Delayed over 2 hours)
            - "会员帮困订票" (Compassionate Booking for Member)

    Returns:
        A formatted string describing if the exception applies and its consequences.
    """
    result = check_exception(exception_type)

    if not result.get("found"):
        return f"未找到例外规则: {exception_type}"

    return f"""=== 例外情况适用 ===

例外: {result.get('exception_name', 'N/A')}
说明: {result.get('exception_description', 'N/A')}

触发规则: {result.get('rule_name', 'N/A')}
规则说明: {result.get('rule_description', 'N/A')}

结果:
  - 退票: {'可退票' if result.get('refundable') else '不可退票'}
  - 手续费: {'免费' if result.get('penalty_rate', 1) == 0 else f'{result.get("penalty_rate", 0) * 100:.0f}%'}
"""


@tool
def lookup_all_ticket_rules(ticket_type: str) -> str:
    """Look up all rules (refund, reschedule) for a specific ticket type.

    This is a convenience tool that returns comprehensive rule information.

    Args:
        ticket_type: The ticket type code (ECO, BUS, FST, DIS)
    """
    refund_info = lookup_refund_rules.invoke(ticket_type)
    change_info = lookup_reschedule_rules.invoke(ticket_type)

    return f"{refund_info}\n{change_info}"
