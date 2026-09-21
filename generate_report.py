"""
generate_report.py — Step 4
Reads:
  - data_store/<slug>/narrative_cache.json   (AI narrative from Copilot)
  - data_store/<slug>/telemetry/<serial>.parquet  (full raw telemetry)
  - data_store/<slug>/scc.json, ade_data.json, controllers.json

Generates proper date-axis charts matching training report style,
then assembles the Word document: chart first, then AI narrative below it.

USAGE:
    python generate_report.py --site "Synthomer Chester SC (US)" --month "May 2026"
"""
import argparse, difflib, json, re, sys, zipfile
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np

from docx import Document
from docx.shared import Inches, Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from src.report_cache import build_cache_slug, find_cache_by_controller_ids, normalize_controller_ids
from src.report_status import STATUS_ACCEPTABLE, STATUS_CRITICAL, STATUS_EXCELLENT, STATUS_PATTERN, display_status, status_from_limits, status_from_percent

ROOT       = Path(__file__).parent
DATA_STORE = ROOT / "data_store"
OUTPUT_DIR = ROOT / "output"
CHARTS_DIR = OUTPUT_DIR / "charts"
OUTPUT_DIR.mkdir(exist_ok=True)
CHARTS_DIR.mkdir(exist_ok=True)
WATER_LOSS_THRESHOLD_PCT = 3.0
SETPOINT_MAINTAINED_TOLERANCE_PCT = 3.0
CELL_FOULING_THRESHOLD_PCT = 30.0

GREEN = RGBColor(0x00,0x85,0x7C); WHITE = RGBColor(0xFF,0xFF,0xFF)
AMBER = RGBColor(0xB8,0x86,0x0B); RED   = RGBColor(0xC0,0x00,0x00)
GREY  = RGBColor(0x44,0x44,0x44)
GH="#00857C"; BH="#0077BB"; RH="#C00000"; YH="#E07000"


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def _load_mu_conductivity(site):
    """Read MU conductivity from data/MU_conductivity.xlsx if present. Returns float or None."""
    mu_file = ROOT / "data" / "MU_conductivity.xlsx"
    if not mu_file.exists():
        return None
    try:
        import openpyxl
        wb = openpyxl.load_workbook(mu_file, data_only=True)
        ws = wb.active
        # Search ALL rows for this site — return first non-null MU value
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or not row[0]: continue
            if str(row[0]).strip().lower() == site.strip().lower():
                val = row[3] if len(row) > 3 else None
                if val is None or str(val).lower() in ("no data","none",""):
                    continue   # skip this row, keep looking for another match
                try: return float(val)
                except: continue
    except Exception as e:
        print(f"  [WARN] Could not read MU_conductivity.xlsx: {e}")
    return None


def _normal_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _float_or_none(value):
    try:
        return float(value) if value not in (None, "NULL", "") else None
    except (TypeError, ValueError):
        return None


def _load_water_efficiency_inputs(site, controllers):
    """Read value-creation water-efficiency rows for the current report scope."""
    value_file = ROOT / "data" / "Value creation.xlsx"
    if not value_file.exists():
        return []

    controller_ids = {
        _normal_key(controller.get("SerialNumber"))
        for controller in controllers
        if controller.get("SerialNumber")
    }
    site_key = _normal_key(site)
    records = []

    try:
        import openpyxl
        wb = openpyxl.load_workbook(value_file, data_only=True)
        ws = wb["Water Efficiency"] if "Water Efficiency" in wb.sheetnames else wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [_normal_key(header) for header in rows[0]]

        def col(*names):
            wanted = {_normal_key(name) for name in names}
            return next((idx for idx, header in enumerate(headers) if header in wanted), None)

        idx_controller = col("Controller Id", "Controller ID")
        idx_site = col("Site Name")
        idx_system = col("System Name")
        idx_target = col("Potential CT Cycles", "Target COC")
        idx_temp = col("Delta T ( F)", "Delta T (F)", "Temperature")
        idx_recirculation = col("Recirculation Rate (gpm)", "Recirculation Rate")
        idx_hours = col("Operating hours", "Operating Hours")

        all_records = []
        for row in rows[1:]:
            record = {
                "controller_id": str(row[idx_controller]).strip() if idx_controller is not None and row[idx_controller] else "",
                "site_name": str(row[idx_site]).strip() if idx_site is not None and row[idx_site] else "",
                "system_name": str(row[idx_system]).strip() if idx_system is not None and row[idx_system] else "",
                "target_coc": _float_or_none(row[idx_target]) if idx_target is not None else None,
                "temperature": _float_or_none(row[idx_temp]) if idx_temp is not None else None,
                "recirculation_rate": _float_or_none(row[idx_recirculation]) if idx_recirculation is not None else None,
                "operating_hours": _float_or_none(row[idx_hours]) if idx_hours is not None else None,
            }
            if record["target_coc"] and record["temperature"] is not None and record["recirculation_rate"]:
                all_records.append(record)

        exact_matches = [
            record for record in all_records
            if record["controller_id"] and _normal_key(record["controller_id"]) in controller_ids
        ]
        if exact_matches:
            return exact_matches

        site_matches = [record for record in all_records if _normal_key(record["site_name"]) == site_key]
        if site_matches:
            return site_matches

        fuzzy_matches = []
        for record in all_records:
            workbook_site_key = _normal_key(record["site_name"])
            if difflib.SequenceMatcher(None, site_key, workbook_site_key).ratio() >= 0.78:
                fuzzy_matches.append(record)
        return fuzzy_matches
    except Exception as e:
        print(f"  [WARN] Could not read Value creation.xlsx water efficiency data: {e}")
    return records


def compute_water_loss(coc, water_efficiency_inputs):
    """Calculate annual water loss and cost when current COC is below target."""
    current_coc = coc.get("actual_coc") if coc else None
    if current_coc is None or current_coc <= 1:
        return {"available": False, "triggered": False, "reason": "Current COC is not available or is <= 1."}

    rows = []
    for record in water_efficiency_inputs:
        target_coc = record.get("target_coc")
        recirculation_rate = record.get("recirculation_rate")
        temperature = record.get("temperature")
        operating_hours = record.get("operating_hours") or 24.0
        if not target_coc or target_coc <= 1 or not recirculation_rate or temperature is None:
            continue
        decrease_pct = (target_coc - current_coc) / target_coc * 100
        if decrease_pct <= WATER_LOSS_THRESHOLD_PCT:
            continue
        evaporation_rate = 0.85 * recirculation_rate / 1000 * temperature
        current_makeup = evaporation_rate * current_coc / (current_coc - 1)
        potential_makeup = evaporation_rate * target_coc / (target_coc - 1)
        current_blowdown = evaporation_rate / (current_coc - 1)
        potential_blowdown = evaporation_rate / (target_coc - 1)
        current_makeup_per_day = current_makeup * 60 * operating_hours
        potential_makeup_per_day = potential_makeup * 60 * operating_hours
        water_savings_per_day = current_makeup_per_day - potential_makeup_per_day
        water_savings_per_annum = water_savings_per_day * 365
        rows.append({
            **record,
            "decrease_pct": decrease_pct,
            "evaporation_rate": evaporation_rate,
            "current_makeup": current_makeup,
            "potential_makeup": potential_makeup,
            "current_blowdown": current_blowdown,
            "potential_blowdown": potential_blowdown,
            "current_makeup_per_day": current_makeup_per_day,
            "potential_makeup_per_day": potential_makeup_per_day,
            "water_savings_per_day": water_savings_per_day,
            "water_savings_per_annum": water_savings_per_annum,
            "water_savings_cost": water_savings_per_annum / 100 * 5,
        })

    if not water_efficiency_inputs:
        return {"available": False, "triggered": False, "reason": "Value creation water-efficiency data is not available."}
    if not rows:
        return {"available": True, "triggered": False, "reason": f"Current COC is not more than {WATER_LOSS_THRESHOLD_PCT:g}% below the value-creation Target COC."}

    return {
        "available": True,
        "triggered": True,
        "current_coc": current_coc,
        "rows": rows,
        "water_savings_per_annum": sum(row["water_savings_per_annum"] for row in rows),
        "water_savings_cost": sum(row["water_savings_cost"] for row in rows),
    }


def load_all(site, month, controller_ids=None):
    controller_ids = normalize_controller_ids(controller_ids)
    if controller_ids:
        try:
            cache, manifest = find_cache_by_controller_ids(DATA_STORE, month, controller_ids)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            print(f"[ERROR] {exc}")
            controller_args = " ".join(f'\"{controller_id}\"' for controller_id in controller_ids)
            print(f"  Run: python prefetch_site.py --controller-ids {controller_args} --month \"{month}\"")
            sys.exit(1)
        site = manifest.get("site_name", site)
        slug = cache.name
    else:
        slug  = build_cache_slug(site, month)
        cache = DATA_STORE / slug

    def jload(f, d):
        p = cache / f
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else d

    # Narrative cache — must exist
    narr_path = cache / "narrative_cache.json"
    if not narr_path.exists():
        print(f"[ERROR] narrative_cache.json not found.")
        print(f"  Run: python prepare_copilot_task.py --site \"{site}\" --month \"{month}\"")
        print(f"  Then paste the COPILOT TASK into Copilot Chat.")
        sys.exit(1)
    narr = json.loads(narr_path.read_text(encoding="utf-8"))
    if narr.get("_status","") == "EMPTY — Copilot must fill this in":
        print("[ERROR] narrative_cache.json is still empty — Copilot has not written it yet.")
        sys.exit(1)

    controllers = jload("controllers.json", [])
    scc         = jload("scc.json", [])
    ade         = jload("ade_data.json", [])
    service_notes = jload("service_notes.json", [])

    # Load parquet — filter to reporting month only
    tel_dir = cache / "telemetry"
    parquet_files = list(tel_dir.glob("*.parquet"))
    if not parquet_files:
        print(f"[ERROR] No parquet file found in {tel_dir}")
        print(f"  The parquet is saved by prefetch_site.py on your machine.")
        print(f"  Make sure you ran prefetch_site.py before this script.")
        sys.exit(1)

    frames = []
    for pf in parquet_files:
        df = pd.read_parquet(pf)
        frames.append(df)
    raw = pd.concat(frames, ignore_index=True)

    # Find the timestamp column
    ts_col = next((c for c in raw.columns if any(k in c.lower()
                   for k in ("time","date","timestamp"))), None)
    if ts_col is None:
        print("[ERROR] No timestamp column found in parquet.")
        sys.exit(1)

    raw[ts_col] = pd.to_datetime(raw[ts_col], errors="coerce")
    raw = raw.dropna(subset=[ts_col]).sort_values(ts_col)

    # Filter to reporting month
    dt = datetime.strptime(month, "%B %Y")
    start = pd.Timestamp(dt.year, dt.month, 1)
    import calendar
    end = pd.Timestamp(dt.year, dt.month, calendar.monthrange(dt.year, dt.month)[1], 23, 59, 59)
    month_df = raw[(raw[ts_col] >= start) & (raw[ts_col] <= end)].copy()

    if month_df.empty:
        print(f"[WARNING] No data found for {month} in parquet — using full dataset.")
        month_df = raw.copy()

    print(f"  Parquet: {len(raw):,} total rows → {len(month_df):,} rows for {month}")

    return site, narr, controllers, scc, ade, service_notes, month_df, ts_col, slug


def _parse_number(text):
    if text is None:
        return None
    raw = str(text).strip().replace(",", "")
    multiplier = 1.0
    if "million" in raw.lower():
        multiplier = 1_000_000.0
    elif "thousand" in raw.lower():
        multiplier = 1_000.0
    sci = re.search(r"(\d+(?:\.\d+)?)\s*(?:x|×|\*)\s*10\s*(?:\^|\*\*)?\s*(\d+)", raw, re.I)
    if sci:
        return float(sci.group(1)) * (10 ** int(sci.group(2)))
    match = re.search(r"\d+(?:\.\d+)?", raw)
    return float(match.group(0)) * multiplier if match else None


def _find_dipslide_cfu(ade, service_notes):
    records = []
    for row in ade:
        text = " ".join(str(row.get(key, "")) for key in row)
        if re.search(r"dip\s*slide|dipslide|cfu|colony", text, re.I):
            value = _parse_number(row.get("Value")) or _parse_number(text)
            if value is not None:
                records.append(value)
    for note in service_notes:
        text = " ".join(str(note.get(key, "")) for key in note)
        if re.search(r"dip\s*slide|dipslide|cfu|colony", text, re.I):
            scoped = re.search(
                r"(?:dip\s*slide|dipslide|cfu|colony)[^\n\r.;:]{0,80}",
                text,
                re.I,
            )
            value = _parse_number(scoped.group(0) if scoped else text)
            if value is not None:
                records.append(value)
    return max(records) if records else None


def _format_cfu(value):
    if value is None:
        return "N/A"
    if value >= 10_000:
        return f"{value:.1e} CFU/mL"
    return f"{int(value):,} CFU/mL"


