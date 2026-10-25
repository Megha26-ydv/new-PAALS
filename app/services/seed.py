"""
Generates realistic supply chain operational data — ~10,000 records total.
All names, routes, and values are based on actual trade patterns.
Runs automatically on first startup; skips if data already exists.
"""
import json
import random
import uuid
import os
from datetime import datetime, timedelta
import aiosqlite

_HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.normpath(os.path.join(_HERE, "..", "..", "database", "paals.db"))

# ── Master data ───────────────────────────────────────────────────────────────

SUPPLIERS = [
    {"id": "SUP-001", "name": "Yangon Industrial Components Ltd",       "country": "Myanmar",      "region": "Southeast Asia", "port": "Yangon",           "lead": 28, "reliability": 0.71, "tier": 2, "cats": ["Electronics", "Cables"],                       "currency": "USD", "spend": 4200000},
    {"id": "SUP-002", "name": "Foxconn Precision Industries",           "country": "Taiwan",       "region": "East Asia",      "port": "Kaohsiung",        "lead": 18, "reliability": 0.94, "tier": 1, "cats": ["Electronics", "PCBs", "Assembly"],               "currency": "USD", "spend": 18500000},
    {"id": "SUP-003", "name": "Tata Advanced Materials",                "country": "India",        "region": "South Asia",     "port": "Nhava Sheva",      "lead": 22, "reliability": 0.87, "tier": 1, "cats": ["Steel", "Composites", "Forgings"],               "currency": "INR", "spend": 9800000},
    {"id": "SUP-004", "name": "Kumho Precision Parts",                  "country": "South Korea",  "region": "East Asia",      "port": "Busan",            "lead": 16, "reliability": 0.92, "tier": 1, "cats": ["Automotive", "Seals", "Bearings"],               "currency": "KRW", "spend": 7300000},
    {"id": "SUP-005", "name": "Guangdong FastTech Manufacturing",       "country": "China",        "region": "East Asia",      "port": "Guangzhou",        "lead": 21, "reliability": 0.79, "tier": 2, "cats": ["Plastics", "Housings", "Injection Moulding"],    "currency": "CNY", "spend": 12100000},
    {"id": "SUP-006", "name": "Vietnam Precision Works Co.",            "country": "Vietnam",      "region": "Southeast Asia", "port": "Ho Chi Minh City", "lead": 24, "reliability": 0.83, "tier": 2, "cats": ["Sheet Metal", "Stamping", "Welding"],           "currency": "USD", "spend": 5600000},
    {"id": "SUP-007", "name": "Boryszew Automotive Components",        "country": "Poland",       "region": "Europe",         "port": "Gdansk",           "lead": 10, "reliability": 0.91, "tier": 1, "cats": ["Automotive", "Aluminium", "Die Casting"],        "currency": "EUR", "spend": 8900000},
    {"id": "SUP-008", "name": "Minth Group (Changzhou)",               "country": "China",        "region": "East Asia",      "port": "Shanghai",         "lead": 19, "reliability": 0.85, "tier": 2, "cats": ["Trim", "Structural", "Aluminium"],               "currency": "CNY", "spend": 6700000},
    {"id": "SUP-009", "name": "Hazel Circuits Pvt Ltd",                "country": "India",        "region": "South Asia",     "port": "Chennai",          "lead": 26, "reliability": 0.76, "tier": 3, "cats": ["PCBs", "Wiring Harness"],                        "currency": "INR", "spend": 2100000},
    {"id": "SUP-010", "name": "SKF Manufacturing (Pune)",              "country": "India",        "region": "South Asia",     "port": "Nhava Sheva",      "lead": 20, "reliability": 0.90, "tier": 1, "cats": ["Bearings", "Seals", "Lubrication"],              "currency": "USD", "spend": 11200000},
    {"id": "SUP-011", "name": "Mahle Filter Systems Thailand",         "country": "Thailand",     "region": "Southeast Asia", "port": "Laem Chabang",     "lead": 23, "reliability": 0.88, "tier": 2, "cats": ["Filtration", "Thermal Management"],             "currency": "USD", "spend": 4800000},
    {"id": "SUP-012", "name": "Nexans Cable Solutions Morocco",        "country": "Morocco",      "region": "North Africa",   "port": "Casablanca",       "lead": 12, "reliability": 0.86, "tier": 2, "cats": ["Cables", "Wiring Harness"],                      "currency": "EUR", "spend": 6300000},
    {"id": "SUP-013", "name": "Continental Tires (Hefei)",             "country": "China",        "region": "East Asia",      "port": "Shanghai",         "lead": 17, "reliability": 0.93, "tier": 1, "cats": ["Tyres", "Rubber"],                               "currency": "CNY", "spend": 15800000},
    {"id": "SUP-014", "name": "Sumitomo Electric Wiring Systems",      "country": "Japan",        "region": "East Asia",      "port": "Yokohama",         "lead": 15, "reliability": 0.96, "tier": 1, "cats": ["Wiring Harness", "Connectors"],                  "currency": "JPY", "spend": 22300000},
    {"id": "SUP-015", "name": "PTT Phenol Co. Ltd",                    "country": "Thailand",     "region": "Southeast Asia", "port": "Map Ta Phut",      "lead": 30, "reliability": 0.74, "tier": 3, "cats": ["Chemicals", "Resins", "Adhesives"],              "currency": "USD", "spend": 1900000},
    {"id": "SUP-016", "name": "Lear Corporation Seating (Monterrey)",  "country": "Mexico",       "region": "North America",  "port": "Manzanillo",       "lead": 8,  "reliability": 0.89, "tier": 2, "cats": ["Seating", "Foam", "Fabric"],                     "currency": "USD", "spend": 7100000},
    {"id": "SUP-017", "name": "Gestamp Automocion (Bizkaia)",          "country": "Spain",        "region": "Europe",         "port": "Bilbao",           "lead": 9,  "reliability": 0.93, "tier": 1, "cats": ["Structural", "Hot Stamping", "Chassis"],         "currency": "EUR", "spend": 13400000},
    {"id": "SUP-018", "name": "Bharat Forge (Pune)",                   "country": "India",        "region": "South Asia",     "port": "Nhava Sheva",      "lead": 25, "reliability": 0.84, "tier": 2, "cats": ["Forgings", "Crankshafts", "Axles"],              "currency": "INR", "spend": 8200000},
    {"id": "SUP-019", "name": "Hanon Systems (Daegu)",                 "country": "South Korea",  "region": "East Asia",      "port": "Busan",            "lead": 14, "reliability": 0.91, "tier": 1, "cats": ["HVAC", "Thermal Management"],                    "currency": "KRW", "spend": 9600000},
    {"id": "SUP-020", "name": "Flex-N-Gate (Ontario)",                 "country": "Canada",       "region": "North America",  "port": "Hamilton",         "lead": 7,  "reliability": 0.90, "tier": 2, "cats": ["Bumpers", "Stampings", "Chrome"],                "currency": "CAD", "spend": 5400000},
]

