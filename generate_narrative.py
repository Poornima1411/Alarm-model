"""
generate_narrative.py
─────────────────────
Calls the Claude API to generate the report narrative and saves it
directly to data_store/<slug>/narrative_cache.json.

This replaces the Copilot Chat step entirely — no file writing issues,
no copy-paste, works every time.

USAGE
─────
    python generate_narrative.py --site "Synthomer Chester SC (US)" --month "May 2026"

REQUIRES
────────
    ANTHROPIC_API_KEY=sk-ant-... in your .env file
    pip install anthropic python-dotenv

WORKFLOW
────────
    1. python prefetch_site.py       --site "..." --month "..."
    2. python generate_narrative.py  --site "..." --month "..."   ← this script
    3. python generate_report.py     --site "..." --month "..."
"""

import argparse
import json
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
import os

from src.report_status import STATUS_ACCEPTABLE, STATUS_EXCELLENT, status_from_limits, status_from_percent

from src.report_cache import build_cache_slug, find_cache_by_controller_ids, normalize_controller_ids, slugify

ROOT       = Path(__file__).parent
DATA_STORE = ROOT / "data_store"
load_dotenv(ROOT / ".env")


def parse_args():
    p = argparse.ArgumentParser()
    site_group = p.add_mutually_exclusive_group(required=True)
    site_group.add_argument("--site")
    site_group.add_argument("--controller-id", "--controller-ids", nargs="+", dest="controller_ids")
    p.add_argument("--month", required=True)
    return p.parse_args()


def fmt(v, d=2):
    try:
        return f"{float(v):.{d}f}" if v not in (None, "NULL", "") else "N/A"
    except:
        return "N/A"


# ── Load prefetch data ────────────────────────────────────────────────────────

def load_cache(site, month, controller_ids=None):
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

    if not (cache / "manifest.json").exists():
        print(f"[ERROR] No prefetch data at {cache}")
        print(f"  Run: python prefetch_site.py --site \"{site}\" --month \"{month}\"")
        sys.exit(1)

    def jload(f, d):
        p = cache / f
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else d

    scc   = jload("scc.json",          [])
    ade   = jload("ade_data.json",     [])
    notes = jload("service_notes.json",[])

    sensors = {}
    for f in (cache / "telemetry").glob("*_summary.json"):
        d = json.loads(f.read_text())
        for name, stats in d.get("sensors", {}).items():
            sensors[name.lower()] = stats

    return site, scc, ade, notes, sensors, slug, cache


# ── Extract KPIs for the prompt ───────────────────────────────────────────────