def dipslide_comment(cfu):
    if cfu is None:
        return "Dip-slide will be analysed in the upcoming visit to ensure good microbial control."
    cfu_text = _format_cfu(cfu)
    if cfu < 100:
        return f"Dip-slide analysis reported {cfu_text}, indicating excellent microbial control."
    if cfu < 10_000:
        return f"Dip-slide analysis reported {cfu_text}, indicating good microbial control."
    if cfu <= 1_000_000:
        return f"Dip-slide analysis reported {cfu_text}, indicating microbial control needs attention."
    return f"Dip-slide analysis reported {cfu_text}, indicating critical microbial control; slug dosage duration needs to be increased."


def frc_comment(frc):
    if frc is None:
        return "FRC will be analysed in the upcoming visit to ensure good microbial control."
    interpretation = "adequate oxidizing biocide residual" if frc >= 0.2 else "residual below the recommended level"
    return f"FRC from the field test data was {frc:.2f} ppm, indicating {interpretation}."


def _orp_spike_summary(month_df, ts_col, orp_col, threshold_mv=50.0):
    if not orp_col or orp_col not in month_df.columns or ts_col not in month_df.columns:
        return {"count": 0, "weeks": 0, "per_week": 0.0, "good_dosage": False}

    frame = month_df[[ts_col, orp_col]].copy()
    frame[ts_col] = pd.to_datetime(frame[ts_col], errors="coerce")
    frame[orp_col] = pd.to_numeric(frame[orp_col], errors="coerce")
    frame = frame.dropna(subset=[ts_col, orp_col]).sort_values(ts_col)
    if frame.empty:
        return {"count": 0, "weeks": 0, "per_week": 0.0, "good_dosage": False}

    hourly = frame.set_index(ts_col)[orp_col].resample("1h").mean().dropna()
    if hourly.empty:
        return {"count": 0, "weeks": 0, "per_week": 0.0, "good_dosage": False}

    spike_count = int((hourly.diff() >= threshold_mv).sum())
    days_covered = max((hourly.index.max() - hourly.index.min()).total_seconds() / 86400.0, 1.0)
    weeks_covered = max(days_covered / 7.0, 1.0)
    spikes_per_week = spike_count / weeks_covered
    return {
        "count": spike_count,
        "weeks": round(weeks_covered, 2),
        "per_week": round(spikes_per_week, 2),
        "good_dosage": spikes_per_week >= 2.0,
    }


def microbial_control_comment(k):
    if k.get("frc") is None and k.get("dipslide_cfu") is None:
        final_comments = ["FRC and dip-slide will be analysed in the upcoming visit to ensure good microbial control."]
    else:
        final_comments = [
            frc_comment(k.get("frc")),
            k.get("dipslide_comment", dipslide_comment(None)),
        ]
    orp_sentence = (
        "ORP spike response of at least 50 mV was observed at least two times per week during oxidizing biocide application, indicating good microbial dosage."
        if k.get("good_microbial_dosage")
        else "Insufficient ORP spike was observed during oxidizing biocide application, so oxidizing biocide feed response should be reviewed during the upcoming service visit."
    )
    return " ".join([
        orp_sentence,
        *final_comments,
    ])


def _fmt_pct(value):
    return f"{value:.1f}%" if value is not None else "N/A"


def _polymer_consumption_display_rates(polymer_rate):
    return polymer_rate.clip(lower=0)


def _fmt_value(value, unit="", decimals=1):
    if value is None:
        return "N/A"
    return f"{value:.{decimals}f}{unit}"


def _fmt_number(value, decimals=0):
    if value is None:
        return "N/A"
    return f"{value:,.{decimals}f}"


def _trend_split(values, threshold=0.01):
    if values is None or len(values) < 4:
        return None, None, "unknown"
    midpoint = len(values) // 2
    early = float(values.iloc[:midpoint].mean())
    late = float(values.iloc[midpoint:].mean())
    if early == 0:
        trend = "increased" if late > 0 else "stable"
    elif late > early * (1 + threshold):
        trend = "increased"
    elif late < early * (1 - threshold):
        trend = "decreased"
    else:
        trend = "stable"
    return early, late, trend


def _pattern_word(trend):
    if trend == "increased":
        return "increased across the month"
    if trend == "decreased":
        return "decreased across the month"
    if trend == "stable":
        return "remained broadly stable across the month"
    return "did not show a clear month-long direction"


def _pattern_line(label, trend, good=None):
    if trend == "increased":
        direction = "increasing"
    elif trend == "decreased":
        direction = "decreasing"
    elif trend == "stable":
        direction = "stable"
    else:
        direction = "not clearly increasing or decreasing"

    if good is True and trend == "stable":
        return f"Pattern: {label} remains good and stable across the month."
    if good is True:
        return f"Pattern: {label} is {direction}, but remains good against the target."
    if good is False:
        return f"Pattern: {label} is {direction} and needs attention against the target."
    return f"Pattern: {label} is {direction} across the month."


def _series_for_comment(month_df, col):
    if col is None or col not in month_df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(month_df[col], errors="coerce").dropna()


def _cell_fouling_above_threshold(k, month_df, threshold=CELL_FOULING_THRESHOLD_PCT):
    values = _series_for_comment(month_df, k.get("cf_col"))
    return not values.empty and float(values.max()) > threshold


def _pct_in_range_from_series(values, lower, upper):
    if values.empty or lower is None or upper is None:
        return None
    return round(float(((values >= lower) & (values <= upper)).mean() * 100), 1)


def _timestamp_col(month_df):
    return next((c for c in month_df.columns if any(k in c.lower() for k in ("time", "date", "timestamp"))), None)


