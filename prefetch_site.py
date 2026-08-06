"""
prefetch_site.py
────────────────
Step 1 — fetch ALL data for one site + month and save to disk.

USAGE
─────
    python prefetch_site.py --site "Flowserve US Raleigh NC (US)" --month "May 2026"
    python prefetch_site.py --site "Synthomer Chester SC (US)"    --month "May 2026"
    python prefetch_site.py --site "Flowserve US Raleigh NC (US)" --month "May 2026" --force

OUTPUT
──────
    data_store/flowserve_us_raleigh_nc_us_may_2026/
    ├── manifest.json           what was fetched and when
    ├── controllers.json        all ACM serial numbers at the site
    ├── service_notes.json      field service notes for the month
    ├── ade_data.json           ADE/MDE field test data (FRC, pH etc.)
    ├── scc.json                SCC setpoints: SP, HH, LL, H, L, product names
    └── telemetry/
        ├── <serial>.parquet            full raw telemetry (90 days)
        └── <serial>_summary.json       per-sensor stats Copilot reads
"""

import argparse
import calendar
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from src.report_cache import build_cache_slug, normalize_controller_ids

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
)
log = logging.getLogger("prefetch_site")

ROOT       = Path(__file__).parent
DATA_STORE = ROOT / "data_store"

sys.path.insert(0, str(ROOT))


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Pre-fetch all report data for one site + month."
    )
    site_group = p.add_mutually_exclusive_group(required=True)
    site_group.add_argument("--site",
                            help='Site name exactly as in the DB e.g. "Flowserve US Raleigh NC (US)"')
    site_group.add_argument("--controller-id", "--controller-ids",
                            nargs="+", dest="controller_ids",
                            help="One or more controller serial numbers to include in one report")
    p.add_argument("--month", required=True,
                   help='Reporting month e.g. "May 2026"')
    p.add_argument("--days",  type=int, default=None,
                   help="Days of telemetry to fetch (default 90)")
    p.add_argument("--force", action="store_true",
                   help="Re-fetch even if cache already exists")
    return p.parse_args()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    reporting_month = args.month
    requested_controller_ids = normalize_controller_ids(args.controller_ids)

    start_date, end_date = _month_to_range(reporting_month)

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")

    import pandas as pd
    from src.data.sql_fetcher import (
        fetch_ade_data,
        fetch_controllers_by_serials,
        fetch_service_notes,
        fetch_site_controllers,
    )
    from src.data.telemetry_fetcher import fetch_telemetry, get_bearer_token
    from src.data.scc_fetcher import fetch_scc_for_site

    days = args.days or int(os.environ.get("TELEMETRY_DAYS", 90))

    if requested_controller_ids:
        log.info("Resolving controller ID(s) from SQL: %s", requested_controller_ids)
        resolved_controllers_df = fetch_controllers_by_serials(requested_controller_ids)
        if resolved_controllers_df.empty:
            log.error("No active ACM controllers found for: %s", requested_controller_ids)
            sys.exit(1)

        found = {str(value).lower() for value in resolved_controllers_df["SerialNumber"].dropna().tolist()}
        missing = [value for value in requested_controller_ids if value.lower() not in found]
        if missing:
            log.error("Controller ID(s) not found or not ACM-enabled: %s", missing)
            sys.exit(1)

        site_names = sorted({str(value).strip() for value in resolved_controllers_df["SiteName"].dropna().tolist()})
        if len(site_names) != 1:
            log.error("Controller IDs must belong to one site for a single report. Found sites: %s", site_names)
            sys.exit(1)
        site_name = site_names[0]
    else:
        site_name = args.site
        resolved_controllers_df = None

    slug    = build_cache_slug(site_name, reporting_month, requested_controller_ids)
    out_dir = DATA_STORE / slug
    tel_dir = out_dir / "telemetry"

    out_dir.mkdir(parents=True, exist_ok=True)
    tel_dir.mkdir(parents=True, exist_ok=True)

    log.info("=" * 60)
    log.info(f"PREFETCH  →  {site_name}  |  {reporting_month}")
    if requested_controller_ids:
        log.info(f"Requested controllers → {requested_controller_ids}")
    log.info(f"Output    →  {out_dir}")
    log.info(f"Period    →  {start_date}  →  {end_date}")
    log.info("=" * 60)

    # ── Step 1: Controllers ───────────────────────────────────────────────────
    ctrl_path = out_dir / "controllers.json"
    if requested_controller_ids:
        log.info("Step 1/5 — Using requested controller ID(s) from SQL …")
        controllers_df = resolved_controllers_df
        controllers_df.to_json(ctrl_path, orient="records", indent=2)
        log.info(f"  ✓  {len(controllers_df)} requested controller(s) → controllers.json")
    elif ctrl_path.exists() and not args.force:
        log.info("Step 1/5 — controllers.json already cached, skipping")
        controllers_df = pd.read_json(ctrl_path)
    else:
        log.info("Step 1/5 — Fetching controllers from SQL …")
        controllers_df = fetch_site_controllers(site_name)
        if controllers_df.empty:
            log.error(f"No controllers found for: {site_name!r}")
            log.error("Check the exact site name with:  SELECT DISTINCT p.Name FROM dbo.Plant p WHERE p.Name LIKE '%keyword%'")
            sys.exit(1)
        controllers_df.to_json(ctrl_path, orient="records", indent=2)
        log.info(f"  ✓  {len(controllers_df)} controller(s) → controllers.json")

    ctrl_ids = controllers_df["SerialNumber"].dropna().unique().tolist()
    log.info(f"  Controllers: {ctrl_ids}")

    # ── Step 2: Service notes ─────────────────────────────────────────────────
    sn_path = out_dir / "service_notes.json"
    if sn_path.exists() and not args.force:
        log.info("Step 2/5 — service_notes.json already cached, skipping")
    else:
        log.info("Step 2/5 — Fetching service notes from SQL …")
        sn_df = fetch_service_notes(site_name, start_date, end_date)
        sn_df.to_json(sn_path, orient="records", indent=2, date_format="iso")
        log.info(f"  ✓  {len(sn_df)} service note(s) → service_notes.json")

    # ── Step 3: ADE data ──────────────────────────────────────────────────────
    ade_path = out_dir / "ade_data.json"
    if ade_path.exists() and not args.force:
        log.info("Step 3/5 — ade_data.json already cached, skipping")
    else:
        log.info("Step 3/5 — Fetching ADE data from SQL …")
        ade_df = fetch_ade_data(site_name, start_date, end_date)
        ade_df.to_json(ade_path, orient="records", indent=2, date_format="iso")
        log.info(f"  ✓  {len(ade_df)} ADE record(s) → ade_data.json")

    # ── Step 4: SCC from Cosmos ───────────────────────────────────────────────
    scc_path = out_dir / "scc.json"
    if scc_path.exists() and not args.force:
        log.info("Step 4/5 — scc.json already cached, skipping")
    else:
        log.info("Step 4/5 — Fetching SCC from Cosmos DB …")
        scc_df = fetch_scc_for_site(controllers_df)
        if scc_df is not None and not scc_df.empty:
            scc_df.to_json(scc_path, orient="records", indent=2)
            log.info(f"  ✓  {len(scc_df)} SCC rows → scc.json")
        else:
            log.warning("  ✗  No SCC data returned — scc.json not written")
            log.warning("     Check COSMOS_URL / COSMOS_KEY in .env")

    # ── Step 5: Telemetry ─────────────────────────────────────────────────────
    log.info(f"Step 5/5 — Fetching {days}-day telemetry from Buckman API …")
    token = get_bearer_token()
    if not token:
        log.error("  Buckman API login failed — telemetry skipped")
    else:
        telem_done = 0
        for serial in ctrl_ids:
            pq_path  = tel_dir / f"{serial}.parquet"
            sum_path = tel_dir / f"{serial}_summary.json"

            if pq_path.exists() and not args.force:
                log.info(f"  {serial} — already cached, skipping")
                continue

            log.info(f"  Fetching {serial} …")
            telem_df = fetch_telemetry([serial], days=days)
            if telem_df is None or telem_df.empty:
                log.warning(f"  {serial} — no data returned")
                continue

            telem_df.to_parquet(pq_path, index=False)
            _save_telemetry_summary(telem_df, serial, sum_path)
            telem_done += 1
            log.info(f"  ✓  {serial} — {len(telem_df):,} rows")

        log.info(f"  Telemetry done: {telem_done}/{len(ctrl_ids)} controller(s)")

    # ── Manifest ──────────────────────────────────────────────────────────────
    manifest = {
        "fetched_at":      datetime.utcnow().isoformat(),
        "site_name":       site_name,
        "requested_controller_ids": requested_controller_ids,
        "reporting_month": reporting_month,
        "start_date":      start_date,
        "end_date":        end_date,
        "telemetry_days":  days,
        "controllers":     ctrl_ids,
        "files": {
            "controllers":   "controllers.json",
            "service_notes": "service_notes.json",
            "ade_data":      "ade_data.json",
            "scc":           "scc.json",
            "telemetry_dir": "telemetry/",
        },
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    log.info("")
    log.info("=" * 60)
    log.info(f"✅  Prefetch complete  →  {out_dir}")
    log.info(f"    Next step:")
    if requested_controller_ids:
        controller_args = " ".join(f'"{controller_id}"' for controller_id in requested_controller_ids)
        log.info(f'    python prepare_report_context.py --controller-ids {controller_args} --month "{reporting_month}"')
    else:
        log.info(f'    python prepare_report_context.py --site "{site_name}" --month "{reporting_month}"')
    log.info("=" * 60)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _month_to_range(month_str: str):
    dt = datetime.strptime(month_str, "%B %Y")
    _, last = calendar.monthrange(dt.year, dt.month)
    return dt.strftime("%Y-%m-01"), f"{dt.year}-{dt.month:02d}-{last:02d}"


def _slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _save_telemetry_summary(df, serial: str, path: Path):
    """Compact JSON summary — per-sensor stats + last 20 readings."""
    import pandas as pd

    summary = {"controller": serial, "total_rows": len(df),
                "time_range": {}, "sensors": {}}

    ts_col = next(
        (c for c in df.columns if any(k in c.lower()
         for k in ("time", "date", "timestamp"))), None,
    )
    if ts_col:
        try:
            df = df.sort_values(ts_col)
            summary["time_range"] = {
                "from": str(df[ts_col].iloc[0]),
                "to":   str(df[ts_col].iloc[-1]),
            }
        except Exception:
            pass

    for col in df.columns:
        if col in (ts_col, "Controller ID", "ControllerName"):
            continue
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if series.empty:
            continue
        summary["sensors"][col] = {
            "count":     int(series.count()),
            "min":       round(float(series.min()), 4),
            "max":       round(float(series.max()), 4),
            "mean":      round(float(series.mean()), 4),
            "first":     round(float(series.iloc[0]), 4),
            "last":      round(float(series.iloc[-1]), 4),
            "recent_20": [round(float(v), 4) for v in series.tail(20).tolist()],
        }

    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