def extract_kpis(scc, ade, sensors):
    def find(*kws):
        for key, stats in sensors.items():
            if all(w in key for w in kws): return stats
        return {}

    def r20(s):  return [float(v) for v in s.get("recent_20", [])]
    def sm(s):   v = s.get("mean"); return float(v) if v is not None else None
    def sn(s):   v = s.get("min");  return float(v) if v is not None else None
    def sx(s):   v = s.get("max");  return float(v) if v is not None else None

    ms_s   = find("corrosion_probe_1")
    cu_s   = find("corrosion_probe_2")
    ec_s   = find("electrode_conductivity") or find("conductivity")
    tp_s   = find("fluorometer_ch_1") or find("fluorometer", "ch1")
    ph_s   = find("ph_probe") or find("ph")
    orp_s  = find("orp")
    turb_s = find("turbidity")
    cf_s   = find("cellfouling") or find("cell_fouling")
    rel_s  = find("relay3") or find("relay5") or find("relay1")

    k = {}
    k["ms_mean"]   = sm(ms_s);   k["cu_mean"]   = sm(cu_s)
    k["ec_mean"]   = sm(ec_s);   k["tp_mean"]   = sm(tp_s)
    k["ph_mean"]   = sm(ph_s);   k["turb_mean"] = sm(turb_s)
    k["cf_mean"]   = sm(cf_s)
    k["ms_r20"]    = r20(ms_s);  k["cu_r20"]    = r20(cu_s)
    k["ec_r20"]    = r20(ec_s);  k["tp_r20"]    = r20(tp_s)
    k["orp_r20"]   = r20(orp_s); k["relay_r20"] = r20(rel_s)

    # SCC setpoints
    def scc_row(*kws):
        for r in scc:
            s = (str(r.get("Input Sensor","")) + str(r.get("Sensor Name",""))).lower()
            if all(w in s for w in kws): return r
        return {}

    ec_r = scc_row("conductivity")
    tp_r = scc_row("fluorometer_ch_1") or scc_row("fluorometer","ch1") or scc_row("traced")

    def fv(row, key):
        v = row.get(key)
        try:    return float(v) if v not in (None,"NULL","") else None
        except: return None

    k["ec_sp"] = fv(ec_r,"SP"); k["ec_db"] = fv(ec_r,"DB")
    k["tp_sp"] = fv(tp_r,"SP"); k["tp_db"] = fv(tp_r,"DB")
    k["ec_ll"] = (k["ec_sp"] - k["ec_db"]) if k["ec_sp"] and k["ec_db"] else None
    k["ec_ul"] = (k["ec_sp"] + k["ec_db"]) if k["ec_sp"] and k["ec_db"] else None
    k["tp_ll"] = (k["tp_sp"] - k["tp_db"]) if k["tp_sp"] and k["tp_db"] else None
    k["tp_ul"] = (k["tp_sp"] + k["tp_db"]) if k["tp_sp"] and k["tp_db"] else None
    prod = tp_r.get("Product Name") or "Traced Product"
    k["product_name"] = "Traced Product" if prod in ("None","none",None) else prod

    def pct(vals, ll, ul):
        if not vals or ll is None or ul is None: return None
        return round(sum(1 for v in vals if ll <= v <= ul) / len(vals) * 100, 1)

    k["tp_pct"] = pct(k["tp_r20"], k["tp_ll"], k["tp_ul"])
    k["ec_pct"] = pct(k["ec_r20"], k["ec_ll"], k["ec_ul"])

    corr_ok = (k["ms_mean"] and k["ms_mean"] < 3.0) and (k["cu_mean"] and k["cu_mean"] < 0.5)
    k["corr_status"] = status_from_limits(bool(corr_ok))
    k["tp_status"]   = status_from_percent(k["tp_pct"])
    k["ec_status"]   = status_from_percent(k["ec_pct"])

    if k["tp_mean"] and k["tp_ul"] and k["tp_ll"]:
        k["tp_dir"] = "HIGH" if k["tp_mean"] > k["tp_ul"] else (
                      "LOW"  if k["tp_mean"] < k["tp_ll"] else "OK")
    else:
        k["tp_dir"] = "UNKNOWN"

    frc_rows = [r for r in ade if any(w in str(r.get("Parameter","")).lower()
                for w in ("free residual","frc","halogen"))]
    k["frc"] = float(frc_rows[0]["Value"]) if frc_rows else None
    k["micro_status"] = STATUS_EXCELLENT if k["frc"] and k["frc"] >= 0.2 else STATUS_ACCEPTABLE
    k["relay_firing"] = bool(k["relay_r20"] and any(v > 0 for v in k["relay_r20"]))

    return k


# ── Build prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a monthly cooling water performance report writer for Buckman Digital Water.
Write professional, customer-facing narrative content following these rules exactly:

CORROSION CONTROL:
- Use exact wording: "The average mild steel corrosion rate was X MPY against the target of within 3.0 MPY, and the average copper corrosion rate was X MPY against the target of within 0.5 MPY."

SCALE CONTROL:
- Write ONLY about Traced Product. Do NOT mention conductivity, pH, turbidity, or any other parameter.
- Status MUST reflect % in range: Excellent >75%, Acceptable 25-75%, Critical <25%.
- Use only these customer-facing status labels: Excellent, Acceptable, Critical.
- If product HIGH (above upper SCC limit): include Observation + Recommendation (check pump rate, verify fluorometer calibration, review dosing schedule).
- If product LOW (below lower SCC limit): include Observation + Recommendation (check pump prime, verify inventory, inspect feed line, verify fluorometer calibration).
- First line must state how much Traced Product was within the Controller Setpoint control range.
- If trace was higher only in the initial days and later moved closer to the control band, mention that detail. If end-of-month control is maintained well, highlight that product is now maintained well; otherwise state it is not yet consistently maintained well.
- If end-of-month trace is higher than setpoint by up to 5%, do not write the exact deviation; mention that the deviation is minimal and the control logic will be optimised. If it is higher than setpoint by more than 5%, mention the pump stroke will be reduced during the upcoming service visit.
- If product control was good initially and later decreased, use conductivity to explain the likely cause: product decreased with conductivity decreased = water loss in the system; product decreased while conductivity was maintained well = possible lack of inventory or dosing pump lost prime.
- If conductivity was below its setpoint configuration range for most of the same period, state that water loss, dilution, or blowdown/makeup behavior should be inspected during the upcoming service visit.
- If product control was good initially and later increased, state that feed control settings and fluorometer calibration should be reviewed during the upcoming service visit.

