"""
Imports the Kaggle "Supply Chain Shipment Pricing Data" (USAID SCMS delivery history) into PAALS.

Source: https://www.kaggle.com/datasets/divyeshardeshana/supply-chain-shipment-pricing-data
        (originally published by USAID — Supply Chain Management System, PEPFAR, 2006–2015)

Each row is a shipment line of health commodities (ARVs, HIV tests, antimalarials) bought from
a vendor and delivered to a recipient country. Mapped onto the PAALS model as:

    SCMS                                    PAALS
    ──────────────────────────────────────  ─────────────────────────────────────────
    Vendor                               →  supplier        SC-SUP-xx (reliability = real on-time rate)
    Destination country                  →  customer        SC-CUST-xx
    PO / SO #                            →  purchase order  SC-PO-<po>
    ASN/DN # (shipment)                  →  delivery        SC-DLV-<asn>
    PO × country                         →  customer order  SC-CO-<po>
    Delivered after scheduled date       →  deviation       late_delivery       SC-DEV-L-<asn>
    Recorded > 14 days after delivery    →  deviation       goods_receipt_skip  SC-DEV-R-<asn>
    Every line (cleaned)                 →  kaggle_scms_lines

A deviation is active only within the last PAALS_SCMS_ACTIVE_DAYS days of the dataset
(default 180); older ones are history. Imported IDs start with "SC-".

Usage:
    python -m app.services.scms_import            # import if not already present
    python -m app.services.scms_import --force    # delete SC-* rows and re-import
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
    "PAALS_SCMS_CSV",
    os.path.join(_ROOT, "data", "kaggle", "scms", "SCMS_Delivery_History_Dataset.csv"),
)
ACTIVE_DAYS = int(os.environ.get("PAALS_SCMS_ACTIVE_DAYS", "180"))
RECORD_LAG_DAYS = 14  # goods receipt recorded later than this counts as a deviation

SOURCE_NAME = "Kaggle USAID SCMS Shipment Pricing"
SEVERITIES = ["low", "medium", "high", "critical"]

PRODUCT_GROUPS = {
    "ARV": "Antiretrovirals", "HRDT": "HIV rapid tests", "ANTM": "Antimalarials",
    "ACT": "Artemisinin combination therapy", "MRDT": "Malaria rapid tests",
}

LINES_DDL = """
CREATE TABLE IF NOT EXISTS kaggle_scms_lines (
    line_id INTEGER PRIMARY KEY,
    project_code TEXT,
    po_number TEXT,
    asn_number TEXT,
    country TEXT,
    managed_by TEXT,
    fulfill_via TEXT,
    incoterm TEXT,
    shipment_mode TEXT,
    po_sent_date TEXT,
    scheduled_date TEXT,
    delivered_date TEXT,
    recorded_date TEXT,
    delay_days INTEGER,
    record_lag_days INTEGER,
    product_group TEXT,
    sub_classification TEXT,
    vendor TEXT,
    item_description TEXT,
    brand TEXT,
    dosage_form TEXT,
    quantity INTEGER,
    line_value_usd REAL,
    pack_price REAL,
    unit_price REAL,
    manufacturing_site TEXT,
    weight_kg REAL,
    freight_cost_usd REAL,
    insurance_usd REAL
);
CREATE INDEX IF NOT EXISTS idx_scms_lines_po ON kaggle_scms_lines(po_number);
"""


def _iso(ts) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%S")


def _bump(sev: str, n: int = 1) -> str:
    return SEVERITIES[min(SEVERITIES.index(sev) + n, len(SEVERITIES) - 1)]


def _num(s: pd.Series) -> pd.Series:
    """Numeric column that may contain notes like 'Freight Included in Commodity'."""
    return pd.to_numeric(s, errors="coerce")


def load_dataframe(csv_path: str = CSV_PATH) -> pd.DataFrame:
    df = pd.read_csv(csv_path, encoding="utf-8-sig")  # file is UTF-8 with a BOM
    df.columns = [c.strip() for c in df.columns]
    for col in ("Scheduled Delivery Date", "Delivered to Client Date", "Delivery Recorded Date"):
        df[col] = pd.to_datetime(df[col], format="%d-%b-%y")
    df["PO Sent to Vendor Date"] = pd.to_datetime(df["PO Sent to Vendor Date"], format="%m/%d/%y", errors="coerce")
    df["delay"] = (df["Delivered to Client Date"] - df["Scheduled Delivery Date"]).dt.days
    df["lag"] = (df["Delivery Recorded Date"] - df["Delivered to Client Date"]).dt.days
    df["freight"] = _num(df["Freight Cost (USD)"])
    df["weight"] = _num(df["Weight (Kilograms)"])
    df["Vendor"] = df["Vendor"].str.strip()
    return df


def build_records(df: pd.DataFrame) -> dict:
    years = max((df["Delivered to Client Date"].max() - df["Delivered to Client Date"].min()).days / 365.25, 1.0)
    active_cutoff = df["Delivered to Client Date"].max() - pd.Timedelta(days=ACTIVE_DAYS)

    # ── Suppliers: real vendors ────────────────────────────────────────────────
    df["lead"] = (df["Delivered to Client Date"] - df["PO Sent to Vendor Date"]).dt.days
    vend = df.groupby("Vendor").agg(
        value=("Line Item Value", "sum"),
        on_time=("delay", lambda s: (s <= 0).mean()),
        lead=("lead", "median"),
        site=("Manufacturing Site", lambda s: s.mode().iat[0]),
        groups=("Product Group", lambda s: list(s.value_counts().index[:3])),
    ).sort_values("value", ascending=False)
    default_lead = int(df["lead"].median())
    vend_ids = {v: f"SC-SUP-{i + 1:02d}" for i, v in enumerate(vend.index)}
    n = len(vend)
    suppliers = []
    for rank, (v, r) in enumerate(vend.iterrows()):
        tier = 1 if rank < max(n // 10, 1) else (2 if rank < n * 0.4 else 3)
        lead = int(r.lead) if pd.notna(r.lead) else default_lead
        name = "SCMS Regional Distribution Centre" if v == "SCMS from RDC" else v.title() if v.isupper() else v
        suppliers.append((
            vend_ids[v], name, "Global", "Global Health (SCMS)", str(r.site)[:80], lead,
            round(float(r.on_time), 3), tier,
            json.dumps([PRODUCT_GROUPS.get(g, g) for g in r.groups]),
            "USD", round(float(r.value) / years, 2),
        ))
    vend_lead = {v: (int(r.lead) if pd.notna(r.lead) else default_lead) for v, r in vend.iterrows()}

    # ── Customers: recipient countries ────────────────────────────────────────
    ctry = df.groupby("Country")["Line Item Value"].sum().sort_values(ascending=False)
    ctry_ids = {c: f"SC-CUST-{i + 1:02d}" for i, c in enumerate(ctry.index)}
    customers = [(ctry_ids[c], f"{c} — SCMS programme", c, "Public health programme",
                  round(float(v) / years, 2), "PMO - US") for c, v in ctry.items()]

    # ── Purchase orders ───────────────────────────────────────────────────────
    df["line_json"] = [
        json.dumps({"description": str(d)[:120], "qty": int(q), "unit_price": round(float(p), 2)})
        for d, q, p in zip(df["Item Description"], df["Line Item Quantity"], df["Pack Price"])
    ]
    po = df.groupby("PO / SO #", sort=False).agg(
        vendor=("Vendor", "first"), country=("Country", "first"),
        sent=("PO Sent to Vendor Date", "min"),
        sched=("Scheduled Delivery Date", "max"), deliv=("Delivered to Client Date", "max"),
        value=("Line Item Value", "sum"), incoterm=("Vendor INCO Term", "first"),
        lines=("line_json", lambda s: "[" + ", ".join(s) + "]"),
    )
    pos, corders = [], []
    for p in po.itertuples():
        po_id = f"SC-PO-{p.Index}"
        # No PO date (RDC stock orders): estimate from the vendor's lead time, anchored on the
        # earlier of scheduled/delivered so early shipments never precede their own PO
        created = p.sent if pd.notna(p.sent) else min(p.sched, p.deliv) - pd.Timedelta(days=vend_lead[p.vendor])
        incoterm = "RDC" if str(p.incoterm).startswith("N/A") else p.incoterm
        pos.append((po_id, vend_ids[p.vendor], _iso(created), _iso(p.sched), _iso(p.deliv),
                    p.lines, round(float(p.value), 2), "delivered", "USD", incoterm))
        corders.append((f"SC-CO-{p.Index}", ctry_ids[p.country], po_id, _iso(created),
                        _iso(p.sched), round(float(p.value), 2), "delivered", p.lines))

    # ── Deliveries (one per ASN/DN shipment) and deviations ──────────────────
    dl = df.groupby("ASN/DN #", sort=False).agg(
        po=("PO / SO #", "first"), vendor=("Vendor", "first"), country=("Country", "first"),
        site=("Manufacturing Site", "first"), mode=("Shipment Mode", "first"),
        via=("Fulfill Via", "first"),
        sched=("Scheduled Delivery Date", "max"), deliv=("Delivered to Client Date", "max"),
        rec=("Delivery Recorded Date", "max"),
        delay=("delay", "max"), lag=("lag", "max"),
        value=("Line Item Value", "sum"), freight=("freight", "sum"),
        product=("Product Group", "first"),
    )
    deliveries, deviations = [], []
    for d in dl.itertuples():
        asn = d.Index
        po_id = f"SC-PO-{d.po}"
        mode = d.mode if isinstance(d.mode, str) else "Unspecified"
        origin = "SCMS Regional Distribution Centre" if d.via == "From RDC" else str(d.site)[:80]
        deliveries.append((f"SC-DLV-{asn}", po_id, origin, d.country, mode, None,
                           _iso(d.sched), _iso(d.deliv), "arrived", json.dumps([])))

        exposure = round(float(d.value) + float(d.freight or 0), 2)
        active = 0 if d.deliv >= active_cutoff else 1
        product = PRODUCT_GROUPS.get(d.product, d.product)
        if d.delay > 0:
            delay = int(d.delay)
            sev = "critical" if delay >= 60 else "high" if delay >= 14 else "medium" if delay >= 7 else "low"
            if exposure >= 500_000:
                sev = _bump(sev)
            deviations.append((
                f"SC-DEV-L-{asn}", po_id, vend_ids[d.vendor], "late_delivery", _iso(d.deliv), sev, delay,
                exposure, json.dumps([ctry_ids[d.country]]),
                f"{mode} shipment {asn} of {product} to {d.country} arrived {delay} day{'s' if delay != 1 else ''} "
                f"after the scheduled date ({d.sched:%d %b %Y} → {d.deliv:%d %b %Y}).",
                active, 0,
            ))
        if d.lag > RECORD_LAG_DAYS:
            lag = int(d.lag)
            sev = "high" if lag > 60 else "medium" if lag > 30 else "low"
            if exposure >= 500_000:
                sev = _bump(sev)
            deviations.append((
                f"SC-DEV-R-{asn}", po_id, vend_ids[d.vendor], "goods_receipt_skip", _iso(d.rec), sev, None,
                exposure, json.dumps([ctry_ids[d.country]]),
                f"Goods receipt for shipment {asn} to {d.country} was recorded {lag} days after delivery "
                f"({d.deliv:%d %b %Y} → {d.rec:%d %b %Y}); three-way match was delayed.",
                active, 0,
            ))

    lines = pd.DataFrame({
        "line_id": df.iloc[:, 0], "project_code": df["Project Code"], "po_number": df["PO / SO #"],
        "asn_number": df["ASN/DN #"], "country": df["Country"], "managed_by": df["Managed By"],
        "fulfill_via": df["Fulfill Via"], "incoterm": df["Vendor INCO Term"], "shipment_mode": df["Shipment Mode"],
        "po_sent_date": df["PO Sent to Vendor Date"].dt.strftime("%Y-%m-%d"),
        "scheduled_date": df["Scheduled Delivery Date"].dt.strftime("%Y-%m-%d"),
        "delivered_date": df["Delivered to Client Date"].dt.strftime("%Y-%m-%d"),
        "recorded_date": df["Delivery Recorded Date"].dt.strftime("%Y-%m-%d"),
        "delay_days": df["delay"], "record_lag_days": df["lag"],
        "product_group": df["Product Group"], "sub_classification": df["Sub Classification"],
        "vendor": df["Vendor"], "item_description": df["Item Description"], "brand": df["Brand"],
        "dosage_form": df["Dosage Form"], "quantity": df["Line Item Quantity"],
        "line_value_usd": df["Line Item Value"], "pack_price": df["Pack Price"], "unit_price": df["Unit Price"],
        "manufacturing_site": df["Manufacturing Site"], "weight_kg": df["weight"],
        "freight_cost_usd": df["freight"], "insurance_usd": df["Line Item Insurance (USD)"],
    })

    return {
        "suppliers": suppliers, "customers": customers, "purchase_orders": pos,
        "deliveries": deliveries, "customer_orders": corders, "deviations": deviations,
        "lines": lines,
    }


def is_imported(db: sqlite3.Connection) -> bool:
    return db.execute("SELECT 1 FROM suppliers WHERE id LIKE 'SC-%' LIMIT 1").fetchone() is not None


def clear_import(db: sqlite3.Connection):
    db.execute("DELETE FROM agent_recommendations WHERE deviation_id LIKE 'SC-%'")
    for table in ("deviations", "customer_orders", "deliveries", "purchase_orders", "customers", "suppliers"):
        db.execute(f"DELETE FROM {table} WHERE id LIKE 'SC-%'")
    db.execute("DELETE FROM event_log WHERE event_type = 'dataset_imported' AND entity_id = 'kaggle_scms'")
    db.execute("DROP TABLE IF EXISTS kaggle_scms_lines")


def import_scms(db_path: str = DB_PATH, csv_path: str = CSV_PATH, force: bool = False) -> dict | None:
    """Import SCMS into the database. Returns row counts, or None if skipped."""
    if not os.path.exists(csv_path):
        print(f"[scms] SCMS CSV not found at {csv_path} - skipping import. See README > Kaggle datasets.")
        return None

    with sqlite3.connect(db_path) as db:
        if is_imported(db) and not force:
            return None

        print(f"[scms] Importing SCMS dataset from {csv_path} ...")
        recs = build_records(load_dataframe(csv_path))

        if force:
            clear_import(db)
        db.executescript(LINES_DDL)
        db.executemany("INSERT INTO suppliers VALUES (?,?,?,?,?,?,?,?,?,?,?)", recs["suppliers"])
        db.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?)", recs["customers"])
        db.executemany("INSERT INTO purchase_orders VALUES (?,?,?,?,?,?,?,?,?,?)", recs["purchase_orders"])
        db.executemany("INSERT INTO deliveries VALUES (?,?,?,?,?,?,?,?,?,?)", recs["deliveries"])
        db.executemany("INSERT INTO customer_orders VALUES (?,?,?,?,?,?,?,?)", recs["customer_orders"])
        db.executemany("INSERT INTO deviations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", recs["deviations"])
        recs["lines"].to_sql("kaggle_scms_lines", db, if_exists="append", index=False)

        counts = {k: len(v) for k, v in recs.items()}
        active = sum(1 for d in recs["deviations"] if d[10] == 0)
        message = (f"Imported {SOURCE_NAME}: {counts['purchase_orders']:,} POs, {counts['suppliers']} vendors, "
                   f"{counts['deviations']:,} deviations ({active} active), {counts['lines']:,} shipment lines.")
        db.execute(
            "INSERT INTO event_log VALUES (?,?,?,?,?,?,?)",
            (uuid.uuid4().hex[:8], datetime.now().isoformat(), "dataset_imported",
             "kaggle_scms", "dataset", message, json.dumps(counts)),
        )
        db.commit()

    print(f"[scms] {message}")
    return counts


if __name__ == "__main__":
    import_scms(force="--force" in sys.argv)
