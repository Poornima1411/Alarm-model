# How to Run — Report Generation Agent

---

## One-time setup (do this once)

### 1. Install Python dependencies

```
pip install pandas pyodbc requests python-dotenv pyarrow
```

For Word report generation and checklist scoring, also install:

```
pip install matplotlib numpy python-docx openpyxl
```

> You need **ODBC Driver 18 for SQL Server** installed on Windows.
> Download from: https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

---

### 2. Create your `.env` file

Copy `.env.example` to `.env` in the same folder:

```
copy .env.example .env
```

Open `.env` and fill in:

```
BUCKMAN_TOKEN=        ← paste your fresh bearer token here (see below)
OBS_API_BASE=https://budig-bb-bbapiappa-01-p.azurewebsites.net/api/v1
PBA_USERNAME=         ← optional service account username for telemetry login
PBA_PASSWORD=         ← optional service account password for telemetry login
SQL_SERVER=tcp:budig-bb-sqls-01-p.database.windows.net
SQL_DATABASE=budig-bb-dbsql-01-p
SQL_USERNAME=prod_db_support
SQL_PASSWORD=         ← fill in the password
```

**How to get a fresh bearer token:**
1. Open the Buckman web app in Chrome
2. Press F12 → go to the **Network** tab
3. Click on any request
4. Find the **Authorization** header
5. Copy the value — it starts with `eyJ...`
6. Paste it into `.env` as `BUCKMAN_TOKEN=eyJ...` (no "Bearer " prefix)

> The token expires in ~24 hours. If telemetry fails with 401, paste a fresh one.

---

## Running for any site

### Step 1 — Fetch the data

```
python prefetch_site.py --site "EXACT SITE NAME FROM DB" --month "Month YYYY"
```

You can also run by controller ID instead of site name. Use one controller ID for a
single-controller report, or pass multiple controller IDs from the same site to build
one combined site report with multiple controller telemetry files:

```
python prefetch_site.py --controller-ids "84253F5EE1C9" --month "May 2026"
python prefetch_site.py --controller-ids "84253F5EE1C9" "84253FAB8CC5" --month "May 2026"
```

When controller IDs are used, the script resolves the site name from SQL. All listed
controller IDs must belong to the same site.

**Examples:**
```
python prefetch_site.py --site "Flowserve US Raleigh NC (US)" --month "May 2026"
python prefetch_site.py --site "Synthomer Chester SC (US)" --month "May 2026"
python prefetch_site.py --site "St. Joseph's Hospital Savannah GA (US)" --month "May 2026"
```

This saves everything to:
```
data_store/
└── flowserve_us_raleigh_nc_us_may_2026/
    ├── manifest.json           ← what was fetched and when
    ├── controllers.json        ← all ACM controllers at the site
    ├── service_notes.json      ← field notes for the month
    ├── ade_data.json           ← ADE/MDE measurements (FRC, pH, etc.)
    └── telemetry/
        ├── 84253FA7D35B.parquet          ← full raw telemetry (90 days)
        └── 84253FA7D35B_summary.json     ← sensor stats Copilot reads
```

**Important — the site name must match exactly what is in the database.**
If you get "No controllers found", run this SQL to find the exact name:
```sql
SELECT DISTINCT p.Name AS SiteName
FROM dbo.Plant p
WHERE p.Name LIKE '%Flowserve%'   -- change the search term
ORDER BY p.Name
```

---

### Step 2 — Build the Copilot context file

```
python prepare_report_context.py --site "EXACT SITE NAME" --month "Month YYYY"
```

If Step 1 used controller IDs, use the same controller IDs here:

```
python prepare_report_context.py --controller-ids "84253F5EE1C9" "84253FAB8CC5" --month "May 2026"
```

**Examples:**
```
python prepare_report_context.py --site "Flowserve US Raleigh NC (US)" --month "May 2026"
python prepare_report_context.py --site "Synthomer Chester SC (US)" --month "May 2026"
```

This writes one file:
```
data_store/flowserve_us_raleigh_nc_us_may_2026/REPORT_CONTEXT.md
```

That file has all the KPIs, service notes, ADE data, and the task prompt for Copilot
— all in one place.

---

### Step 3 — Generate the report with GitHub Copilot

1. Open **VS Code** in the project folder:
   ```
   code .
   ```

2. Open the context file in the editor:
   ```
   data_store/flowserve_us_raleigh_nc_us_may_2026/REPORT_CONTEXT.md
   ```

3. Open **Copilot Chat** — press `Ctrl+Shift+I`

4. Scroll to the bottom of `REPORT_CONTEXT.md` — **Section 7** has the task prompt already written for you.

5. Copy the text inside the triple backticks in Section 7 and paste it into Copilot Chat.

6. Copilot will generate the full report and save it to:
   ```
   output/flowserve_us_raleigh_nc_us_may_2026_report.md
   ```