CUSTOMERS = [
    {"id": "CUST-001", "name": "Stellantis North America LLC",  "country": "USA",         "segment": "OEM",    "revenue": 45000000, "am": "Rachel Torres"},
    {"id": "CUST-002", "name": "BMW Group Purchasing GmbH",     "country": "Germany",     "segment": "OEM",    "revenue": 62000000, "am": "Stefan Hofer"},
    {"id": "CUST-003", "name": "Renault-Nissan Alliance",       "country": "France",      "segment": "OEM",    "revenue": 38000000, "am": "Pierre Dubois"},
    {"id": "CUST-004", "name": "Volvo Car Corporation",         "country": "Sweden",      "segment": "OEM",    "revenue": 28000000, "am": "Anna Lindqvist"},
    {"id": "CUST-005", "name": "Tata Motors (JLR Division)",    "country": "UK",          "segment": "OEM",    "revenue": 19000000, "am": "James Whitfield"},
    {"id": "CUST-006", "name": "Hyundai Mobis Co. Ltd",         "country": "South Korea", "segment": "Tier-1", "revenue": 31000000, "am": "Subin Park"},
    {"id": "CUST-007", "name": "Magna International Europe",    "country": "Austria",     "segment": "Tier-1", "revenue": 24000000, "am": "Klaus Mayer"},
    {"id": "CUST-008", "name": "Denso Manufacturing UK",        "country": "UK",          "segment": "Tier-1", "revenue": 17000000, "am": "James Whitfield"},
    {"id": "CUST-009", "name": "Valeo Thermal Systems",         "country": "France",      "segment": "Tier-1", "revenue": 14000000, "am": "Pierre Dubois"},
    {"id": "CUST-010", "name": "Aptiv Signal and Power Solutions","country": "Ireland",   "segment": "Tier-1", "revenue": 22000000, "am": "Siobhan Carroll"},
]

