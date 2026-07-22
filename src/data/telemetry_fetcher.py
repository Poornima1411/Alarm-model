"""
src/data/telemetry_fetcher.py
──────────────────────────────
Fetches telemetry from the Buckman ACM API.
Uses env vars: BUCKMAN_TOKEN (user bearer token), OBS_API_BASE
"""

import io
import json
import os
from datetime import datetime, timedelta
from typing import List, Optional

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.environ.get("OBS_API_BASE",
    "https://budig-bb-bbapiappa-01-p.azurewebsites.net/api/v1")

# PBA service account — used for telemetry export (same creds as original script)
_PBA_USERNAME = "PBAckconnector@buckman.com"
_PBA_PASSWORD = '4-*fvbsHu-6A"11oILa6'

TELEMETRY_TAGS: List[str] = [
    "envision_fluorometer_cellfouling",
    "envision_sensor_board_corrosion_probe_1",
    "envision_sensor_board_corrosion_probe_2",
    "envision_sensor_board_electrode_conductivity",
    "envision_fluorometer_fluorometer_ch_1",
    "envision_sensor_board_orp",
    "envision_sensor_board_rtd_toroidal",
    "envision_fluorometer_turbidity",
    "envision_sensor_board_analog_in_1",
    "envision_sensor_board_ph_probe",
    "envision_relay_board_contactor",
    "envision_relay_board_relay8",
    "envision_relay_board_relay1",
    "envision_relay_board_relay4",
    "envision_relay_board_relay5",
    "envision_relay_board_relay3",
    "flow_switch",
    "interlock",
    "envision_relay_board_relay6",
    "envision_relay_board_relay7",
    "envision_relay_board_relay2",
    "envision_fluorometer_fluorometer_ch_2",
    "envision_sensor_board_counter_1",
    "envision_sensor_board_counter_2",
    "envision_sensor_board_rtd_corrosion",
    "envision_sensor_board_analog_op_1",
    "envision_sensor_board_analog_op_2",
    "envision_sensor_board_toroidal_conductivity",
    "envision_sensor_board_digital_in_1",
    "envision_sensor_board_digital_in_2",
    "envision_fluorometer_ch1_customratio",
    "envision_fluorometer_ch2_customratio",
    "envision_fluorometer_ch1_backgroundvalue",
    "envision_fluorometer_ch2_backgroundvalue",
    "oxisure_free_halogen",
    "oxisure_temp",
    "envision_sensor_board_analog_in_2",
    "envision_sensor_board_analog_in_3",
    "envision_sensor_board_analog_in_4",
    "fExtWaterTemperature",
    "envision_sensor_board_rtd",
    "totalizer",
]


def get_bearer_token() -> Optional[str]:
    """Login with PBA service account and return bearer token."""
    url = f"{BASE_URL}/Login"
    resp = requests.post(
        url,
        headers={"Content-Type": "application/json-patch+json", "Accept": "*/*"},
        json={"username": _PBA_USERNAME, "password": _PBA_PASSWORD},
        timeout=30,
    )
    try:
        resp.raise_for_status()
        return resp.json().get("accessToken")
    except Exception as e:
        print(f"[telemetry] PBA login failed: {e}")
        # Fall back to user token from .env
        return os.environ.get("BUCKMAN_TOKEN") or None


def fetch_telemetry(controller_ids: List[str], days: int = 90) -> Optional[pd.DataFrame]:
    """Fetch telemetry for given controller serial numbers."""
    end_dt   = datetime.utcnow()
    start_dt = end_dt - timedelta(days=days)

    payload = {
        "Tags": TELEMETRY_TAGS,
        "StartAt":   start_dt.strftime("%Y-%m-%dT%H:%M:%S"),
        "EndBefore": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    token = get_bearer_token()
    if not token:
        print("[telemetry] No token available — skipping telemetry fetch.")
        return None

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    url_tpl = f"{BASE_URL}/TelemetryData/getUserUnitByDeviceTagsExport/{{}}"

    frames = []
    for ctrl in controller_ids:
        print(f"  [telemetry] Fetching {ctrl} …")
        try:
            resp = requests.post(url_tpl.format(ctrl), headers=headers,
                                 json=payload, timeout=120)
            if resp.status_code == 200:
                df = pd.read_csv(io.StringIO(resp.content.decode("utf-8-sig")))
                df.insert(0, "Controller ID", ctrl)
                frames.append(df)
            else:
                print(f"  [telemetry] {ctrl} → HTTP {resp.status_code}")
        except Exception as e:
            print(f"  [telemetry] Error for {ctrl}: {e}")

    return pd.concat(frames, ignore_index=True) if frames else None
