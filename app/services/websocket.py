"""
WebSocket manager for broadcasting live supply chain events to connected clients.
"""
import json
import asyncio
import random
import uuid
import os
from datetime import datetime
from typing import List
from fastapi import WebSocket
import aiosqlite

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.normpath(os.path.join(_HERE, "../../database/paals.db"))


class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()

# Event templates — realistic operational messages
EVENT_TEMPLATES = [
    ("deviation_detected",   "⚠",  "Deviation detected on {po_id}: {dev_type} — exposure ${exposure:,.0f}"),
    ("agent_activated",      "◈",  "Agent activated for {po_id}. Evaluating {dev_type} deviation."),
    ("alternative_evaluated","⬡",  "Alternative supplier identified: {supplier}. Lead time: {lead}d."),
    ("communication_drafted","✉",  "Customer advisory drafted for {n} affected order(s) on {po_id}."),
    ("escalated",            "↑",  "Escalated to procurement: {po_id}. Requires approval (${exposure:,.0f} exposure)."),
    ("approved",             "✓",  "Recommendation approved by {approver}. Executing action on {po_id}."),
    ("rejected",             "✗",  "Recommendation rejected. Manual review assigned for {po_id}."),
    ("resolved",             "●",  "Deviation {dev_id} resolved. Normal operations resumed."),
    ("shipment_update",      "→",  "Vessel {vessel} now {status} at {port}. ETA updated."),
    ("quality_hold",         "◉",  "Incoming quality hold on {po_id}. Batch quarantined pending audit."),
]

APPROVERS   = ["R. Torres", "S. Hofer", "A. Lindqvist", "J. Whitfield", "K. Mayer"]
SUPP_SHORT  = ["Foxconn Precision", "Tata Advanced Materials", "SKF Pune", "Gestamp Bizkaia", "Sumitomo Electric"]
VESSELS     = ["Maersk Emden", "MSC Rossella", "Hamburg Express", "Ever Given", "Kaiwa Bridge"]
PORTS       = ["Rotterdam", "Hamburg", "Felixstowe", "Busan", "Kaohsiung"]
DEV_TYPES   = ["late delivery", "invoice mismatch", "customs hold", "quality rejection", "supplier blackout"]


async def generate_live_event() -> dict:
    template_type, icon, template = random.choice(EVENT_TEMPLATES)
    po_id  = f"PO-{random.randint(1, 350):04d}"
    dev_id = f"DEV-{random.randint(1, 60):04d}"

    try:
        message = template.format(
            po_id=po_id, dev_id=dev_id,
            dev_type=random.choice(DEV_TYPES),
            exposure=random.uniform(20000, 600000),
            supplier=random.choice(SUPP_SHORT),
            lead=random.randint(10, 30),
            n=random.randint(1, 4),
            approver=random.choice(APPROVERS),
            vessel=random.choice(VESSELS),
            status=random.choice(["berthed", "in transit", "anchored", "departed"]),
            port=random.choice(PORTS),
        )
    except KeyError:
        message = f"Operational event recorded on {po_id}"

    event = {
        "id": uuid.uuid4().hex[:8],
        "timestamp": datetime.now().isoformat(),
        "type": template_type,
        "icon": icon,
        "message": message,
    }

    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO event_log VALUES (?,?,?,?,?,?,?)",
                (event["id"], event["timestamp"], template_type,
                 po_id, "purchase_order", message, None)
            )
            await db.commit()
    except Exception:
        pass

    return event


async def event_broadcaster():
    """Background task: emits events at randomised intervals to simulate live ops."""
    while True:
        await asyncio.sleep(random.uniform(4, 10))
        event = await generate_live_event()
        await manager.broadcast({"event": event})
