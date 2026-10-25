"""
Imports the Kaggle "DataCo Smart Supply Chain" dataset into the PAALS database.

Source: https://www.kaggle.com/datasets/shashwatwork/dataco-smart-supply-chain-for-big-data-analysis
        (original: Mendeley Data, doi:10.17632/8gx2fvg2k6.5, CC BY 4.0)

DataCo is a retailer's order/shipment log, so it is mapped onto the PAALS model as:

    DataCo                          PAALS
    ──────────────────────────────  ─────────────────────────────────────────────
    Market × Shipping Mode lane  →  supplier        DC-SUP-xx  (20 fulfilment lanes)
    Customer Segment × Market    →  customer        DC-CUST-xx (15 accounts)
    Order                        →  purchase order  DC-PO-<order id>
                                    delivery        DC-DLV-<order id>
                                    customer order  DC-CO-<order id>
    Late shipment (real > sched) →  deviation       late_delivery
    Order status SUSPECTED_FRAUD →  deviation       suspected_fraud
    Every order line             →  kaggle_dataco_items (cleaned raw rows for analytics)

Supplier reliability is the lane's real on-time shipping rate. A deviation is active
(unresolved) only if its order is still open and falls within the last
PAALS_KAGGLE_ACTIVE_DAYS days of the dataset (fraud flags stay open for review in
that window regardless of order status); everything older is history.

All imported IDs start with "DC-" so they sit alongside the synthetic seed data
without colliding. The import runs once; re-run with --force to rebuild it.

Usage:
    python -m app.services.kaggle_import            # import if not already present
    python -m app.services.kaggle_import --force    # delete DC-* rows and re-import
"""
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime

import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.normpath(os.path.join(_HERE, "..", ".."))
DB_PATH = os.path.join(_ROOT, "database", "paals.db")
CSV_PATH = os.environ.get(
    "PAALS_KAGGLE_CSV",
    os.path.join(_ROOT, "data", "kaggle", "DataCoSupplyChainDataset.csv"),
)
ACTIVE_DAYS = int(os.environ.get("PAALS_KAGGLE_ACTIVE_DAYS", "30"))

ID_PREFIX = "DC-"
SOURCE_NAME = "Kaggle DataCo Smart Supply Chain"

MARKET_REGION = {
    "LATAM": "Latin America",
    "Europe": "Europe",
    "Pacific Asia": "Asia Pacific",
    "USCA": "North America",
    "Africa": "Africa",
}
MODE_SHORT = {"Standard Class": "STD", "Second Class": "2ND", "First Class": "1ST", "Same Day": "SDY"}

OPEN_STATUSES = {"PENDING", "PENDING_PAYMENT", "PROCESSING", "ON_HOLD", "PAYMENT_REVIEW"}
PO_STATUS = {
    "COMPLETE": "delivered", "CLOSED": "delivered",
    "PENDING": "processing", "PROCESSING": "processing",
    "PENDING_PAYMENT": "confirmed", "PAYMENT_REVIEW": "on_hold", "ON_HOLD": "on_hold",
    "CANCELED": "cancelled", "SUSPECTED_FRAUD": "cancelled",
}

SEVERITIES = ["low", "medium", "high", "critical"]

# Raw columns kept in kaggle_dataco_items (PII-like and empty columns are dropped)
ITEM_COLUMNS = {
    "Order Item Id": "order_item_id",
    "Order Id": "order_id",
    "order date (DateOrders)": "order_date",
    "shipping date (DateOrders)": "shipping_date",
    "Type": "payment_type",
    "Days for shipping (real)": "days_shipping_real",
    "Days for shipment (scheduled)": "days_shipping_scheduled",
    "Delivery Status": "delivery_status",
    "Late_delivery_risk": "late_delivery_risk",
    "Order Status": "order_status",
    "Shipping Mode": "shipping_mode",
    "Market": "market",
    "Order Region": "order_region",
    "Order Country": "order_country",
    "Order City": "order_city",
    "Customer Id": "customer_id",
    "Customer Segment": "customer_segment",
    "Customer Country": "customer_country",
    "Customer City": "customer_city",
    "Department Name": "department_name",
    "Category Name": "category_name",
    "Product Card Id": "product_id",
    "Product Name": "product_name",
    "Product Price": "product_price",
    "Order Item Quantity": "quantity",
    "Order Item Discount": "discount",
    "Order Item Discount Rate": "discount_rate",
    "Sales": "sales",
    "Order Item Total": "order_item_total",
    "Order Profit Per Order": "order_profit",
    "Latitude": "store_latitude",
    "Longitude": "store_longitude",
}

