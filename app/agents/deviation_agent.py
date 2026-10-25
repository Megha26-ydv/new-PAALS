"""
LangGraph-based agentic workflow for supply chain deviation processing.
The agent evaluates deviations, assesses downstream impact, and recommends actions.
Uses a mock LLM layer so the system runs without live API keys during demos.
"""
import json
import uuid
import random
from datetime import datetime
from typing import TypedDict, Optional, List, Annotated
from langgraph.graph import StateGraph, END
import operator


APPROVAL_EXPOSURE_THRESHOLD = 150000  # USD
CRITICAL_CUSTOMER_COUNT = 2
STRATEGIC_TIER_THRESHOLD = 1


class AgentState(TypedDict):
    deviation_id: str
    deviation_type: str
    severity: str
    financial_exposure: float
    affected_customers: List[str]
    supplier_tier: int
    supplier_name: str
    supplier_id: str
    po_id: str
    delay_days: Optional[int]
    description: str
    alternative_pool: List[str]  # DB-sourced alternatives (Kaggle lanes); empty → mock pool

    # Outputs built up through the workflow
    risk_level: str
    downstream_impact: dict
    selected_action: str
    reasoning: str
    draft_communication: Optional[str]
    requires_approval: bool
    alternative_suppliers: List[str]
    estimated_cost_impact: float
    recommendation_id: str
    messages: Annotated[List[str], operator.add]


# --- Node implementations ---

def evaluate_risk(state: AgentState) -> AgentState:
    """Classify operational risk based on exposure, severity, and supplier criticality."""
    exposure = state["financial_exposure"]
    severity = state["severity"]
    tier = state["supplier_tier"]
    n_customers = len(state["affected_customers"])

    if severity == "critical" or exposure > 400000 or (tier == 1 and n_customers >= CRITICAL_CUSTOMER_COUNT):
        risk = "critical"
    elif severity == "high" or exposure > 150000 or tier == 1:
        risk = "high"
    elif severity == "medium" or exposure > 50000:
        risk = "medium"
    else:
        risk = "low"

    return {**state, "risk_level": risk, "messages": [f"Risk evaluated as {risk.upper()}"]}


def assess_downstream_impact(state: AgentState) -> AgentState:
    """Estimate downstream impact on customer orders and production schedules."""
    n_affected = len(state["affected_customers"])
    delay = state["delay_days"] or 0

    # Simplified impact calculation — in production this would query the OCEL graph
    production_risk = "high" if delay > 10 or n_affected > 2 else ("medium" if delay > 5 else "low")
    revenue_at_risk = state["financial_exposure"] * (1.2 if n_affected > 2 else 1.0)

    impact = {
        "customer_orders_at_risk": n_affected,
        "production_risk": production_risk,
        "estimated_delay_days": delay,
        "revenue_at_risk_usd": round(revenue_at_risk, 2),
        "sla_breach_likely": delay > 7,
    }

    return {**state, "downstream_impact": impact, "messages": [f"Downstream: {n_affected} customer orders at risk, production risk={production_risk}"]}


def select_action_strategy(state: AgentState) -> AgentState:
    """Select the most appropriate intervention based on deviation type and risk profile."""
    dev_type = state["deviation_type"]
    risk = state["risk_level"]
    delay = state["delay_days"] or 0

    ACTION_MATRIX = {
        "late_delivery": {
            "critical": "reroute_shipment",
            "high": "evaluate_alternatives",
            "medium": "draft_customer_notice",
            "low": "draft_customer_notice",
        },
        "invoice_mismatch": {
            "critical": "hold_payment",
            "high": "hold_payment",
            "medium": "escalate_to_procurement",
            "low": "escalate_to_procurement",
        },
        "goods_receipt_skip": {
            "critical": "hold_payment",
            "high": "hold_payment",
            "medium": "escalate_to_procurement",
            "low": "escalate_to_procurement",
        },
        "customs_hold": {
            "critical": "emergency_order",
            "high": "evaluate_alternatives",
            "medium": "draft_customer_notice",
            "low": "draft_customer_notice",
        },
        "quality_rejection": {
            "critical": "trigger_quality_audit",
            "high": "trigger_quality_audit",
            "medium": "evaluate_alternatives",
            "low": "draft_customer_notice",
        },
        "supplier_blackout": {
            "critical": "emergency_order",
            "high": "evaluate_alternatives",
            "medium": "evaluate_alternatives",
            "low": "draft_customer_notice",
        },
        "suspected_fraud": {
            "critical": "hold_payment",
            "high": "hold_payment",
            "medium": "escalate_to_procurement",
            "low": "escalate_to_procurement",
        },
    }

    action = ACTION_MATRIX.get(dev_type, {}).get(risk, "draft_customer_notice")

    # Build reasoning narrative
    reasoning_parts = [
        f"Deviation type '{dev_type}' with {risk} risk profile.",
        f"Financial exposure: ${state['financial_exposure']:,.0f}.",
        f"Supplier: {state['supplier_name']} (Tier {state['supplier_tier']}).",
    ]
    if delay:
        reasoning_parts.append(f"Estimated delay: {delay} days.")
    reasoning_parts.append(f"Selected action: {action} based on operational impact matrix.")

    reasoning = " ".join(reasoning_parts)

    return {**state, "selected_action": action, "reasoning": reasoning, "messages": [f"Action selected: {action}"]}