MICROBIAL CONTROL:
- Write ONLY about FRC, ORP, and dip-slide CFU analysis. Do NOT mention pH, turbidity, or cell fouling.
- FRC from ADE data only. If missing: "FRC data was not available in the MDE data for this reporting period and will be checked during the upcoming service visit."
- If dip-slide analysis is available, mention the corresponding CFU result. Interpret CFU as: <10^2 = excellent microbial control; 10^2 to <10^4 = good microbial control; 10^4 to 10^6 = needs attention; >10^6 = critical and slug dosage duration needs to be increased.
- If dip-slide analysis is not available, state that it will be measured during the upcoming service visit.
- ORP spike comment is MANDATORY. If consistent, write: "ORP spike response after biocide feed was consistent, indicating the slug dosage of biocide is successful." If not consistent, state that microbial control should continue to be reviewed during the upcoming service visit.
- NEVER write absolute ORP values.

WATER EFFICIENCY:
- Discuss conductivity and COC. State makeup not available if so.

PRODUCT EFFICIENCY:
- Use the exact product name from the data.

PROACTIVE SYSTEM SUPPORT:
- Title must be exactly "Proactive System Support". Never "Alarms".

Return ONLY valid JSON with exactly these 11 keys, no markdown, no explanation:
{
  "corrosion_narrative": "...",
  "corrosion_chart_comment": "1 sentence describing the corrosion trend",
  "scale_narrative": "...",
  "scale_chart_comment": "1 sentence describing the traced product trend chart",
  "microbial_narrative": "...",
  "orp_chart_comment": "1 sentence describing the ORP vs copper corrosion chart",
  "water_efficiency_narrative": "...",
  "conductivity_chart_comment": "1 sentence describing the conductivity trend chart",
  "product_efficiency_narrative": "...",
  "proactive_support_narrative": "...",
  "closing_summary": "2-3 sentences summarising the month"
}"""


def build_user_prompt(site, month, k, notes):
    prod = k["product_name"]
    notes_text = "No service notes were recorded for this period." if not notes else \
        "\n".join(f"Date: {str(n.get('CreatedDate',''))[:10]}\n"
                  f"{n.get('ServiceNotePlain') or n.get('ServiceNote','')}"
                  for n in notes)

    root_cause = (
        "Conductivity was stable during the same period, indicating this is a product "
        "feed or calibration issue, not a water loss or dilution event."
        if (k["ec_pct"] or 0) >= 75 else
        "Conductivity also declined during the same period, suggesting water loss, "
        "dilution, or excess blowdown as a contributing factor."
    )

    return f"""Generate report narrative for:

SITE: {site}
MONTH: {month}

CORROSION:
Mild Steel mean: {fmt(k['ms_mean'])} MPY (target: within 3.0 MPY) | Status: {k['corr_status']}
Copper mean: {fmt(k['cu_mean'], 4)} MPY (target: within 0.5 MPY)
MS recent 20: {k['ms_r20']}
Cu recent 20: {k['cu_r20']}

SCALE CONTROL ({prod}):
SCC SP: {fmt(k['tp_sp'],1)} ppm | DB: {fmt(k['tp_db'],1)} ppm | Range: {fmt(k['tp_ll'],1)}–{fmt(k['tp_ul'],1)} ppm
Monthly mean: {fmt(k['tp_mean'],1)} ppm
% of recent 20 in SCC range: {k['tp_pct']}% → Status: {k['tp_status']}
Direction: {k['tp_dir']} (HIGH=above upper limit, LOW=below lower limit, OK=in range)
Root cause context: {root_cause}
Recent 20 readings: {k['tp_r20']}

MICROBIAL:
FRC from ADE/MDE: {'Not available' if k['frc'] is None else f"{k['frc']} ppm"}
Biocide relay firing: {k['relay_firing']} | Status: {k['micro_status']}
ORP recent 20 (DO NOT report these values — spike language only): {k['orp_r20']}