ITEMS_DDL = """
CREATE TABLE IF NOT EXISTS kaggle_dataco_items (
    order_item_id INTEGER PRIMARY KEY,
    order_id INTEGER,
    order_date TEXT,
    shipping_date TEXT,
    payment_type TEXT,
    days_shipping_real INTEGER,
    days_shipping_scheduled INTEGER,
    delivery_status TEXT,
    late_delivery_risk INTEGER,
    order_status TEXT,
    shipping_mode TEXT,
    market TEXT,
    order_region TEXT,
    order_country TEXT,
    order_city TEXT,
    customer_id INTEGER,
    customer_segment TEXT,
    customer_country TEXT,
    customer_city TEXT,
    department_name TEXT,
    category_name TEXT,
    product_id INTEGER,
    product_name TEXT,
    product_price REAL,
    quantity INTEGER,
    discount REAL,
    discount_rate REAL,
    sales REAL,
    order_item_total REAL,
    order_profit REAL,
    store_latitude REAL,
    store_longitude REAL
);
CREATE INDEX IF NOT EXISTS idx_dataco_items_order ON kaggle_dataco_items(order_id);
"""


def _iso(ts) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%S")


def _bump(sev: str, n: int = 1) -> str:
    return SEVERITIES[min(SEVERITIES.index(sev) + n, len(SEVERITIES) - 1)]


def load_dataframe(csv_path: str = CSV_PATH) -> pd.DataFrame:
    df = pd.read_csv(csv_path, encoding="latin-1")
    df.columns = [c.strip() for c in df.columns]
    df["Product Name"] = df["Product Name"].str.strip()
    for col in ("order date (DateOrders)", "shipping date (DateOrders)"):
        df[col] = pd.to_datetime(df[col], format="%m/%d/%Y %H:%M")
    return df


