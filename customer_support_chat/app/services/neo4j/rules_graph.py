# neo4j/rules_graph.py - Knowledge graph for booking rules

from .connection import get_neo4j


# =============================================================================
# Initialization Queries - Run once to populate the knowledge graph
# =============================================================================

INITIALIZE_QUERIES = [
    # -------------------------------------------------------------------------
    # Ticket Types
    # -------------------------------------------------------------------------
    """
    MERGE (t:TicketType {name: 'Economy', code: 'ECO', description: '经济舱'})
    MERGE (t:TicketType {name: 'Business', code: 'BUS', description: '商务舱'})
    MERGE (t:TicketType {name: 'FirstClass', code: 'FST', description: '头等舱'})
    MERGE (t:TicketType {name: 'Discount', code: 'DIS', description: '特价票'})
    """,

    # -------------------------------------------------------------------------
    # Membership Levels
    # -------------------------------------------------------------------------
    """
    MERGE (m:MembershipLevel {name: 'Regular', code: 'REG', tier: 0, description: '普通会员'})
    MERGE (m:MembershipLevel {name: 'Silver', code: 'SIL', tier: 1, description: '银卡会员'})
    MERGE (m:MembershipLevel {name: 'Gold', code: 'GLD', tier: 2, description: '金卡会员'})
    MERGE (m:MembershipLevel {name: 'Platinum', code: 'PLT', tier: 3, description: '白金会员'})
    """,

    # -------------------------------------------------------------------------
    # Flight Types
    # -------------------------------------------------------------------------
    """
    MERGE (f:FlightType {name: 'Domestic', code: 'DOM', description: '国内航班'})
    MERGE (f:FlightType {name: 'International', code: 'INT', description: '国际航班'})
    MERGE (f:FlightType {name: 'Special', code: 'SPC', description: '特价航班'})
    MERGE (f:FlightType {name: 'Charter', code: 'CHT', description: '包机'})
    """,

    # -------------------------------------------------------------------------
    # Refund Rules
    # -------------------------------------------------------------------------
    """
    // 规则1: 经济舱 - 起飞前24小时外免费退票
    MATCH (t:TicketType {code: 'ECO'})
    MERGE (r:Rule {id: 'REFUND_ECO_24H', type: 'refund', name: '经济舱24小时外退票规则'})
    SET r.description = '经济舱机票，起飞前24小时外申请退票，免收退票费',
        r.refundable = true,
        r.penalty_rate = 0.0
    MERGE (t)-[:HAS_REFUND_RULE]->(r)

    MERGE (c:Condition {id: 'TIME_BEFORE_24H', type: 'time', name: '起飞前24小时外'})
    SET c.description = '航班起飞时间距离当前时间超过24小时'
    MERGE (r)-[:APPLIES_IF]->(c)
    """,

    """
    // 规则2: 经济舱 - 起飞前24小时内退票，收取10%手续费
    MATCH (t:TicketType {code: 'ECO'})
    MERGE (r:Rule {id: 'REFUND_ECO_WITHIN_24H', type: 'refund', name: '经济舱24小时内退票规则'})
    SET r.description = '经济舱机票，起飞前24小时内申请退票，收取票面价10%作为退票费',
        r.refundable = true,
        r.penalty_rate = 0.1
    MERGE (t)-[:HAS_REFUND_RULE]->(r)

    MERGE (c:Condition {id: 'TIME_WITHIN_24H', type: 'time', name: '起飞前24小时内'})
    SET c.description = '航班起飞时间距离当前时间不足24小时'
    MERGE (r)-[:APPLIES_IF]->(c)
    """,

    """
    // 规则3: 商务舱 - 起飞前4小时外免费退票
    MATCH (t:TicketType {code: 'BUS'})
    MERGE (r:Rule {id: 'REFUND_BUS_4H', type: 'refund', name: '商务舱4小时外退票规则'})
    SET r.description = '商务舱机票，起飞前4小时外申请退票，免收退票费',
        r.refundable = true,
        r.penalty_rate = 0.0
    MERGE (t)-[:HAS_REFUND_RULE]->(r)

    MERGE (c:Condition {id: 'TIME_BEFORE_4H', type: 'time', name: '起飞前4小时外'})
    SET c.description = '航班起飞时间距离当前时间超过4小时'
    MERGE (r)-[:APPLIES_IF]->(c)
    """,

    """
    // 规则4: 商务舱 - 起飞前4小时内收取5%手续费
    MATCH (t:TicketType {code: 'BUS'})
    MERGE (r:Rule {id: 'REFUND_BUS_WITHIN_4H', type: 'refund', name: '商务舱4小时内退票规则'})
    SET r.description = '商务舱机票，起飞前4小时内申请退票，收取票面价5%作为退票费',
        r.refundable = true,
        r.penalty_rate = 0.05
    MERGE (t)-[:HAS_REFUND_RULE]->(r)

    MERGE (c:Condition {id: 'TIME_WITHIN_4H', type: 'time', name: '起飞前4小时内'})
    SET c.description = '航班起飞时间距离当前时间不足4小时'
    MERGE (r)-[:APPLIES_IF]->(c)
    """,

    """
    // 规则5: 特价票 - 不可退票
    MATCH (t:TicketType {code: 'DIS'})
    MERGE (r:Rule {id: 'REFUND_DIS_NO', type: 'refund', name: '特价票不可退规则'})
    SET r.description = '特价机票不可申请退票',
        r.refundable = false,
        r.penalty_rate = 1.0
    MERGE (t)-[:HAS_REFUND_RULE]->(r)

    MERGE (c:Condition {id: 'ALWAYS', type: 'time', name: '任何时间'})
    SET c.description = '无条件适用'
    MERGE (r)-[:APPLIES_IF]->(c)
    """,

    # -------------------------------------------------------------------------
    # Reschedule (Change) Rules
    # -------------------------------------------------------------------------
    """
    // 改签规则: 经济舱 - 起飞前12小时外免费改签
    MATCH (t:TicketType {code: 'ECO'})
    MERGE (r:Rule {id: 'CHANGE_ECO_12H', type: 'reschedule', name: '经济舱12小时外改签规则'})
    SET r.description = '经济舱机票，起飞前12小时外申请改签，免收改签费',
        r.changeable = true,
        r.penalty_rate = 0.0
    MERGE (t)-[:HAS_RESCHEDULE_RULE]->(r)

    MERGE (c:Condition {id: 'TIME_BEFORE_12H', type: 'time', name: '起飞前12小时外'})
    SET c.description = '航班起飞时间距离当前时间超过12小时'
    MERGE (r)-[:APPLIES_IF]->(c)
    """,

    """
    // 改签规则: 经济舱 - 起飞前12小时内收取15%改签费
    MATCH (t:TicketType {code: 'ECO'})
    MERGE (r:Rule {id: 'CHANGE_ECO_WITHIN_12H', type: 'reschedule', name: '经济舱12小时内改签规则'})
    SET r.description = '经济舱机票，起飞前12小时内申请改签，收取票面价15%作为改签费',
        r.changeable = true,
        r.penalty_rate = 0.15
    MERGE (t)-[:HAS_RESCHEDULE_RULE]->(r)

    MERGE (c:Condition {id: 'TIME_WITHIN_12H', type: 'time', name: '起飞前12小时内'})
    SET c.description = '航班起飞时间距离当前时间不足12小时'
    MERGE (r)-[:APPLIES_IF]->(c)
    """,

    """
    // 改签规则: 商务舱 - 全程免费改签
    MATCH (t:TicketType {code: 'BUS'})
    MERGE (r:Rule {id: 'CHANGE_BUS_FREE', type: 'reschedule', name: '商务舱免费改签规则'})
    SET r.description = '商务舱机票，可在任意时间免费改签',
        r.changeable = true,
        r.penalty_rate = 0.0
    MERGE (t)-[:HAS_RESCHEDULE_RULE]->(r)

    MERGE (c:Condition {id: 'ALWAYS', type: 'time', name: '任何时间'})
    SET c.description = '无条件适用'
    MERGE (r)-[:APPLIES_IF]->(c)
    """,

    """
    // 改签规则: 头等舱 - 全程免费改签
    MATCH (t:TicketType {code: 'FST'})
    MERGE (r:Rule {id: 'CHANGE_FST_FREE', type: 'reschedule', name: '头等舱免费改签规则'})
    SET r.description = '头等舱机票，可在任意时间免费改签',
        r.changeable = true,
        r.penalty_rate = 0.0
    MERGE (t)-[:HAS_RESCHEDULE_RULE]->(r)

    MERGE (c:Condition {id: 'ALWAYS', type: 'time', name: '任何时间'})
    SET c.description = '无条件适用'
    MERGE (r)-[:APPLIES_IF]->(c)
    """,

    """
    // 改签规则: 特价票 - 不可改签
    MATCH (t:TicketType {code: 'DIS'})
    MERGE (r:Rule {id: 'CHANGE_DIS_NO', type: 'reschedule', name: '特价票不可改签规则'})
    SET r.description = '特价机票不可申请改签',
        r.changeable = false,
        r.penalty_rate = 1.0
    MERGE (t)-[:HAS_RESCHEDULE_RULE]->(r)

    MERGE (c:Condition {id: 'ALWAYS', type: 'time', name: '任何时间'})
    SET c.description = '无条件适用'
    MERGE (r)-[:APPLIES_IF]->(c)
    """,

    # -------------------------------------------------------------------------
    # Membership Benefits
    # -------------------------------------------------------------------------
    """
    // 银卡会员: 额外10%退票费减免
    MATCH (m:MembershipLevel {code: 'SIL'})
    MERGE (b:Benefit {id: 'BEN_SIL_REFUND', type: 'refund_discount', name: '银卡退票费减免'})
    SET b.description = '银卡会员享受退票费额外10%减免',
        b.discount_rate = 0.1
    MERGE (m)-[:ENABLES]->(b)
    """,

    """
    // 金卡会员: 退票费减免25%，改签免费
    MATCH (m:MembershipLevel {code: 'GLD'})
    MERGE (b:Benefit {id: 'BEN_GLD_REFUND', type: 'refund_discount', name: '金卡退票费减免'})
    SET b.description = '金卡会员享受退票费25%减免',
        b.discount_rate = 0.25
    MERGE (m)-[:ENABLES]->(b)

    MERGE (b2:Benefit {id: 'BEN_GLD_CHANGE', type: 'free_change', name: '金卡免费改签'})
    SET b2.description = '金卡会员享受免费改签',
        b2.free = true
    MERGE (m)-[:ENABLES]->(b2)
    """,

    """
    // 白金会员: 退票费全免，改签免费
    MATCH (m:MembershipLevel {code: 'PLT'})
    MERGE (b:Benefit {id: 'BEN_PLT_REFUND', type: 'refund_exemption', name: '白金全额退票'})
    SET b.description = '白金会员享受全额退票（不限票种）',
        b.exemption = true
    MERGE (m)-[:ENABLES]->(b)

    MERGE (b2:Benefit {id: 'BEN_PLT_CHANGE', type: 'free_change', name: '白金免费改签'})
    SET b2.description = '白金会员享受免费改签（不限票种）',
        b2.free = true
    MERGE (m)-[:ENABLES]->(b2)
    """,

    # -------------------------------------------------------------------------
    # Exceptions
    # -------------------------------------------------------------------------
    """
    // 例外1: 航班取消 - 全额退款
    MERGE (e:Exception {id: 'EX_FLIGHT_CANCEL', name: '航班取消'})
    SET e.description = '若航班被取消，乘客可申请全额退款，无需支付退票费'

    MERGE (r:Rule {id: 'EX_REFUND_ON_CANCEL', type: 'exception', name: '航班取消全额退款'})
    SET r.description = '航班取消时适用全额退款例外规则',
        r.refundable = true,
        r.penalty_rate = 0.0
    MERGE (e)-[:TRIGGERS]->(r)
    """,

    """
    // 例外2: 航班延误超过2小时 - 可免费退票
    MERGE (e:Exception {id: 'EX_FLIGHT_DELAY_2H', name: '航班延误超过2小时'})
    SET e.description = '若航班延误超过2小时，乘客可申请免费退票'

    MERGE (r:Rule {id: 'EX_REFUND_ON_DELAY', type: 'exception', name: '延误2小时退票'})
    SET r.description = '航班延误超过2小时时适用免费退票例外规则',
        r.refundable = true,
        r.penalty_rate = 0.0
    MERGE (e)-[:TRIGGERS]->(r)
    """,

    """
    // 例外3: 会员帮困订票 - 豁免退票费
    MATCH (m:MembershipLevel {code: 'PLT'})
    MERGE (e:Exception {id: 'EX_COMPASSIONATE', name: '会员帮困订票'})
    SET e.description = '白金会员因帮困需要为直系亲属购票，可豁免退票费'
    MERGE (m)-[:CAN_TRIGGER]->(e)
    """,
]