def _recent_series_for_comment(month_df, col, days=7):
    if col is None or col not in month_df.columns:
        return pd.Series(dtype=float)
    ts_col = _timestamp_col(month_df)
    frame = month_df[[ts_col, col]].copy() if ts_col else month_df[[col]].copy()
    frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=[col])
    if frame.empty:
        return pd.Series(dtype=float)
    if ts_col:
        frame[ts_col] = pd.to_datetime(frame[ts_col], errors="coerce")
        frame = frame.dropna(subset=[ts_col]).sort_values(ts_col)
        if not frame.empty:
            cutoff = frame[ts_col].max() - pd.Timedelta(days=days)
            recent = frame.loc[frame[ts_col] >= cutoff, col].dropna()
            if not recent.empty:
                return recent
    count = min(len(frame), max(len(frame) // 4, 1))
    return frame[col].tail(count).dropna()


def _deviation_from_setpoint(values, setpoint):
    if values.empty or setpoint in (None, 0, "", "NULL"):
        return None
    return round(float((values - float(setpoint)).abs().mean() / float(setpoint) * 100), 1)


def _position_text(mean, lower, upper, label="average"):
    if mean is None or lower is None or upper is None:
        return f"The {label} could not be compared with a configured range."
    if mean < lower:
        return f"The {label} was below the configured range."
    if mean > upper:
        return f"The {label} was above the configured range."
    return f"The {label} was within the configured range."


def _mean_within_range(mean, lower, upper):
    return mean is not None and lower is not None and upper is not None and lower <= mean <= upper


def _control_not_maintained(mean, lower, upper, in_range_pct):
    if mean is not None and lower is not None and upper is not None and not lower <= mean <= upper:
        return True
    return in_range_pct is not None and in_range_pct < 75


def _conductivity_link_reason(k, trace_trend, cond_trend):
    tp_mean = k.get("tp_mean")
    tp_ll = k.get("tp_ll")
    tp_ul = k.get("tp_ul")
    ec_mean = k.get("ec_mean")
    ec_ll = k.get("ec_ll")
    ec_ul = k.get("ec_ul")

    both_low = tp_mean is not None and tp_ll is not None and tp_mean < tp_ll and ec_mean is not None and ec_ll is not None and ec_mean < ec_ll
    both_high = tp_mean is not None and tp_ul is not None and tp_mean > tp_ul and ec_mean is not None and ec_ul is not None and ec_mean > ec_ul
    same_direction = trace_trend == cond_trend and trace_trend in ("increased", "decreased")

    if both_low:
        return "Likely reason: the Traced Product trend is related to the low conductivity trend; dilution, water loss, excess blowdown, or makeup changes are pulling both down."
    if both_high:
        return "Likely reason: the Traced Product trend is related to the high conductivity trend; reduced blowdown, higher cycles, or concentration effects are pushing both up."
    if same_direction:
        return f"Likely reason: Traced Product is following the {cond_trend} conductivity trend, so cycles, blowdown, makeup, or dilution changes should be corrected first."
    return "Likely reason: conductivity was not maintained, so the Traced Product variation should be tied to conductivity control before assigning another cause."


def _scale_pattern_summary(k, trace_trend, recent_deviation_pct, recent_in_range_pct):
    trace_good = _mean_within_range(k.get("tp_mean"), k.get("tp_ll"), k.get("tp_ul"))
    ongoing_late_issue = (
        recent_deviation_pct is not None and recent_deviation_pct >= 20
    ) or (
        recent_in_range_pct is not None and recent_in_range_pct < 75
    )
    if ongoing_late_issue:
        return "Pattern: Traced Product is still not maintained at the end of the month."
    return _pattern_line("Traced Product", trace_trend, trace_good)


def _scale_recent_detail(recent_deviation_pct, trace_start, trace_end):
    if recent_deviation_pct is not None and recent_deviation_pct >= 20:
        return f"The last 7 days still show about {_fmt_pct(recent_deviation_pct)} deviation from setpoint, indicating the issue is still present."
    return f"The trend moved from about {_fmt_value(trace_start, ' ppm')} at the start to {_fmt_value(trace_end, ' ppm')} at the end."


def _scale_reason(k, trace_trend, cond_trend):
    tp_mean = k.get("tp_mean")
    tp_ll = k.get("tp_ll")
    tp_ul = k.get("tp_ul")
    ec_mean = k.get("ec_mean")
    ec_ll = k.get("ec_ll")
    ec_ul = k.get("ec_ul")

    tp_not_maintained = _control_not_maintained(tp_mean, tp_ll, tp_ul, k.get("tp_pct"))
    ec_not_maintained = _control_not_maintained(ec_mean, ec_ll, ec_ul, k.get("ec_pct"))

    if tp_not_maintained and ec_not_maintained:
        return _conductivity_link_reason(k, trace_trend, cond_trend)

    if tp_mean is not None and tp_ul is not None and tp_mean > tp_ul:
        if trace_trend == "decreased":
            return "Likely reason: feed is recovering from overfeed; review pump stroke or calibration if it does not return to range."
        return "Likely reason: overfeed, high pump output, or fluorometer calibration should be checked."
    if tp_mean is not None and tp_ll is not None and tp_mean < tp_ll:
        if cond_trend == "decreased" or (ec_mean is not None and ec_ll is not None and ec_mean < ec_ll):
            return "Likely reason: water loss, dilution, excess blowdown, or makeup changes may be pulling product down."
        return "Likely reason: low inventory, pump prime, or feed delivery should be checked."
    if trace_trend == "decreased" and cond_trend == "decreased":
        return "Likely reason: water loss, dilution, or blowdown/makeup changes may be reducing both product and conductivity."
    if _mean_within_range(tp_mean, tp_ll, tp_ul) and _mean_within_range(ec_mean, ec_ll, ec_ul):
        return "Likely reason: chemical feed and tower cycles are balanced, so scale control remains steady."
    return "Likely reason: feed control, conductivity control, and field residuals should be reviewed together."


def _corrosion_reason(k, ms_trend, cu_trend, corrosion_good):
    if corrosion_good and "increased" not in (ms_trend, cu_trend):
        return "Likely reason: inhibitor residual and operating chemistry are keeping corrosion protected."
    if corrosion_good:
        return "Likely reason: corrosion is still protected, but increasing movement should be checked against product and ORP trends."
    return "Likely reason: low inhibitor residual, deposit activity, high oxidizer exposure, or control drift should be investigated."


def _orp_reason(spike_visible, cu_good):
    if spike_visible and cu_good:
        return "Likely reason: biocide response is present and corrosion inhibitor is preventing a copper upset."
    if spike_visible:
        return "Likely reason: oxidizer response is present, but copper protection should be checked with corrosion and product residuals."
    return "Likely reason: biocide feed timing, relay operation, oxidizer inventory, or field FRC residual should be checked."


def _biocide_reason(relay_visible, cu_good):
    if relay_visible and cu_good:
        return "Likely reason: relay feed timing is adequate and copper corrosion remains protected."
    if relay_visible:
        return "Likely reason: biocide feed is occurring, but corrosion protection or oxidizer exposure needs review."
    return "Likely reason: relay signal, pump operation, oxidizer inventory, or feed schedule should be checked."


def _conductivity_reason(k, cond_trend, trace_trend):
    ec_mean = k.get("ec_mean")
    ec_ll = k.get("ec_ll")
    ec_ul = k.get("ec_ul")

    if ec_mean is not None and ec_ll is not None and ec_mean < ec_ll:
        if trace_trend == "decreased":
            return "Likely reason: dilution, water loss, excess blowdown, or makeup changes are pulling both conductivity and product down."
        return "Likely reason: dilution, water loss, excess blowdown, or makeup changes are keeping conductivity low."
    if ec_mean is not None and ec_ul is not None and ec_mean > ec_ul:
        return "Likely reason: reduced blowdown, higher cycles, evaporation concentration, or concentrated makeup is raising conductivity."
    if cond_trend == "decreased":
        return "Likely reason: increased makeup, dilution, water loss, or blowdown activity caused the downward movement."
    if cond_trend == "increased":
        return "Likely reason: reduced blowdown, higher cycles, or concentration of dissolved solids caused the upward movement."
    return "Likely reason: makeup and blowdown control are balanced, so tower cycles remained steady."


def _last_day_conductivity_status(k, month_df):
    cond_col = k.get("ec_col")
    ts_col = _timestamp_col(month_df)
    result = {
        "available": False,
        "maintained": False,
        "mean": None,
        "date": None,
        "criterion": "configured conductivity setpoint",
    }
    if not cond_col or cond_col not in month_df.columns:
        return result

    frame = month_df[[cond_col] + ([ts_col] if ts_col else [])].copy()
    frame[cond_col] = pd.to_numeric(frame[cond_col], errors="coerce")
    frame = frame.dropna(subset=[cond_col])
    if frame.empty:
        return result
    if ts_col:
        frame[ts_col] = pd.to_datetime(frame[ts_col], errors="coerce")
        frame = frame.dropna(subset=[ts_col]).sort_values(ts_col)
        if frame.empty:
            return result
        last_date = frame[ts_col].max().date()
        last_day = frame.loc[frame[ts_col].dt.date == last_date, cond_col].dropna()
        result["date"] = last_date.isoformat()
    else:
        last_day = frame[cond_col].tail(max(len(frame) // 30, 1)).dropna()
    if last_day.empty:
        return result

    last_mean = float(last_day.mean())
    result["available"] = True
    result["mean"] = last_mean
    if k.get("ec_ll") is not None and k.get("ec_ul") is not None:
        result["maintained"] = k["ec_ll"] <= last_mean <= k["ec_ul"]
        result["criterion"] = f"{k['ec_ll']:.0f}-{k['ec_ul']:.0f} µS/cm"
    elif k.get("ec_sp"):
        deviation_pct = abs(last_mean - k["ec_sp"]) / k["ec_sp"] * 100
        result["maintained"] = deviation_pct <= SETPOINT_MAINTAINED_TOLERANCE_PCT
        result["criterion"] = f"{k['ec_sp']:.0f} µS/cm setpoint (+/-{SETPOINT_MAINTAINED_TOLERANCE_PCT:g}%)"
    return result


def _water_efficiency_status(k, coc, water_loss, month_df):
    if water_loss.get("triggered"):
        last_day = _last_day_conductivity_status(k, month_df)
        return STATUS_ACCEPTABLE if last_day.get("maintained") else STATUS_CRITICAL
    return coc.get("coc_status") or k.get("ec_status") or STATUS_ACCEPTABLE


def _conductivity_setpoint_text(k):
    if k.get("ec_ll") is not None and k.get("ec_ul") is not None:
        return f"the recommended setpoint range of {k['ec_ll']:.0f}-{k['ec_ul']:.0f} µS/cm"
    if k.get("ec_sp"):
        return f"the recommended setpoint of {k['ec_sp']:.0f} µS/cm"
    return "the recommended conductivity setpoint"


def _conductivity_position_text(k):
    mean = k.get("ec_mean")
    if mean is None:
        return "could not be compared because conductivity data was not available"
    if k.get("ec_ll") is not None and k.get("ec_ul") is not None:
        if mean < k["ec_ll"]:
            return "below"
        if mean > k["ec_ul"]:
            return "above"
        return "within"
    if k.get("ec_sp"):
        deviation_pct = abs(mean - k["ec_sp"]) / k["ec_sp"] * 100
        if deviation_pct <= SETPOINT_MAINTAINED_TOLERANCE_PCT:
            return "within"
        return "below" if mean < k["ec_sp"] else "above"
    return "compared against"


def _water_efficiency_comment(k, month_df, water_loss):
    cond = _series_for_comment(month_df, k.get("ec_col"))
    cond_start, cond_end, cond_trend = _trend_split(cond)
    trace_trend = _trend_split(_series_for_comment(month_df, k.get("tp_col")))[2]
    avg_text = _fmt_value(k.get("ec_mean"), " µS/cm", 1)
    position = _conductivity_position_text(k)
    setpoint_text = _conductivity_setpoint_text(k)

    if cond_trend == "decreased":
        pattern = f"Conductivity decreased from about {_fmt_value(cond_start, ' µS/cm', 1)} at the start of the month to {_fmt_value(cond_end, ' µS/cm', 1)} at the end."
    elif cond_trend == "increased":
        pattern = f"Conductivity increased from about {_fmt_value(cond_start, ' µS/cm', 1)} at the start of the month to {_fmt_value(cond_end, ' µS/cm', 1)} at the end."
    elif cond_trend == "stable":
        pattern = f"Conductivity remained broadly stable from about {_fmt_value(cond_start, ' µS/cm', 1)} at the start of the month to {_fmt_value(cond_end, ' µS/cm', 1)} at the end."
    else:
        pattern = "Conductivity did not show a clear month-long increase or decrease pattern."

    recommendations = []
    if water_loss.get("triggered"):
        last_day = _last_day_conductivity_status(k, month_df)
        if last_day.get("maintained"):
            recommendations.append(
                f"Water loss was observed from the COC gap, but last-day conductivity averaged {_fmt_value(last_day.get('mean'), ' µS/cm', 1)} and was maintained at {last_day.get('criterion')}; continue monitoring blowdown and makeup stability."
            )
        else:
            last_day_text = _fmt_value(last_day.get("mean"), " µS/cm", 1) if last_day.get("available") else "not available"
            recommendations.append(
                f"Water loss was observed from the COC gap and last-day conductivity was {last_day_text}, so inspect blowdown valve operation, makeup changes, dilution sources, and possible water loss."
            )
    else:
        recommendations.append(_conductivity_reason(k, cond_trend, trace_trend).replace("Likely reason: ", "Recommendation: "))

    return " ".join([
        f"The average conductivity is {avg_text}, which is {position} {setpoint_text}.",
        pattern,
        *recommendations,
    ])


def _add_unique_recommendation(recommendations, text, key):
    if not text or key in {item[0] for item in recommendations}:
        return
    recommendations.append((key, text))


def _is_empty_service_note_sentence(sentence):
    return bool(re.search(r"\bno\s+service\s+notes?\s+(?:were\s+)?(?:recorded|found)\b", sentence, re.I))


def _proactive_support_summary(k, narr, coc, month_df):
    recommendations = []

    base = _strip_status(narr.get("proactive_support_narrative", ""))
    alarm_sentence = ""
    for sentence in re.split(r"(?<=[.!?])\s+", base):
        if _is_empty_service_note_sentence(sentence):
            continue
        if re.search(r"\balarm\b|service note", sentence, re.I):
            alarm_sentence = sentence.strip()
            break

    ms = _series_for_comment(month_df, k.get("ms_col"))
    cu = _series_for_comment(month_df, k.get("cu_col"))
    _, _, ms_trend = _trend_split(ms)
    _, _, cu_trend = _trend_split(cu)
    corrosion_good = k.get("ms_mean") is not None and k.get("ms_mean") < 3.0 and k.get("cu_mean") is not None and k.get("cu_mean") < 0.5
    if not corrosion_good or "increased" in (ms_trend, cu_trend):
        _add_unique_recommendation(
            recommendations,
            "Confirm inhibitor residual, inspect for deposit activity, and compare corrosion movement with ORP and product trends.",
            "corrosion",
        )

    trace = _series_for_comment(month_df, k.get("tp_col"))
    cond = _series_for_comment(month_df, k.get("ec_col"))
    _, _, trace_trend = _trend_split(trace)
    _, _, cond_trend = _trend_split(cond)
    recent_trace = _recent_series_for_comment(month_df, k.get("tp_col"))
    recent_trace_deviation = _deviation_from_setpoint(recent_trace, k.get("tp_sp"))
    trace_not_maintained = _control_not_maintained(k.get("tp_mean"), k.get("tp_ll"), k.get("tp_ul"), k.get("tp_pct"))
    cond_not_maintained = _control_not_maintained(k.get("ec_mean"), k.get("ec_ll"), k.get("ec_ul"), k.get("ec_pct"))

    if trace_not_maintained:
        if cond_not_maintained:
            if recent_trace_deviation is not None and recent_trace_deviation >= 20:
                text = f"Traced Product deviation remained at about {_fmt_pct(recent_trace_deviation)} in the last 7 days, so correct the conductivity trend by checking cycles, blowdown, makeup, and dilution behavior before changing feed settings."
            else:
                text = "Traced Product was not maintained while conductivity was also not maintained, so treat the product issue as conductivity-related and check cycles, blowdown, makeup, and dilution behavior first."
        elif trace_trend == "decreased":
            text = "Traced Product was not maintained while conductivity was maintained, so verify product inventory, pump prime, feed delivery, and fluorometer calibration."
        else:
            text = "Traced Product was not maintained, so review product feed delivery, pump stroke, inventory, and fluorometer calibration."
        _add_unique_recommendation(recommendations, text, "scale-product")

    if cond_not_maintained:
        if trace_not_maintained:
            text = ""
        elif cond_trend == "decreased":
            text = "Conductivity decreased or stayed below range, so inspect excess blowdown, dilution, makeup changes, or water loss."
        elif cond_trend == "increased":
            text = "Conductivity increased or stayed above range, so inspect blowdown settings, higher cycles, evaporation concentration, or concentrated makeup."
        else:
            text = "Conductivity was not maintained, so inspect blowdown control, makeup conditions, and tower cycle stability."
        _add_unique_recommendation(recommendations, text, "water-efficiency")

    if coc and coc.get("mu_available") is False:
        _add_unique_recommendation(
            recommendations,
            "Capture makeup water conductivity during the next service visit so actual cycles of concentration can be verified.",
            "coc-makeup",
        )
    elif coc and coc.get("deviation_pct") is not None and coc.get("deviation_pct") > 20:
        _add_unique_recommendation(
            recommendations,
            "Review makeup conductivity and blowdown control because cycles of concentration are still deviating from target.",
            "coc-deviation",
        )
    if coc and coc.get("coc_gap") is not None and coc.get("coc_gap") >= 1.0:
        _add_unique_recommendation(
            recommendations,
            "Actual cycles of concentration are more than 1.0 below target, so treat water efficiency as Critical and inspect for water loss, excess blowdown, or dilution.",
            "coc-low-gap",
        )

    if k.get("frc") is None:
        _add_unique_recommendation(
            recommendations,
            "Check FRC during the upcoming service visit to confirm oxidizing biocide residual.",
            "frc",
        )
    if k.get("dipslide_cfu") is None:
        _add_unique_recommendation(
            recommendations,
            "Measure dip-slide CFU during the upcoming service visit to confirm microbial control.",
            "dipslide",
        )
    elif k.get("dipslide_cfu") >= 10_000:
        _add_unique_recommendation(
            recommendations,
            "Review microbial control and adjust slug dosage duration if CFU remains elevated.",
            "microbial-cfu",
        )
    if not k.get("relay_firing"):
        _add_unique_recommendation(
            recommendations,
            "Verify biocide relay signal, pump operation, oxidizer inventory, and feed schedule.",
            "biocide-relay",
        )

    if k.get("polymer_consumption_rate_pct") is not None:
        _add_unique_recommendation(
            recommendations,
            "Verify phosphate and silica residuals during the next service visit.",
            "polymer-residuals",
        )

    if not recommendations:
        return alarm_sentence or "No unresolved performance recommendations were identified from the system health check, water efficiency, or product efficiency review. Continue routine monitoring."

    rec_text = " ".join(text for _, text in recommendations)
    if alarm_sentence:
        return f"{alarm_sentence} Recommended follow-up: {rec_text}"
    return f"Recommended follow-up: {rec_text}"


def _trace_product_low_then_maintained_comment(k, month_df):
    trace_col = k.get("tp_col")
    setpoint = k.get("tp_sp")
    ts_col = _timestamp_col(month_df)
    if not trace_col or trace_col not in month_df.columns or not setpoint or not ts_col:
        return None

    frame = month_df[[ts_col, trace_col]].copy()
    frame[ts_col] = pd.to_datetime(frame[ts_col], errors="coerce")
    frame[trace_col] = pd.to_numeric(frame[trace_col], errors="coerce")
    frame = frame.dropna(subset=[ts_col, trace_col]).sort_values(ts_col)
    if frame.empty:
        return None

    daily = frame.set_index(ts_col)[trace_col].resample("1D").mean().dropna()
    if len(daily) < 4:
        return None

    if k.get("tp_ll") is not None and k.get("tp_ul") is not None:
        maintained = (daily >= k["tp_ll"]) & (daily <= k["tp_ul"])
        low = daily < k["tp_ll"]
    else:
        maintained = daily >= float(setpoint) * 0.90
        low = daily < float(setpoint) * 0.90

    if not bool(low.iloc[0]) or not bool(maintained.tail(max(3, len(maintained) // 4)).all()):
        return None

    maintained_positions = [idx for idx, ok in enumerate(maintained) if ok]
    if not maintained_positions:
        return None
    first_maintained_index = maintained_positions[0]
    if first_maintained_index == 0:
        return None
    low_period = daily.iloc[:first_maintained_index]
    if low_period.empty or not bool((low_period < float(setpoint) * 0.90).any()):
        return None

    low_until = low_period.index[-1]
    low_days = len(low_period)
    return (
        f"The Traced Product level was maintained below the setpoint until {low_until.strftime('%d %B %Y')}. "
        f"Later, the Traced Product level was well maintained at the setpoint of {setpoint:.1f} ppm. "
        f"The low Traced Product during the first {low_days} days can be due to lack of inventory, dosing pump lost prime, or a leak in the pump discharge line."
    )


def _format_date_range(start, end):
    start_text = pd.Timestamp(start).strftime("%d %B %Y")
    end_text = pd.Timestamp(end).strftime("%d %B %Y")
    return start_text if start_text == end_text else f"{start_text} to {end_text}"


def _true_date_ranges(mask):
    ranges = []
    active_start = None
    previous_date = None
    for date, is_active in mask.items():
        if bool(is_active) and active_start is None:
            active_start = date
        elif not bool(is_active) and active_start is not None:
            ranges.append((active_start, previous_date))
            active_start = None
        previous_date = date
    if active_start is not None and previous_date is not None:
        ranges.append((active_start, previous_date))
    return ranges


def _trace_low_mask(k, daily_trace):
    if daily_trace.empty:
        return daily_trace.astype(bool)
    if k.get("tp_ll") is not None:
        return daily_trace < k["tp_ll"]
    if k.get("tp_sp"):
        return daily_trace < float(k["tp_sp"]) * 0.90
    return daily_trace < daily_trace.mean()


def _orp_copper_corrosion_comment(k, month_df):
    ts_col = _timestamp_col(month_df)
    orp_col = k.get("orp_col")
    cu_col = k.get("cu_col")
    trace_col = k.get("tp_col")
    comments = []

    if ts_col and orp_col and orp_col in month_df.columns:
        orp_frame = month_df[[ts_col, orp_col]].copy()
        orp_frame[ts_col] = pd.to_datetime(orp_frame[ts_col], errors="coerce")
        orp_frame[orp_col] = pd.to_numeric(orp_frame[orp_col], errors="coerce")
        orp_frame = orp_frame.dropna(subset=[ts_col, orp_col]).sort_values(ts_col)
        if not orp_frame.empty:
            hourly_orp = orp_frame.set_index(ts_col)[orp_col].resample("1h").mean().dropna()
            weekly_spikes = (hourly_orp.diff() >= 50).resample("7D", origin="start_day").sum()
            if not weekly_spikes.empty and bool((weekly_spikes >= 3).all()):
                comments.append("The ORP spikes more than 50 mV at least three times weekly, indicating sufficient slug dosage of biocide.")
            elif not weekly_spikes.empty:
                deficient = weekly_spikes[weekly_spikes < 3]
                middle = deficient
                if len(weekly_spikes) > 2:
                    middle = deficient[(deficient.index > weekly_spikes.index.min()) & (deficient.index < weekly_spikes.index.max())]
                selected_start = (middle if not middle.empty else deficient).index[0]
                selected_end = min(selected_start + pd.Timedelta(days=6), hourly_orp.index.max())
                comments.append(
                    f"ORP did not show more than 50 mV spikes at least three times during the week from {_format_date_range(selected_start, selected_end)}; no slug dosage of biocide is observed during this period. This could be due to lack of inventory, dosing pump lost prime, or a leak in the pump discharge line."
                )
    if not comments:
        comments.append("ORP spike response could not be fully verified from the available trend data, so slug dosage response should be checked during the next service visit.")

    if ts_col and cu_col and cu_col in month_df.columns:
        cu_frame = month_df[[ts_col, cu_col]].copy()
        cu_frame[ts_col] = pd.to_datetime(cu_frame[ts_col], errors="coerce")
        cu_frame[cu_col] = pd.to_numeric(cu_frame[cu_col], errors="coerce")
        cu_frame = cu_frame.dropna(subset=[ts_col, cu_col]).sort_values(ts_col)
        if not cu_frame.empty:
            daily_cu = cu_frame.set_index(ts_col)[cu_col].resample("1D").mean().dropna()
            high_cu = daily_cu > 0.5
            if not bool(high_cu.any()):
                comments.append("Copper corrosion remained within the recommended limit of 0.5 mpy.")
            else:
                ranges = _true_date_ranges(high_cu)
                range_text = "; ".join(_format_date_range(start, end) for start, end in ranges[:3])
                comments.append(f"Copper corrosion was above the recommended limit of 0.5 mpy from {range_text}.")
                if trace_col and trace_col in month_df.columns:
                    trace_frame = month_df[[ts_col, trace_col]].copy()
                    trace_frame[ts_col] = pd.to_datetime(trace_frame[ts_col], errors="coerce")
                    trace_frame[trace_col] = pd.to_numeric(trace_frame[trace_col], errors="coerce")
                    trace_frame = trace_frame.dropna(subset=[ts_col, trace_col]).sort_values(ts_col)
                    if not trace_frame.empty:
                        daily_trace = trace_frame.set_index(ts_col)[trace_col].resample("1D").mean().dropna()
                        low_trace = _trace_low_mask(k, daily_trace)
                        overlap_found = False
                        for start, end in ranges:
                            overlap = low_trace[(low_trace.index >= start) & (low_trace.index <= end)]
                            if not overlap.empty and bool(overlap.any()):
                                overlap_found = True
                                break
                        if overlap_found:
                            comments.append("Traced Product was low during the high copper corrosion period, indicating possible lack of inventory.")
    return comments


def _chart_pattern_comment(kind, k, month_df):
    if kind == "corrosion":
        return [_corrosion_narrative(k)]

    if kind == "scale":
        recovery_comment = _trace_product_low_then_maintained_comment(k, month_df)
        if recovery_comment:
            return [recovery_comment]
        trace = _series_for_comment(month_df, k.get("tp_col"))
        trace_start, trace_end, trace_trend = _trend_split(trace)
        recent_trace = _recent_series_for_comment(month_df, k.get("tp_col"))
        recent_deviation_pct = _deviation_from_setpoint(recent_trace, k.get("tp_sp"))
        recent_in_range_pct = _pct_in_range_from_series(recent_trace, k.get("tp_ll"), k.get("tp_ul"))
        pct_range = _pct_in_range_from_series(trace, k.get("tp_ll"), k.get("tp_ul"))
        position = _position_text(k.get("tp_mean"), k.get("tp_ll"), k.get("tp_ul"), "Traced Product average")
        return [
            _scale_pattern_summary(k, trace_trend, recent_deviation_pct, recent_in_range_pct),
            _scale_recent_detail(recent_deviation_pct, trace_start, trace_end),
            f"{position} The monthly in-range performance was {_fmt_pct(pct_range)}.",
            _scale_reason(k, trace_trend, _trend_split(_series_for_comment(month_df, k.get("ec_col")))[2]),
        ]

    if kind == "orp_corrosion":
        return _orp_copper_corrosion_comment(k, month_df)

    if kind == "biocide_corrosion":
        relay = _series_for_comment(month_df, k.get("rel_col"))
        cu = _series_for_comment(month_df, k.get("cu_col"))
        _, _, relay_trend = _trend_split(relay)
        _, _, cu_trend = _trend_split(cu)
        relay_visible = len(relay) and relay.mean() > 0.01
        relay_text = "Biocide relay activity was present" if relay_visible else "Biocide relay activity was limited or not visible"
        cu_good = k.get("cu_mean") is not None and k.get("cu_mean") < 0.5
        return [
            _pattern_line("biocide feed versus copper corrosion", cu_trend, cu_good),
            f"{relay_text} in the monthly trend.",
            f"Relay activity {_pattern_word(relay_trend)} when the month is split into early and late periods.",
            _biocide_reason(relay_visible, cu_good),
        ]

    if kind == "conductivity":
        cond = _series_for_comment(month_df, k.get("ec_col"))
        trace = _series_for_comment(month_df, k.get("tp_col"))
        cond_start, cond_end, cond_trend = _trend_split(cond)
        _, _, trace_trend = _trend_split(trace)
        pct_range = _pct_in_range_from_series(cond, k.get("ec_ll"), k.get("ec_ul"))
        position = _position_text(k.get("ec_mean"), k.get("ec_ll"), k.get("ec_ul"), "conductivity average")
        cond_good = _mean_within_range(k.get("ec_mean"), k.get("ec_ll"), k.get("ec_ul"))
        return [
            _pattern_line("conductivity", cond_trend, cond_good),
            f"The trend moved from about {_fmt_value(cond_start, ' µS/cm')} at the start to {_fmt_value(cond_end, ' µS/cm')} at the end.",
            f"{position} The monthly in-range performance was {_fmt_pct(pct_range)}.",
            _conductivity_reason(k, cond_trend, trace_trend),
        ]

    if kind == "traced_product_cell_fouling":
        trace = _series_for_comment(month_df, k.get("tp_col"))
        fouling = _series_for_comment(month_df, k.get("cf_col"))
        _, _, trace_trend = _trend_split(trace)
        _, _, fouling_trend = _trend_split(fouling)
        max_fouling = float(fouling.max()) if not fouling.empty else None
        avg_fouling = float(fouling.mean()) if not fouling.empty else None
        if max_fouling is not None and max_fouling > CELL_FOULING_THRESHOLD_PCT:
            reason = "Cell fouling exceeded the 30% limit, so the fluorometer cell should be inspected and cleaned, and sample flow should be confirmed during the next service visit."
        else:
            reason = "Cell fouling remained below the 30% limit, so routine monitoring is appropriate."
        return [
            _pattern_line("cell fouling", fouling_trend, max_fouling is not None and max_fouling <= CELL_FOULING_THRESHOLD_PCT),
            f"Cell fouling averaged {_fmt_value(avg_fouling, '%', 1)} and peaked at {_fmt_value(max_fouling, '%', 1)} during the month.",
            f"Traced Product {_pattern_word(trace_trend)} while cell fouling {_pattern_word(fouling_trend)}.",
            reason,
        ]

    return []


def _scale_control_comment(k, ade, month_df, ts_col):
    trace_col = k.get("tp_col")
    tag_col = k.get("tag_polymer_col")
    cond_col = k.get("ec_col")
    target = k.get("tp_sp")
    if not trace_col or trace_col not in month_df.columns or not target:
        return ""

    optional_cols = []
    for col in (tag_col, cond_col):
        if col and col in month_df.columns and col not in optional_cols:
            optional_cols.append(col)
    frame = month_df[[ts_col, trace_col] + optional_cols].copy()
    frame[trace_col] = pd.to_numeric(frame[trace_col], errors="coerce")
    if tag_col and tag_col in frame.columns:
        frame[tag_col] = pd.to_numeric(frame[tag_col], errors="coerce")
    if cond_col and cond_col in frame.columns:
        frame[cond_col] = pd.to_numeric(frame[cond_col], errors="coerce")
    frame = frame.dropna(subset=[ts_col, trace_col]).sort_values(ts_col)
    frame = frame[frame[trace_col] > 0]
    if len(frame) < 4:
        return ""

    trace = frame[trace_col]
    trace_early, trace_late, trace_trend = _trend_split(trace)
    in_range_pct = k.get("tp_pct")
    chunk_size = max(len(trace) // 4, 1)
    initial_trace = trace.iloc[:chunk_size]
    final_trace = trace.iloc[-chunk_size:]

    def pct(mask):
        return round(float(mask.mean() * 100), 1) if len(mask) else 0.0

    initial_in_range = pct((initial_trace >= k.get("tp_ll")) & (initial_trace <= k.get("tp_ul"))) if k.get("tp_ll") is not None and k.get("tp_ul") is not None else 0.0
    final_in_range = pct((final_trace >= k.get("tp_ll")) & (final_trace <= k.get("tp_ul"))) if k.get("tp_ll") is not None and k.get("tp_ul") is not None else 0.0
    initial_high = pct(initial_trace > k.get("tp_ul")) if k.get("tp_ul") is not None else 0.0
    final_high = pct(final_trace > k.get("tp_ul")) if k.get("tp_ul") is not None else 0.0
    final_low = pct(final_trace < k.get("tp_ll")) if k.get("tp_ll") is not None else 0.0
    final_trace_mean = float(final_trace.mean()) if len(final_trace) else None
    final_trace_above_setpoint_pct = ((final_trace_mean - target) / target * 100) if final_trace_mean is not None else None

    cond_trend = "unknown"
    cond_position = "unknown"
    cond_in_range_pct = k.get("ec_pct")
    if cond_col and cond_col in frame.columns:
        cond = frame[cond_col].dropna()
        _, _, cond_trend = _trend_split(cond) if len(cond) >= 4 else (None, None, "unknown")
        if k.get("ec_ll") is not None and len(cond):
            cond_position = "low" if float(cond.mean()) < k["ec_ll"] else "in_range_or_above"
        if k.get("ec_ll") is not None and k.get("ec_ul") is not None and len(cond):
            cond_in_range_pct = float(((cond >= k["ec_ll"]) & (cond <= k["ec_ul"])).mean() * 100)
            cond_chunk_size = max(len(cond) // 4, 1)
            final_cond = cond.iloc[-cond_chunk_size:]
            final_cond_in_range_pct = float(((final_cond >= k["ec_ll"]) & (final_cond <= k["ec_ul"])).mean() * 100)
            if final_cond_in_range_pct >= 75 or cond_in_range_pct >= 75:
                cond_position = "maintained_in_range"

    notes = [
        f"Traced Product was within the recommended range for {in_range_pct:.1f}% of the reporting month."
        if in_range_pct is not None else
        "Traced Product in-range performance could not be calculated for this reporting month."
    ]

    polymer_rate = None
    polymer_consumption_increase_pct = None
    if tag_col and tag_col in frame.columns:
        polymer_frame = frame[[trace_col, tag_col]].dropna()
        polymer_frame = polymer_frame[polymer_frame[trace_col] > 0]
        if not polymer_frame.empty:
            polymer_rate = (polymer_frame[trace_col] - polymer_frame[tag_col]) / polymer_frame[trace_col] * 100
            if float(polymer_frame[trace_col].mean()) > float(polymer_frame[tag_col].mean()):
                polymer_display_rate = _polymer_consumption_display_rates(polymer_rate)
                k["polymer_consumption_rate_pct"] = round(float(polymer_display_rate.mean()), 1)
                rate_chunk_size = max(len(polymer_display_rate) // 4, 1)
                rate_start = float(polymer_display_rate.iloc[:rate_chunk_size].mean())
                rate_end = float(polymer_display_rate.iloc[-rate_chunk_size:].mean())
                polymer_consumption_increase_pct = rate_end - rate_start
                if rate_end > rate_start:
                    rate_direction = "increased"
                elif rate_end < rate_start:
                    rate_direction = "decreased"
                else:
                    rate_direction = "remained stable"
                notes.append(
                    f"Polymer consumption rate averaged {_fmt_pct(k['polymer_consumption_rate_pct'])} and "
                    f"{rate_direction} from {_fmt_pct(rate_start)} at the start of the month "
                    f"to {_fmt_pct(rate_end)} at the end of the month."
                )
            else:
                k["polymer_consumption_rate_pct"] = None
    else:
        k["polymer_consumption_rate_pct"] = None

    initial_high_later_maintained = initial_high >= 50 and final_in_range >= 75
    initial_high_later_improved = initial_high >= 50 and final_in_range > initial_in_range and not initial_high_later_maintained
    initial_good_later_changed = initial_in_range >= 75 and final_in_range < 75
    trace_not_maintained = _control_not_maintained(k.get("tp_mean"), k.get("tp_ll"), k.get("tp_ul"), in_range_pct)
    cond_not_maintained = _control_not_maintained(k.get("ec_mean"), k.get("ec_ll"), k.get("ec_ul"), cond_in_range_pct)

    if cond_in_range_pct is not None:
        notes.append(
            f"Conductivity was within the recommended range for {cond_in_range_pct:.1f}% of the reporting month."
        )

    if initial_high_later_maintained:
        notes.append(
            f"Traced Product was higher than target during the initial part of the month, but end-of-month control improved to {final_in_range:.1f}% within range, indicating product is now maintained well."
        )
    elif initial_high_later_improved:
        notes.append(
            f"The product was higher than target during the initial part of the month and moved closer to the control band later, but end-of-month control was {final_in_range:.1f}% within range, so it is not yet consistently maintained well."
        )

    if initial_good_later_changed:
        if final_low >= 50 or trace_trend == "decreased":
            if cond_position == "maintained_in_range":
                notes.append("Product control was good initially and then decreased while conductivity was maintained well. This could be due to lack of inventory or the dosing pump losing prime, which will be inspected during the upcoming service visit.")
            elif cond_position == "low" or cond_trend == "decreased":
                notes.append("Product control was good initially and then decreased along with conductivity, indicating water loss in the system; this will be inspected during the upcoming service visit.")
        elif final_high >= 50 or trace_trend == "increased":
            if trace_not_maintained and cond_not_maintained:
                notes.append("Product control was good initially and then increased while conductivity was not maintained, indicating the Traced Product trend is related to the conductivity trend; cycles, blowdown, makeup, or dilution behavior should be inspected during the upcoming service visit.")
            else:
                notes.append("Product control was good initially and then increased later in the month, so the feed control settings and fluorometer calibration should be reviewed during the upcoming service visit.")

    if final_trace_above_setpoint_pct is not None and final_trace_above_setpoint_pct > 0:
        if final_trace_above_setpoint_pct <= 5:
            notes.append(
                "The end-of-month traced product deviation from setpoint is minimal, so the control logic will be optimised."
            )
        else:
            if trace_not_maintained and cond_not_maintained:
                notes.append(
                    f"End-of-month Traced Product was {final_trace_above_setpoint_pct:.1f}% higher than the setpoint, and conductivity was also not maintained, so the product trend should be treated as conductivity-related until cycles, blowdown, makeup, or dilution behavior is corrected."
                )
            else:
                notes.append(
                    f"End-of-month Traced Product was {final_trace_above_setpoint_pct:.1f}% higher than the setpoint, so the pump stroke will be reduced during the upcoming service visit."
                )

    if cond_position == "low" or cond_trend == "decreased":
        notes.append("Conductivity was below its setpoint configuration range for most of the same period, so water loss, dilution, or blowdown/makeup behavior should be inspected during the upcoming service visit.")
    elif cond_position == "maintained_in_range":
        notes.append("Conductivity remained stable and maintained within its setpoint configuration range, so the Traced Product deviation is not linked to water loss or dilution and should be addressed through product control optimisation.")

    if polymer_consumption_increase_pct is not None and polymer_consumption_increase_pct > 5:
        notes.append("Because polymer consumption increased by more than 5%, phosphate residual will be checked during the upcoming service visit.")

    return " ".join(notes)


def compute_kpis(scc, ade, service_notes, month_df, ts_col):
    """Extract KPIs from the monthly parquet slice."""
    k = {}

    def find_col(*kws):
        for c in month_df.columns:
            if all(w in c.lower() for w in kws): return c
        return None

    ms_col   = find_col("corrosion_probe_1")
    cu_col   = find_col("corrosion_probe_2")
    ec_col   = find_col("electrode_conductivity") or find_col("conductivity")
    tp_col   = find_col("fluorometer_ch_1") or find_col("fluorometer","ch1")
    tag_polymer_col = find_col("fluorometer_ch_2") or find_col("fluorometer","ch2")
    ph_col   = find_col("ph_probe") or find_col("ph")
    orp_col  = find_col("orp")
    turb_col = find_col("turbidity")
    cf_col   = find_col("cellfouling") or find_col("cell_fouling")
    rel_col  = find_col("relay3") or find_col("relay5") or find_col("relay1")

    k["ms_col"] = ms_col; k["cu_col"] = cu_col; k["ec_col"] = ec_col
    k["tp_col"] = tp_col; k["tag_polymer_col"] = tag_polymer_col; k["orp_col"] = orp_col; k["rel_col"] = rel_col
    k["ph_col"] = ph_col; k["turb_col"] = turb_col; k["cf_col"] = cf_col

    def series(col):
        if col is None or col not in month_df.columns: return pd.Series(dtype=float)
        return pd.to_numeric(month_df[col], errors="coerce").dropna()

    def smean(col): s=series(col); return round(float(s.mean()),4) if len(s) else None
    def smin(col):  s=series(col); return round(float(s.min()),4)  if len(s) else None
    def smax(col):  s=series(col); return round(float(s.max()),4)  if len(s) else None

    k["ms_mean"] = smean(ms_col); k["ms_min"] = smin(ms_col); k["ms_max"] = smax(ms_col)
    k["cu_mean"] = smean(cu_col); k["cu_min"] = smin(cu_col); k["cu_max"] = smax(cu_col)
    k["ec_mean"] = smean(ec_col); k["ph_mean"] = smean(ph_col)
    k["tp_mean"] = smean(tp_col); k["tag_polymer_mean"] = smean(tag_polymer_col); k["turb_mean"] = smean(turb_col)
    k["cf_mean"] = smean(cf_col)

    # Controller Setpoints
    def scc_row(*kws):
        for r in scc:
            s = (str(r.get("Input Sensor",""))+str(r.get("Sensor Name",""))).lower()
            if all(w in s for w in kws): return r
        return {}

    ec_r = scc_row("conductivity")
    tp_r = scc_row("fluorometer_ch_1") or scc_row("fluorometer","ch1") or scc_row("traced")

    def fv(row, key):
        v = row.get(key)
        try: return float(v) if v not in (None,"NULL","") else None
        except: return None

    k["ec_sp"]=fv(ec_r,"SP"); k["ec_db"]=fv(ec_r,"DB")
    k["tp_sp"]=fv(tp_r,"SP"); k["tp_db"]=fv(tp_r,"DB")
    k["ec_ll"]=(k["ec_sp"]-k["ec_db"]) if k["ec_sp"] and k["ec_db"] else None
    k["ec_ul"]=(k["ec_sp"]+k["ec_db"]) if k["ec_sp"] and k["ec_db"] else None
    k["tp_ll"]=(k["tp_sp"]-k["tp_db"]) if k["tp_sp"] and k["tp_db"] else None
    k["tp_ul"]=(k["tp_sp"]+k["tp_db"]) if k["tp_sp"] and k["tp_db"] else None
    prod = tp_r.get("Product Name") or "Traced Product"
    k["product_name"] = "Traced Product" if prod in ("None","none",None) else prod

    def pct_in_range(col, ll, ul):
        s = series(col)
        if s.empty or ll is None or ul is None: return None
        return round(sum((s>=ll)&(s<=ul))/len(s)*100, 1)

    k["tp_pct"] = pct_in_range(tp_col, k["tp_ll"], k["tp_ul"])
    k["ec_pct"] = pct_in_range(ec_col, k["ec_ll"], k["ec_ul"])

    corr_ok = (k["ms_mean"] and k["ms_mean"]<3.0) and (k["cu_mean"] and k["cu_mean"]<0.5)
    k["corr_status"] = status_from_limits(bool(corr_ok))
    k["tp_status"]   = status_from_percent(k["tp_pct"])
    k["ec_status"]   = status_from_percent(k["ec_pct"])
    k["scale_control_comment"] = _scale_control_comment(k, ade, month_df, ts_col)

    if k["tp_mean"] and k["tp_ul"] and k["tp_ll"]:
        k["tp_dir"] = "HIGH" if k["tp_mean"]>k["tp_ul"] else ("LOW" if k["tp_mean"]<k["tp_ll"] else "OK")
    else: k["tp_dir"] = "UNKNOWN"

    frc_rows = [r for r in ade if any(w in str(r.get("Parameter","")).lower()
                for w in ("free residual","frc","halogen"))]
    k["frc"] = float(frc_rows[0]["Value"]) if frc_rows else None
    k["micro_status"] = STATUS_EXCELLENT if k["frc"] and k["frc"]>=0.2 else STATUS_ACCEPTABLE
    k["dipslide_cfu"] = _find_dipslide_cfu(ade, service_notes)
    k["dipslide_comment"] = dipslide_comment(k["dipslide_cfu"])
    k["orp_spike_summary"] = _orp_spike_summary(month_df, ts_col, orp_col)
    k["good_microbial_dosage"] = k["orp_spike_summary"]["good_dosage"]
    k["relay_firing"] = rel_col is not None and series(rel_col).mean() > 0.01

    return k


def compute_coc(k, mu_cond):
    """
    Compute COC and status based on MU conductivity.

    Target COC = SCC conductivity setpoint / MU conductivity
    Actual COC = monthly average conductivity / MU conductivity
    Deviation %  = abs(Actual - Target) / Target * 100

    Status thresholds (based on % deviation from target, with low-COC override):
    Critical  : actual COC is at least 1.0 below target COC
    Excellent : deviation <= 20%
    Acceptable: 20% < deviation <= 50%
    Critical  : deviation > 50%
    """
    if mu_cond is None or mu_cond == 0:
        return {
            "mu_available": False, "mu_cond": None,
            "target_coc": None, "actual_coc": None,
            "deviation_pct": None, "coc_status": None,
        }

    target_coc = (k["ec_sp"] / mu_cond) if k["ec_sp"] else None
    actual_coc = (k["ec_mean"] / mu_cond) if k["ec_mean"] else None

    coc_gap = None
    if target_coc and actual_coc:
        coc_gap = target_coc - actual_coc
        dev = abs(actual_coc - target_coc) / target_coc * 100
        if   coc_gap >= 1.0: coc_status = STATUS_CRITICAL
        elif dev <= 20: coc_status = STATUS_EXCELLENT
        elif dev <= 50: coc_status = STATUS_ACCEPTABLE
        else:           coc_status = STATUS_CRITICAL
    else:
        dev, coc_status = None, None

    return {
        "mu_available": True, "mu_cond": round(mu_cond, 2),
        "target_coc": round(target_coc, 2) if target_coc else None,
        "actual_coc": round(actual_coc, 2) if actual_coc else None,
        "coc_gap": round(coc_gap, 2) if coc_gap is not None else None,
        "deviation_pct": round(dev, 1) if dev is not None else None,
        "coc_status": coc_status,
    }


# ══════════════════════════════════════════════════════════════════════════════
# CHART BUILDERS — full date-axis, matching training report style
# ══════════════════════════════════════════════════════════════════════════════

def _date_axis(ax, month_df, ts_col):
    """Apply date-formatted x-axis matching training report style."""
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=3))
    ax.xaxis.set_minor_locator(mdates.DayLocator(interval=1))
    # Month label below
    dt = month_df[ts_col].iloc[0]
    ax.set_xlabel(f"{dt.strftime('%b')}\n{dt.year}", fontsize=9, color="#444444")


def _style(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.18, linestyle="--", color="#AAAAAA")
    ax.grid(axis="x", alpha=0.10, linestyle="--", color="#AAAAAA")


def _resample(month_df, ts_col, col, freq="4h"):
    """Resample to reduce density for cleaner charts (like training reports)."""
    if col not in month_df.columns: return None
    s = month_df[[ts_col, col]].copy()
    s[col] = pd.to_numeric(s[col], errors="coerce")
    s = s.set_index(ts_col).resample(freq)[col].mean().dropna().reset_index()
    return s


def make_corrosion_chart(k, month_df, ts_col, slug, month):
    """ORP vs Copper Corrosion — dual axis, matching Flowserve training chart exactly."""
    fig, ax1 = plt.subplots(figsize=(8, 3.8))
    ax2 = ax1.twinx()

    # Copper corrosion (right axis, yellow/orange like training report)
    cu = _resample(month_df, ts_col, k["cu_col"], "2h")
    if cu is not None and not cu.empty:
        ax2.plot(cu[ts_col], cu[k["cu_col"]], color=YH, lw=1.0, alpha=0.9,
                 label=f"Corrosion Cu (MPY)")
        ax2.fill_between(cu[ts_col], 0, cu[k["cu_col"]], color=YH, alpha=0.15)
        ax2.set_ylabel("Copper Corrosion (MPY)", fontsize=9, color=YH)
        ax2.tick_params(axis="y", colors=YH)
        ax2.set_ylim(bottom=0)
        # Target line
        ax2.axhline(0.5, color=YH, lw=0.8, ls=":", alpha=0.6)

    # Mild Steel corrosion (left axis, green like training report)
    ms = _resample(month_df, ts_col, k["ms_col"], "2h")
    if ms is not None and not ms.empty:
        ax1.plot(ms[ts_col], ms[k["ms_col"]], color=GH, lw=1.2, alpha=0.9,
                 label="Corrosion MS (MPY)")
        ax1.set_ylabel("Mild Steel Corrosion (MPY)", fontsize=9, color=GH)
        ax1.tick_params(axis="y", colors=GH)
        ax1.set_ylim(bottom=0)
        ax1.axhline(3.0, color=GH, lw=0.8, ls=":", alpha=0.6)

    ax1.set_title(f"Corrosion Rate — {month}", fontsize=11, fontweight="bold", pad=8)
    _style(ax1)
    _date_axis(ax1, month_df, ts_col)

    h1,l1 = ax1.get_legend_handles_labels()
    h2,l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1+h2, l1+l2, fontsize=8, loc="upper right")

    fig.tight_layout()
    p = CHARTS_DIR / f"{slug}_corrosion.png"
    fig.savefig(p, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  ✓ corrosion chart: {p.name}")
    return p


def make_orp_corrosion_chart(k, month_df, ts_col, slug, month):
    """ORP vs Copper corrosion — exactly matching training report KPM trend page."""
    fig, ax1 = plt.subplots(figsize=(8, 3.8))
    ax2 = ax1.twinx()

    # ORP (left axis, green) — show absolute values here for the chart
    # Note: ORP values appear in the chart but narrative still uses spike language
    orp = _resample(month_df, ts_col, k["orp_col"], "1h")
    if orp is not None and not orp.empty:
        ax1.plot(orp[ts_col], orp[k["orp_col"]], color=GH, lw=0.9, alpha=0.85,
                 label="ORP (mV)")
        ax1.set_ylabel("ORP (mV)", fontsize=9, color=GH)
        ax1.tick_params(axis="y", colors=GH)

    # Copper corrosion (right axis, yellow)
    cu = _resample(month_df, ts_col, k["cu_col"], "2h")
    if cu is not None and not cu.empty:
        ax2.plot(cu[ts_col], cu[k["cu_col"]], color=YH, lw=1.2, alpha=0.9,
                 label="Corrosion Cu (MPY)")
        ax2.fill_between(cu[ts_col], 0, cu[k["cu_col"]], color=YH, alpha=0.15)
        ax2.set_ylabel("Copper Corrosion (MPY)", fontsize=9, color=YH)
        ax2.tick_params(axis="y", colors=YH)
        ax2.set_ylim(bottom=0)

    ax1.set_title(f"ORP vs Copper Corrosion Rate — {month}", fontsize=11, fontweight="bold", pad=8)
    _style(ax1)
    _date_axis(ax1, month_df, ts_col)

    h1,l1 = ax1.get_legend_handles_labels()
    h2,l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1+h2, l1+l2, fontsize=8, loc="upper right")

    fig.tight_layout()
    p = CHARTS_DIR / f"{slug}_orp_corrosion.png"
    fig.savefig(p, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  ✓ ORP vs corrosion chart: {p.name}")
    return p


def make_traced_product_chart(k, month_df, ts_col, slug, month):
    """Traced product full month trend with Controller Setpoint limits."""
    sp = k["tp_sp"] or 100; db = k["tp_db"] or 5
    ll = k["tp_ll"] or sp-db; ul = k["tp_ul"] or sp+db
    prod = k["product_name"]

    fig, ax = plt.subplots(figsize=(8, 3.8))

    tp = _resample(month_df, ts_col, k["tp_col"], "4h")
    if tp is not None and not tp.empty:
        # Shade SCC control band
        ax.axhspan(ll, ul, alpha=0.10, color=GH, label=f"Controller Setpoint range {ll:.1f}–{ul:.1f} ppm")
        ax.axhline(sp, color=GH, lw=1.2, ls="--", alpha=0.7, label=f"Setpoint {sp:.1f} ppm")
        ax.axhline(ul, color="#AAAAAA", lw=0.7, ls=":")
        ax.axhline(ll, color="#AAAAAA", lw=0.7, ls=":")

        vals = tp[k["tp_col"]].values
        times = tp[ts_col].values
        in_range  = np.where((vals>=ll) & (vals<=ul), vals, np.nan)
        out_range = np.where((vals<ll)  | (vals>ul),  vals, np.nan)

        ax.plot(times, vals,      color=GH,  lw=1.0, alpha=0.6)
        ax.fill_between(times, ll, vals, where=(vals>=ll)&(vals<=ul),
                        color=GH, alpha=0.15, label="In Controller Setpoint range")
        ax.fill_between(times, vals, ul, where=(vals>ul),
                        color=RH, alpha=0.18, label="Above Controller Setpoint range")
        ax.fill_between(times, ll, vals, where=(vals<ll),
                        color=RH, alpha=0.18, label="Below Controller Setpoint range")

    ax.set_ylabel(f"{prod} (ppm)", fontsize=9)
    ax.set_title(f"{prod} — {month}", fontsize=11, fontweight="bold", pad=8)
    _style(ax); _date_axis(ax, month_df, ts_col)
    ax.legend(fontsize=7.5, loc="best")

    fig.tight_layout()
    p = CHARTS_DIR / f"{slug}_traced_product.png"
    fig.savefig(p, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  ✓ traced product chart: {p.name}")
    return p


def make_conductivity_chart(k, month_df, ts_col, slug, month):
    """Conductivity full month trend matching training report style."""
    sp = k["ec_sp"] or 1000; db = k["ec_db"] or 50
    ll = k["ec_ll"] or sp-db; ul = k["ec_ul"] or sp+db

    fig, ax = plt.subplots(figsize=(8, 3.8))

    ec = _resample(month_df, ts_col, k["ec_col"], "2h")
    if ec is not None and not ec.empty:
        ax.axhspan(ll, ul, alpha=0.10, color=BH, label=f"Controller Setpoint range {ll:.0f}–{ul:.0f} µS/cm")
        ax.axhline(sp, color=BH, lw=1.2, ls="--", alpha=0.7, label=f"Setpoint {sp:.0f} µS/cm")

        vals  = ec[k["ec_col"]].values
        times = ec[ts_col].values
        ax.plot(times, vals, color=YH, lw=1.0, alpha=0.85, label="Conductivity (µS/cm)")
        ax.fill_between(times, ll, vals, where=(vals>=ll)&(vals<=ul),
                        color=BH, alpha=0.12)

    ax.set_ylabel("Conductivity (µS/cm)", fontsize=9)
    ax.set_title(f"Electrode Conductivity — {month}", fontsize=11, fontweight="bold", pad=8)
    _style(ax); _date_axis(ax, month_df, ts_col)
    ax.legend(fontsize=8, loc="best")

    fig.tight_layout()
    p = CHARTS_DIR / f"{slug}_conductivity.png"
    fig.savefig(p, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  ✓ conductivity chart: {p.name}")
    return p


def make_biocide_corrosion_chart(k, month_df, ts_col, slug, month):
    """Biocide pump relay vs copper corrosion — matches Flowserve page 7."""
    fig, ax1 = plt.subplots(figsize=(8, 3.8))
    ax2 = ax1.twinx()

    # Biocide relay (left, green dashed)
    rel = _resample(month_df, ts_col, k["rel_col"], "1h") if k["rel_col"] else None
    if rel is not None and not rel.empty:
        ax1.plot(rel[ts_col], rel[k["rel_col"]], color=GH, lw=0.8, ls="--",
                 alpha=0.7, label="Biocide Pump Relay")
        ax1.set_ylabel("Biocide Relay (on/off)", fontsize=9, color=GH)
        ax1.tick_params(axis="y", colors=GH)
        ax1.set_ylim(-0.1, 1.5)

    # Copper corrosion (right, yellow)
    cu = _resample(month_df, ts_col, k["cu_col"], "2h")
    if cu is not None and not cu.empty:
        ax2.plot(cu[ts_col], cu[k["cu_col"]], color=YH, lw=1.2, alpha=0.9,
                 label="Corrosion Cu (MPY)")
        ax2.fill_between(cu[ts_col], 0, cu[k["cu_col"]], color=YH, alpha=0.15)
        ax2.set_ylabel("Copper Corrosion (MPY)", fontsize=9, color=YH)
        ax2.tick_params(axis="y", colors=YH)
        ax2.set_ylim(bottom=0)

    ax1.set_title(f"Oxidizing Biocide Pump Relay vs Copper Corrosion — {month}",
                  fontsize=11, fontweight="bold", pad=8)
    _style(ax1); _date_axis(ax1, month_df, ts_col)

    h1,l1 = ax1.get_legend_handles_labels()
    h2,l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1+h2, l1+l2, fontsize=8, loc="upper right")

    fig.tight_layout()
    p = CHARTS_DIR / f"{slug}_biocide_corrosion.png"
    fig.savefig(p, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  ✓ biocide vs corrosion chart: {p.name}")
    return p


def make_traced_product_cell_fouling_chart(k, month_df, ts_col, slug, month):
    """Traced Product vs Cell Fouling chart shown when fouling exceeds 30%."""
    fig, ax1 = plt.subplots(figsize=(8, 3.8))
    ax2 = ax1.twinx()
    prod = k["product_name"]

    tp = _resample(month_df, ts_col, k["tp_col"], "4h") if k.get("tp_col") else None
    if tp is not None and not tp.empty:
        ax1.plot(tp[ts_col], tp[k["tp_col"]], color=GH, lw=1.0, alpha=0.85,
                 label=f"{prod} (ppm)")
        if k.get("tp_sp"):
            ax1.axhline(k["tp_sp"], color=GH, lw=1.0, ls="--", alpha=0.55,
                        label=f"{prod} setpoint {k['tp_sp']:.1f} ppm")
        ax1.set_ylabel(f"{prod} (ppm)", fontsize=9, color=GH)
        ax1.tick_params(axis="y", colors=GH)

    cf = _resample(month_df, ts_col, k["cf_col"], "4h") if k.get("cf_col") else None
    if cf is not None and not cf.empty:
        ax2.plot(cf[ts_col], cf[k["cf_col"]], color=RH, lw=1.0, alpha=0.85,
                 label="Cell Fouling (%)")
        ax2.fill_between(cf[ts_col], CELL_FOULING_THRESHOLD_PCT, cf[k["cf_col"]],
                         where=(cf[k["cf_col"]] > CELL_FOULING_THRESHOLD_PCT),
                         color=RH, alpha=0.16, label="Above 30%")
        ax2.axhline(CELL_FOULING_THRESHOLD_PCT, color=RH, lw=1.0, ls=":", alpha=0.75,
                    label="Cell Fouling 30% limit")
        ax2.set_ylabel("Cell Fouling (%)", fontsize=9, color=RH)
        ax2.tick_params(axis="y", colors=RH)
        ax2.set_ylim(bottom=0)

    ax1.set_title(f"{prod} vs Cell Fouling — {month}", fontsize=11, fontweight="bold", pad=8)
    _style(ax1)
    _date_axis(ax1, month_df, ts_col)

    h1,l1 = ax1.get_legend_handles_labels()
    h2,l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1+h2, l1+l2, fontsize=7.5, loc="best")

    fig.tight_layout()
    p = CHARTS_DIR / f"{slug}_traced_product_cell_fouling.png"
    fig.savefig(p, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  ✓ traced product vs cell fouling chart: {p.name}")
    return p


# ══════════════════════════════════════════════════════════════════════════════
# WORD DOCUMENT ASSEMBLY
# ══════════════════════════════════════════════════════════════════════════════

def set_bg(cell, hx):
    tc=cell._tc; tcPr=tc.get_or_add_tcPr(); shd=OxmlElement("w:shd")
    shd.set(qn("w:val"),"clear"); shd.set(qn("w:color"),"auto")
    shd.set(qn("w:fill"),hx.lstrip("#")); tcPr.append(shd)


def add_para(doc, text="", size=10, bold=False, color=None, italic=False,
             sb=4, sa=6, align=WD_ALIGN_PARAGRAPH.LEFT):
    p = doc.add_paragraph(); p.alignment = align
    p.paragraph_format.space_before = Pt(sb)
    p.paragraph_format.space_after  = Pt(sa)
    if text:
        r = p.add_run(text); r.font.size=Pt(size); r.font.bold=bold; r.font.italic=italic
        if color: r.font.color.rgb = color
    return p


def _strip_status(text):
    """Remove any 'Status: X.' or 'Status: X,' prefix from AI-generated text."""
    if not text: return text
    # Remove patterns like "Status: Excellent." or legacy "Status: Action Required." at the start
    return re.sub(rf"^\s*Status:\s*({STATUS_PATTERN})[.,:]\s*",
                  "", text, flags=re.IGNORECASE).strip()


def _strip_polymer_consumption(text):
    if not text:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(sentence for sentence in sentences if "polymer consumption" not in sentence.lower()).strip()


def _corrosion_narrative(k):
    return (
        f"During the reporting period, the system remained under good control. "
        f"The mild steel and copper corrosion rates averaged {_fmt_value(k.get('ms_mean'), ' mpy', 2)} "
        f"and {_fmt_value(k.get('cu_mean'), ' mpy', 2)}, respectively, both of which are well within "
        f"the recommended limits of <5 mpy and <0.5 mpy."
    )


def add_h1(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before=Pt(14); p.paragraph_format.space_after=Pt(4)
    r = p.add_run(text); r.font.size=Pt(16); r.font.bold=True; r.font.color.rgb=GREEN
    pPr=p._p.get_or_add_pPr(); pBdr=OxmlElement("w:pBdr"); bot=OxmlElement("w:bottom")
    bot.set(qn("w:val"),"single"); bot.set(qn("w:sz"),"8")
    bot.set(qn("w:space"),"4"); bot.set(qn("w:color"),"00857C")
    pBdr.append(bot)
    ps=pPr.find(qn("w:pStyle"))
    if ps is not None: ps.addnext(pBdr)
    else: pPr.insert(0,pBdr)


def add_h2(doc, text):
    p=doc.add_paragraph()
    p.paragraph_format.space_before=Pt(10); p.paragraph_format.space_after=Pt(3)
    r=p.add_run(text); r.font.size=Pt(13); r.font.bold=True
    r.font.color.rgb=RGBColor(0x00,0x5F,0x58)


def add_h3(doc, text):
    p=doc.add_paragraph()
    p.paragraph_format.space_before=Pt(8); p.paragraph_format.space_after=Pt(2)
    r=p.add_run(text); r.font.size=Pt(11); r.font.bold=True
    r.font.color.rgb=RGBColor(0x22,0x22,0x22)


def add_status(doc, s):
    label = display_status(s)
    c = GREEN if label==STATUS_EXCELLENT else (AMBER if label==STATUS_ACCEPTABLE else RED)
    p = doc.add_paragraph()
    p.paragraph_format.space_before=Pt(3); p.paragraph_format.space_after=Pt(5)
    r1=p.add_run("Status: "); r1.font.size=Pt(10); r1.font.bold=True
    r2=p.add_run(label);     r2.font.size=Pt(10); r2.font.bold=True; r2.font.color.rgb=c


def add_img(doc, path, w=6.0, caption=None, fig_num=None):
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(path), width=Inches(w))
    if caption:
        lbl = f"Figure {fig_num}: {caption}" if fig_num else caption
        cp=doc.add_paragraph(lbl); cp.alignment=WD_ALIGN_PARAGRAPH.CENTER
        for r in cp.runs:
            r.font.size=Pt(8.5); r.font.italic=True; r.font.color.rgb=GREY
        cp.paragraph_format.space_after=Pt(6)


def add_comment(doc, text):
    if not text: return
    lines = text if isinstance(text, list) else str(text).splitlines()
    lines = [line.strip() for line in lines if line and line.strip()]
    if not lines: return
    p=doc.add_paragraph()
    p.paragraph_format.space_before=Pt(2); p.paragraph_format.space_after=Pt(10)
    label=p.add_run("Comment: ")
    label.font.size=Pt(9.5); label.font.italic=True; label.font.bold=True; label.font.color.rgb=RGBColor(0x33,0x33,0x33)
    for index, line in enumerate(lines):
        if index:
            p.add_run().add_break()
        r=p.add_run(line)
        r.font.size=Pt(9.5); r.font.italic=True; r.font.color.rgb=RGBColor(0x33,0x33,0x33)


def add_table(doc, headers, rows, col_cm):
    tbl=doc.add_table(rows=1, cols=len(headers)); tbl.style="Table Grid"
    hdr=tbl.rows[0]
    for i,(cell,h) in enumerate(zip(hdr.cells, headers)):
        cell.width=Cm(col_cm[i]); set_bg(cell,"00857C")
        p=cell.paragraphs[0]; p.paragraph_format.space_before=Pt(3); p.paragraph_format.space_after=Pt(3)
        r=p.add_run(h); r.font.bold=True; r.font.size=Pt(9); r.font.color.rgb=WHITE
    for ri, rd in enumerate(rows):
        row=tbl.add_row(); bg="FFFFFF" if ri%2==0 else "F2F8F7"
        for i,(cell,val) in enumerate(zip(row.cells, rd)):
            cell.width=Cm(col_cm[i]); set_bg(cell,bg)
            p=cell.paragraphs[0]; p.paragraph_format.space_before=Pt(3); p.paragraph_format.space_after=Pt(3)
            r=p.add_run(str(val)); r.font.size=Pt(9)
    doc.add_paragraph()


def build_docx(site, month, controllers, k, narr, charts, month_df, coc, water_loss):
    doc = Document()
    sec = doc.sections[0]
    sec.page_width=Cm(21.59); sec.page_height=Cm(27.94)
    sec.left_margin=sec.right_margin=Cm(1.9)
    sec.top_margin=sec.bottom_margin=Cm(1.9)

    # Header
    hdr=sec.header; hp=hdr.paragraphs[0]; hp.clear()
    hr=hp.add_run(f"Buckman  |  {site}  |  {month} Cooling Water Performance Report")
    hr.font.size=Pt(8); hr.font.color.rgb=GREY
    pPr=hp._p.get_or_add_pPr(); pBdr=OxmlElement("w:pBdr"); bot=OxmlElement("w:bottom")
    bot.set(qn("w:val"),"single"); bot.set(qn("w:sz"),"4")
    bot.set(qn("w:space"),"4"); bot.set(qn("w:color"),"00857C")
    pBdr.append(bot)
    ps=pPr.find(qn("w:pStyle"))
    if ps is not None: ps.addnext(pBdr)
    else: pPr.insert(0,pBdr)

    # Footer
    ftr=sec.footer; fp=ftr.paragraphs[0]; fp.clear()
    fr=fp.add_run("Buckman Digital Water  |  Confidential")
    fr.font.size=Pt(8); fr.font.color.rgb=GREY

    ctrl_ids = [str(controller.get("SerialNumber", "")).strip() for controller in controllers]
    ctrl_id = ", ".join(controller_id for controller_id in ctrl_ids if controller_id) or "N/A"
    today   = datetime.now().strftime("%d %B %Y")
    prod    = k["product_name"]

    def fmt(v, d=2):
        try: return f"{float(v):.{d}f}" if v not in (None,"NULL","") else "N/A"
        except: return "N/A"
    def si(s):
        label = display_status(s)
        return "✓" if label==STATUS_EXCELLENT else ("⚠" if label==STATUS_ACCEPTABLE else "✗")

    # ── PAGE 1: TITLE ─────────────────────────────────────────────────────────
    add_para(doc,"BUCKMAN DIGITAL WATER",size=10,bold=True,color=GREY,
             align=WD_ALIGN_PARAGRAPH.CENTER,sb=36,sa=3)
    add_para(doc,"Monthly Cooling Water Performance Report",
             size=20,bold=True,align=WD_ALIGN_PARAGRAPH.CENTER,sb=3,sa=3)
    add_para(doc,site,size=15,bold=True,color=GREEN,
             align=WD_ALIGN_PARAGRAPH.CENTER,sb=3,sa=10)
    add_para(doc,f"Reporting Month: {month}",size=10,color=GREY,
             align=WD_ALIGN_PARAGRAPH.CENTER,sb=3,sa=18)
    add_table(doc,["Customer / Site","System","Controller","Prepared For"],
              [[site,"Cooling Tower",ctrl_id,"Monthly Performance Review"]],
              [5.5,3.0,3.5,4.5])
    add_para(doc,sb=10,sa=6)
    add_para(doc,
        f"This report summarises corrosion control, scale control, microbial control, "
        f"water efficiency, product efficiency, and proactive system support for "
        f"{site}, {month}, using controller setpoints, telemetry KPIs, field data, "
        f"and service note records.",
        size=9.5,color=GREY,align=WD_ALIGN_PARAGRAPH.CENTER)
    add_para(doc,sb=10)
    add_table(doc,["Prepared By","Prepared Date","Report Status"],
              [["Buckman Digital Water",today,"Draft"]],[5.5,5.0,6.0])
    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════════════
    # PAGES 2–3: EXECUTIVE SUMMARY — narrative text only, no charts
    # ══════════════════════════════════════════════════════════════════════════
    add_h1(doc,"Executive Summary")
    add_h2(doc,"System Health Check")

    # ── Corrosion Control ─────────────────────────────────────────────────────
    add_h3(doc,"Corrosion Control")
    add_status(doc, k["corr_status"])
    add_para(doc, _corrosion_narrative(k))

    # ── Scale Control ─────────────────────────────────────────────────────────
    add_h3(doc,"Scale Control")
    add_status(doc, k["tp_status"])
    if k.get("scale_control_comment"):
        add_para(doc, k["scale_control_comment"])
    else:
        add_para(doc, _strip_status(narr.get("scale_narrative","")))

    # ── Microbial Control ─────────────────────────────────────────────────────
    add_h3(doc,"Microbial Control")
    add_status(doc, k["micro_status"])
    add_para(doc, microbial_control_comment(k))

    # ── Water Efficiency ──────────────────────────────────────────────────────
    add_h2(doc,"Water Efficiency")
    water_efficiency_status = _water_efficiency_status(k, coc, water_loss, month_df)
    water_efficiency_status_label = display_status(water_efficiency_status)

    if coc["mu_available"]:
        add_status(doc, water_efficiency_status)

        add_table(doc,
            ["MU Conductivity","Target COC","Actual COC","Deviation","Status"],
            [[f"{coc['mu_cond']} µS/cm",
              f"{coc['target_coc']}" if coc['target_coc'] else "N/A",
              f"{coc['actual_coc']}" if coc['actual_coc'] else "N/A",
              f"{coc['deviation_pct']}%" if coc['deviation_pct'] is not None else "N/A",
              water_efficiency_status_label]],
            [3.4, 3.4, 3.4, 3.4, 3.4])
        if coc.get("coc_gap") is not None and coc.get("coc_gap") >= 1.0:
            add_para(doc,
                "Actual COC is more than 1.0 below target COC, so this is Critical and needs attention because there can be water loss, excess blowdown, or dilution.",
                size=10)
        if water_loss.get("triggered"):
            add_table(doc,
                ["System", "Current COC", "Target COC", "Decrease", "Annual Water Loss", "Estimated Cost"],
                [[row.get("system_name") or row.get("site_name") or "Cooling Tower",
                  f"{water_loss['current_coc']:.2f}",
                  f"{row['target_coc']:.2f}",
                  f"{row['decrease_pct']:.1f}%",
                  f"{_fmt_number(row['water_savings_per_annum'])} gal/year",
                  f"${_fmt_number(row['water_savings_cost'], 2)}/year"]
                 for row in water_loss["rows"]],
                [3.4, 2.2, 2.2, 2.2, 3.6, 3.4])
            add_para(doc,
                f"Because current COC is more than {WATER_LOSS_THRESHOLD_PCT:g}% below the value-creation Target COC, estimated avoidable makeup water is {_fmt_number(water_loss['water_savings_per_annum'])} gallons per annum. At a makeup water cost of $5 per 100 gallons, the estimated annual savings opportunity is ${_fmt_number(water_loss['water_savings_cost'], 2)}.",
                size=10)
        add_para(doc, _water_efficiency_comment(k, month_df, water_loss))
    else:
        add_status(doc, water_efficiency_status)
        add_para(doc,
            "Makeup water conductivity is not available for this site. "
            "Actual cycles of concentration cannot be calculated. "
            "Makeup conductivity should be captured at the next service visit.",
            size=10)
        add_para(doc, _water_efficiency_comment(k, month_df, water_loss))

    # ── Product Efficiency ────────────────────────────────────────────────────
    add_h2(doc,"Product Efficiency")
    add_status(doc, k["tp_status"])
    product_efficiency_text = _strip_polymer_consumption(_strip_status(narr.get("product_efficiency_narrative", "")))
    add_para(doc, product_efficiency_text)

    # ── Proactive System Support ──────────────────────────────────────────────
    add_h2(doc,"Proactive System Support")
    add_para(doc, _proactive_support_summary(k, narr, coc, month_df))
    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════════════
    # PERFORMANCE SUMMARY
    # ══════════════════════════════════════════════════════════════════════════
    add_h1(doc,"Performance Summary")
    add_para(doc,
        "Controller Setpoints are used as control limits below. "
        "% In Range is calculated from the full reporting month telemetry.",
        size=9,italic=True,color=GREY)

    add_table(doc,
        ["Parameter","Context Point","Average","Std Dev","Min","Max",
         "Lower Limit","Upper Limit","% In Range","Status"],
        _perf_rows(k, month_df),
        [3.2,2.2,1.5,1.5,1.4,1.4,1.7,1.7,1.8,2.2])
    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════════════
    # CHARTS AND COMMENTS — separate section after Performance Summary
    # ══════════════════════════════════════════════════════════════════════════
    add_h1(doc,"Charts and Comments")

    # Chart 1: Corrosion Rate
    add_h2(doc,"Corrosion Rate")
    add_img(doc, charts["corrosion"],
            caption=f"Corrosion Rate — {month}", fig_num=1)
    add_comment(doc, _chart_pattern_comment("corrosion", k, month_df))

    # Chart 2: Traced Product
    add_h2(doc,f"{prod} Control Trend")
    add_img(doc, charts["traced_product"],
            caption=f"{prod} — {month}", fig_num=2)
    add_comment(doc, _chart_pattern_comment("scale", k, month_df))

    # Chart 3: ORP vs Copper Corrosion
    add_h2(doc,"ORP vs Copper Corrosion Rate")
    add_img(doc, charts["orp_corrosion"],
            caption=f"ORP vs Copper Corrosion Rate — {month}", fig_num=3)
    add_comment(doc, _chart_pattern_comment("orp_corrosion", k, month_df))

    # Chart 4: Conductivity
    add_h2(doc,"Electrode Conductivity")
    add_img(doc, charts["conductivity"],
            caption=f"Electrode Conductivity — {month}", fig_num=4)
    add_comment(doc, _water_efficiency_comment(k, month_df, water_loss))

    doc.add_page_break()

    # ══════════════════════════════════════════════════════════════════════════
    # CLOSING SUMMARY (no checklist)
    # ══════════════════════════════════════════════════════════════════════════
    add_h1(doc,"Closing Summary")
    add_para(doc, _strip_status(narr.get("closing_summary","")))
    return doc


def _perf_rows(k, month_df):
    """Build performance summary rows with full-month stats from parquet."""
    def col_stats(col):
        if col is None or col not in month_df.columns:
            return "N/A","N/A","N/A","N/A"
        s = pd.to_numeric(month_df[col], errors="coerce").dropna()
        if s.empty: return "N/A","N/A","N/A","N/A"
        return (f"{s.mean():.3f}", f"{s.std():.3f}",
                f"{s.min():.3f}", f"{s.max():.3f}")

    def pct_str(col, ll, ul):
        if col is None or ll is None or ul is None: return "–"
        s = pd.to_numeric(month_df.get(col, pd.Series()), errors="coerce").dropna()
        if s.empty: return "–"
        return f"{round(sum((s>=ll)&(s<=ul))/len(s)*100,1)}%"

    def fmt(v, d=2):
        try: return f"{float(v):.{d}f}" if v not in (None,"NULL","") else "–"
        except: return "–"

    def status_cell(status):
        label = display_status(status)
        icon = "✓" if label == STATUS_EXCELLENT else ("⚠" if label == STATUS_ACCEPTABLE else "✗")
        return f"{icon} {label}"

    prod = k["product_name"]

    # Helper: get setpoint limits for a sensor from SCC data
    def get_limits(sensor_key):
        """Return (lower, upper) from SCC for a sensor, or (None, None)."""
        # Check if k already has computed limits
        if sensor_key == "ph":
            return "7.50", "10.00"
        if sensor_key == "turb":
            return "–", "75.0"
        if sensor_key == "cf":
            return "–", "30.0"
        if sensor_key == "orp":
            return "–", "–"
        return "–", "–"

    # pH stats from parquet
    ph_stats = col_stats(k.get("ph_col"))
    ph_ll, ph_ul = get_limits("ph")
    ph_pct = pct_str(k.get("ph_col"), 7.5, 10.0) if k.get("ph_col") else "–"

    # ORP stats from parquet (show values in table, not in narrative)
    orp_stats = col_stats(k.get("orp_col"))

    # Turbidity stats from parquet
    turb_stats = col_stats(k.get("turb_col"))

    # Cell Fouling stats from parquet
    cf_stats = col_stats(k.get("cf_col"))

    rows = [
        ["Corrosion – MS (MPY)", "ACM Skid",
         *col_stats(k["ms_col"]), "0.00", "3.00",
         pct_str(k["ms_col"], 0, 3.0),
         status_cell(k['corr_status'])],
        ["Corrosion – Cu (MPY)", "ACM Skid",
         *col_stats(k["cu_col"]), "0.00", "0.50",
         pct_str(k["cu_col"], 0, 0.5),
         status_cell(k['corr_status'])],
        [f"{prod} (ppm)", "ACM Skid",
         *col_stats(k["tp_col"]),
         fmt(k["tp_ll"],1), fmt(k["tp_ul"],1),
         f"{k['tp_pct']}%" if k['tp_pct'] is not None else "–",
         status_cell(k['tp_status'])],
        ["Conductivity (µS/cm)", "ACM Skid",
         *col_stats(k["ec_col"]),
         fmt(k["ec_ll"],0), fmt(k["ec_ul"],0),
         f"{k['ec_pct']}%" if k['ec_pct'] is not None else "–",
         status_cell(k['ec_status'])],
        ["pH", "ACM Skid",
         *ph_stats, ph_ll, ph_ul, ph_pct, "ℹ Info"],
        ["ORP (mV)", "ACM Skid",
         *orp_stats, "–", "–", "–", "See chart"],
        ["Turbidity (NTU)", "ACM Skid",
         *turb_stats, "–", "75.0", "–", "ℹ Info"],
        ["Cell Fouling (%)", "ACM Skid",
         *cf_stats, "–", "30.0", "–", "ℹ Info"],
    ]
    return rows


def _fix(path):
    tmp = path.with_suffix(".tmp.docx")
    with zipfile.ZipFile(path,"r") as zin:
        with zipfile.ZipFile(tmp,"w",zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                if item.filename=="word/settings.xml":
                    text=data.decode("utf-8")
                    text=re.sub(r'<w:zoom\b(?![^>]*w:percent)([^>]*)/>', r'<w:zoom w:percent="100"\1/>',text)
                    data=text.encode("utf-8")
                zout.writestr(item,data)
    tmp.replace(path)


def save_report_document(doc, slug):
    candidates = [
        OUTPUT_DIR / f"{slug}_report.docx",
        OUTPUT_DIR / f"{slug}_report_updated.docx",
        OUTPUT_DIR / f"{slug}_report_updated_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx",
    ]
    for index, path in enumerate(candidates):
        try:
            doc.save(str(path))
            if index:
                print(f"  Report file is locked; saving alternate copy -> {path}")
            return path
        except PermissionError:
            continue
    raise PermissionError("Could not save report because all output paths are locked.")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser()
    site_group = p.add_mutually_exclusive_group(required=True)
    site_group.add_argument("--site")
    site_group.add_argument("--controller-id", "--controller-ids", nargs="+", dest="controller_ids")
    p.add_argument("--month", required=True)
    args = p.parse_args()
    site = args.site; month = args.month
    controller_ids = normalize_controller_ids(args.controller_ids)

    print(f"\n{'='*60}")
    print(f"  Report Generator  —  Loading cache  |  {month}")
    print(f"{'='*60}\n")

    print("Step 1/4 — Loading narrative cache and parquet telemetry …")
    site, narr, controllers, scc, ade, service_notes, month_df, ts_col, slug = load_all(site, month, controller_ids)
    print(f"  Site: {site}")
    k = compute_kpis(scc, ade, service_notes, month_df, ts_col)

    print(f"  MS: {k['ms_mean']} MPY  |  Cu: {k['cu_mean']} MPY  → {k['corr_status']}")
    print(f"  {k['product_name']}: {k['tp_mean']} ppm  ({k['tp_pct']}% in range → {k['tp_status']})")
    print(f"  Conductivity: {k['ec_mean']} µS/cm  ({k['ec_pct']}% in range → {k['ec_status']})")
    print(f"  FRC: {k['frc']}  |  Microbial: {k['micro_status']}")

    print("\nStep 2/4 — Generating full date-axis charts from parquet …")
    charts = {
        "corrosion":        make_corrosion_chart(k, month_df, ts_col, slug, month),
        "orp_corrosion":    make_orp_corrosion_chart(k, month_df, ts_col, slug, month),
        "traced_product":   make_traced_product_chart(k, month_df, ts_col, slug, month),
        "conductivity":     make_conductivity_chart(k, month_df, ts_col, slug, month),
    }

    print(f"  Loading MU conductivity from data/MU_conductivity.xlsx …")
    mu_cond = _load_mu_conductivity(site)
    if mu_cond:
        print(f"  ✓ MU conductivity for this site: {mu_cond} µS/cm")
    else:
        print(f"  – No MU conductivity available for this site")
    coc = compute_coc(k, mu_cond)
    if coc["mu_available"]:
        print(f"  COC — Target: {coc['target_coc']}  |  Actual: {coc['actual_coc']}  "
              f"|  Deviation: {coc['deviation_pct']}%  →  {coc['coc_status']}")

    print("\nStep 3/4 — Assembling Word document …")
    water_efficiency_inputs = _load_water_efficiency_inputs(site, controllers)
    water_loss = compute_water_loss(coc, water_efficiency_inputs)
    if water_loss.get("triggered"):
        print(f"  Water loss — Annual: {water_loss['water_savings_per_annum']:,.0f} gal/year  "
              f"|  Cost: ${water_loss['water_savings_cost']:,.2f}/year")
    elif water_loss.get("available"):
        print(f"  Water loss — {water_loss.get('reason')}")
    else:
        print(f"  Water loss — {water_loss.get('reason')}")

    doc = build_docx(site, month, controllers, k, narr, charts, month_df, coc, water_loss)
    out = save_report_document(doc, slug)
    _fix(out)

    print(f"\n✅  Report ready → {out}")
    print(f"    Charts from full parquet: {len(month_df):,} rows for {month}\n")

    print("Step 4/4 — Running report checklist scorecard …")
    from score_report import score_generated_report
    scorecard, scorecard_path = score_generated_report(
        site,
        month,
        controller_ids=controller_ids,
        verbose=False,
        show_ai_guidance=False,
    )
    print(f"  Checklist score: {scorecard['percentage']}%  →  Grade {scorecard['grade']}")
    print(f"  Scorecard ready → {scorecard_path}\n")


if __name__ == "__main__":
    main()