CARRIERS = [
    ("Maersk Line",     "Maersk Emden"),
    ("Maersk Line",     "Maersk Eindhoven"),
    ("MSC",             "MSC Rossella"),
    ("MSC",             "MSC Isabella"),
    ("COSCO Shipping",  "COSCO Excellence"),
    ("COSCO Shipping",  "COSCO Harmony"),
    ("Evergreen Marine","Ever Given"),
    ("Evergreen Marine","Ever Forward"),
    ("Hapag-Lloyd",     "Hamburg Express"),
    ("Hapag-Lloyd",     "Berlin Express"),
    ("ONE Line",        "Kaiwa Bridge"),
    ("ONE Line",        "Tsugaru Bridge"),
    ("Yang Ming",       "YM Warranty"),
    ("Yang Ming",       "YM Ubiquity"),
    ("HMM",             "HMM Algeciras"),
    ("HMM",             "HMM Copenhagen"),
    ("CMA CGM",         "CMA CGM Marseille"),
    ("ZIM",             "ZIM Tarragona"),
]

DESTINATION_PORTS = [
    "Rotterdam", "Hamburg", "Felixstowe", "Antwerp", "Baltimore",
    "Los Angeles", "Detroit", "Tilbury", "Le Havre", "Genoa",
    "Valencia", "Piraeus", "Gothenburg", "Bremerhaven", "New York",
]

ITEMS_CATALOG = [
    ("Wiring Harness Assembly",              280,   850),
    ("Precision Ball Bearing 6205-2RS",        4.5,   22),
    ("Aluminium Die Cast Housing",            34,   180),
    ("PCB Control Module Rev 4",             65,   340),
    ("Hydraulic Seal Kit",                   12,    45),
    ("Hot-Stamped B-Pillar Reinforcement",   95,   320),
    ("HVAC Blower Motor Assembly",           48,   190),
    ("High-Pressure Fuel Injector",          85,   260),
    ("LED Headlamp Module",                 120,   480),
    ("Crankshaft Forging 2.0L",             145,   520),
    ("Composite Bumper Fascia",              55,   230),
    ("Thermostat Housing Assembly",          28,    95),
    ("Power Steering Rack",                 190,   680),
    ("Transmission Gear Set",               320,  1100),
    ("Exhaust Manifold Casting",             75,   280),
    ("Brake Caliper Assembly",               88,   310),
    ("Airbag Inflator Module",               55,   175),
    ("Drive Shaft Assembly",                160,   540),
    ("Fuel Pump Module",                     45,   165),
    ("ABS Sensor Ring",                       9,    38),
    ("Coolant Hose Set",                     18,    62),
    ("Alternator Assembly 120A",             78,   245),
    ("Starter Motor 1.4kW",                  55,   185),
    ("Camshaft Forging",                    110,   390),
    ("Suspension Control Arm",              135,   420),
    ("Radiator Core Assembly",               95,   310),
    ("Tyre 215/65 R16",                      48,   145),
    ("Rubber Engine Mount",                  22,    78),
    ("Clutch Disc Assembly",                 68,   210),
    ("Oil Pump Assembly",                    42,   155),
]

