"""
API routes: dashboard metrics, deviation management, agent execution, and action centre.
"""
import json
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
import aiosqlite

from app.models.database import get_db
from app.agents.deviation_agent import run_deviation_agent
from app.services.graph import get_dashboard_metrics, build_supply_chain_graph, get_supplier_risk_distribution

router = APIRouter(prefix="/api")


# Imported Kaggle datasets are told apart by ID prefix
SOURCE_PREFIXES = {"dataco": "DC-", "scms": "SC-"}


def source_clause(column: str, source: str = None) -> str:
    """SQL filter on data source: 'dataco' (DC-*), 'scms' (SC-*), 'kaggle' (both), 'synthetic' (seed data)."""
    if source in SOURCE_PREFIXES:
        return f" AND {column} LIKE '{SOURCE_PREFIXES[source]}%'"
    likes = [f"{column} LIKE '{p}%'" for p in SOURCE_PREFIXES.values()]
    if source == "kaggle":
        return f" AND ({' OR '.join(likes)})"
    if source == "synthetic":
        return f" AND NOT ({' OR '.join(likes)})"
    return ""


@router.get("/dashboard")
async def dashboard_metrics():
    metrics = await get_dashboard_metrics()
    risk_dist = await get_supplier_risk_distribution()
    return {**metrics, "supplier_risk_by_region": risk_dist}