---

### Step 4 — Generate Word report and automatic checklist score

If `narrative_cache.json` has been created, run:

```
python generate_report.py --site "EXACT SITE NAME" --month "Month YYYY"
```

For a controller-ID cache, use the same controller IDs:

```
python generate_report.py --controller-ids "84253F5EE1C9" "84253FAB8CC5" --month "May 2026"
```

Every time `generate_report.py` creates the Word report, it now reads
`Report Checklist/report checklist.xlsx`, checks each numbered checklist item
one by one, and saves the scorecard to:

```
output/<slug>_scorecard.json
```

You can also run the checklist scorer separately:

```
python score_report.py --site "EXACT SITE NAME" --month "Month YYYY" --verbose
python score_report.py --controller-ids "84253F5EE1C9" "84253FAB8CC5" --month "May 2026" --verbose
```

---

## What the folder looks like after running for multiple sites

```
report-agent/
├── .env                                    ← your credentials (never commit this)
├── prefetch_site.py
├── prepare_report_context.py
│
├── data_store/
│   ├── flowserve_us_raleigh_nc_us_may_2026/
│   │   ├── manifest.json
│   │   ├── controllers.json
│   │   ├── service_notes.json
│   │   ├── ade_data.json
│   │   ├── REPORT_CONTEXT.md               ← open this in VS Code
│   │   └── telemetry/
│   │       ├── 84253FA7D35B.parquet
│   │       └── 84253FA7D35B_summary.json
│   │
│   ├── synthomer_chester_sc_us_may_2026/
│   │   ├── manifest.json
│   │   ├── controllers.json
│   │   ├── service_notes.json
│   │   ├── ade_data.json
│   │   ├── REPORT_CONTEXT.md
│   │   └── telemetry/
│   │       ├── AABBCC112233.parquet
│   │       └── AABBCC112233_summary.json
│   │
│   └── st_josephs_hospital_savannah_ga_us_may_2026/
│       └── ...
│
├── output/
│   ├── flowserve_us_raleigh_nc_us_may_2026_report.md    ← Copilot writes here
│   └── synthomer_chester_sc_us_may_2026_report.md
│
├── training_reports/
│   ├── Flowserve_report.pdf
│   ├── st_joseph_report.pdf
│   └── Synthomer_Cooling_Tower_Performance_Report_-_May_26.pdf
│
└── sql/
    ├── get_site_controllers.sql
    ├── get_service_notes.sql
    └── get_ade_data.sql
```

One folder per site per month. Each folder is self-contained — you can regenerate
the report any time by re-running Step 3 without fetching again.

---

## Re-running and caching

**Skip the fetch if already cached** (default behaviour):
```
python prefetch_site.py --site "Flowserve US Raleigh NC (US)" --month "May 2026"
# → skips files that already exist
```

**Force a fresh fetch** (e.g. new service notes added):
```
python prefetch_site.py --site "Flowserve US Raleigh NC (US)" --month "May 2026" --force
```

**Rebuild REPORT_CONTEXT.md without re-fetching** (e.g. you adjusted the script):
```
python prepare_report_context.py --site "Flowserve US Raleigh NC (US)" --month "May 2026"
# → always overwrites REPORT_CONTEXT.md, reads from existing cache
```

For a controller-ID cache:
```
python prepare_report_context.py --controller-ids "84253F5EE1C9" "84253FAB8CC5" --month "May 2026"
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `No controllers found for site` | Site name doesn't match DB exactly. Run the SQL above to find it. |
| `HTTP 401` on telemetry | Bearer token expired. Paste a fresh one into `.env` as `BUCKMAN_TOKEN=`. |
| `pyodbc.InterfaceError` | ODBC Driver 18 not installed. Download from the Microsoft link above. |
| `Login failed for user` | Check `SQL_USERNAME` and `SQL_PASSWORD` in `.env`. |
| Copilot writes absolute ORP values | Remind Copilot: "Never mention absolute ORP values — only ORP spike / Delta ORP response language" |
| REPORT_CONTEXT.md is empty / short | The prefetch may have failed. Check the telemetry folder for `_summary.json` files. |

---

## Quick reference — all commands

```bash
# Setup (once)
pip install pandas pyodbc requests python-dotenv pyarrow
copy .env.example .env        # then fill in credentials

# For each site + month:
python prefetch_site.py         --site "Site Name" --month "May 2026"
python prepare_report_context.py --site "Site Name" --month "May 2026"
python generate_report.py       --site "Site Name" --month "May 2026"   # also writes scorecard

# Then in VS Code:
# Open data_store/<slug>/REPORT_CONTEXT.md
# Open Copilot Chat (Ctrl+Shift+I)
# Paste the task from Section 7 of REPORT_CONTEXT.md
```