def build_records(df: pd.DataFrame) -> dict:
    """Turn the item-level DataCo frame into PAALS table rows."""
    df = df.copy()
    df["lane"] = df["Market"] + "|" + df["Shipping Mode"]
    df["account"] = df["Customer Segment"] + "|" + df["Market"]

    orders = df.groupby("Order Id", sort=True).agg(
        order_date=("order date (DateOrders)", "first"),
        shipping_date=("shipping date (DateOrders)", "first"),
        real_days=("Days for shipping (real)", "first"),
        sched_days=("Days for shipment (scheduled)", "first"),
        delivery_status=("Delivery Status", "first"),
        order_status=("Order Status", "first"),
        shipping_mode=("Shipping Mode", "first"),
        market=("Market", "first"),
        lane=("lane", "first"),
        account=("account", "first"),
        segment=("Customer Segment", "first"),
        store_city=("Customer City", "first"),
        store_state=("Customer State", "first"),
        dest_city=("Order City", "first"),
        dest_country=("Order Country", "first"),
        value=("Order Item Total", "sum"),
    )
    orders["delay"] = orders["real_days"] - orders["sched_days"]
    orders["late"] = orders["delivery_status"] == "Late delivery"

    years = max((orders["order_date"].max() - orders["order_date"].min()).days / 365.25, 1.0)
    active_cutoff = orders["order_date"].max() - pd.Timedelta(days=ACTIVE_DAYS)

    # ── Suppliers: one per Market × Shipping Mode lane ─────────────────────────
    shipped = orders[orders["delivery_status"] != "Shipping canceled"]
    lane_stats = shipped.groupby("lane").agg(
        on_time=("late", lambda s: 1 - s.mean()),
        lead=("sched_days", "median"),
        value=("value", "sum"),
    )
    lane_value = orders.groupby("lane")["value"].sum().sort_values(ascending=False)
    lane_ids = {lane: f"DC-SUP-{i + 1:02d}" for i, lane in enumerate(lane_value.index)}
    top_cats = (
        df.groupby(["lane", "Category Name"])["Order Item Total"].sum()
        .sort_values(ascending=False).groupby(level=0).head(3)
    )
    # Tier by value share: top quarter strategic, next half preferred, rest standard
    n_lanes = len(lane_value)
    suppliers = []
    for rank, lane in enumerate(lane_value.index):
        market, mode = lane.split("|")
        tier = 1 if rank < n_lanes / 4 else (2 if rank < n_lanes * 3 / 4 else 3)
        cats = [c for (_, c) in top_cats.loc[[lane]].index]
        suppliers.append((
            lane_ids[lane], f"DataCo {market} · {mode}", "USA", MARKET_REGION.get(market, market),
            "DataCo Fulfilment (Caguas, PR)", int(lane_stats.at[lane, "lead"]),
            round(float(lane_stats.at[lane, "on_time"]), 3), tier, json.dumps(cats),
            "USD", round(float(lane_value[lane]) / years, 2),
        ))
    sup_by_lane = {lane: (lane_ids[lane], s[1], s[7]) for lane, s in zip(lane_value.index, suppliers)}

    # ── Customers: one per Segment × Market account ───────────────────────────
    acct_value = orders.groupby("account")["value"].sum().sort_values(ascending=False)
    acct_ids = {a: f"DC-CUST-{i + 1:02d}" for i, a in enumerate(acct_value.index)}
    customers = [
        (acct_ids[a], f"DataCo {a.split('|')[0]} — {a.split('|')[1]}", MARKET_REGION.get(a.split("|")[1], a.split("|")[1]),
         a.split("|")[0], round(float(v) / years, 2), "DataCo Sales")
        for a, v in acct_value.items()
    ]

    # ── Line items per order ──────────────────────────────────────────────────
    lines = (
        df.groupby(["Order Id", "Product Name"], sort=False)
        .agg(qty=("Order Item Quantity", "sum"), price=("Product Price", "first"))
        .reset_index()
    )
    lines["json"] = [
        json.dumps({"description": name, "qty": int(qty), "unit_price": round(float(price), 2)})
        for name, qty, price in zip(lines["Product Name"], lines["qty"], lines["price"])
    ]
    line_items = ("[" + lines.groupby("Order Id", sort=False)["json"].agg(", ".join) + "]").to_dict()

    pos, deliveries, corders, deviations = [], [], [], []
    for o in orders.itertuples():
        oid = o.Index
        sup_id, sup_name, tier = sup_by_lane[o.lane]
        cust_id = acct_ids[o.account]
        po_id = f"DC-PO-{oid}"
        created = _iso(o.order_date)
        expected = _iso(o.order_date + pd.Timedelta(days=int(o.sched_days)))
        cancelled = o.delivery_status == "Shipping canceled"
        actual = None if cancelled else _iso(o.shipping_date)
        value = round(float(o.value), 2)
        po_status = PO_STATUS.get(o.order_status, "processing")
        is_open = o.order_status in OPEN_STATUSES

        pos.append((po_id, sup_id, created, expected, actual, line_items[oid], value,
                    po_status, "USD", "DAP"))

        dlv_status = "cancelled" if cancelled else ("arrived" if po_status == "delivered" else "in_transit")
        deliveries.append((
            f"DC-DLV-{oid}", po_id, f"{o.store_city}, {o.store_state}",
            f"{o.dest_city}, {o.dest_country}", o.shipping_mode, None,
            expected, actual, dlv_status, json.dumps([]),
        ))

        if cancelled:
            co_status = "cancelled"
        elif po_status == "delivered":
            co_status = "delivered"
        else:
            co_status = "delayed" if o.late else "pending"
        corders.append((f"DC-CO-{oid}", cust_id, po_id, created, expected, value,
                        co_status, line_items[oid]))

        # ── Deviations from real outcomes ─────────────────────────────────────
        dev = None
        if o.late and o.delay > 0:
            delay = int(o.delay)
            sev = "high" if delay >= 4 else ("medium" if delay == 3 else "low")
            if o.segment == "Corporate" or value >= 1000:
                sev = _bump(sev)
            dev = ("late_delivery", sev, delay, _iso(o.shipping_date),
                   f"{o.shipping_mode} shipment to {o.dest_city}, {o.dest_country} took {int(o.real_days)} days "
                   f"against {int(o.sched_days)} scheduled ({delay} day{'s' if delay != 1 else ''} late). "
                   f"Order status: {o.order_status}.")
        elif o.order_status == "SUSPECTED_FRAUD":
            sev = "critical" if value >= 1000 else "high"
            dev = ("suspected_fraud", sev, None, created,
                   f"Order {oid} flagged SUSPECTED_FRAUD; shipment to {o.dest_city}, {o.dest_country} "
                   f"cancelled. Payment of ${value:,.2f} requires review before release.")
        if dev:
            dev_type, sev, delay, detected, desc = dev
            # Fraud orders are closed out as cancelled, but still await payment review
            active = (is_open or dev_type == "suspected_fraud") and o.order_date >= active_cutoff
            deviations.append((
                f"DC-DEV-{oid}", po_id, sup_id, dev_type, detected, sev, delay, value,
                json.dumps([cust_id]), desc, 0 if active else 1, 0,
            ))

    items = df[list(ITEM_COLUMNS)].rename(columns=ITEM_COLUMNS)
    for col in ("order_date", "shipping_date"):
        items[col] = items[col].dt.strftime("%Y-%m-%dT%H:%M:%S")

    return {
        "suppliers": suppliers, "customers": customers, "purchase_orders": pos,
        "deliveries": deliveries, "customer_orders": corders, "deviations": deviations,
        "items": items,
    }


