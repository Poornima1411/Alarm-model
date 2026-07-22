"""
src/data/scc_fetcher.py
────────────────────────
Fetches SCC (System Control Configuration) data from Azure Cosmos DB
for all controllers at a given site.

The SCC contains the actual programmed setpoints for each controller:
  - SP  : Control setpoint  (e.g. ORP target = 3.0 ppm, Conductivity target = 1250 µS/cm)
  - DB  : Dead band
  - HH  : High-High alarm limit
  - LL  : Low-Low alarm limit
  - H   : High alarm limit
  - L   : Low alarm limit
  - Product Name : what chemical is being dosed by each relay
  - CustomRatio  : fluorometer calibration ratio (converts reading → ppm)
  - BackgroundValue : fluorometer baseline

These are the SITE-SPECIFIC limits — much more useful for report analysis
than the generic Buckman standard limits.

Uses env vars: COSMOS_URL, COSMOS_KEY, COSMOS_DB_NAME
"""

import os
import logging
from typing import Optional, List, Dict, Any

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

COSMOS_URL       = os.environ.get("COSMOS_URL", "")
COSMOS_KEY       = os.environ.get("COSMOS_KEY", "")
COSMOS_DB_NAME   = os.environ.get("COSMOS_DB_NAME", "budig-bb-cosmosdbsql-01-p")
COSMOS_CONTAINER = os.environ.get("COSMOS_CONTAINER", "mixed")

# typeId → human-readable control type
TYPEID_TO_CONTROL_TYPE: Dict[int, str] = {
    1: "On Off Control", 2: "Manual", 3: "Fail Safe",
    4: "Flow Switch", 5: "Interlock", 6: "EStop",
    7: "Timer Control", 8: "Low Flow", 9: "Service Mode",
    10: "Override", 11: "On Off Control", 12: "On Off Control",
    13: "On Off Control", 27: "On Off Control",
}

# The columns we care about for the report
REPORT_COLUMNS = [
    "ControllerId", "Site Name",
    "Input Sensor",                  # e.g. envision_sensor_board_orp
    "Control Type",                  # On Off Control / Timer Control
    "Exact Relay",                   # relay3, relay5 etc.
    "Product Name",                  # BUSAN 1735, IMPACKT 547M etc.
    "SP",                            # setpoint
    "DB",                            # dead band
    "HH",                            # high-high alarm
    "LL",                            # low-low alarm
    "H",                             # high alarm
    "L",                             # low alarm
    "Relay Timeout (min)",
    "CustomRatio",
    "BackgroundValue",
]


# ── Friendly sensor name map (tag → readable name) ────────────────────────────
SENSOR_FRIENDLY = {
    "envision_sensor_board_electrode_conductivity": "Electrode Conductivity",
    "envision_sensor_board_toroidal_conductivity":  "Toroidal Conductivity",
    "envision_sensor_board_orp":                    "ORP",
    "envision_sensor_board_ph_probe":               "pH",
    "envision_sensor_board_corrosion_probe_1":      "Corrosion Probe 1 (MS)",
    "envision_sensor_board_corrosion_probe_2":      "Corrosion Probe 2 (Cu)",
    "envision_fluorometer_fluorometer_ch_1":        "Fluorometer Ch1 (Traced Product)",
    "envision_fluorometer_fluorometer_ch_2":        "Fluorometer Ch2 (Tagged Polymer)",
    "envision_fluorometer_cellfouling":             "Cell Fouling",
    "envision_fluorometer_turbidity":               "Turbidity",
    "envision_sensor_board_analog_in_1":            "Analog In 1 (Flow)",
    "envision_sensor_board_analog_in_2":            "Analog In 2",
    "envision_sensor_board_analog_in_3":            "Analog In 3",
    "envision_sensor_board_analog_in_4":            "Analog In 4",
    "oxisure_free_halogen":                         "Free Halogen (OxiSure)",
}


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_scc_for_site(
    controllers_df: pd.DataFrame,
) -> Optional[pd.DataFrame]:
    """
    Fetch SCC from Cosmos for all controllers at a site.

    Parameters
    ----------
    controllers_df : pd.DataFrame
        Output of sql_fetcher.fetch_site_controllers().
        Must have columns: SerialNumber, DeviceId, SiteName.

    Returns
    -------
    pd.DataFrame with SCC rows, or None on failure.
    """
    if not COSMOS_URL or not COSMOS_KEY:
        log.warning("COSMOS_URL / COSMOS_KEY not set — SCC fetch skipped.")
        return None

    try:
        from azure.cosmos import CosmosClient
        from azure.cosmos.exceptions import CosmosResourceNotFoundError
    except ImportError:
        log.error("azure-cosmos not installed. Run: pip install azure-cosmos")
        return None

    container = (
        CosmosClient(COSMOS_URL, credential=COSMOS_KEY)
        .get_database_client(COSMOS_DB_NAME)
        .get_container_client(COSMOS_CONTAINER)
    )

    all_rows = []
    for _, row in controllers_df.iterrows():
        serial      = str(row["SerialNumber"]).strip()
        internal_id = str(row["DeviceId"]).strip()
        site        = str(row["SiteName"]).strip()

        rows = _fetch_one(container, internal_id, serial, site)
        if rows:
            all_rows.extend(rows)
            log.info(f"  ✓ {serial} — {len(rows)} SCC rows")
        else:
            log.warning(f"  ✗ {serial} — no SCC data found")

    if not all_rows:
        return None

    df = pd.DataFrame(all_rows)
    # Add friendly sensor name column
    df["Sensor Name"] = df["Input Sensor"].map(SENSOR_FRIENDLY).fillna(df["Input Sensor"])
    return df


