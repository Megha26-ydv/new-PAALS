"""
SQLite database setup. Uses aiosqlite for async operations throughout the API.
"""
import aiosqlite
import os

# Resolve to project-root/database/paals.db regardless of cwd
_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.normpath(os.path.join(_HERE, "..", "..", "database", "paals.db"))


async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS suppliers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                country TEXT,
                region TEXT,
                port_of_origin TEXT,
                lead_time_days INTEGER,
                reliability_score REAL,
                strategic_tier INTEGER,
                categories TEXT,
                currency TEXT,
                annual_spend_usd REAL
            );

            CREATE TABLE IF NOT EXISTS purchase_orders (
                id TEXT PRIMARY KEY,
                supplier_id TEXT,
                created_date TEXT,
                expected_delivery TEXT,
                actual_delivery TEXT,
                line_items TEXT,
                total_value_usd REAL,
                status TEXT,
                currency TEXT,
                incoterm TEXT,
                FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
            );

            CREATE TABLE IF NOT EXISTS customers (
                id TEXT PRIMARY KEY,
                name TEXT,
                country TEXT,
                segment TEXT,
                annual_revenue_usd REAL,
                account_manager TEXT
            );

            CREATE TABLE IF NOT EXISTS deliveries (
                id TEXT PRIMARY KEY,
                po_id TEXT,
                origin_port TEXT,
                destination_port TEXT,
                carrier TEXT,
                vessel_name TEXT,
                scheduled_arrival TEXT,
                actual_arrival TEXT,
                status TEXT,
                container_ids TEXT,
                FOREIGN KEY (po_id) REFERENCES purchase_orders(id)
            );

            CREATE TABLE IF NOT EXISTS customer_orders (
                id TEXT PRIMARY KEY,
                customer_id TEXT,
                po_id TEXT,
                order_date TEXT,
                promised_delivery TEXT,
                value_usd REAL,
                status TEXT,
                items TEXT
            );

            CREATE TABLE IF NOT EXISTS deviations (
                id TEXT PRIMARY KEY,
                po_id TEXT,
                supplier_id TEXT,
                deviation_type TEXT,
                detected_at TEXT,
                severity TEXT,
                delay_days INTEGER,
                financial_exposure_usd REAL,
                affected_customers TEXT,
                description TEXT,
                resolved INTEGER DEFAULT 0,
                agent_activated INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS agent_recommendations (
                id TEXT PRIMARY KEY,
                deviation_id TEXT,
                action TEXT,
                reasoning TEXT,
                draft_communication TEXT,
                requires_approval INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                executed_at TEXT,
                approved_by TEXT,
                alternative_suppliers TEXT,
                estimated_cost_impact_usd REAL,
                FOREIGN KEY (deviation_id) REFERENCES deviations(id)
            );

            CREATE TABLE IF NOT EXISTS event_log (
                id TEXT PRIMARY KEY,
                timestamp TEXT,
                event_type TEXT,
                entity_id TEXT,
                entity_type TEXT,
                message TEXT,
                metadata TEXT
            );
        """)
        await db.commit()