DEVIATION_TEMPLATES = {
    "late_delivery": [
        "Shipment delayed at {port} due to port congestion. Vessel {vessel} now ETA {days} days late.",
        "Carrier {carrier} reported berth unavailability at {port}. Rescheduled to next available slot.",
        "Customs examination at {port} triggered by documentation discrepancy. Clearance pending.",
        "Severe weather conditions in {port} approach channel. Vessel {vessel} diverted; ETA revised by {days} days.",
        "Strike action at {port} longshoremen's union. Container handling suspended for {days} days.",
    ],
    "invoice_mismatch": [
        "Invoice value {inv_val} does not match PO {po_val}. Variance of {var}% exceeds tolerance.",
        "Currency conversion applied incorrectly. Invoice in {currency} does not reconcile with agreed USD terms.",
        "Line item quantities on invoice differ from goods receipt. Audit required before payment.",
        "Supplier applied wrong tax rate. Invoice total overstated; credit note requested.",
        "Unit prices on invoice do not match contracted rates. Procurement review initiated.",
    ],
    "goods_receipt_skip": [
        "Goods receipt step bypassed in system. Three-way match cannot complete without GR confirmation.",
        "Warehouse team processed payment without recording goods receipt. Compliance violation flagged.",
        "GR document missing from system — warehouse entry not completed before invoice processed.",
        "Automated GR posting failed due to ERP integration error. Manual correction required.",
    ],
    "customs_hold": [
        "Shipment placed on hold by {authority} customs. Reason: restricted material classification.",
        "HS code mismatch detected during customs filing. Goods held pending reclassification.",
        "Export licence documentation incomplete. Goods held at {port} pending authorisation.",
        "Dual-use goods flagged by {authority} border agency. Compliance review underway.",
    ],
    "quality_rejection": [
        "Incoming quality inspection failed. {pct}% of batch rejected against AQL threshold.",
        "Dimensional non-conformance detected on critical parts. Supplier notified, return authorisation pending.",
        "Surface finish specification breach identified. Batch quarantined for supplier disposition.",
        "Material certification mismatch. Chemical composition test failed; full batch rejected.",
        "Torque specification failure on fasteners. Safety-critical parts quarantined immediately.",
    ],
    "supplier_blackout": [
        "Supplier facility shutdown reported due to {reason}. Production capacity unavailable for {days} days.",
        "Force majeure event at supplier site. Temporary halt on all outbound shipments.",
        "Regulatory inspection closure. Supplier unable to dispatch for {days} days.",
    ],
    "duplicate_payment": [
        "Duplicate payment detected for invoice reference {inv_ref}. AP team notified; recovery initiated.",
        "Two payments processed for same delivery. Finance team coordinating refund with supplier.",
        "System error in payment run generated duplicate transaction. Bank recall instruction issued.",
    ],
}

AGENT_ACTIONS = [
    "evaluate_alternatives", "draft_customer_notice", "escalate_to_procurement",
    "reroute_shipment", "hold_payment", "trigger_quality_audit", "emergency_order",
]

APPROVAL_NAMES = [
    "Operations Manager", "Chief Procurement Officer", "Supply Chain Director",
    "Finance Controller", "Risk Manager", "Head of Logistics",
]

SUPPLIER_NAMES = {s["id"]: s["name"] for s in SUPPLIERS}


# ── Helpers ────────────────────────────────────────────────────────────────────

def rand_ts(start_days_ago=540, end_days_ago=0):
    base = datetime.now() - timedelta(
        days=random.randint(end_days_ago, start_days_ago),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
        seconds=random.randint(0, 59),
    )
    return base.strftime("%Y-%m-%dT%H:%M:%S")