# ── Cosmos fetch for one controller ──────────────────────────────────────────

def _fetch_one(
    container,
    internal_device_id: str,
    controller_serial: str,
    site_name: str,
) -> Optional[List[Dict[str, Any]]]:
    """Fetch and parse one controller's SCC document from Cosmos."""
    doc_id = f"{internal_device_id}-config"

    # Get partition key
    try:
        results = list(container.query_items(
            query="SELECT c._partitionKey FROM c WHERE c.id = @id",
            parameters=[{"name": "@id", "value": doc_id}],
            enable_cross_partition_query=True,
        ))
        if not results:
            return None
        pk = results[0].get("_partitionKey", "")
    except Exception as e:
        log.error(f"Cosmos partition-key query failed ({doc_id}): {e}")
        return None

    # Read document
    try:
        from azure.cosmos.exceptions import CosmosResourceNotFoundError
        doc = container.read_item(item=doc_id, partition_key=pk)
    except Exception as e:
        log.error(f"Cosmos read failed ({doc_id}): {e}")
        return None

    return _parse_doc(doc, controller_serial, site_name)


def _parse_doc(
    doc: dict,
    controller_serial: str,
    site_name: str,
) -> List[Dict[str, Any]]:
    """
    Parse a Cosmos SCC document into a flat list of rows.
    Each row = one (input sensor, output relay) control pair.
    """
    controls = doc.get("controls") or []
    alarms   = doc.get("alarms")   or {}
    outputs  = doc.get("outputs")  or {}
    config   = doc.get("configuration") or {}

    # Build alarm limit map: input_tag → {4: HH_alarm, 5: H, 6: L, 7: LL}
    hh_ll_map: Dict[str, Dict[int, Any]] = {}
    for inp_tag, alarm_list in alarms.items():
        if isinstance(alarm_list, list):
            for alm in alarm_list:
                atype = alm.get("alarmType") or alm.get("type")
                hh_ll_map.setdefault(inp_tag, {})[atype] = alm
        elif isinstance(alarm_list, dict):
            hh_ll_map[inp_tag] = alarm_list

    # Build timeout map: output_tag → alarm dict
    timeout_map: Dict[str, Any] = {}
    for out_tag, alm in (alarms.get("outputs") or {}).items():
        timeout_map[out_tag] = alm

    # Fluorometer custom ratio / background
    custom_ratio_map: Dict[str, float] = {}
    bg_value_map:     Dict[str, float] = {}
    for ch in ["fluorometer_ch1", "fluorometer_ch2",
               "fluorometer_ch_1", "fluorometer_ch_2"]:
        cfg_ch = config.get(ch) or {}
        related = cfg_ch.get("relatedTag") or ch
        cr = cfg_ch.get("customRatio")   or cfg_ch.get("custom_ratio")
        bv = cfg_ch.get("backgroundValue") or cfg_ch.get("background_value")
        if cr is not None:
            custom_ratio_map[related] = cr
        if bv is not None:
            bg_value_map[related] = bv

    rows = []
    for ctrl in controls:
        inp  = (ctrl.get("input")  or "").strip()
        outp = (ctrl.get("output") or "").strip()
        if not inp:
            continue

        type_id      = ctrl.get("typeId")
        control_type = TYPEID_TO_CONTROL_TYPE.get(type_id, "") if type_id else ""
        exact_relay  = _strip_relay_prefix(outp)

        sp_raw = (ctrl.get("setPoint") or {}).get("value")
        db_raw = (ctrl.get("deadBand") or {}).get("value")
        sp_val = _scale(sp_raw, inp)
        db_val = _scale(db_raw, inp)

        alm      = hh_ll_map.get(inp, {})
        hh_alarm = alm.get(4)
        h_alarm  = alm.get(5)
        l_alarm  = alm.get(6)
        ll_alarm = alm.get(7)

        to_alarm      = timeout_map.get(outp)
        relay_timeout = None
        if to_alarm:
            relay_timeout = _timeout_min(
                (to_alarm.get("onMonitor") or {}).get("value")
            )

        product_name = (outputs.get(outp) or {}).get("productFriendlyName")
        custom_ratio = custom_ratio_map.get(inp)
        bg_value     = bg_value_map.get(inp)

        rows.append({
            "ControllerId":        controller_serial,
            "Site Name":           site_name,
            "Input Sensor":        inp,
            "Control Type":        control_type,
            "Exact Relay":         exact_relay,
            "Relay":               outp,
            "Product Name":        product_name,
            "SP":                  sp_val,
            "DB":                  db_val,
            "HH":                  _fmt(_sp_val(hh_alarm), inp),
            "LL":                  _fmt(_sp_val(ll_alarm), inp),
            "H":                   _fmt(_sp_val(h_alarm),  inp),
            "L":                   _fmt(_sp_val(l_alarm),  inp),
            "Relay Timeout (min)": relay_timeout,
            "CustomRatio":         custom_ratio,
            "BackgroundValue":     bg_value,
            "_source":             "cosmos",
        })

    return rows