def initialize_knowledge_graph():
    """Initialize the knowledge graph with booking rules"""
    neo4j = get_neo4j()

    if not neo4j.is_connected():
        print("Neo4j not connected, skipping knowledge graph initialization")
        return False

    try:
        # Clear existing data
        neo4j.run_query("MATCH (n) DETACH DELETE n")

        # Insert all rules
        for query in INITIALIZE_QUERIES:
            neo4j.run_query(query)

        print("Knowledge graph initialized successfully")
        return True
    except Exception as e:
        print(f"Failed to initialize knowledge graph: {e}")
        return False


def get_refund_rules(ticket_type: str = None) -> list:
    """Query refund rules, optionally filtered by ticket type"""
    neo4j = get_neo4j()

    if not neo4j.is_connected():
        return []

    if ticket_type:
        query = """
        MATCH (t:TicketType {code: $ticket_type})-[:HAS_REFUND_RULE]->(r:Rule)
        OPTIONAL MATCH (r)-[:APPLIES_IF]->(c:Condition)
        RETURN r.id as rule_id, r.name as rule_name, r.description as description,
               r.refundable as refundable, r.penalty_rate as penalty_rate,
               c.name as condition, c.description as condition_description
        """
        results = neo4j.run_query(query, {"ticket_type": ticket_type})
    else:
        query = """
        MATCH (t:TicketType)-[:HAS_REFUND_RULE]->(r:Rule)
        OPTIONAL MATCH (r)-[:APPLIES_IF]->(c:Condition)
        RETURN t.code as ticket_type, r.id as rule_id, r.name as rule_name,
               r.description as description, r.refundable as refundable,
               r.penalty_rate as penalty_rate, c.name as condition
        """
        results = neo4j.run_query(query)

    return [dict(record) for record in results]


