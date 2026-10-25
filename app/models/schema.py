"""
Core data models for the supply chain operational database.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class DeviationType(str, Enum):
    LATE_DELIVERY = "late_delivery"
    INVOICE_MISMATCH = "invoice_mismatch"
    GOODS_RECEIPT_SKIP = "goods_receipt_skip"
    DUPLICATE_PAYMENT = "duplicate_payment"
    SUPPLIER_BLACKOUT = "supplier_blackout"
    CUSTOMS_HOLD = "customs_hold"
    QUALITY_REJECTION = "quality_rejection"
    SUSPECTED_FRAUD = "suspected_fraud"  # Kaggle DataCo orders flagged SUSPECTED_FRAUD


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"


class AgentAction(str, Enum):
    EVALUATE_ALTERNATIVES = "evaluate_alternatives"
    DRAFT_CUSTOMER_NOTICE = "draft_customer_notice"
    ESCALATE_TO_PROCUREMENT = "escalate_to_procurement"
    REROUTE_SHIPMENT = "reroute_shipment"
    HOLD_PAYMENT = "hold_payment"
    TRIGGER_QUALITY_AUDIT = "trigger_quality_audit"
    EMERGENCY_ORDER = "emergency_order"


class Supplier(BaseModel):
    id: str
    name: str
    country: str
    region: str
    port_of_origin: str
    lead_time_days: int
    reliability_score: float  # 0-1
    strategic_tier: int  # 1=critical, 2=preferred, 3=standard
    categories: List[str]
    currency: str
    annual_spend_usd: float


class PurchaseOrder(BaseModel):
    id: str
    supplier_id: str
    created_date: str
    expected_delivery: str
    actual_delivery: Optional[str]
    line_items: List[dict]
    total_value_usd: float
    status: str
    currency: str
    incoterm: str


class Deviation(BaseModel):
    id: str
    po_id: str
    supplier_id: str
    deviation_type: DeviationType
    detected_at: str
    severity: Severity
    delay_days: Optional[int]
    financial_exposure_usd: float
    affected_customers: List[str]
    description: str
    resolved: bool = False
    agent_activated: bool = False


class AgentRecommendation(BaseModel):
    id: str
    deviation_id: str
    action: AgentAction
    reasoning: str
    draft_communication: Optional[str]
    requires_approval: bool
    status: ActionStatus = ActionStatus.PENDING
    created_at: str
    executed_at: Optional[str]
    approved_by: Optional[str]
    alternative_suppliers: Optional[List[str]]
    estimated_cost_impact_usd: Optional[float]


class EventLog(BaseModel):
    id: str
    timestamp: str
    event_type: str
    entity_id: str
    entity_type: str
    message: str
    metadata: Optional[dict]