# ── Scaling helpers (mirrors cosmos_scc.py logic) ─────────────────────────────

def _sp_val(alarm_dict) -> Optional[float]:
    if not alarm_dict:
        return None
    sp = alarm_dict.get("setPoint") or alarm_dict.get("sp")
    if isinstance(sp, dict):
        return sp.get("value")
    return sp


def _scale(v, tag: str = "") -> Optional[float]:
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None

    tag = tag.lower()

    if "orp" in tag:
        result = v * 10000 if v < 1.0 else v
        return 0.0 if result < -50 else result

    if "conductivity" in tag:
        return round(v * 10000, 4) if v < 10 else round(v, 4)

    if "fluorometer" in tag:
        return round(v * 10000, 6) if v < 1 else round(v, 6)

    if "corrosion" in tag:
        if v > 100:
            return round(v / 10000, 4)
        elif v < 1.0:
            return round(v * 10000, 4)
        return round(v, 4)

    if "turbidity" in tag or "cellfouling" in tag:
        return round(v / 10000, 4) if v > 1000 else round(v, 4)

    return round(v * 10000, 6) if v < 1.0 else round(v, 6)


def _fmt(v, tag: str = "") -> str:
    scaled = _scale(v, tag)
    return str(scaled) if scaled is not None else "NULL"


def _strip_relay_prefix(tag: str) -> str:
    tl = tag.lower()
    if tl.startswith("envision_relay_board_"):
        return tag[len("envision_relay_board_"):]
    if tl.startswith("relay_"):
        return tag[len("relay_"):]
    return tag


def _timeout_min(v) -> Optional[float]:
    """Cosmos stores timeout in seconds → convert to minutes."""
    return round(v / 60, 2) if v is not None else None
