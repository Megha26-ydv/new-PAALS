"""
Digital twin: builds and queries a NetworkX graph of supply chain relationships.
Used for dependency analysis and deviation impact propagation.
"""
import json
import os
import aiosqlite

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.normpath(os.path.join(_HERE, "../../database/paals.db"))


async def build_supply_chain_graph(limit: int = 80) -> dict:
    """
    Directed graph: Supplier → PO → Customer Order → Customer.
    Returns JSON-serialisable structure for D3 force-directed rendering.
    """
    nodes = []
    edges = []
    node_set = set()

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute("""
            SELECT s.id, s.name, s.country, s.strategic_tier, s.reliability_score,
                   p.id as po_id, p.total_value_usd, p.status as po_status,
                   co.id as co_id, co.customer_id, co.value_usd as co_value, co.status as co_status,
                   c.name as customer_name, c.segment
            FROM suppliers s
            JOIN purchase_orders p ON p.supplier_id = s.id
            JOIN customer_orders co ON co.po_id = p.id
            JOIN customers c ON c.id = co.customer_id
            LIMIT ?
        """, (limit,)) as cur:
            rows = await cur.fetchall()

        async with db.execute("SELECT po_id, severity FROM deviations WHERE resolved = 0") as cur:
            deviation_map = {r["po_id"]: r["severity"] for r in await cur.fetchall()}

    for row in rows:
        sup_id = f"s_{row['id']}"
        po_id  = f"p_{row['po_id']}"
        co_id  = f"c_{row['co_id']}"
        cust_id = f"cust_{row['customer_id']}"

        if sup_id not in node_set:
            node_set.add(sup_id)
            nodes.append({"id": sup_id, "label": row["name"], "type": "supplier",
                          "tier": row["strategic_tier"], "country": row["country"],
                          "reliability": row["reliability_score"]})

        if po_id not in node_set:
            node_set.add(po_id)
            has_dev = row["po_id"] in deviation_map
            nodes.append({"id": po_id, "label": row["po_id"], "type": "po",
                          "value": row["total_value_usd"], "status": row["po_status"],
                          "has_deviation": has_dev,
                          "deviation_severity": deviation_map.get(row["po_id"])})

        if co_id not in node_set:
            node_set.add(co_id)
            nodes.append({"id": co_id, "label": row["co_id"], "type": "customer_order",
                          "value": row["co_value"], "status": row["co_status"]})

        if cust_id not in node_set:
            node_set.add(cust_id)
            nodes.append({"id": cust_id, "label": row["customer_name"], "type": "customer",
                          "segment": row["segment"]})

        edges.append({"source": sup_id, "target": po_id, "weight": float(row["total_value_usd"] or 0)})
        edges.append({"source": po_id,  "target": co_id, "weight": float(row["co_value"] or 0)})
        edges.append({"source": co_id,  "target": cust_id, "weight": float(row["co_value"] or 0)})

    return {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}


async def get_supplier_risk_distribution() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT s.region,
                   COUNT(DISTINCT d.id)          AS deviation_count,
                   COALESCE(SUM(d.financial_exposure_usd), 0) AS total_exposure,
                   AVG(s.reliability_score)       AS avg_reliability
            FROM suppliers s
            LEFT JOIN deviations d ON d.supplier_id = s.id AND d.resolved = 0
            GROUP BY s.region
            ORDER BY total_exposure DESC
        """) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_dashboard_metrics() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute("SELECT COUNT(*) AS cnt FROM deviations WHERE resolved = 0") as cur:
            active_devs = (await cur.fetchone())["cnt"]

        async with db.execute(
            "SELECT COUNT(*) AS cnt FROM agent_recommendations WHERE requires_approval = 1 AND status = 'pending'"
        ) as cur:
            pending_approvals = (await cur.fetchone())["cnt"]

        async with db.execute(
            "SELECT COALESCE(SUM(financial_exposure_usd), 0) AS total FROM deviations WHERE resolved = 0"
        ) as cur:
            exposure = (await cur.fetchone())["total"]

        async with db.execute(
            "SELECT COUNT(*) AS cnt FROM agent_recommendations WHERE DATE(created_at) = DATE('now')"
        ) as cur:
            actions_today = (await cur.fetchone())["cnt"]

        async with db.execute("""
            SELECT severity, COUNT(*) AS cnt
            FROM deviations WHERE resolved = 0
            GROUP BY severity
        """) as cur:
            severity_dist = {r["severity"]: r["cnt"] for r in await cur.fetchall()}

        async with db.execute("""
            SELECT deviation_type, COUNT(*) AS cnt,
                   SUM(financial_exposure_usd) AS exposure
            FROM deviations WHERE resolved = 0
            GROUP BY deviation_type
            ORDER BY exposure DESC
        """) as cur:
            deviation_types = [dict(r) for r in await cur.fetchall()]

    return {
        "active_deviations": active_devs,
        "pending_approvals": pending_approvals,
        "financial_exposure_usd": round(exposure, 2),
        "agent_actions_today": actions_today,
        "severity_distribution": severity_dist,
        "deviation_types": deviation_types,
    }