def is_imported(db: sqlite3.Connection) -> bool:
    return db.execute("SELECT 1 FROM suppliers WHERE id LIKE 'DC-%' LIMIT 1").fetchone() is not None


def clear_import(db: sqlite3.Connection):
    db.execute("DELETE FROM agent_recommendations WHERE deviation_id LIKE 'DC-%'")
    for table in ("deviations", "customer_orders", "deliveries", "purchase_orders", "customers", "suppliers"):
        db.execute(f"DELETE FROM {table} WHERE id LIKE 'DC-%'")
    db.execute("DELETE FROM event_log WHERE event_type = 'dataset_imported' AND entity_id = 'kaggle_dataco'")
    db.execute("DROP TABLE IF EXISTS kaggle_dataco_items")


def import_dataco(db_path: str = DB_PATH, csv_path: str = CSV_PATH, force: bool = False) -> dict | None:
    """Import DataCo into the database. Returns row counts, or None if skipped."""
    if not os.path.exists(csv_path):
        print(f"[kaggle] DataCo CSV not found at {csv_path} — skipping import. See README › Kaggle dataset.")
        return None

    with sqlite3.connect(db_path) as db:
        if is_imported(db) and not force:
            return None

        print(f"[kaggle] Importing DataCo dataset from {csv_path} ...")
        recs = build_records(load_dataframe(csv_path))

        if force:
            clear_import(db)
        db.executescript(ITEMS_DDL)
        db.executemany("INSERT INTO suppliers VALUES (?,?,?,?,?,?,?,?,?,?,?)", recs["suppliers"])
        db.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?)", recs["customers"])
        db.executemany("INSERT INTO purchase_orders VALUES (?,?,?,?,?,?,?,?,?,?)", recs["purchase_orders"])
        db.executemany("INSERT INTO deliveries VALUES (?,?,?,?,?,?,?,?,?,?)", recs["deliveries"])
        db.executemany("INSERT INTO customer_orders VALUES (?,?,?,?,?,?,?,?)", recs["customer_orders"])
        db.executemany("INSERT INTO deviations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", recs["deviations"])
        recs["items"].to_sql("kaggle_dataco_items", db, if_exists="append", index=False, chunksize=20000)

        counts = {k: len(v) for k, v in recs.items()}
        active = sum(1 for d in recs["deviations"] if d[10] == 0)
        message = (f"Imported {SOURCE_NAME}: {counts['purchase_orders']:,} orders, "
                   f"{counts['deviations']:,} deviations ({active} active), {counts['items']:,} order lines.")
        db.execute(
            "INSERT INTO event_log VALUES (?,?,?,?,?,?,?)",
            (uuid.uuid4().hex[:8], datetime.now().isoformat(), "dataset_imported",
             "kaggle_dataco", "dataset", message, json.dumps(counts)),
        )
        db.commit()

    print(f"[kaggle] {message}")
    return counts


if __name__ == "__main__":
    import_dataco(force="--force" in sys.argv)
