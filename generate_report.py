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
import argparse, json, re, sys, zipfile
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

ROOT       = Path(__file__).parent
DATA_STORE = ROOT / "data_store"
OUTPUT_DIR = ROOT / "output"
CHARTS_DIR = OUTPUT_DIR / "charts"
OUTPUT_DIR.mkdir(exist_ok=True)
CHARTS_DIR.mkdir(exist_ok=True)

GREEN = RGBColor(0x00,0x85,0x7C); WHITE = RGBColor(0xFF,0xFF,0xFF)
AMBER = RGBColor(0xB8,0x86,0x0B); RED   = RGBColor(0xC0,0x00,0x00)
GREY  = RGBColor(0x44,0x44,0x44)
GH="#00857C"; BH="#0077BB"; RH="#C00000"; YH="#E07000"


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════════════════════

def slugify(t): return re.sub(r"[^a-z0-9]+","_",t.lower()).strip("_")


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


def load_all(site, month):
    slug  = slugify(f"{site}_{month}")
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

    return narr, controllers, scc, ade, month_df, ts_col, slug


def compute_kpis(scc, ade, month_df, ts_col):
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
    ph_col   = find_col("ph_probe") or find_col("ph")
    orp_col  = find_col("orp")
    turb_col = find_col("turbidity")
    cf_col   = find_col("cellfouling") or find_col("cell_fouling")
    rel_col  = find_col("relay3") or find_col("relay5") or find_col("relay1")

    k["ms_col"] = ms_col; k["cu_col"] = cu_col; k["ec_col"] = ec_col
    k["tp_col"] = tp_col; k["orp_col"] = orp_col; k["rel_col"] = rel_col
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
    k["tp_mean"] = smean(tp_col); k["turb_mean"] = smean(turb_col)
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

    def status(p):
        if p is None: return "Stable"
        return "Good" if p>75 else ("Stable" if p>=25 else "Action Required")

    corr_ok = (k["ms_mean"] and k["ms_mean"]<3.0) and (k["cu_mean"] and k["cu_mean"]<0.5)
    k["corr_status"] = "Good" if corr_ok else "Action Required"
    k["tp_status"]   = status(k["tp_pct"])
    k["ec_status"]   = status(k["ec_pct"])

    if k["tp_mean"] and k["tp_ul"] and k["tp_ll"]:
        k["tp_dir"] = "HIGH" if k["tp_mean"]>k["tp_ul"] else ("LOW" if k["tp_mean"]<k["tp_ll"] else "OK")
    else: k["tp_dir"] = "UNKNOWN"

    frc_rows = [r for r in ade if any(w in str(r.get("Parameter","")).lower()
                for w in ("free residual","frc","halogen"))]
    k["frc"] = float(frc_rows[0]["Value"]) if frc_rows else None
    k["micro_status"] = "Good" if k["frc"] and k["frc"]>=0.2 else "Stable"
    k["relay_firing"] = rel_col is not None and series(rel_col).mean() > 0.01

    return k