def get_reschedule_rules(ticket_type: str = None) -> list:
    """Query reschedule rules, optionally filtered by ticket type"""
    neo4j = get_neo4j()

    if not neo4j.is_connected():
        return []

    if ticket_type:
        query = """
        MATCH (t:TicketType {code: $ticket_type})-[:HAS_RESCHEDULE_RULE]->(r:Rule)
        OPTIONAL MATCH (r)-[:APPLIES_IF]->(c:Condition)
        RETURN r.id as rule_id, r.name as rule_name, r.description as description,
               r.changeable as changeable, r.penalty_rate as penalty_rate,
               c.name as condition, c.description as condition_description
        """
        results = neo4j.run_query(query, {"ticket_type": ticket_type})
    else:
        query = """
        MATCH (t:TicketType)-[:HAS_RESCHEDULE_RULE]->(r:Rule)
        OPTIONAL MATCH (r)-[:APPLIES_IF]->(c:Condition)
        RETURN t.code as ticket_type, r.id as rule_id, r.name as rule_name,
               r.description as description, r.changeable as changeable,
               r.penalty_rate as penalty_rate, c.name as condition
        """
        results = neo4j.run_query(query)

    return [dict(record) for record in results]


def get_membership_benefits(level: str) -> list:
    """Query benefits for a membership level"""
    neo4j = get_neo4j()

    if not neo4j.is_connected():
        return []

    query = """
    MATCH (m:MembershipLevel {code: $level})-[:ENABLES]->(b:Benefit)
    RETURN b.id as benefit_id, b.name as benefit_name,
           b.description as description, b.discount_rate as discount_rate,
           b.free as free, b.exemption as exemption
    """
    results = neo4j.run_query(query, {"level": level})
    return [dict(record) for record in results]


def check_exception(exception_name: str) -> dict:
    """Check if an exception applies and returns the triggered rule"""
    neo4j = get_neo4j()

    if not neo4j.is_connected():
        return {"found": False}

    query = """
    MATCH (e:Exception {name: $name})-[:TRIGGERS]->(r:Rule)
    RETURN e.id as exception_id, e.name as exception_name, e.description as exception_description,
           r.id as rule_id, r.name as rule_name, r.description as rule_description,
           r.refundable as refundable, r.penalty_rate as penalty_rate
    """
    results = neo4j.run_query(query, {"name": exception_name})

    if results:
        return {"found": True, **dict(results[0])}
    return {"found": False}