def future_ts(base_str, days_min, days_max):
    base = datetime.fromisoformat(base_str)
    delta = random.randint(days_min, days_max)
    return (base + timedelta(days=delta)).strftime("%Y-%m-%dT%H:%M:%S")


def uid8():
    return uuid.uuid4().hex[:8]


def rec_id():
    return "REC-" + uuid.uuid4().hex[:8].upper()


# ── Data generation ────────────────────────────────────────────────────────────

def generate_all_data():
    random.seed(2024)

    supplier_records = [
        {
            "id": s["id"], "name": s["name"], "country": s["country"],
            "region": s["region"], "port_of_origin": s["port"],
            "lead_time_days": s["lead"], "reliability_score": s["reliability"],
            "strategic_tier": s["tier"], "categories": json.dumps(s["cats"]),
            "currency": s["currency"], "annual_spend_usd": s["spend"],
        }
        for s in SUPPLIERS
    ]

    customer_records = [
        {
            "id": c["id"], "name": c["name"], "country": c["country"],
            "segment": c["segment"], "annual_revenue_usd": c["revenue"],
            "account_manager": c["am"],
        }
        for c in CUSTOMERS
    ]

    sup_index = {s["id"]: s for s in SUPPLIERS}
    cust_ids = [c["id"] for c in CUSTOMERS]

    po_records = []
    delivery_records = []
    co_records = []
    deviation_records = []
    agent_rec_records = []
    event_log_records = []

    co_counter = 1
    dev_counter = 1

    for i in range(4000):
        po_num = i + 1
        sup = random.choice(SUPPLIERS)
        carrier, vessel = random.choice(CARRIERS)
        dest_port = random.choice(DESTINATION_PORTS)
        created = rand_ts(540, 7)
        lead = sup["lead"]
        expected_del = future_ts(created, lead - 3, lead + 5)

        rand_outcome = random.random()
        if rand_outcome < 0.65:
            actual_del = future_ts(created, lead, lead + random.randint(0, 14))
        elif rand_outcome < 0.85:
            actual_del = None
        else:
            actual_del = future_ts(created, lead + 15, lead + 45)

        items = random.sample(ITEMS_CATALOG, k=random.randint(1, 4))
        line_items = []
        po_total = 0
        for item_name, unit_min, unit_max in items:
            qty = random.randint(50, 800)
            unit_price = round(random.uniform(unit_min, unit_max), 2)
            line_items.append({"description": item_name, "qty": qty, "unit_price": unit_price})
            po_total += qty * unit_price

        po_id = f"PO-{po_num:04d}"
        incoterm = random.choice(["FOB", "CIF", "DAP", "EXW", "FCA", "CFR", "DDP"])
        po_status = "delivered" if actual_del else random.choice(["in_transit", "confirmed", "processing"])

        po_records.append((
            po_id, sup["id"], created, expected_del,
            actual_del, json.dumps(line_items), round(po_total, 2),
            po_status, sup["currency"], incoterm,
        ))

        del_status = "arrived" if actual_del else random.choice(["in_transit", "at_port", "customs_hold"])
        container_ids = [f"CONT-{random.randint(10000, 99999)}" for _ in range(random.randint(1, 4))]
        delivery_records.append((
            f"DLV-{po_num:04d}", po_id, sup["port"], dest_port,
            carrier, vessel, expected_del, actual_del,
            del_status, json.dumps(container_ids),
        ))

        # Customer orders (1–3 per PO)
        n_customers = random.randint(1, 3)
        selected_custs = random.sample(cust_ids, k=n_customers)
        for cust_id in selected_custs:
            co_val = round(po_total * random.uniform(0.10, 0.55), 2)
            promised = future_ts(expected_del, 2, 12)
            co_status = "delivered" if actual_del else random.choice(["pending", "at_risk", "delayed"])
            co_records.append((
                f"CO-{co_counter:05d}", cust_id, po_id, created,
                promised, co_val, co_status, json.dumps(line_items),
            ))
            co_counter += 1

        # Deviation (~18% of POs)
        if random.random() < 0.18:
            dev_type = random.choice(list(DEVIATION_TEMPLATES.keys()))
            templates = DEVIATION_TEMPLATES[dev_type]
            inv_ref = f"INV-{random.randint(100000, 999999)}"
            desc = random.choice(templates).format(
                port=random.choice(DESTINATION_PORTS),
                vessel=random.choice(CARRIERS)[1],
                carrier=random.choice(CARRIERS)[0],
                days=random.randint(3, 21),
                inv_val=f"${po_total * random.uniform(0.95, 1.10):.0f}",
                po_val=f"${po_total:.0f}",
                var=round(random.uniform(2, 14), 1),
                currency=sup["currency"],
                authority=random.choice(["US", "UK", "EU", "Indian", "Chinese", "Canadian"]),
                pct=round(random.uniform(8, 40), 1),
                reason=random.choice([
                    "labour dispute", "fire safety inspection", "flooding",
                    "equipment failure", "planned maintenance shutdown", "power outage",
                ]),
                inv_ref=inv_ref,
            )

            exposure = po_total * random.uniform(0.3, 1.3)
            tier = sup["tier"]
            n_affected = len(selected_custs)

            if exposure > 450000 or (tier == 1 and n_affected >= 2):
                sev = "critical"
            elif exposure > 200000 or tier == 1:
                sev = "high"
            elif exposure > 80000:
                sev = "medium"
            else:
                sev = "low"

            delay = random.randint(3, 21) if dev_type in ["late_delivery", "customs_hold", "supplier_blackout"] else None
            resolved = 1 if random.random() < 0.28 else 0
            agent_activated = 1 if random.random() < 0.60 else 0
            dev_id = f"DEV-{dev_counter:04d}"
            dev_counter += 1

            deviation_records.append((
                dev_id, po_id, sup["id"], dev_type,
                rand_ts(60, 0), sev, delay,
                round(exposure, 2), json.dumps(selected_custs),
                desc, resolved, agent_activated,
            ))

            if agent_activated:
                action = random.choice(AGENT_ACTIONS)
                rec_status = random.choice(["pending", "approved", "rejected", "executed"])
                approved_by = random.choice(APPROVAL_NAMES) if rec_status in ("approved", "executed") else None
                requires_approval = 1 if (exposure > 150000 or tier == 1 or sev in ("high", "critical")) else 0
                created_at = rand_ts(30, 0)
                executed_at = rand_ts(20, 0) if rec_status in ("approved", "executed", "rejected") else None

                alt_suppliers = []
                if action == "evaluate_alternatives":
                    candidates = [SUPPLIER_NAMES[s["id"]] for s in SUPPLIERS if s["id"] != sup["id"]]
                    alt_suppliers = random.sample(candidates, k=min(3, len(candidates)))

                cost_impact = round(exposure * random.uniform(0.03, 0.25), 2) if random.random() < 0.7 else None

                reasoning = (
                    f"Deviation type '{dev_type}' with {sev} risk profile. "
                    f"Financial exposure: ${exposure:,.0f}. "
                    f"Supplier: {sup['name']} (Tier {tier}). "
                    f"Selected action: {action} based on operational impact matrix."
                )
                if requires_approval:
                    reasoning += f" Approval required: exposure exceeds $150,000, {sev} risk classification."

                draft_comm = None
                if action == "draft_customer_notice":
                    draft_comm = (
                        f"Dear Valued Customer,\n\nWe regret to inform you of a supply chain deviation "
                        f"affecting purchase order {po_id}. A {dev_type.replace('_', ' ')} has been detected "
                        f"with a potential impact of up to {delay or 'several'} days delay. "
                        f"Our team is actively working to mitigate the impact.\n\nPAALS Supply Chain Operations"
                    )
                elif action == "hold_payment":
                    draft_comm = (
                        f"INTERNAL MEMO — Accounts Payable\n\nPayment for invoice associated with {po_id} "
                        f"has been placed on hold pending resolution of a {dev_type.replace('_', ' ')} deviation. "
                        f"Do not process payment until cleared by procurement compliance."
                    )

                agent_rec_records.append((
                    rec_id(), dev_id, action, reasoning, draft_comm,
                    requires_approval, rec_status, created_at, executed_at,
                    approved_by, json.dumps(alt_suppliers), cost_impact,
                ))

            # Event log for deviation
            ev_type = random.choice(["deviation_detected", "agent_activated", "customer_notified", "escalation_raised"])
            messages = {
                "deviation_detected": f"Deviation detected on {po_id}: {dev_type.replace('_', ' ')}.",
                "agent_activated": f"Agent activated for {po_id}. Evaluating {dev_type.replace('_', ' ')} deviation.",
                "customer_notified": f"Customer notification issued for delay on {po_id}.",
                "escalation_raised": f"Deviation escalated to procurement for {po_id}.",
            }
            event_log_records.append((
                uid8(), rand_ts(60, 0), ev_type, po_id, "purchase_order",
                messages[ev_type], None,
            ))

        elif random.random() < 0.35:
            ev_type = random.choice(["po_created", "delivery_updated", "alternative_evaluated", "rejected"])
            msgs = {
                "po_created": f"Purchase order {po_id} created and sent to supplier.",
                "delivery_updated": f"Delivery status updated for {po_id}: {del_status}.",
                "alternative_evaluated": f"Routine alternative supplier review for {po_id}.",
                "rejected": f"Recommendation rejected. Manual review assigned for {po_id}.",
            }
            event_log_records.append((
                uid8(), rand_ts(90, 0), ev_type, po_id, "purchase_order",
                msgs[ev_type], None,
            ))

    return supplier_records, customer_records, po_records, delivery_records, co_records, deviation_records, agent_rec_records, event_log_records