def identify_alternatives(state: AgentState) -> AgentState:
    """Find alternative suppliers for the same commodity category (mock implementation)."""
    # In production: query supplier graph filtered by category and availability
    ALTERNATIVE_POOL = {
        "Electronics": ["Foxconn Precision Industries", "Hazel Circuits Pvt Ltd"],
        "Bearings": ["SKF Manufacturing (Pune)", "Kumho Precision Parts"],
        "Cables": ["Nexans Cable Solutions Morocco", "Sumitomo Electric Wiring Systems"],
        "Stamping": ["Gestamp Automocion (Bizkaia)", "Vietnam Precision Works Co."],
        "HVAC": ["Hanon Systems (Daegu)", "Mahle Filter Systems Thailand"],
    }
    alternatives = [a for a in state.get("alternative_pool") or [] if a != state["supplier_name"]]
    for cat, alts in ({} if alternatives else ALTERNATIVE_POOL).items():
        for alt in alts:
            if alt != state["supplier_name"] and alt not in alternatives:
                alternatives.append(alt)
            if len(alternatives) >= 3:
                break
        if len(alternatives) >= 3:
            break

    cost_premium = round(state["financial_exposure"] * random.uniform(0.05, 0.18), 2)

    return {**state, "alternative_suppliers": alternatives[:3], "estimated_cost_impact": cost_premium, "messages": [f"Identified {len(alternatives[:3])} alternative suppliers"]}


def draft_communication(state: AgentState) -> AgentState:
    """Compose a draft customer-facing notice based on deviation context."""
    action = state["selected_action"]
    affected_count = len(state["affected_customers"])
    delay = state["delay_days"]

    if action in ["draft_customer_notice", "reroute_shipment", "emergency_order"]:
        subject = f"Supply Disruption Notice — Order Impact Advisory"
        if delay:
            body = (
                f"We are writing to notify you of a disruption affecting orders linked to purchase order "
                f"{state['po_id']}. Due to {state['deviation_type'].replace('_',' ')}, "
                f"we anticipate a delay of approximately {delay} days.\n\n"
                f"Our procurement team has activated contingency sourcing with alternative suppliers. "
                f"We will provide a confirmed revised delivery date within 48 hours.\n\n"
                f"We apologise for the inconvenience and appreciate your continued partnership."
            )
        else:
            body = (
                f"We are writing to advise of a process exception on purchase order {state['po_id']} "
                f"that may affect your order fulfilment. Our operations team is investigating and "
                f"will confirm resolution within 24 hours."
            )
        draft = f"Subject: {subject}\n\n{body}"
    elif action == "hold_payment":
        draft = (
            f"INTERNAL MEMO — Accounts Payable\n\n"
            f"Payment for invoice associated with {state['po_id']} has been placed on hold pending "
            f"resolution of a {state['deviation_type'].replace('_',' ')} deviation. "
            f"Do not process payment until cleared by procurement compliance."
        )
    elif action == "trigger_quality_audit":
        draft = (
            f"QUALITY ALERT — {state['supplier_name']}\n\n"
            f"Incoming inspection has flagged a non-conformance on goods received under {state['po_id']}. "
            f"A full quality audit is required before these parts are released to production. "
            f"Supplier has been notified and return authorisation will be issued."
        )
    else:
        draft = None

    return {**state, "draft_communication": draft, "messages": ["Communication drafted" if draft else "No communication required for this action type"]}


