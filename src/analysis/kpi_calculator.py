"""
src/analysis/kpi_calculator.py
-------------------------------
Compute per-controller and site-level KPIs from raw telemetry.

Outputs a structured dict consumed by the report generator:

{
  "site_name": str,
  "reporting_month": str,          # "May 2026"
  "controllers": [
    {
      "controller_id": str,
      "ms_corrosion_avg": float,   # MPY
      "cu_corrosion_avg": float,   # MPY
      "conductivity_avg": float,   # µS/cm
      "ph_avg": float,
      "orp_spike_detected": bool,
      "traced_product_avg": float, # ppm
      "traced_product_pct_in_range": float,  # 0-100
      "cell_fouling_avg": float,   # %
      "coc_actual": float,
      "raw_df": pd.DataFrame,      # filtered telemetry for this controller
    }
  ],
  "service_notes": list[dict],     # parsed plain-text notes
  "ade_frc": float | None,         # Free Residual Chlorine from MDE data
}
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import pandas as pd


# ── Column name helpers ───────────────────────────────────────────────────────
# Telemetry column names vary slightly by site; we match by substring.

def _find_col(df: pd.DataFrame, *substrings: str) -> Optional[str]:
    """Return the first column whose name contains all given substrings (case-insensitive)."""
    for col in df.columns:
        cl = col.lower()
        if all(s.lower() in cl for s in substrings):
            return col
    return None


def _numeric(df: pd.DataFrame, col: Optional[str]) -> pd.Series:
    if col is None or col not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[col], errors="coerce").dropna()


# ── Per-controller KPIs ───────────────────────────────────────────────────────

def compute_controller_kpis(
    controller_id: str,
    df: pd.DataFrame,
    makeup_conductivity: Optional[float] = None,
    traced_product_ll: float = 60.0,
    traced_product_ul: float = 130.0,
) -> Dict[str, Any]:
    """
    Compute KPIs for a single controller's telemetry slice.

    Parameters
    ----------
    controller_id : str
    df : pd.DataFrame
        Telemetry rows for this controller only.
    makeup_conductivity : float | None
        Makeup water conductivity (µS/cm) used to compute COC.
        If None, COC is not calculated.
    traced_product_ll / ul : float
        Lower / upper control limit for traced product (ppm).
    """
    kpi: Dict[str, Any] = {"controller_id": controller_id, "raw_df": df}

    # Corrosion
    ms_col = _find_col(df, "corrosion_probe_1") or _find_col(df, "corrosion", "ms") or _find_col(df, "corrosion 1")
    cu_col = _find_col(df, "corrosion_probe_2") or _find_col(df, "corrosion", "cu") or _find_col(df, "corrosion 2")

    kpi["ms_corrosion_avg"] = round(_numeric(df, ms_col).mean(), 3) if ms_col else None
    kpi["cu_corrosion_avg"] = round(_numeric(df, cu_col).mean(), 3) if cu_col else None

    # Conductivity
    ec_col = _find_col(df, "electrode_conductivity") or _find_col(df, "electrode conductivity")
    ec_series = _numeric(df, ec_col)
    kpi["conductivity_avg"] = round(ec_series.mean(), 1) if not ec_series.empty else None

    # COC
    if makeup_conductivity and not ec_series.empty:
        kpi["coc_actual"] = round(ec_series.mean() / makeup_conductivity, 2)
    else:
        kpi["coc_actual"] = None

    # pH
    ph_col = _find_col(df, "ph_probe") or _find_col(df, "ph")
    kpi["ph_avg"] = round(_numeric(df, ph_col).mean(), 2) if ph_col else None

    # ORP — detect spikes (spike = reading > 200 mV above median)
    orp_col = _find_col(df, "orp")
    orp_series = _numeric(df, orp_col)
    if not orp_series.empty:
        median_orp = orp_series.median()
        kpi["orp_spike_detected"] = bool((orp_series > median_orp + 200).any())
    else:
        kpi["orp_spike_detected"] = None

    # Traced product
    trace_col = (
        _find_col(df, "fluorometer_ch_1")
        or _find_col(df, "traced product")
        or _find_col(df, "fluorometer", "ch1")
    )
    trace_series = _numeric(df, trace_col)
    if not trace_series.empty:
        kpi["traced_product_avg"] = round(trace_series.mean(), 1)
        in_range = trace_series[(trace_series >= traced_product_ll) & (trace_series <= traced_product_ul)]
        kpi["traced_product_pct_in_range"] = round(len(in_range) / len(trace_series) * 100, 1)
    else:
        kpi["traced_product_avg"] = None
        kpi["traced_product_pct_in_range"] = None

    # Cell fouling
    cf_col = _find_col(df, "cellfouling") or _find_col(df, "cell fouling")
    cf_series = _numeric(df, cf_col)
    kpi["cell_fouling_avg"] = round(cf_series.mean(), 1) if not cf_series.empty else None

    return kpi


# ── Site-level aggregation ────────────────────────────────────────────────────

def compute_site_kpis(
    site_name: str,
    reporting_month: str,
    telemetry_df: pd.DataFrame,
    service_notes_df: pd.DataFrame,
    ade_df: pd.DataFrame,
    controller_meta: pd.DataFrame,
    makeup_conductivity: Optional[float] = None,
    traced_product_ll: float = 60.0,
    traced_product_ul: float = 130.0,
) -> Dict[str, Any]:
    """
    Build the full KPI payload consumed by the report generator.

    Parameters
    ----------
    site_name : str
    reporting_month : str  e.g. "May 2026"
    telemetry_df : pd.DataFrame  — combined telemetry with 'Controller ID' column
    service_notes_df : pd.DataFrame  — from sql_fetcher.fetch_service_notes
    ade_df : pd.DataFrame  — from sql_fetcher.fetch_ade_data
    controller_meta : pd.DataFrame  — from sql_fetcher.fetch_site_controllers
    makeup_conductivity : float | None
    traced_product_ll / ul : float
    """
    controllers_kpis: List[Dict[str, Any]] = []

    for ctrl_id in telemetry_df["Controller ID"].unique():
        ctrl_df = telemetry_df[telemetry_df["Controller ID"] == ctrl_id].copy()
        kpi = compute_controller_kpis(
            controller_id=ctrl_id,
            df=ctrl_df,
            makeup_conductivity=makeup_conductivity,
            traced_product_ll=traced_product_ll,
            traced_product_ul=traced_product_ul,
        )
        # Enrich with metadata
        meta_row = controller_meta[controller_meta["SerialNumber"] == ctrl_id]
        if not meta_row.empty:
            kpi["system_name"] = meta_row.iloc[0].get("SystemName", "")
            kpi["plant_system_name"] = meta_row.iloc[0].get("PlantSystemName", "")
        controllers_kpis.append(kpi)

    # FRC from ADE data — look for 'Free Residual Chlorine' or 'FRC' parameter
    frc_rows = ade_df[
        ade_df["Parameter"].str.contains("frc|free residual|halogen", case=False, na=False)
    ]
    ade_frc = round(frc_rows["Value"].astype(float).mean(), 2) if not frc_rows.empty else None

    # Parse service notes → plain text list
    notes = service_notes_df[["ContextPoint", "CreatedDate", "ServiceNotePlain", "Status"]].to_dict("records")

    return {
        "site_name": site_name,
        "reporting_month": reporting_month,
        "controllers": controllers_kpis,
        "service_notes": notes,
        "ade_frc": ade_frc,
    }