def compute_coc(k, mu_cond):
    """
    Compute COC and status based on MU conductivity.

    Target COC = SCC conductivity setpoint / MU conductivity
    Actual COC = monthly average conductivity / MU conductivity
    Deviation %  = abs(Actual - Target) / Target * 100

    Status thresholds (based on % deviation from target):
      Good      : deviation <= 20%
      Okay      : 20% < deviation <= 50%
      Bad       : deviation > 50%
    """
    if mu_cond is None or mu_cond == 0:
        return {
            "mu_available": False, "mu_cond": None,
            "target_coc": None, "actual_coc": None,
            "deviation_pct": None, "coc_status": None,
        }

    target_coc = (k["ec_sp"] / mu_cond) if k["ec_sp"] else None
    actual_coc = (k["ec_mean"] / mu_cond) if k["ec_mean"] else None

    if target_coc and actual_coc:
        dev = abs(actual_coc - target_coc) / target_coc * 100
        if   dev <= 20: coc_status = "Good"
        elif dev <= 50: coc_status = "Okay"
        else:           coc_status = "Bad"
    else:
        dev, coc_status = None, None

    return {
        "mu_available": True, "mu_cond": round(mu_cond, 2),
        "target_coc": round(target_coc, 2) if target_coc else None,
        "actual_coc": round(actual_coc, 2) if actual_coc else None,
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
    # Remove patterns like "Status: Good." or "Status: Action Required." at the start
    return re.sub(r"^\s*Status:\s*(Good|Stable|Action Required)[.,:]\s*",
                  "", text, flags=re.IGNORECASE).strip()


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
    c = GREEN if s=="Good" else (AMBER if s=="Stable" else RED)
    p = doc.add_paragraph()
    p.paragraph_format.space_before=Pt(3); p.paragraph_format.space_after=Pt(5)
    r1=p.add_run("Status: "); r1.font.size=Pt(10); r1.font.bold=True
    r2=p.add_run(s);         r2.font.size=Pt(10); r2.font.bold=True; r2.font.color.rgb=c


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
    p=doc.add_paragraph()
    p.paragraph_format.space_before=Pt(2); p.paragraph_format.space_after=Pt(10)
    r=p.add_run(f"Comment: {text}")
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


def build_docx(site, month, controllers, k, narr, charts, month_df, coc):
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

    ctrl_id = controllers[0].get("SerialNumber","N/A") if controllers else "N/A"
    today   = datetime.now().strftime("%d %B %Y")
    prod    = k["product_name"]

    def fmt(v, d=2):
        try: return f"{float(v):.{d}f}" if v not in (None,"NULL","") else "N/A"
        except: return "N/A"
    def si(s): return "✓" if s=="Good" else ("⚠" if s=="Stable" else "✗")

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
    add_para(doc, _strip_status(narr.get("corrosion_narrative","")))

    # ── Scale Control ─────────────────────────────────────────────────────────
    add_h3(doc,"Scale Control")
    add_status(doc, k["tp_status"])
    add_para(doc, _strip_status(narr.get("scale_narrative","")))

    # ── Microbial Control ─────────────────────────────────────────────────────
    add_h3(doc,"Microbial Control")
    add_status(doc, k["micro_status"])
    add_para(doc, _strip_status(narr.get("microbial_narrative","")))

    # ── Water Efficiency ──────────────────────────────────────────────────────
    add_h2(doc,"Water Efficiency")

    if coc["mu_available"]:
        cs = coc["coc_status"] or "N/A"
        add_status(doc, cs if cs != "Okay" else "Stable")

        add_table(doc,
            ["MU Conductivity","Target COC","Actual COC","Deviation","Status"],
            [[f"{coc['mu_cond']} µS/cm",
              f"{coc['target_coc']}" if coc['target_coc'] else "N/A",
              f"{coc['actual_coc']}" if coc['actual_coc'] else "N/A",
              f"{coc['deviation_pct']}%" if coc['deviation_pct'] is not None else "N/A",
              cs]],
            [3.4, 3.4, 3.4, 3.4, 3.4])
        add_para(doc, _strip_status(narr.get("water_efficiency_narrative","")))
    else:
        add_para(doc,
            "Makeup water conductivity is not available for this site. "
            "Actual cycles of concentration cannot be calculated. "
            "Makeup conductivity should be captured at the next service visit.",
            size=10)
        add_para(doc, _strip_status(narr.get("water_efficiency_narrative","")))

    # ── Product Efficiency ────────────────────────────────────────────────────
    add_h2(doc,"Product Efficiency")
    add_para(doc, _strip_status(narr.get("product_efficiency_narrative","")))

    # ── Proactive System Support ──────────────────────────────────────────────
    add_h2(doc,"Proactive System Support")
    add_para(doc, _strip_status(narr.get("proactive_support_narrative","")))
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
    add_comment(doc, narr.get("corrosion_chart_comment",""))

    # Chart 2: Traced Product
    add_h2(doc,f"{prod} Control Trend")
    add_img(doc, charts["traced_product"],
            caption=f"{prod} — {month}", fig_num=2)
    add_comment(doc, narr.get("scale_chart_comment",""))

    # Chart 3: ORP vs Copper Corrosion
    add_h2(doc,"ORP vs Copper Corrosion Rate")
    add_img(doc, charts["orp_corrosion"],
            caption=f"ORP vs Copper Corrosion Rate — {month}", fig_num=3)
    add_comment(doc, narr.get("orp_chart_comment",""))

    # Chart 4: Biocide Relay vs Copper Corrosion
    add_h2(doc,"Oxidizing Biocide Pump Relay vs Copper Corrosion")
    add_img(doc, charts["biocide_corrosion"],
            caption=f"Oxidizing Biocide Pump Relay vs Copper Corrosion — {month}", fig_num=4)

    # Chart 5: Conductivity
    add_h2(doc,"Electrode Conductivity")
    add_img(doc, charts["conductivity"],
            caption=f"Electrode Conductivity — {month}", fig_num=5)
    add_comment(doc, narr.get("conductivity_chart_comment",""))

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
         f"✓ {k['corr_status']}"],
        ["Corrosion – Cu (MPY)", "ACM Skid",
         *col_stats(k["cu_col"]), "0.00", "0.50",
         pct_str(k["cu_col"], 0, 0.5),
         f"{'✓' if k['corr_status']=='Good' else '✗'} {k['corr_status']}"],
        [f"{prod} (ppm)", "ACM Skid",
         *col_stats(k["tp_col"]),
         fmt(k["tp_ll"],1), fmt(k["tp_ul"],1),
         f"{k['tp_pct']}%" if k['tp_pct'] is not None else "–",
         f"{'✓' if k['tp_status']=='Good' else '⚠'} {k['tp_status']}"],
        ["Conductivity (µS/cm)", "ACM Skid",
         *col_stats(k["ec_col"]),
         fmt(k["ec_ll"],0), fmt(k["ec_ul"],0),
         f"{k['ec_pct']}%" if k['ec_pct'] is not None else "–",
         f"{'✓' if k['ec_status']=='Good' else '⚠'} {k['ec_status']}"],
        ["pH", "ACM Skid",
         *ph_stats, ph_ll, ph_ul, ph_pct, "ℹ Info"],
        ["ORP (mV)", "ACM Skid",
         *orp_stats, "–", "–", "–", "See chart"],
        ["Turbidity (NTU)", "ACM Skid",
         *turb_stats, "–", "75.0", "–", "ℹ Info"],
        ["Cell Fouling (%)", "ACM Skid",
         *cf_stats, "–", "30.0", "–", "ℹ Info"],
        ["FRC", "Field Data",
         fmt(k["frc"]) if k["frc"] else "Not avail.",
         "–", "–", "–", "–", "–", "–",
         "⚠ Check" if not k["frc"] else "✓"],
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


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--site",  required=True)
    p.add_argument("--month", required=True)
    args = p.parse_args()
    site = args.site; month = args.month

    print(f"\n{'='*60}")
    print(f"  Report Generator  —  {site}  |  {month}")
    print(f"{'='*60}\n")

    print("Step 1/4 — Loading narrative cache and parquet telemetry …")
    narr, controllers, scc, ade, month_df, ts_col, slug = load_all(site, month)
    k = compute_kpis(scc, ade, month_df, ts_col)

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
        "biocide_corrosion":make_biocide_corrosion_chart(k, month_df, ts_col, slug, month),
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
    doc = build_docx(site, month, controllers, k, narr, charts, month_df, coc)
    out = OUTPUT_DIR / f"{slug}_report.docx"
    doc.save(str(out)); _fix(out)

    print(f"\n✅  Report ready → {out}")
    print(f"    Charts from full parquet: {len(month_df):,} rows for {month}\n")


if __name__ == "__main__":
    main()