def determine_approval_requirement(state: AgentState) -> AgentState:
    """Decide if human approval is required before executing the recommendation."""
    requires = (
        state["financial_exposure"] > APPROVAL_EXPOSURE_THRESHOLD
        or len(state["affected_customers"]) >= CRITICAL_CUSTOMER_COUNT
        or state["supplier_tier"] <= STRATEGIC_TIER_THRESHOLD
        or state["risk_level"] in ["critical", "high"]
    )

    reason = []
    if state["financial_exposure"] > APPROVAL_EXPOSURE_THRESHOLD:
        reason.append(f"exposure exceeds ${APPROVAL_EXPOSURE_THRESHOLD:,}")
    if len(state["affected_customers"]) >= CRITICAL_CUSTOMER_COUNT:
        reason.append(f"{len(state['affected_customers'])} customers affected")
    if state["supplier_tier"] <= STRATEGIC_TIER_THRESHOLD:
        reason.append("strategic tier supplier")
    if state["risk_level"] in ["critical", "high"]:
        reason.append(f"{state['risk_level']} risk classification")

    if requires:
        state["reasoning"] += f" Approval required: {', '.join(reason)}."

    return {**state, "requires_approval": requires, "messages": [f"Approval required: {requires}"]}


def finalise_recommendation(state: AgentState) -> AgentState:
    """Package the complete recommendation for storage and presentation."""
    rec_id = f"REC-{uuid.uuid4().hex[:8].upper()}"
    return {**state, "recommendation_id": rec_id, "messages": ["Recommendation finalised"]}


# --- Graph construction ---

def should_find_alternatives(state: AgentState):
    return "find_alternatives" if state["selected_action"] in ["evaluate_alternatives", "reroute_shipment", "emergency_order"] else "draft_communication"


def build_agent_graph():
    g = StateGraph(AgentState)

    g.add_node("evaluate_risk", evaluate_risk)
    g.add_node("assess_downstream", assess_downstream_impact)
    g.add_node("select_action", select_action_strategy)
    g.add_node("find_alternatives", identify_alternatives)
    g.add_node("draft_comm_node", draft_communication)
    g.add_node("determine_approval", determine_approval_requirement)
    g.add_node("finalise", finalise_recommendation)

    g.set_entry_point("evaluate_risk")
    g.add_edge("evaluate_risk", "assess_downstream")
    g.add_edge("assess_downstream", "select_action")
    g.add_conditional_edges("select_action", should_find_alternatives, {
        "find_alternatives": "find_alternatives",
        "draft_communication": "draft_comm_node",
    })
    g.add_edge("find_alternatives", "draft_comm_node")
    g.add_edge("draft_comm_node", "determine_approval")
    g.add_edge("determine_approval", "finalise")
    g.add_edge("finalise", END)

    return g.compile()


agent_graph = build_agent_graph()


async def run_deviation_agent(deviation: dict, supplier: dict, alternative_pool: Optional[List[str]] = None) -> dict:
    """Entry point for processing a deviation through the agent workflow."""
    initial_state: AgentState = {
        "deviation_id": deviation["id"],
        "deviation_type": deviation["deviation_type"],
        "severity": deviation["severity"],
        "financial_exposure": deviation["financial_exposure_usd"],
        "affected_customers": json.loads(deviation["affected_customers"]) if isinstance(deviation["affected_customers"], str) else deviation["affected_customers"],
        "supplier_tier": supplier["strategic_tier"],
        "supplier_name": supplier["name"],
        "supplier_id": supplier["id"],
        "po_id": deviation["po_id"],
        "delay_days": deviation.get("delay_days"),
        "description": deviation["description"],
        "alternative_pool": alternative_pool or [],
        "risk_level": "",
        "downstream_impact": {},
        "selected_action": "",
        "reasoning": "",
        "draft_communication": None,
        "requires_approval": False,
        "alternative_suppliers": [],
        "estimated_cost_impact": 0.0,
        "recommendation_id": "",
        "messages": [],
    }

    result = await agent_graph.ainvoke(initial_state)
    return result