WATER EFFICIENCY:
Conductivity SP: {fmt(k['ec_sp'],0)} µS/cm | Range: {fmt(k['ec_ll'],0)}–{fmt(k['ec_ul'],0)} µS/cm
Monthly mean: {fmt(k['ec_mean'],1)} µS/cm | % in range: {k['ec_pct']}% | Status: {k['ec_status']}
Makeup conductivity: Not available (COC cannot be calculated)

PRODUCT EFFICIENCY:
{prod} mean: {fmt(k['tp_mean'],1)} ppm vs SCC target {fmt(k['tp_sp'],1)} ppm ({k['tp_pct']}% in range)
Actual consumption data: Not available

SUPPORTING (Performance Summary only — do NOT include in narrative sections):
pH mean: {fmt(k['ph_mean'],2)} | Turbidity: {fmt(k['turb_mean'],2)} NTU | Cell Fouling: {fmt(k['cf_mean'],2)}%

SERVICE NOTES:
{notes_text}

Return ONLY the JSON object."""


# ── Call Claude API ───────────────────────────────────────────────────────────

def call_claude(system_prompt, user_prompt):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[ERROR] ANTHROPIC_API_KEY not set in .env")
        print("  Add this line to your .env file:")
        print("  ANTHROPIC_API_KEY=sk-ant-...")
        print("  Get your key from: https://console.anthropic.com")
        sys.exit(1)

    try:
        import anthropic
    except ImportError:
        print("[ERROR] anthropic not installed.")
        print("  Run: pip install anthropic")
        sys.exit(1)

    print("  Calling Claude API …")
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    raw = msg.content[0].text.strip()

    # Strip markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[WARNING] JSON parse error: {e}")
        print(f"  Raw response (first 400 chars): {raw[:400]}")
        # Try to extract JSON from within the response
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
        print("[ERROR] Could not parse JSON from Claude response.")
        sys.exit(1)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args  = parse_args()
    site  = args.site
    month = args.month
    controller_ids = normalize_controller_ids(args.controller_ids)

    print(f"\n{'='*60}")
    print(f"  Narrative Generator  —  Loading cache  |  {month}")
    print(f"{'='*60}\n")

    print("Step 1/3 — Loading prefetch cache …")
    site, scc, ade, notes, sensors, slug, cache = load_cache(site, month, controller_ids)
    print(f"  Site: {site}")
    k = extract_kpis(scc, ade, sensors)

    print(f"  MS: {fmt(k['ms_mean'])} MPY  |  Cu: {fmt(k['cu_mean'],4)} MPY  → {k['corr_status']}")
    print(f"  {k['product_name']}: {fmt(k['tp_mean'],1)} ppm  ({k['tp_pct']}% in range → {k['tp_status']})")
    print(f"  Conductivity: {fmt(k['ec_mean'],1)} µS/cm  ({k['ec_pct']}% in range → {k['ec_status']})")
    print(f"  FRC: {k['frc']}  |  Biocide relay firing: {k['relay_firing']}")

    print("\nStep 2/3 — Generating narrative via Claude API …")
    user_prompt = build_user_prompt(site, month, k, notes)
    narrative   = call_claude(SYSTEM_PROMPT, user_prompt)
    print("  ✓ Narrative received")

    # Validate all 11 keys present
    required = [
        "corrosion_narrative","corrosion_chart_comment",
        "scale_narrative","scale_chart_comment",
        "microbial_narrative","orp_chart_comment",
        "water_efficiency_narrative","conductivity_chart_comment",
        "product_efficiency_narrative","proactive_support_narrative",
        "closing_summary",
    ]
    missing = [k2 for k2 in required if k2 not in narrative or not narrative[k2]]
    if missing:
        print(f"  [WARNING] Missing keys: {missing}")

    print("\nStep 3/3 — Saving narrative_cache.json …")
    out_path = cache / "narrative_cache.json"
    out_path.write_text(json.dumps(narrative, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  ✓ Saved → {out_path}")

    print(f"\n✅  Narrative ready. Now run:")
    if controller_ids:
        controller_args = " ".join(f'"{controller_id}"' for controller_id in controller_ids)
        print(f'    python generate_report.py --controller-ids {controller_args} --month "{month}"\n')
    else:
        print(f'    python generate_report.py --site "{site}" --month "{month}"\n')


if __name__ == "__main__":
    main()