# ── Database seeding ───────────────────────────────────────────────────────────

async def seed_database():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM suppliers") as cur:
            count = (await cur.fetchone())[0]
        if count > 0:
            return  # Already seeded

        print("Seeding database with ~10,000 records... (first run only)")
        suppliers, customers, pos, deliveries, corders, deviations, agent_recs, events = generate_all_data()

        await db.executemany(
            "INSERT OR IGNORE INTO suppliers VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [(s["id"], s["name"], s["country"], s["region"], s["port_of_origin"],
              s["lead_time_days"], s["reliability_score"], s["strategic_tier"],
              s["categories"], s["currency"], s["annual_spend_usd"]) for s in suppliers]
        )
        await db.executemany(
            "INSERT OR IGNORE INTO customers VALUES (?,?,?,?,?,?)",
            [(c["id"], c["name"], c["country"], c["segment"], c["annual_revenue_usd"], c["account_manager"]) for c in customers]
        )
        await db.executemany(
            "INSERT OR IGNORE INTO purchase_orders VALUES (?,?,?,?,?,?,?,?,?,?)", pos
        )
        await db.executemany(
            "INSERT OR IGNORE INTO deliveries VALUES (?,?,?,?,?,?,?,?,?,?)", deliveries
        )
        await db.executemany(
            "INSERT OR IGNORE INTO customer_orders VALUES (?,?,?,?,?,?,?,?)", corders
        )
        await db.executemany(
            "INSERT OR IGNORE INTO deviations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", deviations
        )
        await db.executemany(
            "INSERT OR IGNORE INTO agent_recommendations VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", agent_recs
        )
        await db.executemany(
            "INSERT OR IGNORE INTO event_log VALUES (?,?,?,?,?,?,?)", events
        )
        await db.commit()
        print(f"Database seeded: {len(pos)} POs, {len(corders)} customer orders, "
              f"{len(deviations)} deviations, {len(agent_recs)} recommendations, "
              f"{len(events)} events.")
