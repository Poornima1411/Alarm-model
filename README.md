# Cooling Water Report Generation Agent — GitHub Copilot POC

Generates monthly cooling water performance reports using **GitHub Copilot in VS Code**.
No model API keys needed. Copilot reads the data from files and writes the report.

---

## How it works

```
Step 1 — prefetch_site.py        (you run this — needs DB + Buckman API credentials)
          │
          ├─ SQL: get_site_controllers.sql  →  controllers.json
          ├─ SQL: get_service_notes.sql     →  service_notes.json
          ├─ SQL: get_ade_data.sql          →  ade_data.json
          └─ Buckman API (telemetry)        →  telemetry/<serial>_summary.json

Step 2 — prepare_report_context.py  (you run this — no credentials needed)
          │
          └─ Reads all prefetched files
             Writes: data_store/<slug>/REPORT_CONTEXT.md
             (one clean Markdown file with all numbers, notes, and ADE data)

Step 3 — GitHub Copilot in VS Code  (Copilot does this)
          │
          └─ You open REPORT_CONTEXT.md in VS Code
             You paste the task prompt from Section 7 of REPORT_CONTEXT.md into Copilot Chat
             Copilot reads the file and generates the report
             Output: output/<site>_<month>_report.md
```

---

## Quickstart

```bash
# 1. Setup
pip install -r requirements.txt
cp .env.example .env          # fill in DB credentials + Buckman API credentials

# 2. Fetch data for a site (run once per site per month)
python prefetch_site.py --site "Flowserve US Raleigh NC (US)" --month "May 2026"

# 3. Build the Copilot context file
python prepare_report_context.py --site "Flowserve US Raleigh NC (US)" --month "May 2026"

# 4. Open VS Code
code .

# 5. Open the context file:
#    data_store/flowserve_us_raleigh_nc_us_may_2026/REPORT_CONTEXT.md

# 6. Open Copilot Chat (Ctrl+Shift+I)

# 7. Paste the task prompt from Section 7 at the bottom of REPORT_CONTEXT.md
```

---

## Try it now (no credentials needed)

An example prefetch + context file is already included:

```bash
# The example data is already there — just run step 3:
python prepare_report_context.py --site "Flowserve US Raleigh NC (US)" --month "May 2026"

# Then open VS Code and follow steps 4–7 above
```

---

## Project structure

```
report-agent/
│
├── prefetch_site.py              ← Step 1: fetch data for one site+month
├── prepare_report_context.py     ← Step 2: build REPORT_CONTEXT.md for Copilot
├── requirements.txt
├── .env.example
│
├── .github/
│   └── copilot-instructions/
│       └── report-agent.md       ← Copilot agent rules (auto-loaded by VS Code)
│
├── sql/
│   ├── get_site_controllers.sql  ← Real production SQL (featureRollOutMapping join)
│   ├── get_service_notes.sql     ← Real production SQL (ServiceNote.ServiceNote)
│   └── get_ade_data.sql          ← Real production SQL (MDETemplate + Latest CTE)
│
├── src/
│   ├── data/
│   │   ├── sql_fetcher.py        ← Runs SQL via pyodbc
│   │   └── telemetry_fetcher.py  ← Buckman API login + telemetry export
│   └── analysis/
│       └── kpi_calculator.py     ← Computes stats from telemetry (used by prepare script)
│
├── training_reports/
│   ├── README.md                 ← What Copilot learns from the training examples
│   ├── Flowserve_report.pdf      ← (add the PDF here)
│   ├── st_joseph_report.pdf      ← (add the PDF here)
│   └── Synthomer_*.pdf           ← (add the PDF here)
│
├── data_store/
│   └── flowserve_us_raleigh_nc_us_may_2026/   ← example prefetch output
│       ├── manifest.json
│       ├── controllers.json
│       ├── service_notes.json
│       ├── ade_data.json
│       ├── REPORT_CONTEXT.md                  ← what Copilot reads
│       └── telemetry/
│           └── 84253FA7D35B_summary.json
│
└── output/                       ← generated reports go here (gitignored)
```

---

## The two scripts

### `prefetch_site.py`
Fetches all data for one site from SQL + Buckman API and saves to disk.
Run once per site per month. Resumable — skips files that already exist.

```bash
python prefetch_site.py --site "Synthomer Chester SC (US)" --month "May 2026"
python prefetch_site.py --site "Flowserve US Raleigh NC (US)" --month "May 2026" --force  # re-fetch
```

### `prepare_report_context.py`
Reads the prefetched data and writes a single `REPORT_CONTEXT.md` for Copilot.
No credentials needed. Safe to re-run any time.

```bash
python prepare_report_context.py --site "Synthomer Chester SC (US)" --month "May 2026"
```

---

## SQL table mapping

The SQL files use the real Buckman production schema. No changes needed unless your schema differs.

| SQL file | Key tables used |
|---|---|
| `get_site_controllers.sql` | `dbo.Device`, `dbo.featureRollOutMapping`, `dbo.Plant`, `dbo.Component`, `dbo.PlantSystem` |
| `get_service_notes.sql` | `ServiceNote.ServiceNote`, `dbo.Plant`, `Context.Vertex`, `dbo.Status` |
| `get_ade_data.sql` | `dbo.MDETemplate`, `dbo.Plant`, `Context.ParameterInstance`, `dbo.Latest` (CTE) |

---

## When the model is approved

Replace Step 3 (Copilot Chat) with an API call to whichever model is approved.
The `REPORT_CONTEXT.md` and `.github/copilot-instructions/report-agent.md` become
the system + user prompt. No other changes needed.
