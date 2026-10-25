# PAALS — Process-Aware Agentic Loop for Supply Chain Oversight

A real-time supply chain oversight platform with an autonomous LangGraph agent
that detects deviations, evaluates risk, and recommends corrective actions.

---

## Quick Start (Windows 11)

### Prerequisites

| Requirement | Version | Download |
|---|---|---|
| Python | 3.10, 3.11, or 3.12 | https://www.python.org/downloads/ |
| pip | bundled with Python | — |

> **Important:** During Python installation, check ✅ **"Add Python to PATH"**.

---

### One-Command Start

1. Open the project folder in VS Code
2. Open the terminal (`Ctrl + `` ` ``)
3. Run:

```bat
start.bat
```

That's it. The script will:
- Create a Python virtual environment (`.venv`)
- Install all dependencies from `requirements.txt`
- Initialize the SQLite database (`database/paals.db`)
- Seed ~10,000 realistic supply chain records (first run only, takes ~5 seconds)
- Start the web server

---

### Access the Application

After `start.bat` completes, open your browser:

| Page | URL |
|---|---|
| Dashboard | http://127.0.0.1:8000 |
| Deviations | http://127.0.0.1:8000/deviations |
| Action Centre | http://127.0.0.1:8000/action-centre |
| Suppliers | http://127.0.0.1:8000/suppliers |
| Purchase Orders | http://127.0.0.1:8000/purchase-orders |
| Digital Twin | http://127.0.0.1:8000/digital-twin |
| Research | http://127.0.0.1:8000/research |
| API Docs | http://127.0.0.1:8000/docs |

---

## Project Structure

```
paals/
├── app/
│   ├── agents/
│   │   └── deviation_agent.py     # LangGraph agentic workflow
│   ├── models/
│   │   ├── database.py            # SQLite init + async connection
│   │   └── schema.py              # Pydantic data models
│   ├── routes/
│   │   └── api.py                 # All REST API endpoints
│   ├── services/
│   │   ├── graph.py               # NetworkX supply chain graph + dashboard metrics
│   │   ├── seed.py                # 10,000-record data generator (auto-runs on start)
│   │   ├── kaggle_import.py       # Kaggle DataCo dataset importer (auto-runs on start)
│   │   ├── scms_import.py         # Kaggle USAID SCMS dataset importer (auto-runs on start)
│   │   └── websocket.py           # Live event broadcaster
│   ├── static/
│   │   ├── css/main.css           # Dark industrial design system
│   │   └── js/                    # Page-specific frontend scripts
│   └── templates/                 # Jinja2 HTML templates
├── data/kaggle/
│   ├── DataCoSupplyChainDataset.csv  # Kaggle DataCo dataset (95.9 MB, see below)
│   └── scms/SCMS_Delivery_History_Dataset.csv  # Kaggle USAID SCMS dataset (3.8 MB)
├── database/
│   └── paals.db                   # SQLite database (auto-created on first run)
├── main.py                        # FastAPI application entry point
├── requirements.txt               # Python dependencies
├── start.bat                      # Windows one-click launcher
├── .env.example                   # Environment variable template
└── README.md                      # This file
```

---

## Dataset

On first run the database is automatically populated with **~10,000 records**:

| Table | Records |
|---|---|
| Suppliers | 20 |
| Customers | 10 |
| Purchase Orders | 4,000 |
| Deliveries | 4,000 |
| Customer Orders | ~7,800 |
| Deviations | ~720 |
| Agent Recommendations | ~380 |
| Event Log | ~3,000+ |

All data is realistic: real company names, actual trade routes, accurate
port-of-origin/destination pairs, correct incoterms, and coherent
inter-table relationships.

### Kaggle dataset — DataCo Smart Supply Chain