@router.get("/deviations")
async def list_deviations(resolved: int = 0, limit: int = 50, source: str = None,
                          db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute(f"""
        SELECT d.*, s.name as supplier_name, s.strategic_tier, s.country as supplier_country
        FROM deviations d
        JOIN suppliers s ON s.id = d.supplier_id
        WHERE d.resolved = ?{source_clause("d.id", source)}
        ORDER BY d.detected_at DESC
        LIMIT ?
    """, (resolved, limit)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]

    for r in rows:
        r["affected_customers"] = json.loads(r["affected_customers"]) if r["affected_customers"] else []
    return rows


@router.get("/deviations/{dev_id}")
async def get_deviation(dev_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("""
        SELECT d.*, s.name as supplier_name, s.strategic_tier, s.reliability_score,
               s.port_of_origin, s.country as supplier_country, s.annual_spend_usd
        FROM deviations d
        JOIN suppliers s ON s.id = d.supplier_id
        WHERE d.id = ?
    """, (dev_id,)) as cur:
        row = await cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Deviation not found")

    result = dict(row)
    result["affected_customers"] = json.loads(result["affected_customers"]) if result["affected_customers"] else []

    # Fetch recommendations
    async with db.execute(
        "SELECT * FROM agent_recommendations WHERE deviation_id = ? ORDER BY created_at DESC",
        (dev_id,)
    ) as cur:
        result["recommendations"] = [dict(r) for r in await cur.fetchall()]

    # Fetch PO details
    async with db.execute("SELECT * FROM purchase_orders WHERE id = ?", (result["po_id"],)) as cur:
        po = await cur.fetchone()
        if po:
            result["purchase_order"] = dict(po)

    return result


@router.post("/deviations/{dev_id}/run-agent")
async def trigger_agent(dev_id: str, db: aiosqlite.Connection = Depends(get_db)):
    """Run the LangGraph agent against a specific deviation and persist the recommendation."""
    async with db.execute("SELECT * FROM deviations WHERE id = ?", (dev_id,)) as cur:
        dev = await cur.fetchone()
    if not dev:
        raise HTTPException(status_code=404, detail="Deviation not found")

    async with db.execute("SELECT * FROM suppliers WHERE id = ?", (dict(dev)["supplier_id"],)) as cur:
        supplier = await cur.fetchone()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    dev_dict = dict(dev)
    sup_dict = dict(supplier)

    # Kaggle suppliers: alternatives are other suppliers from the same dataset and region
    # with better measured on-time reliability (synthetic suppliers keep the mock pool)
    alternative_pool = []
    prefix = next((p for p in SOURCE_PREFIXES.values() if sup_dict["id"].startswith(p)), None)
    if prefix:
        async with db.execute("""
            SELECT name FROM suppliers
            WHERE id LIKE ? AND id != ? AND region = ? AND reliability_score > ?
            ORDER BY reliability_score DESC, annual_spend_usd DESC LIMIT 3
        """, (prefix + "%", sup_dict["id"], sup_dict["region"], sup_dict["reliability_score"])) as cur:
            alternative_pool = [r["name"] for r in await cur.fetchall()]

    result = await run_deviation_agent(dev_dict, sup_dict, alternative_pool)

    rec_id = result["recommendation_id"]
    now = datetime.now().isoformat()

    await db.execute("""
        INSERT INTO agent_recommendations
        (id, deviation_id, action, reasoning, draft_communication, requires_approval,
         status, created_at, alternative_suppliers, estimated_cost_impact_usd)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (
        rec_id, dev_id, result["selected_action"], result["reasoning"],
        result.get("draft_communication"), 1 if result["requires_approval"] else 0,
        "pending", now,
        json.dumps(result.get("alternative_suppliers", [])),
        result.get("estimated_cost_impact", 0)
    ))

    await db.execute("UPDATE deviations SET agent_activated = 1 WHERE id = ?", (dev_id,))
    await db.commit()

    return {
        "recommendation_id": rec_id,
        "action": result["selected_action"],
        "reasoning": result["reasoning"],
        "requires_approval": result["requires_approval"],
        "draft_communication": result.get("draft_communication"),
        "alternative_suppliers": result.get("alternative_suppliers", []),
        "estimated_cost_impact_usd": result.get("estimated_cost_impact", 0),
        "agent_messages": result.get("messages", []),
    }


@router.get("/recommendations")
async def list_recommendations(status: str = "pending", db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("""
        SELECT r.*, d.deviation_type, d.severity, d.financial_exposure_usd,
               d.po_id, s.name as supplier_name
        FROM agent_recommendations r
        JOIN deviations d ON d.id = r.deviation_id
        JOIN suppliers s ON s.id = d.supplier_id
        WHERE r.status = ?
        ORDER BY r.created_at DESC
    """, (status,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]

    for r in rows:
        if r.get("alternative_suppliers"):
            try:
                r["alternative_suppliers"] = json.loads(r["alternative_suppliers"])
            except Exception:
                r["alternative_suppliers"] = []
    return rows


@router.post("/recommendations/{rec_id}/approve")
async def approve_recommendation(rec_id: str, db: aiosqlite.Connection = Depends(get_db)):
    now = datetime.now().isoformat()
    await db.execute(
        "UPDATE agent_recommendations SET status='approved', approved_by='Operations Manager', executed_at=? WHERE id=?",
        (now, rec_id)
    )
    # Mark deviation resolved if approved
    async with db.execute("SELECT deviation_id FROM agent_recommendations WHERE id=?", (rec_id,)) as cur:
        row = await cur.fetchone()
    if row:
        await db.execute("UPDATE deviations SET resolved=1 WHERE id=?", (row["deviation_id"],))
    await db.commit()
    return {"status": "approved", "executed_at": now}


@router.post("/recommendations/{rec_id}/reject")
async def reject_recommendation(rec_id: str, db: aiosqlite.Connection = Depends(get_db)):
    now = datetime.now().isoformat()
    await db.execute(
        "UPDATE agent_recommendations SET status='rejected', executed_at=? WHERE id=?",
        (now, rec_id)
    )
    await db.commit()
    return {"status": "rejected"}


@router.get("/graph")
async def supply_chain_graph(limit: int = 80):
    return await build_supply_chain_graph(limit=limit)


@router.get("/events")
async def recent_events(limit: int = 50, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute(
        "SELECT * FROM event_log ORDER BY timestamp DESC LIMIT ?", (limit,)
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


@router.get("/suppliers")
async def list_suppliers(source: str = None, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute(f"""
        SELECT s.*,
               COUNT(DISTINCT d.id) as active_deviations,
               COALESCE(SUM(d.financial_exposure_usd), 0) as total_exposure
        FROM suppliers s
        LEFT JOIN deviations d ON d.supplier_id = s.id AND d.resolved = 0
        WHERE 1=1{source_clause("s.id", source)}
        GROUP BY s.id
        ORDER BY s.strategic_tier, s.annual_spend_usd DESC
    """) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    for r in rows:
        r["categories"] = json.loads(r["categories"]) if r["categories"] else []
    return rows


@router.get("/purchase-orders")
async def list_pos(status: str = None, limit: int = 50, source: str = None,
                   db: aiosqlite.Connection = Depends(get_db)):
    # Kaggle orders are historical (SCMS 2006–2015, DataCo 2015–2018), so show the most recent first
    order = " ORDER BY p.created_date DESC" if source in ("kaggle", *SOURCE_PREFIXES) else ""
    if status:
        async with db.execute(
            f"SELECT p.*, s.name as supplier_name FROM purchase_orders p JOIN suppliers s ON s.id=p.supplier_id WHERE p.status=?{source_clause('p.id', source)}{order} LIMIT ?",
            (status, limit)
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    else:
        async with db.execute(
            f"SELECT p.*, s.name as supplier_name FROM purchase_orders p JOIN suppliers s ON s.id=p.supplier_id WHERE 1=1{source_clause('p.id', source)}{order} LIMIT ?",
            (limit,)
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    for r in rows:
        r["line_items"] = json.loads(r["line_items"]) if r["line_items"] else []
    return rows


@router.get("/customer-orders")
async def list_customer_orders(po_id: str = None, customer_id: str = None,
                                limit: int = 50, db: aiosqlite.Connection = Depends(get_db)):
    """Customer orders, optionally filtered by PO or customer."""
    if po_id:
        async with db.execute("""
            SELECT co.*, c.name as customer_name, c.segment
            FROM customer_orders co
            JOIN customers c ON c.id = co.customer_id
            WHERE co.po_id = ? LIMIT ?
        """, (po_id, limit)) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    elif customer_id:
        async with db.execute("""
            SELECT co.*, c.name as customer_name, c.segment
            FROM customer_orders co
            JOIN customers c ON c.id = co.customer_id
            WHERE co.customer_id = ? LIMIT ?
        """, (customer_id, limit)) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    else:
        async with db.execute("""
            SELECT co.*, c.name as customer_name, c.segment
            FROM customer_orders co
            JOIN customers c ON c.id = co.customer_id
            LIMIT ?
        """, (limit,)) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    return rows


@router.get("/deliveries")
async def list_deliveries(status: str = None, limit: int = 50,
                           db: aiosqlite.Connection = Depends(get_db)):
    """Delivery records with optional status filter."""
    if status:
        async with db.execute("""
            SELECT d.*, p.total_value_usd, s.name as supplier_name
            FROM deliveries d
            JOIN purchase_orders p ON p.id = d.po_id
            JOIN suppliers s ON s.id = p.supplier_id
            WHERE d.status = ? LIMIT ?
        """, (status, limit)) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    else:
        async with db.execute("""
            SELECT d.*, p.total_value_usd, s.name as supplier_name
            FROM deliveries d
            JOIN purchase_orders p ON p.id = d.po_id
            JOIN suppliers s ON s.id = p.supplier_id
            LIMIT ?
        """, (limit,)) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    for r in rows:
        if r.get("container_ids"):
            try:
                r["container_ids"] = json.loads(r["container_ids"])
            except Exception:
                pass
    return rows


@router.get("/customers")
async def list_customers(db: aiosqlite.Connection = Depends(get_db)):
    """Customer accounts with order summary stats."""
    async with db.execute("""
        SELECT c.*,
               COUNT(DISTINCT co.id) as total_orders,
               SUM(co.value_usd) as total_order_value,
               COUNT(DISTINCT CASE WHEN co.status IN ('at_risk','delayed') THEN co.id END) as at_risk_orders
        FROM customers c
        LEFT JOIN customer_orders co ON co.customer_id = c.id
        GROUP BY c.id
        ORDER BY c.annual_revenue_usd DESC
    """) as cur:
        return [dict(r) for r in await cur.fetchall()]


@router.get("/stats/summary")
async def system_summary(db: aiosqlite.Connection = Depends(get_db)):
    """High-level system statistics for the research page and reporting."""
    async with db.execute("SELECT COUNT(*) as n FROM suppliers") as c:
        n_suppliers = (await c.fetchone())["n"]
    async with db.execute("SELECT COUNT(*) as n FROM purchase_orders") as c:
        n_pos = (await c.fetchone())["n"]
    async with db.execute("SELECT COUNT(*) as n FROM customers") as c:
        n_customers = (await c.fetchone())["n"]
    async with db.execute("SELECT COUNT(*) as n FROM customer_orders") as c:
        n_cordrs = (await c.fetchone())["n"]
    async with db.execute("SELECT COUNT(*) as n FROM deliveries") as c:
        n_deliveries = (await c.fetchone())["n"]
    async with db.execute("SELECT COUNT(*) as n FROM deviations") as c:
        n_devs = (await c.fetchone())["n"]
    async with db.execute("SELECT COUNT(*) as n FROM agent_recommendations") as c:
        n_recs = (await c.fetchone())["n"]
    async with db.execute("SELECT COUNT(*) as n FROM event_log") as c:
        n_events = (await c.fetchone())["n"]
    kaggle = {}
    for name, prefix in SOURCE_PREFIXES.items():
        async with db.execute("""
            SELECT (SELECT COUNT(*) FROM suppliers WHERE id LIKE ?1) AS suppliers,
                   (SELECT COUNT(*) FROM purchase_orders WHERE id LIKE ?1) AS orders,
                   (SELECT COUNT(*) FROM deviations WHERE id LIKE ?1) AS deviations
        """, (prefix + "%",)) as c:
            kaggle[name] = dict(await c.fetchone())
    return {
        "kaggle_dataco": kaggle["dataco"],
        "kaggle_scms": kaggle["scms"],
        "suppliers": n_suppliers,
        "purchase_orders": n_pos,
        "customers": n_customers,
        "customer_orders": n_cordrs,
        "deliveries": n_deliveries,
        "deviations": n_devs,
        "agent_recommendations": n_recs,
        "event_log_entries": n_events,
    }



# Insights aggregate the full imported tables (DataCo takes ~3 s), but that data only changes on
# re-import — so results are cached per table, keyed by its row count to notice a re-import.
_insights_cache: dict = {}


async def _cached_insights(db, table: str, build):
    async with db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)) as cur:
        if not await cur.fetchone():
            return {"imported": False}
    async with db.execute(f"SELECT COUNT(*) FROM {table}") as cur:
        n = (await cur.fetchone())[0]
    hit = _insights_cache.get(table)
    if hit and hit[0] == n:
        return hit[1]
    result = await build(db)
    _insights_cache[table] = (n, result)
    return result


@router.get("/kaggle/insights")
async def kaggle_insights(db: aiosqlite.Connection = Depends(get_db)):
    """Analytics over the imported Kaggle DataCo order lines (real, not simulated, outcomes)."""
    return await _cached_insights(db, "kaggle_dataco_items", _dataco_insights)


async def _dataco_insights(db):

    # One row per order: shipping outcome fields are order-level in DataCo
    orders_cte = """
        WITH o AS (
            SELECT order_id, MIN(order_date) AS order_date, shipping_mode, market,
                   delivery_status, order_status,
                   MAX(days_shipping_real) - MAX(days_shipping_scheduled) AS delay,
                   SUM(order_item_total) AS value
            FROM kaggle_dataco_items GROUP BY order_id
        )
    """

    async def rows(sql, params=()):
        async with db.execute(sql, params) as cur:
            return [dict(r) for r in await cur.fetchall()]

    totals = (await rows(orders_cte + """
        SELECT COUNT(*) AS orders, SUM(value) AS sales_usd,
               AVG(delivery_status = 'Late delivery') AS late_rate,
               AVG(CASE WHEN delivery_status = 'Late delivery' THEN delay END) AS avg_delay_days,
               SUM(order_status = 'SUSPECTED_FRAUD') AS suspected_fraud,
               MIN(order_date) AS first_order, MAX(order_date) AS last_order
        FROM o
    """))[0]
    async with db.execute("SELECT COUNT(*) AS n FROM kaggle_dataco_items") as cur:
        totals["order_lines"] = (await cur.fetchone())["n"]

    by_mode = await rows(orders_cte + """
        SELECT shipping_mode AS label, COUNT(*) AS orders,
               AVG(delivery_status = 'Late delivery') AS late_rate
        FROM o WHERE delivery_status != 'Shipping canceled'
        GROUP BY shipping_mode ORDER BY late_rate DESC
    """)
    by_market = await rows(orders_cte + """
        SELECT market AS label, COUNT(*) AS orders, SUM(value) AS sales_usd,
               AVG(delivery_status = 'Late delivery') AS late_rate
        FROM o WHERE delivery_status != 'Shipping canceled'
        GROUP BY market ORDER BY sales_usd DESC
    """)
    by_category = await rows("""
        SELECT category_name AS label, COUNT(*) AS lines, SUM(order_item_total) AS sales_usd,
               AVG(late_delivery_risk) AS late_rate
        FROM kaggle_dataco_items
        GROUP BY category_name ORDER BY sales_usd DESC LIMIT 10
    """)
    monthly = await rows(orders_cte + """
        SELECT SUBSTR(order_date, 1, 7) AS month, COUNT(*) AS orders, SUM(value) AS value_usd,
               AVG(delivery_status = 'Late delivery') AS late_rate
        FROM o GROUP BY month ORDER BY month
    """)
    return {"imported": True, "source": "Kaggle — DataCo Smart Supply Chain",
            "totals": totals, "by_shipping_mode": by_mode, "by_market": by_market,
            "top_categories": by_category, "monthly": monthly}


@router.get("/kaggle/scms/insights")
async def scms_insights(db: aiosqlite.Connection = Depends(get_db)):
    """Analytics over the imported USAID SCMS shipment lines (real delivery outcomes)."""
    return await _cached_insights(db, "kaggle_scms_lines", _scms_insights)


async def _scms_insights(db):

    async def rows(sql):
        async with db.execute(sql) as cur:
            return [dict(r) for r in await cur.fetchall()]

    totals = (await rows("""
        SELECT COUNT(*) AS lines, COUNT(DISTINCT po_number) AS pos, COUNT(DISTINCT vendor) AS vendors,
               COUNT(DISTINCT country) AS countries, SUM(line_value_usd) AS value_usd,
               SUM(freight_cost_usd) AS freight_usd,
               AVG(delay_days > 0) AS late_rate,
               AVG(CASE WHEN delay_days > 0 THEN delay_days END) AS avg_delay_days,
               AVG(record_lag_days > 14) AS late_receipt_rate,
               MIN(delivered_date) AS first_delivery, MAX(delivered_date) AS last_delivery
        FROM kaggle_scms_lines
    """))[0]
    by_mode = await rows("""
        SELECT COALESCE(shipment_mode, 'Unspecified') AS label, COUNT(*) AS lines,
               AVG(delay_days > 0) AS late_rate
        FROM kaggle_scms_lines GROUP BY label ORDER BY late_rate DESC
    """)
    by_product = await rows("""
        SELECT product_group AS label, COUNT(*) AS lines, SUM(line_value_usd) AS value_usd,
               AVG(delay_days > 0) AS late_rate
        FROM kaggle_scms_lines GROUP BY product_group ORDER BY value_usd DESC
    """)
    top_vendors = await rows("""
        SELECT vendor AS label, COUNT(*) AS lines, SUM(line_value_usd) AS value_usd,
               AVG(delay_days > 0) AS late_rate
        FROM kaggle_scms_lines GROUP BY vendor ORDER BY value_usd DESC LIMIT 8
    """)
    top_countries = await rows("""
        SELECT country AS label, COUNT(*) AS lines, SUM(line_value_usd) AS value_usd,
               AVG(delay_days > 0) AS late_rate
        FROM kaggle_scms_lines GROUP BY country ORDER BY value_usd DESC LIMIT 8
    """)
    monthly = await rows("""
        SELECT SUBSTR(delivered_date, 1, 7) AS month, COUNT(DISTINCT po_number) AS orders,
               SUM(line_value_usd) AS value_usd, AVG(delay_days > 0) AS late_rate
        FROM kaggle_scms_lines GROUP BY month ORDER BY month
    """)
    return {"imported": True, "source": "Kaggle — USAID SCMS Shipment Pricing",
            "totals": totals, "by_shipment_mode": by_mode, "by_product_group": by_product,
            "top_vendors": top_vendors, "top_countries": top_countries, "monthly": monthly}