PAALS also imports the real
[DataCo Smart Supply Chain](https://www.kaggle.com/datasets/shashwatwork/dataco-smart-supply-chain-for-big-data-analysis)
dataset (180,519 order lines, 65,752 orders, Jan 2015 – Jan 2018; CC BY 4.0,
original at [Mendeley Data](https://data.mendeley.com/datasets/8gx2fvg2k6/5)).
It is added **alongside** the synthetic data — all imported IDs start with `DC-`.

**Getting the file:** download `DataCoSupplyChainDataset.csv` from Kaggle or
Mendeley and place it at `data/kaggle/DataCoSupplyChainDataset.csv`. On the next
start the server imports it in the background (~30 s, first run only). To
re-import manually: `python -m app.services.kaggle_import --force`.

| DataCo | PAALS table | IDs |
|---|---|---|
| Market × Shipping Mode lane | `suppliers` (reliability = real on-time rate) | `DC-SUP-01…20` |
| Customer Segment × Market | `customers` | `DC-CUST-01…15` |
| Order | `purchase_orders`, `deliveries`, `customer_orders` | `DC-PO-<id>`, `DC-DLV-<id>`, `DC-CO-<id>` |
| Late shipment (real > scheduled days) | `deviations` — `late_delivery` | `DC-DEV-<id>` |
| Order status `SUSPECTED_FRAUD` | `deviations` — `suspected_fraud` | `DC-DEV-<id>` |
| Every order line (PII columns dropped) | `kaggle_dataco_items` | — |

Severity for late deliveries is driven by days late (≥4 high, 3 medium, else low),
raised one level for Corporate customers or orders ≥ $1,000. A DataCo deviation is
**active** only if its order is still open and falls in the last 30 days of the
dataset (`PAALS_KAGGLE_ACTIVE_DAYS`); older ones are history (resolved). When the
agent runs on a DataCo deviation, alternative suppliers are the other DataCo lanes
in the same region with better measured reliability.

### Kaggle dataset — USAID SCMS Shipment Pricing

The second imported dataset is
[Supply Chain Shipment Pricing Data](https://www.kaggle.com/datasets/divyeshardeshana/supply-chain-shipment-pricing-data):
USAID's Supply Chain Management System delivery history for PEPFAR health commodities
(10,324 shipment lines, 6,233 POs, 73 vendors, 43 countries, deliveries May 2006 – Sep 2015).
Kaggle lists the licence as unknown; the data was originally released publicly by USAID.
All imported IDs start with `SC-`.

**Getting the file:** with a Kaggle API token in `~/.kaggle/kaggle.json`, run

    .venv\Scripts\kaggle datasets download -d divyeshardeshana/supply-chain-shipment-pricing-data -p data\kaggle\scms --unzip

It is imported on the next start (~4 s). Re-import manually with
`python -m app.services.scms_import --force`.

| SCMS | PAALS table | IDs |
|---|---|---|
| Vendor | `suppliers` (reliability = real on-time rate, lead = median PO→delivery days) | `SC-SUP-01…73` |
| Destination country | `customers` | `SC-CUST-01…43` |
| `PO / SO #` | `purchase_orders`, `customer_orders` | `SC-PO-<po>`, `SC-CO-<po>` |
| `ASN/DN #` shipment | `deliveries` | `SC-DLV-<asn>` |
| Delivered after scheduled date | `deviations` — `late_delivery` | `SC-DEV-L-<asn>` |
| Recorded 14+ days after delivery | `deviations` — `goods_receipt_skip` | `SC-DEV-R-<asn>` |
| Every shipment line | `kaggle_scms_lines` | — |

Late-delivery severity: ≥60 days late critical, ≥14 high, ≥7 medium, else low; raised
one level when the shipment (value + freight) is ≥ $500,000. A deviation is active only
if it falls in the last 180 days of the dataset (`PAALS_SCMS_ACTIVE_DAYS`). The CSV is
UTF-8 with a BOM (country names like Côte d'Ivoire), unlike DataCo, which is Latin-1.

### Where imported data shows up

**Source** filters on Deviations, Purchase Orders and Suppliers (Synthetic, Kaggle · DataCo,
Kaggle · USAID SCMS); the dashboard totals include every source; the Research page has a
section per dataset backed by `GET /api/kaggle/insights` and `GET /api/kaggle/scms/insights`.
`/api/deviations`, `/api/purchase-orders` and `/api/suppliers` accept
`?source=synthetic|dataco|scms|kaggle` (`kaggle` = both imported datasets).

---

## Features

- **Real-time dashboard** — active deviations, financial exposure, severity
  breakdown, deviation-type analytics
- **Deviation management** — full list with filters, per-deviation detail
  with agent recommendations
- **LangGraph agent** — autonomous 6-node graph: risk evaluation →
  downstream impact → action selection → alternative sourcing →
  communication drafting → approval gating
- **Action Centre** — approve or reject pending agent recommendations
- **Digital Twin** — D3 force-directed graph of supplier → PO → customer
  relationships, with deviation overlays
- **Suppliers page** — tier/region/reliability breakdown with live
  deviation exposure
- **Purchase Orders** — filterable, sortable list with status and line items
- **Research page** — system-wide statistics and export
- **Live WebSocket feed** — simulated real-time operational events

---

## Stopping the Server

Press `Ctrl + C` in the terminal window where `start.bat` is running.

---

## Restarting After First Run

Subsequent starts are fast — dependencies are already installed and the
database is already seeded. Just run `start.bat` again.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` not found | Re-install Python and check "Add to PATH" |
| Port 8000 in use | Edit `start.bat` — change `--port 8000` to `--port 8001` |
| Database error | Delete `database/paals.db` and re-run `start.bat` |
| Blank page in browser | Wait 3 seconds and refresh — server may still be starting |
