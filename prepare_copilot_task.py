# """
# prepare_copilot_task.py
# ────────────────────────
# Step 3 — Run AFTER prefetch_site.py and prepare_report_context.py.

# Creates two files in data_store/<slug>/:

#   copilot_task.md      ← Open this in VS Code, paste Section marked
#                           COPILOT TASK into Copilot Chat.
#                           Copilot writes the narrative JSON back.

#   narrative_cache.json ← Empty template. Copilot fills this in.
#                           generate_report.py reads from here.

# USAGE
# ─────
#     python prepare_copilot_task.py --site "Synthomer Chester SC (US)" --month "May 2026"

# WORKFLOW
# ────────
#     1. python prefetch_site.py          --site "..." --month "..."
#     2. python prepare_copilot_task.py   --site "..." --month "..."
#     3. Open VS Code → open copilot_task.md
#     4. Open Copilot Chat (Ctrl+Shift+I, Agent mode)
#     5. Paste the COPILOT TASK section into Copilot Chat
#     6. Copilot writes narrative_cache.json
#     7. python generate_report.py        --site "..." --month "..."
# """

# import argparse
# import json
# import re
# import sys
# from pathlib import Path

# ROOT       = Path(__file__).parent
# DATA_STORE = ROOT / "data_store"


# def parse_args():
#     p = argparse.ArgumentParser()
#     p.add_argument("--site",  required=True)
#     p.add_argument("--month", required=True)
#     return p.parse_args()


# def slugify(text):
#     return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


# def _load(path, default):
#     return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


# def fmt(v, d=2):
#     try:    return f"{float(v):.{d}f}" if v not in (None, "NULL", "") else "N/A"
#     except: return "N/A"


# def main():
#     args  = parse_args()
#     site  = args.site
#     month = args.month
#     slug  = slugify(f"{site}_{month}")
#     cache = DATA_STORE / slug

#     if not (cache / "manifest.json").exists():
#         print(f"[ERROR] No prefetch data at {cache}")
#         print(f"  Run first: python prefetch_site.py --site \"{site}\" --month \"{month}\"")
#         sys.exit(1)

#     # ── Load all data ─────────────────────────────────────────────────────────
#     controllers = _load(cache / "controllers.json", [])
#     scc         = _load(cache / "scc.json",          [])
#     ade         = _load(cache / "ade_data.json",     [])
#     notes       = _load(cache / "service_notes.json",[])

#     telem_sensors = {}
#     for f in (cache / "telemetry").glob("*_summary.json"):
#         d = json.loads(f.read_text())
#         for name, stats in d.get("sensors", {}).items():
#             telem_sensors[name.lower()] = stats

#     # ── Helper: find sensor by keywords ──────────────────────────────────────
#     def find(*kws):
#         for key, stats in telem_sensors.items():
#             if all(w in key for w in kws):
#                 return stats
#         return {}

#     def r20(stats):   return [round(float(v),4) for v in stats.get("recent_20",[])]
#     def smean(stats): v=stats.get("mean"); return float(v) if v is not None else None
#     def smin(stats):  v=stats.get("min");  return float(v) if v is not None else None
#     def smax(stats):  v=stats.get("max");  return float(v) if v is not None else None

#     ms_s   = find("corrosion_probe_1")
#     cu_s   = find("corrosion_probe_2")
#     ec_s   = find("electrode_conductivity")
#     tp_s   = find("fluorometer_ch_1") or find("fluorometer","ch1")
#     ph_s   = find("ph_probe") or find("ph")
#     orp_s  = find("orp")
#     turb_s = find("turbidity")
#     cf_s   = find("cellfouling") or find("cell_fouling")
#     rel_s  = find("relay3") or find("relay5") or find("relay1")

#     # ── Controller Setpoints ─────────────────────────────────────────────────────────
#     def scc_row(*kws):
#         for r in scc:
#             s = (str(r.get("Input Sensor",""))+str(r.get("Sensor Name",""))).lower()
#             if all(w in s for w in kws): return r
#         return {}

#     ec_r = scc_row("conductivity")
#     tp_r = scc_row("fluorometer_ch_1") or scc_row("fluorometer","ch1") or scc_row("traced")

#     def fv(row, key):
#         v = row.get(key)
#         try:    return float(v) if v not in (None,"NULL","") else None
#         except: return None

#     ec_sp = fv(ec_r,"SP"); ec_db = fv(ec_r,"DB")
#     tp_sp = fv(tp_r,"SP"); tp_db = fv(tp_r,"DB")
#     ec_ll = (ec_sp-ec_db) if ec_sp and ec_db else None
#     ec_ul = (ec_sp+ec_db) if ec_sp and ec_db else None
#     tp_ll = (tp_sp-tp_db) if tp_sp and tp_db else None
#     tp_ul = (tp_sp+tp_db) if tp_sp and tp_db else None
#     prod  = tp_r.get("Product Name") or "Traced Product"
#     if prod in ("None","none",None): prod = "Traced Product"

#     # ── % in range ────────────────────────────────────────────────────────────
#     def pct(vals, ll, ul):
#         if not vals or ll is None or ul is None: return None
#         return round(sum(1 for v in vals if ll<=v<=ul)/len(vals)*100,1)

#     tp_r20_vals = r20(tp_s); ec_r20_vals = r20(ec_s)
#     tp_pct = pct(tp_r20_vals, tp_ll, tp_ul)
#     ec_pct = pct(ec_r20_vals, ec_ll, ec_ul)

#     def status(p):
#         if p is None: return "Stable"
#         return "Good" if p>75 else ("Stable" if p>=25 else "Action Required")

#     ms_mean = smean(ms_s); cu_mean = smean(cu_s)
#     corr_ok = (ms_mean is not None and ms_mean<3.0) and (cu_mean is not None and cu_mean<0.5)
#     corr_status = "Good" if corr_ok else "Action Required"
#     tp_status   = status(tp_pct)
#     ec_status   = status(ec_pct)

#     tp_mean = smean(tp_s); ec_mean = smean(ec_s)
#     if tp_mean and tp_ul and tp_ll:
#         tp_dir = "HIGH" if tp_mean>tp_ul else ("LOW" if tp_mean<tp_ll else "OK")
#     else: tp_dir = "UNKNOWN"

#     frc_rows = [r for r in ade if any(w in str(r.get("Parameter","")).lower()
#                 for w in ("free residual","frc","halogen"))]
#     frc = float(frc_rows[0]["Value"]) if frc_rows else None
#     micro_status = "Good" if frc and frc>=0.2 else "Stable"

#     relay_r20 = r20(rel_s)
#     relay_firing = bool(relay_r20 and any(v>0 for v in relay_r20))

#     notes_text = "No service notes were recorded for this reporting period." if not notes else \
#         "\n".join(f"Date: {str(n.get('CreatedDate',''))[:10]}\n"
#                   f"{n.get('ServiceNotePlain') or n.get('ServiceNote','')}"
#                   for n in notes)

#     # ═══════════════════════════════════════════════════════════════════════════
#     # Build copilot_task.md
#     # ═══════════════════════════════════════════════════════════════════════════
#     task_lines = [
#         f"# Copilot Task — {site} | {month}",
#         "",
#         "> **Instructions for Copilot Agent:**",
#         "> 1. Read ALL the data below carefully",
#         "> 2. Follow EVERY rule in the RULES section",
#         "> 3. Write the narrative_cache.json file at the path shown",
#         "> 4. Do not add markdown, do not truncate, write valid JSON",
#         "",
#         "---",
#         "",
#         "## RULES (follow exactly)",
#         "",
#         "**CORROSION CONTROL:**",
#         f"- Use this exact wording: 'The average mild steel corrosion rate was X MPY against",
#         f"  the target of within 3.0 MPY, and the average copper corrosion rate was X MPY",
#         f"  against the target of within 0.5 MPY.'",
#         f"- Status: {corr_status}",
#         "",
#         "**SCALE CONTROL:**",
#         f"- Write ONLY about {prod}. Do NOT mention conductivity, pH, turbidity, or anything else.",
#         f"- Status MUST be: {tp_status} (because {tp_pct}% of recent readings are in Controller Setpoint range)",
#         f"- {tp_pct}% in range means: Good>75%, Stable 25-75%, Action Required<25%",
#         f"- Product is {tp_dir} (HIGH=above upper limit, LOW=below lower limit, OK=in range)",
#     ]

#     if tp_dir == "HIGH":
#         task_lines += [
#             f"- MUST include Observation: '{prod} concentration was above the Controller Setpoint upper",
#             f"  control limit of {fmt(tp_ul,1)} ppm, indicating overfeeding.'",
#             f"- MUST include Recommendation: 'Check dosing pump rate and reduce if running",
#             f"  above setpoint. Verify fluorometer calibration with a grab sample. Review",
#             f"  the dosing schedule and confirm the relay is not in manual override.'",
#         ]
#     elif tp_dir == "LOW":
#         task_lines += [
#             f"- MUST include Observation: '{prod} concentration was below the Controller Setpoint lower",
#             f"  control limit of {fmt(tp_ll,1)} ppm.'",
#             f"- MUST include Recommendation: 'Verify dosing pump operation and confirm it",
#             f"  is primed. Check product inventory level. Inspect the chemical feed line",
#             f"  for blockage or air lock. Verify fluorometer calibration with a grab sample.'",
#         ]

#     root_cause = ("Conductivity was stable during the same period, indicating this is a "
#                   "product feed or calibration issue, not a water loss event."
#                   if (ec_pct or 0) >= 75 else
#                   "Conductivity also declined during the same period, suggesting water loss, "
#                   "dilution, or excess blowdown as a contributing factor.")
#     task_lines += [
#         f"- Root cause to include: '{root_cause}'",
#         "",
#         "**MICROBIAL CONTROL:**",
#         f"- Write ONLY about FRC and ORP. Do NOT mention pH, turbidity, cell fouling, or anything else.",
#         f"- Status: {micro_status}",
#     ]

#     if frc is not None:
#         task_lines.append(f"- FRC from field test data: {frc} ppm. Comment on whether this is adequate.")
#     else:
#         task_lines.append(
#             "- FRC: NOT in field test data. Write: 'FRC data was not available in the field test data "
#             "for this reporting period and will be checked during the upcoming service visit.'")

#     task_lines += [
#         f"- Biocide relay was firing: {relay_firing}",
#         f"- MANDATORY ORP sentence: 'ORP spike response after timer-controlled biocide feed "
#         f"{'was consistent, indicating the system responded to treatment.' if relay_firing else 'was not consistent. Possible causes include low oxidizing biocide residual, biocide inventory issue, dosing pump lost prime, or incorrect timer schedule. These will be investigated at the upcoming service visit.'}'",
#         "- NEVER write absolute ORP values anywhere. Relative/spike language only.",
#         "",
#         "**WATER EFFICIENCY:**",
#         f"- Discuss conductivity and COC here (NOT in Scale Control).",
#         f"- Controller Setpoint conductivity: {fmt(ec_sp,0)} µS/cm, range {fmt(ec_ll,0)}–{fmt(ec_ul,0)} µS/cm",
#         f"- {ec_pct}% of recent readings within Controller Setpoint control range",
#         f"- 90-day average: {fmt(ec_mean,1)} µS/cm",
#         f"- Makeup water conductivity not available — state COC cannot be calculated,",
#         f"  should be captured at next service visit.",
#         "",
#         "**PRODUCT EFFICIENCY:**",
#         f"- Product name: {prod}",
#         f"- Mean: {fmt(tp_mean,1)} ppm vs Controller Setpoint target {fmt(tp_sp,1)} ppm",
#         f"- {tp_pct}% in range",
#         f"- Actual consumption not available — state this.",
#         "",
#         "**PROACTIVE SYSTEM SUPPORT:**",
#         "- Section title MUST be exactly: Proactive System Support (never 'Alarms')",
#         "- No alarm data available — state Ackumen average is 6 alarms per controller",
#         "- Incorporate any service note Actions Completed below",
#         "",
#         "**CHART COMMENTS (one sentence each — describe the trend shown in the chart):**",
#         "- corrosion_chart_comment: describe MS and Cu trend across W1-W4",
#         f"- scale_chart_comment: describe {prod} trend vs Controller Setpoint range {fmt(tp_ll,1)}–{fmt(tp_ul,1)} ppm",
#         "- orp_chart_comment: describe ORP spike pattern relative to biocide relay activity",
#         f"- conductivity_chart_comment: describe conductivity trend vs setpoint {fmt(ec_sp,0)} µS/cm",
#         "",
#         "---",
#         "",
#         "## SITE DATA",
#         "",
#         f"**Site:** {site}",
#         f"**Month:** {month}",
#         f"**Controller:** {controllers[0].get('SerialNumber','N/A') if controllers else 'N/A'}",
#         "",
#         "### Corrosion",
#         f"| Parameter | Mean | Min | Max | Target | Status |",
#         f"|---|---|---|---|---|---|",
#         f"| Mild Steel (MPY) | {fmt(ms_mean)} | {fmt(smin(ms_s))} | {fmt(smax(ms_s))} | <3.0 | {corr_status} |",
#         f"| Copper (MPY) | {fmt(cu_mean,4)} | {fmt(smin(cu_s),4)} | {fmt(smax(cu_s),4)} | <0.5 | {corr_status} |",
#         "",
#         "**Mild Steel recent 20 readings (MPY):**",
#         f"`{r20(ms_s)}`",
#         "",
#         "**Copper recent 20 readings (MPY):**",
#         f"`{r20(cu_s)}`",
#         "",
#         f"### {prod} (Scale Control)",
#         f"| Parameter | Value |",
#         f"|---|---|",
#         f"| Controller Setpoint (SP) | {fmt(tp_sp,1)} ppm |",
#         f"| Dead Band (DB) | {fmt(tp_db,1)} ppm |",
#         f"| Controller Setpoint Range | {fmt(tp_ll,1)} – {fmt(tp_ul,1)} ppm |",
#         f"| 90-day Mean | {fmt(tp_mean,1)} ppm |",
#         f"| % Recent in Controller Setpoint Range | {tp_pct}% ({status(tp_pct)}) |",
#         f"| Direction | {tp_dir} |",
#         "",
#         f"**{prod} recent 20 readings (ppm):**",
#         f"`{tp_r20_vals}`",
#         "",
#         "### Conductivity (Water Efficiency)",
#         f"| Parameter | Value |",
#         f"|---|---|",
#         f"| Controller Setpoint (SP) | {fmt(ec_sp,0)} µS/cm |",
#         f"| Dead Band (DB) | {fmt(ec_db,0)} µS/cm |",
#         f"| Controller Setpoint Range | {fmt(ec_ll,0)} – {fmt(ec_ul,0)} µS/cm |",
#         f"| 90-day Mean | {fmt(ec_mean,1)} µS/cm |",
#         f"| % Recent in Controller Setpoint Range | {ec_pct}% ({status(ec_pct)}) |",
#         "",
#         "**Conductivity recent 20 readings (µS/cm):**",
#         f"`{ec_r20_vals}`",
#         "",
#         "### Microbial",
#         f"| Parameter | Value |",
#         f"|---|---|",
#         f"| FRC (from field test data) | {'Not available' if frc is None else f'{frc} ppm'} |",
#         f"| Biocide relay firing | {relay_firing} |",
#         f"| Microbial status | {micro_status} |",
#         "",
#         "**Biocide relay recent 20 readings (1=ON, 0=OFF):**",
#         f"`{relay_r20}`",
#         "",
#         "**ORP recent 20 readings (DO NOT report these values — use spike language only):**",
#         f"`{r20(orp_s)}`",
#         "",
#         "### Supporting parameters (for Performance Summary table only — do not use in narrative sections)",
#         f"| Parameter | Mean | Min | Max |",
#         f"|---|---|---|---|",
#         f"| pH | {fmt(smean(ph_s),2)} | {fmt(smin(ph_s),2)} | {fmt(smax(ph_s),2)} |",
#         f"| Turbidity (NTU) | {fmt(smean(turb_s),2)} | {fmt(smin(turb_s),2)} | {fmt(smax(turb_s),2)} |",
#         f"| Cell Fouling (%) | {fmt(smean(cf_s),2)} | {fmt(smin(cf_s),2)} | {fmt(smax(cf_s),2)} |",
#         "",
#         "### Service Notes",
#         "",
#         notes_text,
#         "",
#         "---",
#         "",
#         "## COPILOT TASK",
#         "",
#         "> **Copy everything in the box below and paste into Copilot Chat.**",
#         "> **Make sure this file (copilot_task.md) is open in the editor.**",
#         "",
#         "```",
#         f"Read copilot_task.md carefully.",
#         f"",
#         f"Write the narrative for the {site} {month} cooling water performance report.",
#         f"Follow ALL rules in the RULES section exactly.",
#         f"",
#         f"Save your response as valid JSON to this exact file:",
#         f"data_store/{slug}/narrative_cache.json",
#         f"",
#         f"The JSON must have exactly these keys:",
#         f"{{",
#         f'  "corrosion_narrative": "2-3 sentences using exact SME wording",',
#         f'  "corrosion_chart_comment": "1 sentence describing the corrosion trend chart",',
#         f'  "scale_narrative": "3-5 sentences about {prod} ONLY — no other parameters",',
#         f'  "scale_chart_comment": "1 sentence describing the {prod} trend chart",',
#         f'  "microbial_narrative": "2-3 sentences about FRC and ORP ONLY — no pH/turbidity",',
#         f'  "orp_chart_comment": "1 sentence describing the ORP spike pattern chart",',
#         f'  "water_efficiency_narrative": "2-3 sentences about conductivity and COC",',
#         f'  "conductivity_chart_comment": "1 sentence describing the conductivity trend chart",',
#         f'  "product_efficiency_narrative": "2-3 sentences about {prod} consumption",',
#         f'  "proactive_support_narrative": "2-3 sentences about alarms and service notes",',
#         f'  "closing_summary": "2-3 sentences summarising the month overall"',
#         f"}}",
#         f"",
#         f"Rules:",
#         f"- Corrosion: use exact wording 'average mild steel corrosion rate was X MPY against the target of within 3.0 MPY'",
#         f"- Scale Control: {prod} ONLY. Status MUST be {tp_status} ({tp_pct}% in range).",
#         f"- {'Include Observation and Recommendation for ' + tp_dir + ' product level.' if tp_dir in ('HIGH','LOW') else 'Product is within range — no observation/recommendation needed.'}",
#         f"- Microbial: FRC and ORP ONLY. No pH, turbidity, cell fouling.",
#         f"- NEVER write absolute ORP values.",
#         f"- Proactive Support title: exactly 'Proactive System Support'",
#         f"- Write professional customer-facing language",
#         f"- Return ONLY valid JSON — no markdown, no explanation outside the JSON",
#         "```",
#         "",
#     ]

#     task_path = cache / "copilot_task.md"
#     task_path.write_text("\n".join(task_lines), encoding="utf-8")
#     print(f"✅  copilot_task.md  → {task_path}")

#     # ═══════════════════════════════════════════════════════════════════════════
#     # Create empty narrative_cache.json template
#     # ═══════════════════════════════════════════════════════════════════════════
#     empty = {
#         "corrosion_narrative":           "",
#         "corrosion_chart_comment":       "",
#         "scale_narrative":               "",
#         "scale_chart_comment":           "",
#         "microbial_narrative":           "",
#         "orp_chart_comment":             "",
#         "water_efficiency_narrative":    "",
#         "conductivity_chart_comment":    "",
#         "product_efficiency_narrative":  "",
#         "proactive_support_narrative":   "",
#         "closing_summary":               "",
#         "_status": "EMPTY — Copilot must fill this in",
#         "_site":   site,
#         "_month":  month,
#     }
#     narrative_path = cache / "narrative_cache.json"
#     narrative_path.write_text(json.dumps(empty, indent=2), encoding="utf-8")
#     print(f"✅  narrative_cache.json → {narrative_path}  (Copilot fills this in)")

#     print(f"")
#     print(f"Next steps:")
#     print(f"  1. Open VS Code:  code .")
#     print(f"  2. Open file:     data_store/{slug}/copilot_task.md")
#     print(f"  3. Also open:     data_store/{slug}/narrative_cache.json")
#     print(f"  4. Copilot Chat:  Ctrl+Shift+I  (Agent mode)")
#     print(f"  5. Copy the COPILOT TASK block (bottom of copilot_task.md)")
#     print(f"     and paste into Copilot Chat")
#     print(f"  6. Copilot writes narrative_cache.json")
#     print(f"  7. Run: python generate_report.py --site \"{site}\" --month \"{month}\"")


# if __name__ == "__main__":
#     main()


# """
# prepare_copilot_task.py
# ────────────────────────
# Step 3 — Run AFTER prefetch_site.py and prepare_report_context.py.

# Creates two files in data_store/<slug>/:

#   copilot_task.md      ← Open this in VS Code, paste Section marked
#                           COPILOT TASK into Copilot Chat.
#                           Copilot writes the narrative JSON back.

#   narrative_cache.json ← Empty template. Copilot fills this in.
#                           generate_report.py reads from here.

# USAGE
# ─────
#     python prepare_copilot_task.py --site "Synthomer Chester SC (US)" --month "May 2026"

# WORKFLOW
# ────────
#     1. python prefetch_site.py          --site "..." --month "..."
#     2. python prepare_copilot_task.py   --site "..." --month "..."
#     3. Open VS Code → open copilot_task.md
#     4. Open Copilot Chat (Ctrl+Shift+I, Agent mode)
#     5. Paste the COPILOT TASK section into Copilot Chat
#     6. Copilot writes narrative_cache.json
#     7. python generate_report.py        --site "..." --month "..."
# """

# import argparse
# import json
# import re
# import sys
# from pathlib import Path

# ROOT       = Path(__file__).parent
# DATA_STORE = ROOT / "data_store"


# def parse_args():
#     p = argparse.ArgumentParser()
#     p.add_argument("--site",  required=True)
#     p.add_argument("--month", required=True)
#     return p.parse_args()


# def slugify(text):
#     return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


# def _load(path, default):
#     return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


# def fmt(v, d=2):
#     try:    return f"{float(v):.{d}f}" if v not in (None, "NULL", "") else "N/A"
#     except: return "N/A"


# def _load_mu_conductivity(site):
#     """Read MU conductivity from data/MU_conductivity.xlsx if present. Returns float or None.

#     Kept in sync with generate_report.py's _load_mu_conductivity() — both scripts
#     need to agree on whether MU conductivity is available for a site, otherwise
#     the Copilot narrative and the generated COC table will contradict each other.
#     """
#     mu_file = ROOT / "data" / "MU_conductivity.xlsx"
#     if not mu_file.exists():
#         return None
#     try:
#         import openpyxl
#         wb = openpyxl.load_workbook(mu_file, data_only=True)
#         ws = wb.active
#         for row in ws.iter_rows(min_row=2, values_only=True):
#             if not row or not row[0]: continue
#             if str(row[0]).strip().lower() == site.strip().lower():
#                 val = row[3] if len(row) > 3 else None
#                 if val is None or str(val).lower() in ("no data","none","",None):
#                     return None
#                 try: return float(val)
#                 except: return None
#     except Exception as e:
#         print(f"  [WARN] Could not read MU_conductivity.xlsx: {e}")
#     return None


# def compute_coc(ec_sp, ec_mean, mu_cond):
#     """Same COC math as generate_report.py's compute_coc(), reduced to the two inputs
#     this script has on hand (Controller Setpoint conductivity + monthly mean conductivity)."""
#     if mu_cond is None or mu_cond == 0:
#         return {"mu_available": False, "mu_cond": None,
#                 "target_coc": None, "actual_coc": None,
#                 "deviation_pct": None, "coc_status": None}

#     target_coc = (ec_sp / mu_cond) if ec_sp else None
#     actual_coc = (ec_mean / mu_cond) if ec_mean else None

#     if target_coc and actual_coc:
#         dev = abs(actual_coc - target_coc) / target_coc * 100
#         if   dev <= 20: coc_status = "Good"
#         elif dev <= 50: coc_status = "Okay"
#         else:           coc_status = "Bad"
#     else:
#         dev, coc_status = None, None

#     return {
#         "mu_available": True, "mu_cond": round(mu_cond, 2),
#         "target_coc": round(target_coc, 2) if target_coc else None,
#         "actual_coc": round(actual_coc, 2) if actual_coc else None,
#         "deviation_pct": round(dev, 1) if dev is not None else None,
#         "coc_status": coc_status,
#     }


# def main():
#     args  = parse_args()
#     site  = args.site
#     month = args.month
#     slug  = slugify(f"{site}_{month}")
#     cache = DATA_STORE / slug

#     if not (cache / "manifest.json").exists():
#         print(f"[ERROR] No prefetch data at {cache}")
#         print(f"  Run first: python prefetch_site.py --site \"{site}\" --month \"{month}\"")
#         sys.exit(1)

#     # ── Load all data ─────────────────────────────────────────────────────────
#     controllers = _load(cache / "controllers.json", [])
#     scc         = _load(cache / "scc.json",          [])
#     ade         = _load(cache / "ade_data.json",     [])
#     notes       = _load(cache / "service_notes.json",[])

#     telem_sensors = {}
#     for f in (cache / "telemetry").glob("*_summary.json"):
#         d = json.loads(f.read_text())
#         for name, stats in d.get("sensors", {}).items():
#             telem_sensors[name.lower()] = stats

#     # ── Helper: find sensor by keywords ──────────────────────────────────────
#     def find(*kws):
#         for key, stats in telem_sensors.items():
#             if all(w in key for w in kws):
#                 return stats
#         return {}

#     def r20(stats):   return [round(float(v),4) for v in stats.get("recent_20",[])]
#     def smean(stats): v=stats.get("mean"); return float(v) if v is not None else None
#     def smin(stats):  v=stats.get("min");  return float(v) if v is not None else None
#     def smax(stats):  v=stats.get("max");  return float(v) if v is not None else None

#     ms_s   = find("corrosion_probe_1")
#     cu_s   = find("corrosion_probe_2")
#     ec_s   = find("electrode_conductivity")
#     tp_s   = find("fluorometer_ch_1") or find("fluorometer","ch1")
#     ph_s   = find("ph_probe") or find("ph")
#     orp_s  = find("orp")
#     turb_s = find("turbidity")
#     cf_s   = find("cellfouling") or find("cell_fouling")
#     rel_s  = find("relay3") or find("relay5") or find("relay1")

#     # ── Controller Setpoints ─────────────────────────────────────────────────────────
#     def scc_row(*kws):
#         for r in scc:
#             s = (str(r.get("Input Sensor",""))+str(r.get("Sensor Name",""))).lower()
#             if all(w in s for w in kws): return r
#         return {}

#     ec_r = scc_row("conductivity")
#     tp_r = scc_row("fluorometer_ch_1") or scc_row("fluorometer","ch1") or scc_row("traced")

#     def fv(row, key):
#         v = row.get(key)
#         try:    return float(v) if v not in (None,"NULL","") else None
#         except: return None

#     ec_sp = fv(ec_r,"SP"); ec_db = fv(ec_r,"DB")
#     tp_sp = fv(tp_r,"SP"); tp_db = fv(tp_r,"DB")
#     ec_ll = (ec_sp-ec_db) if ec_sp and ec_db else None
#     ec_ul = (ec_sp+ec_db) if ec_sp and ec_db else None
#     tp_ll = (tp_sp-tp_db) if tp_sp and tp_db else None
#     tp_ul = (tp_sp+tp_db) if tp_sp and tp_db else None
#     prod  = tp_r.get("Product Name") or "Traced Product"
#     if prod in ("None","none",None): prod = "Traced Product"

#     # ── % in range ────────────────────────────────────────────────────────────
#     def pct(vals, ll, ul):
#         if not vals or ll is None or ul is None: return None
#         return round(sum(1 for v in vals if ll<=v<=ul)/len(vals)*100,1)

#     tp_r20_vals = r20(tp_s); ec_r20_vals = r20(ec_s)
#     tp_pct = pct(tp_r20_vals, tp_ll, tp_ul)
#     ec_pct = pct(ec_r20_vals, ec_ll, ec_ul)

#     def status(p):
#         if p is None: return "Stable"
#         return "Good" if p>75 else ("Stable" if p>=25 else "Action Required")

#     ms_mean = smean(ms_s); cu_mean = smean(cu_s)
#     corr_ok = (ms_mean is not None and ms_mean<3.0) and (cu_mean is not None and cu_mean<0.5)
#     corr_status = "Good" if corr_ok else "Action Required"
#     tp_status   = status(tp_pct)
#     ec_status   = status(ec_pct)

#     tp_mean = smean(tp_s); ec_mean = smean(ec_s)
#     if tp_mean and tp_ul and tp_ll:
#         tp_dir = "HIGH" if tp_mean>tp_ul else ("LOW" if tp_mean<tp_ll else "OK")
#     else: tp_dir = "UNKNOWN"

#     frc_rows = [r for r in ade if any(w in str(r.get("Parameter","")).lower()
#                 for w in ("free residual","frc","halogen"))]
#     frc = float(frc_rows[0]["Value"]) if frc_rows else None
#     micro_status = "Good" if frc and frc>=0.2 else "Stable"

#     relay_r20 = r20(rel_s)
#     relay_firing = bool(relay_r20 and any(v>0 for v in relay_r20))

#     notes_text = "No service notes were recorded for this reporting period." if not notes else \
#         "\n".join(f"Date: {str(n.get('CreatedDate',''))[:10]}\n"
#                   f"{n.get('ServiceNotePlain') or n.get('ServiceNote','')}"
#                   for n in notes)

#     # ═══════════════════════════════════════════════════════════════════════════
#     # Build copilot_task.md
#     # ═══════════════════════════════════════════════════════════════════════════
#     task_lines = [
#         f"# Copilot Task — {site} | {month}",
#         "",
#         "> **Instructions for Copilot Agent:**",
#         "> 1. Read ALL the data below carefully",
#         "> 2. Follow EVERY rule in the RULES section",
#         "> 3. Write the narrative_cache.json file at the path shown",
#         "> 4. Do not add markdown, do not truncate, write valid JSON",
#         "",
#         "---",
#         "",
#         "## RULES (follow exactly)",
#         "",
#         "**CORROSION CONTROL:**",
#         f"- Use this exact wording: 'The average mild steel corrosion rate was X MPY against",
#         f"  the target of within 3.0 MPY, and the average copper corrosion rate was X MPY",
#         f"  against the target of within 0.5 MPY.'",
#         f"- Status: {corr_status}",
#         "",
#         "**SCALE CONTROL:**",
#         f"- Write ONLY about {prod}. Do NOT mention conductivity, pH, turbidity, or anything else.",
#         f"- Status MUST be: {tp_status} (because {tp_pct}% of recent readings are in Controller Setpoint range)",
#         f"- {tp_pct}% in range means: Good>75%, Stable 25-75%, Action Required<25%",
#         f"- Product is {tp_dir} (HIGH=above upper limit, LOW=below lower limit, OK=in range)",
#     ]

#     if tp_dir == "HIGH":
#         task_lines += [
#             f"- MUST include Observation: '{prod} concentration was above the Controller Setpoint upper",
#             f"  control limit of {fmt(tp_ul,1)} ppm, indicating overfeeding.'",
#             f"- MUST include Recommendation: 'Check dosing pump rate and reduce if running",
#             f"  above setpoint. Verify fluorometer calibration with a grab sample. Review",
#             f"  the dosing schedule and confirm the relay is not in manual override.'",
#         ]
#     elif tp_dir == "LOW":
#         task_lines += [
#             f"- MUST include Observation: '{prod} concentration was below the Controller Setpoint lower",
#             f"  control limit of {fmt(tp_ll,1)} ppm.'",
#             f"- MUST include Recommendation: 'Verify dosing pump operation and confirm it",
#             f"  is primed. Check product inventory level. Inspect the chemical feed line",
#             f"  for blockage or air lock. Verify fluorometer calibration with a grab sample.'",
#         ]

#     root_cause = ("Conductivity was stable during the same period, indicating this is a "
#                   "product feed or calibration issue, not a water loss event."
#                   if (ec_pct or 0) >= 75 else
#                   "Conductivity also declined during the same period, suggesting water loss, "
#                   "dilution, or excess blowdown as a contributing factor.")
#     task_lines += [
#         f"- Root cause to include: '{root_cause}'",
#         "",
#         "**MICROBIAL CONTROL:**",
#         f"- Write ONLY about FRC and ORP. Do NOT mention pH, turbidity, cell fouling, or anything else.",
#         f"- Status: {micro_status}",
#     ]

#     if frc is not None:
#         task_lines.append(f"- FRC from field test data: {frc} ppm. Comment on whether this is adequate.")
#     else:
#         task_lines.append(
#             "- FRC: NOT in field test data. Write: 'FRC data was not available in the field test data "
#             "for this reporting period and will be checked during the upcoming service visit.'")

#     task_lines += [
#         f"- Biocide relay was firing: {relay_firing}",
#         f"- MANDATORY ORP sentence: 'ORP spike response after timer-controlled biocide feed "
#         f"{'was consistent, indicating the system responded to treatment.' if relay_firing else 'was not consistent. Possible causes include low oxidizing biocide residual, biocide inventory issue, dosing pump lost prime, or incorrect timer schedule. These will be investigated at the upcoming service visit.'}'",
#         "- NEVER write absolute ORP values anywhere. Relative/spike language only.",
#         "",
#         "**WATER EFFICIENCY:**",
#         f"- Discuss conductivity and COC here (NOT in Scale Control).",
#         f"- Controller Setpoint conductivity: {fmt(ec_sp,0)} µS/cm, range {fmt(ec_ll,0)}–{fmt(ec_ul,0)} µS/cm",
#         f"- {ec_pct}% of recent readings within Controller Setpoint control range",
#         f"- 90-day average: {fmt(ec_mean,1)} µS/cm",
#     ]

#     mu_cond = _load_mu_conductivity(site)
#     coc = compute_coc(ec_sp, ec_mean, mu_cond)
#     mu_row_text  = f"{coc['mu_cond']} µS/cm" if coc["mu_available"] else "Not available"
#     coc_dev_text = f"{coc['deviation_pct']}%" if coc["deviation_pct"] is not None else "N/A"
#     if coc["mu_available"] and coc["target_coc"] is not None and coc["actual_coc"] is not None:
#         task_lines += [
#             f"- Makeup water conductivity: {coc['mu_cond']} µS/cm",
#             f"- Target COC (Controller Setpoint / MU conductivity): {coc['target_coc']}",
#             f"- Actual COC (90-day average conductivity / MU conductivity): {coc['actual_coc']}",
#             f"- COC deviation from target: {coc['deviation_pct']}%  →  Status: {coc['coc_status']}",
#             f"- State the actual COC value and deviation explicitly — do NOT say COC cannot be calculated.",
#         ]
#     else:
#         task_lines += [
#             f"- Makeup water conductivity not available — state COC cannot be calculated,",
#             f"  should be captured at next service visit.",
#         ]

#     task_lines += [
#         "",
#         "**PRODUCT EFFICIENCY:**",
#         f"- Product name: {prod}",
#         f"- Mean: {fmt(tp_mean,1)} ppm vs Controller Setpoint target {fmt(tp_sp,1)} ppm",
#         f"- {tp_pct}% in range",
#         f"- Actual consumption not available — state this.",
#         "",
#         "**PROACTIVE SYSTEM SUPPORT:**",
#         "- Section title MUST be exactly: Proactive System Support (never 'Alarms')",
#         "- No alarm data available — state Ackumen average is 6 alarms per controller",
#         "- Incorporate any service note Actions Completed below",
#         "",
#         "**CHART COMMENTS (one sentence each — describe the trend shown in the chart):**",
#         "- corrosion_chart_comment: describe MS and Cu trend across W1-W4",
#         f"- scale_chart_comment: describe {prod} trend vs Controller Setpoint range {fmt(tp_ll,1)}–{fmt(tp_ul,1)} ppm",
#         "- orp_chart_comment: describe ORP spike pattern relative to biocide relay activity",
#         f"- conductivity_chart_comment: describe conductivity trend vs setpoint {fmt(ec_sp,0)} µS/cm",
#         "",
#         "---",
#         "",
#         "## SITE DATA",
#         "",
#         f"**Site:** {site}",
#         f"**Month:** {month}",
#         f"**Controller:** {controllers[0].get('SerialNumber','N/A') if controllers else 'N/A'}",
#         "",
#         "### Corrosion",
#         f"| Parameter | Mean | Min | Max | Target | Status |",
#         f"|---|---|---|---|---|---|",
#         f"| Mild Steel (MPY) | {fmt(ms_mean)} | {fmt(smin(ms_s))} | {fmt(smax(ms_s))} | <3.0 | {corr_status} |",
#         f"| Copper (MPY) | {fmt(cu_mean,4)} | {fmt(smin(cu_s),4)} | {fmt(smax(cu_s),4)} | <0.5 | {corr_status} |",
#         "",
#         "**Mild Steel recent 20 readings (MPY):**",
#         f"`{r20(ms_s)}`",
#         "",
#         "**Copper recent 20 readings (MPY):**",
#         f"`{r20(cu_s)}`",
#         "",
#         f"### {prod} (Scale Control)",
#         f"| Parameter | Value |",
#         f"|---|---|",
#         f"| Controller Setpoint (SP) | {fmt(tp_sp,1)} ppm |",
#         f"| Dead Band (DB) | {fmt(tp_db,1)} ppm |",
#         f"| Controller Setpoint Range | {fmt(tp_ll,1)} – {fmt(tp_ul,1)} ppm |",
#         f"| 90-day Mean | {fmt(tp_mean,1)} ppm |",
#         f"| % Recent in Controller Setpoint Range | {tp_pct}% ({status(tp_pct)}) |",
#         f"| Direction | {tp_dir} |",
#         "",
#         f"**{prod} recent 20 readings (ppm):**",
#         f"`{tp_r20_vals}`",
#         "",
#         "### Conductivity (Water Efficiency)",
#         f"| Parameter | Value |",
#         f"|---|---|",
#         f"| Controller Setpoint (SP) | {fmt(ec_sp,0)} µS/cm |",
#         f"| Dead Band (DB) | {fmt(ec_db,0)} µS/cm |",
#         f"| Controller Setpoint Range | {fmt(ec_ll,0)} – {fmt(ec_ul,0)} µS/cm |",
#         f"| 90-day Mean | {fmt(ec_mean,1)} µS/cm |",
#         f"| % Recent in Controller Setpoint Range | {ec_pct}% ({status(ec_pct)}) |",
#         f"| Makeup Water Conductivity | {mu_row_text} |",
#         f"| Target COC | {coc['target_coc'] if coc['target_coc'] is not None else 'N/A'} |",
#         f"| Actual COC | {coc['actual_coc'] if coc['actual_coc'] is not None else 'N/A'} |",
#         f"| COC Deviation | {coc_dev_text} |",
#         "",
#         "**Conductivity recent 20 readings (µS/cm):**",
#         f"`{ec_r20_vals}`",
#         "",
#         "### Microbial",
#         f"| Parameter | Value |",
#         f"|---|---|",
#         f"| FRC (from field test data) | {'Not available' if frc is None else f'{frc} ppm'} |",
#         f"| Biocide relay firing | {relay_firing} |",
#         f"| Microbial status | {micro_status} |",
#         "",
#         "**Biocide relay recent 20 readings (1=ON, 0=OFF):**",
#         f"`{relay_r20}`",
#         "",
#         "**ORP recent 20 readings (DO NOT report these values — use spike language only):**",
#         f"`{r20(orp_s)}`",
#         "",
#         "### Supporting parameters (for Performance Summary table only — do not use in narrative sections)",
#         f"| Parameter | Mean | Min | Max |",
#         f"|---|---|---|---|",
#         f"| pH | {fmt(smean(ph_s),2)} | {fmt(smin(ph_s),2)} | {fmt(smax(ph_s),2)} |",
#         f"| Turbidity (NTU) | {fmt(smean(turb_s),2)} | {fmt(smin(turb_s),2)} | {fmt(smax(turb_s),2)} |",
#         f"| Cell Fouling (%) | {fmt(smean(cf_s),2)} | {fmt(smin(cf_s),2)} | {fmt(smax(cf_s),2)} |",
#         "",
#         "### Service Notes",
#         "",
#         notes_text,
#         "",
#         "---",
#         "",
#         "## COPILOT TASK",
#         "",
#         "> **Copy everything in the box below and paste into Copilot Chat.**",
#         "> **Make sure this file (copilot_task.md) is open in the editor.**",
#         "",
#         "```",
#         f"Read copilot_task.md carefully.",
#         f"",
#         f"Write the narrative for the {site} {month} cooling water performance report.",
#         f"Follow ALL rules in the RULES section exactly.",
#         f"",
#         f"Save your response as valid JSON to this exact file:",
#         f"data_store/{slug}/narrative_cache.json",
#         f"",
#         f"The JSON must have exactly these keys:",
#         f"{{",
#         f'  "corrosion_narrative": "2-3 sentences using exact SME wording",',
#         f'  "corrosion_chart_comment": "1 sentence describing the corrosion trend chart",',
#         f'  "scale_narrative": "3-5 sentences about {prod} ONLY — no other parameters",',
#         f'  "scale_chart_comment": "1 sentence describing the {prod} trend chart",',
#         f'  "microbial_narrative": "2-3 sentences about FRC and ORP ONLY — no pH/turbidity",',
#         f'  "orp_chart_comment": "1 sentence describing the ORP spike pattern chart",',
#         f'  "water_efficiency_narrative": "2-3 sentences about conductivity and COC",',
#         f'  "conductivity_chart_comment": "1 sentence describing the conductivity trend chart",',
#         f'  "product_efficiency_narrative": "2-3 sentences about {prod} consumption",',
#         f'  "proactive_support_narrative": "2-3 sentences about alarms and service notes",',
#         f'  "closing_summary": "2-3 sentences summarising the month overall"',
#         f"}}",
#         f"",
#         f"Rules:",
#         f"- Corrosion: use exact wording 'average mild steel corrosion rate was X MPY against the target of within 3.0 MPY'",
#         f"- Scale Control: {prod} ONLY. Status MUST be {tp_status} ({tp_pct}% in range).",
#         f"- {'Include Observation and Recommendation for ' + tp_dir + ' product level.' if tp_dir in ('HIGH','LOW') else 'Product is within range — no observation/recommendation needed.'}",
#         f"- Microbial: FRC and ORP ONLY. No pH, turbidity, cell fouling.",
#         f"- NEVER write absolute ORP values.",
#         f"- Proactive Support title: exactly 'Proactive System Support'",
#         f"- Write professional customer-facing language",
#         f"- Return ONLY valid JSON — no markdown, no explanation outside the JSON",
#         "```",
#         "",
#     ]

#     task_path = cache / "copilot_task.md"
#     task_path.write_text("\n".join(task_lines), encoding="utf-8")
#     print(f"✅  copilot_task.md  → {task_path}")

#     # ═══════════════════════════════════════════════════════════════════════════
#     # Create empty narrative_cache.json template
#     # ═══════════════════════════════════════════════════════════════════════════
#     empty = {
#         "corrosion_narrative":           "",
#         "corrosion_chart_comment":       "",
#         "scale_narrative":               "",
#         "scale_chart_comment":           "",
#         "microbial_narrative":           "",
#         "orp_chart_comment":             "",
#         "water_efficiency_narrative":    "",
#         "conductivity_chart_comment":    "",
#         "product_efficiency_narrative":  "",
#         "proactive_support_narrative":   "",
#         "closing_summary":               "",
#         "_status": "EMPTY — Copilot must fill this in",
#         "_site":   site,
#         "_month":  month,
#     }
#     narrative_path = cache / "narrative_cache.json"
#     narrative_path.write_text(json.dumps(empty, indent=2), encoding="utf-8")
#     print(f"✅  narrative_cache.json → {narrative_path}  (Copilot fills this in)")

#     print(f"")
#     print(f"Next steps:")
#     print(f"  1. Open VS Code:  code .")
#     print(f"  2. Open file:     data_store/{slug}/copilot_task.md")
#     print(f"  3. Also open:     data_store/{slug}/narrative_cache.json")
#     print(f"  4. Copilot Chat:  Ctrl+Shift+I  (Agent mode)")
#     print(f"  5. Copy the COPILOT TASK block (bottom of copilot_task.md)")
#     print(f"     and paste into Copilot Chat")
#     print(f"  6. Copilot writes narrative_cache.json")
#     print(f"  7. Run: python generate_report.py --site \"{site}\" --month \"{month}\"")


# if __name__ == "__main__":
#     main()



# """
# prepare_copilot_task.py
# ────────────────────────
# Step 3 — Run AFTER prefetch_site.py and prepare_report_context.py.

# Creates two files in data_store/<slug>/:

#   copilot_task.md      ← Open this in VS Code, paste Section marked
#                           COPILOT TASK into Copilot Chat.
#                           Copilot writes the narrative JSON back.

#   narrative_cache.json ← Empty template. Copilot fills this in.
#                           generate_report.py reads from here.

# USAGE
# ─────
#     python prepare_copilot_task.py --site "Synthomer Chester SC (US)" --month "May 2026"

# WORKFLOW
# ────────
#     1. python prefetch_site.py          --site "..." --month "..."
#     2. python prepare_copilot_task.py   --site "..." --month "..."
#     3. Open VS Code → open copilot_task.md
#     4. Open Copilot Chat (Ctrl+Shift+I, Agent mode)
#     5. Paste the COPILOT TASK section into Copilot Chat
#     6. Copilot writes narrative_cache.json
#     7. python generate_report.py        --site "..." --month "..."
# """

# import argparse
# import json
# import re
# import sys
# from pathlib import Path

# ROOT       = Path(__file__).parent
# DATA_STORE = ROOT / "data_store"


# def parse_args():
#     p = argparse.ArgumentParser()
#     p.add_argument("--site",  required=True)
#     p.add_argument("--month", required=True)
#     return p.parse_args()


# def slugify(text):
#     return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


# def _load(path, default):
#     return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


# def fmt(v, d=2):
#     try:    return f"{float(v):.{d}f}" if v not in (None, "NULL", "") else "N/A"
#     except: return "N/A"


# def main():
#     args  = parse_args()
#     site  = args.site
#     month = args.month
#     slug  = slugify(f"{site}_{month}")
#     cache = DATA_STORE / slug

#     if not (cache / "manifest.json").exists():
#         print(f"[ERROR] No prefetch data at {cache}")
#         print(f"  Run first: python prefetch_site.py --site \"{site}\" --month \"{month}\"")
#         sys.exit(1)

#     # ── Load all data ─────────────────────────────────────────────────────────
#     controllers = _load(cache / "controllers.json", [])
#     scc         = _load(cache / "scc.json",          [])
#     ade         = _load(cache / "ade_data.json",     [])
#     notes       = _load(cache / "service_notes.json",[])

#     telem_sensors = {}
#     for f in (cache / "telemetry").glob("*_summary.json"):
#         d = json.loads(f.read_text())
#         for name, stats in d.get("sensors", {}).items():
#             telem_sensors[name.lower()] = stats

#     # ── Helper: find sensor by keywords ──────────────────────────────────────
#     def find(*kws):
#         for key, stats in telem_sensors.items():
#             if all(w in key for w in kws):
#                 return stats
#         return {}

#     def r20(stats):   return [round(float(v),4) for v in stats.get("recent_20",[])]
#     def smean(stats): v=stats.get("mean"); return float(v) if v is not None else None
#     def smin(stats):  v=stats.get("min");  return float(v) if v is not None else None
#     def smax(stats):  v=stats.get("max");  return float(v) if v is not None else None

#     ms_s   = find("corrosion_probe_1")
#     cu_s   = find("corrosion_probe_2")
#     ec_s   = find("electrode_conductivity")
#     tp_s   = find("fluorometer_ch_1") or find("fluorometer","ch1")
#     ph_s   = find("ph_probe") or find("ph")
#     orp_s  = find("orp")
#     turb_s = find("turbidity")
#     cf_s   = find("cellfouling") or find("cell_fouling")
#     rel_s  = find("relay3") or find("relay5") or find("relay1")

#     # ── Controller Setpoints ─────────────────────────────────────────────────────────
#     def scc_row(*kws):
#         for r in scc:
#             s = (str(r.get("Input Sensor",""))+str(r.get("Sensor Name",""))).lower()
#             if all(w in s for w in kws): return r
#         return {}

#     ec_r = scc_row("conductivity")
#     tp_r = scc_row("fluorometer_ch_1") or scc_row("fluorometer","ch1") or scc_row("traced")

#     def fv(row, key):
#         v = row.get(key)
#         try:    return float(v) if v not in (None,"NULL","") else None
#         except: return None

#     ec_sp = fv(ec_r,"SP"); ec_db = fv(ec_r,"DB")
#     tp_sp = fv(tp_r,"SP"); tp_db = fv(tp_r,"DB")
#     ec_ll = (ec_sp-ec_db) if ec_sp and ec_db else None
#     ec_ul = (ec_sp+ec_db) if ec_sp and ec_db else None
#     tp_ll = (tp_sp-tp_db) if tp_sp and tp_db else None
#     tp_ul = (tp_sp+tp_db) if tp_sp and tp_db else None
#     prod  = tp_r.get("Product Name") or "Traced Product"
#     if prod in ("None","none",None): prod = "Traced Product"

#     # ── % in range ────────────────────────────────────────────────────────────
#     def pct(vals, ll, ul):
#         if not vals or ll is None or ul is None: return None
#         return round(sum(1 for v in vals if ll<=v<=ul)/len(vals)*100,1)

#     tp_r20_vals = r20(tp_s); ec_r20_vals = r20(ec_s)
#     tp_pct = pct(tp_r20_vals, tp_ll, tp_ul)
#     ec_pct = pct(ec_r20_vals, ec_ll, ec_ul)

#     def status(p):
#         if p is None: return "Stable"
#         return "Good" if p>75 else ("Stable" if p>=25 else "Action Required")

#     ms_mean = smean(ms_s); cu_mean = smean(cu_s)
#     corr_ok = (ms_mean is not None and ms_mean<3.0) and (cu_mean is not None and cu_mean<0.5)
#     corr_status = "Good" if corr_ok else "Action Required"
#     tp_status   = status(tp_pct)
#     ec_status   = status(ec_pct)

#     tp_mean = smean(tp_s); ec_mean = smean(ec_s)
#     if tp_mean and tp_ul and tp_ll:
#         tp_dir = "HIGH" if tp_mean>tp_ul else ("LOW" if tp_mean<tp_ll else "OK")
#     else: tp_dir = "UNKNOWN"

#     frc_rows = [r for r in ade if any(w in str(r.get("Parameter","")).lower()
#                 for w in ("free residual","frc","halogen"))]
#     frc = float(frc_rows[0]["Value"]) if frc_rows else None
#     micro_status = "Good" if frc and frc>=0.2 else "Stable"

#     relay_r20 = r20(rel_s)
#     relay_firing = bool(relay_r20 and any(v>0 for v in relay_r20))

#     notes_text = "No service notes were recorded for this reporting period." if not notes else \
#         "\n".join(f"Date: {str(n.get('CreatedDate',''))[:10]}\n"
#                   f"{n.get('ServiceNotePlain') or n.get('ServiceNote','')}"
#                   for n in notes)

#     # ═══════════════════════════════════════════════════════════════════════════
#     # Build copilot_task.md
#     # ═══════════════════════════════════════════════════════════════════════════
#     task_lines = [
#         f"# Copilot Task — {site} | {month}",
#         "",
#         "> **Instructions for Copilot Agent:**",
#         "> 1. Read ALL the data below carefully",
#         "> 2. Follow EVERY rule in the RULES section",
#         "> 3. Write the narrative_cache.json file at the path shown",
#         "> 4. Do not add markdown, do not truncate, write valid JSON",
#         "",
#         "---",
#         "",
#         "## RULES (follow exactly)",
#         "",
#         "**CORROSION CONTROL:**",
#         f"- Use this exact wording: 'The average mild steel corrosion rate was X MPY against",
#         f"  the target of within 3.0 MPY, and the average copper corrosion rate was X MPY",
#         f"  against the target of within 0.5 MPY.'",
#         f"- Status: {corr_status}",
#         "",
#         "**SCALE CONTROL:**",
#         f"- Write ONLY about {prod}. Do NOT mention conductivity, pH, turbidity, or anything else.",
#         f"- Status MUST be: {tp_status} (because {tp_pct}% of recent readings are in Controller Setpoint range)",
#         f"- {tp_pct}% in range means: Good>75%, Stable 25-75%, Action Required<25%",
#         f"- Product is {tp_dir} (HIGH=above upper limit, LOW=below lower limit, OK=in range)",
#     ]

#     if tp_dir == "HIGH":
#         task_lines += [
#             f"- MUST include Observation: '{prod} concentration was above the Controller Setpoint upper",
#             f"  control limit of {fmt(tp_ul,1)} ppm, indicating overfeeding.'",
#             f"- MUST include Recommendation: 'Check dosing pump rate and reduce if running",
#             f"  above setpoint. Verify fluorometer calibration with a grab sample. Review",
#             f"  the dosing schedule and confirm the relay is not in manual override.'",
#         ]
#     elif tp_dir == "LOW":
#         task_lines += [
#             f"- MUST include Observation: '{prod} concentration was below the Controller Setpoint lower",
#             f"  control limit of {fmt(tp_ll,1)} ppm.'",
#             f"- MUST include Recommendation: 'Verify dosing pump operation and confirm it",
#             f"  is primed. Check product inventory level. Inspect the chemical feed line",
#             f"  for blockage or air lock. Verify fluorometer calibration with a grab sample.'",
#         ]

#     root_cause = ("Conductivity was stable during the same period, indicating this is a "
#                   "product feed or calibration issue, not a water loss event."
#                   if (ec_pct or 0) >= 75 else
#                   "Conductivity also declined during the same period, suggesting water loss, "
#                   "dilution, or excess blowdown as a contributing factor.")
#     task_lines += [
#         f"- Root cause to include: '{root_cause}'",
#         "",
#         "**MICROBIAL CONTROL:**",
#         f"- Write ONLY about FRC and ORP. Do NOT mention pH, turbidity, cell fouling, or anything else.",
#         f"- Status: {micro_status}",
#     ]

#     if frc is not None:
#         task_lines.append(f"- FRC from field test data: {frc} ppm. Comment on whether this is adequate.")
#     else:
#         task_lines.append(
#             "- FRC: NOT in field test data. Write: 'FRC data was not available in the field test data "
#             "for this reporting period and will be checked during the upcoming service visit.'")

#     task_lines += [
#         f"- Biocide relay was firing: {relay_firing}",
#         f"- MANDATORY ORP sentence: 'ORP spike response after timer-controlled biocide feed "
#         f"{'was consistent, indicating the system responded to treatment.' if relay_firing else 'was not consistent. Possible causes include low oxidizing biocide residual, biocide inventory issue, dosing pump lost prime, or incorrect timer schedule. These will be investigated at the upcoming service visit.'}'",
#         "- NEVER write absolute ORP values anywhere. Relative/spike language only.",
#         "",
#         "**WATER EFFICIENCY:**",
#         f"- Discuss conductivity and COC here (NOT in Scale Control).",
#         f"- Controller Setpoint conductivity: {fmt(ec_sp,0)} µS/cm, range {fmt(ec_ll,0)}–{fmt(ec_ul,0)} µS/cm",
#         f"- {ec_pct}% of recent readings within Controller Setpoint control range",
#         f"- 90-day average: {fmt(ec_mean,1)} µS/cm",
#         f"- Makeup water conductivity not available — state COC cannot be calculated,",
#         f"  should be captured at next service visit.",
#         "",
#         "**PRODUCT EFFICIENCY:**",
#         f"- Product name: {prod}",
#         f"- Mean: {fmt(tp_mean,1)} ppm vs Controller Setpoint target {fmt(tp_sp,1)} ppm",
#         f"- {tp_pct}% in range",
#         f"- Actual consumption not available — state this.",
#         "",
#         "**PROACTIVE SYSTEM SUPPORT:**",
#         "- Section title MUST be exactly: Proactive System Support (never 'Alarms')",
#         "- No alarm data available — state Ackumen average is 6 alarms per controller",
#         "- Incorporate any service note Actions Completed below",
#         "",
#         "**CHART COMMENTS (one sentence each — describe the trend shown in the chart):**",
#         "- corrosion_chart_comment: describe MS and Cu trend across W1-W4",
#         f"- scale_chart_comment: describe {prod} trend vs Controller Setpoint range {fmt(tp_ll,1)}–{fmt(tp_ul,1)} ppm",
#         "- orp_chart_comment: describe ORP spike pattern relative to biocide relay activity",
#         f"- conductivity_chart_comment: describe conductivity trend vs setpoint {fmt(ec_sp,0)} µS/cm",
#         "",
#         "---",
#         "",
#         "## SITE DATA",
#         "",
#         f"**Site:** {site}",
#         f"**Month:** {month}",
#         f"**Controller:** {controllers[0].get('SerialNumber','N/A') if controllers else 'N/A'}",
#         "",
#         "### Corrosion",
#         f"| Parameter | Mean | Min | Max | Target | Status |",
#         f"|---|---|---|---|---|---|",
#         f"| Mild Steel (MPY) | {fmt(ms_mean)} | {fmt(smin(ms_s))} | {fmt(smax(ms_s))} | <3.0 | {corr_status} |",
#         f"| Copper (MPY) | {fmt(cu_mean,4)} | {fmt(smin(cu_s),4)} | {fmt(smax(cu_s),4)} | <0.5 | {corr_status} |",
#         "",
#         "**Mild Steel recent 20 readings (MPY):**",
#         f"`{r20(ms_s)}`",
#         "",
#         "**Copper recent 20 readings (MPY):**",
#         f"`{r20(cu_s)}`",
#         "",
#         f"### {prod} (Scale Control)",
#         f"| Parameter | Value |",
#         f"|---|---|",
#         f"| Controller Setpoint (SP) | {fmt(tp_sp,1)} ppm |",
#         f"| Dead Band (DB) | {fmt(tp_db,1)} ppm |",
#         f"| Controller Setpoint Range | {fmt(tp_ll,1)} – {fmt(tp_ul,1)} ppm |",
#         f"| 90-day Mean | {fmt(tp_mean,1)} ppm |",
#         f"| % Recent in Controller Setpoint Range | {tp_pct}% ({status(tp_pct)}) |",
#         f"| Direction | {tp_dir} |",
#         "",
#         f"**{prod} recent 20 readings (ppm):**",
#         f"`{tp_r20_vals}`",
#         "",
#         "### Conductivity (Water Efficiency)",
#         f"| Parameter | Value |",
#         f"|---|---|",
#         f"| Controller Setpoint (SP) | {fmt(ec_sp,0)} µS/cm |",
#         f"| Dead Band (DB) | {fmt(ec_db,0)} µS/cm |",
#         f"| Controller Setpoint Range | {fmt(ec_ll,0)} – {fmt(ec_ul,0)} µS/cm |",
#         f"| 90-day Mean | {fmt(ec_mean,1)} µS/cm |",
#         f"| % Recent in Controller Setpoint Range | {ec_pct}% ({status(ec_pct)}) |",
#         "",
#         "**Conductivity recent 20 readings (µS/cm):**",
#         f"`{ec_r20_vals}`",
#         "",
#         "### Microbial",
#         f"| Parameter | Value |",
#         f"|---|---|",
#         f"| FRC (from field test data) | {'Not available' if frc is None else f'{frc} ppm'} |",
#         f"| Biocide relay firing | {relay_firing} |",
#         f"| Microbial status | {micro_status} |",
#         "",
#         "**Biocide relay recent 20 readings (1=ON, 0=OFF):**",
#         f"`{relay_r20}`",
#         "",
#         "**ORP recent 20 readings (DO NOT report these values — use spike language only):**",
#         f"`{r20(orp_s)}`",
#         "",
#         "### Supporting parameters (for Performance Summary table only — do not use in narrative sections)",
#         f"| Parameter | Mean | Min | Max |",
#         f"|---|---|---|---|",
#         f"| pH | {fmt(smean(ph_s),2)} | {fmt(smin(ph_s),2)} | {fmt(smax(ph_s),2)} |",
#         f"| Turbidity (NTU) | {fmt(smean(turb_s),2)} | {fmt(smin(turb_s),2)} | {fmt(smax(turb_s),2)} |",
#         f"| Cell Fouling (%) | {fmt(smean(cf_s),2)} | {fmt(smin(cf_s),2)} | {fmt(smax(cf_s),2)} |",
#         "",
#         "### Service Notes",
#         "",
#         notes_text,
#         "",
#         "---",
#         "",
#         "## COPILOT TASK",
#         "",
#         "> **Copy everything in the box below and paste into Copilot Chat.**",
#         "> **Make sure this file (copilot_task.md) is open in the editor.**",
#         "",
#         "```",
#         f"Read copilot_task.md carefully.",
#         f"",
#         f"Write the narrative for the {site} {month} cooling water performance report.",
#         f"Follow ALL rules in the RULES section exactly.",
#         f"",
#         f"Save your response as valid JSON to this exact file:",
#         f"data_store/{slug}/narrative_cache.json",
#         f"",
#         f"The JSON must have exactly these keys:",
#         f"{{",
#         f'  "corrosion_narrative": "2-3 sentences using exact SME wording",',
#         f'  "corrosion_chart_comment": "1 sentence describing the corrosion trend chart",',
#         f'  "scale_narrative": "3-5 sentences about {prod} ONLY — no other parameters",',
#         f'  "scale_chart_comment": "1 sentence describing the {prod} trend chart",',
#         f'  "microbial_narrative": "2-3 sentences about FRC and ORP ONLY — no pH/turbidity",',
#         f'  "orp_chart_comment": "1 sentence describing the ORP spike pattern chart",',
#         f'  "water_efficiency_narrative": "2-3 sentences about conductivity and COC",',
#         f'  "conductivity_chart_comment": "1 sentence describing the conductivity trend chart",',
#         f'  "product_efficiency_narrative": "2-3 sentences about {prod} consumption",',
#         f'  "proactive_support_narrative": "2-3 sentences about alarms and service notes",',
#         f'  "closing_summary": "2-3 sentences summarising the month overall"',
#         f"}}",
#         f"",
#         f"Rules:",
#         f"- Corrosion: use exact wording 'average mild steel corrosion rate was X MPY against the target of within 3.0 MPY'",
#         f"- Scale Control: {prod} ONLY. Status MUST be {tp_status} ({tp_pct}% in range).",
#         f"- {'Include Observation and Recommendation for ' + tp_dir + ' product level.' if tp_dir in ('HIGH','LOW') else 'Product is within range — no observation/recommendation needed.'}",
#         f"- Microbial: FRC and ORP ONLY. No pH, turbidity, cell fouling.",
#         f"- NEVER write absolute ORP values.",
#         f"- Proactive Support title: exactly 'Proactive System Support'",
#         f"- Write professional customer-facing language",
#         f"- Return ONLY valid JSON — no markdown, no explanation outside the JSON",
#         "```",
#         "",
#     ]

#     task_path = cache / "copilot_task.md"
#     task_path.write_text("\n".join(task_lines), encoding="utf-8")
#     print(f"✅  copilot_task.md  → {task_path}")

#     # ═══════════════════════════════════════════════════════════════════════════
#     # Create empty narrative_cache.json template
#     # ═══════════════════════════════════════════════════════════════════════════
#     empty = {
#         "corrosion_narrative":           "",
#         "corrosion_chart_comment":       "",
#         "scale_narrative":               "",
#         "scale_chart_comment":           "",
#         "microbial_narrative":           "",
#         "orp_chart_comment":             "",
#         "water_efficiency_narrative":    "",
#         "conductivity_chart_comment":    "",
#         "product_efficiency_narrative":  "",
#         "proactive_support_narrative":   "",
#         "closing_summary":               "",
#         "_status": "EMPTY — Copilot must fill this in",
#         "_site":   site,
#         "_month":  month,
#     }
#     narrative_path = cache / "narrative_cache.json"
#     narrative_path.write_text(json.dumps(empty, indent=2), encoding="utf-8")
#     print(f"✅  narrative_cache.json → {narrative_path}  (Copilot fills this in)")

#     print(f"")
#     print(f"Next steps:")
#     print(f"  1. Open VS Code:  code .")
#     print(f"  2. Open file:     data_store/{slug}/copilot_task.md")
#     print(f"  3. Also open:     data_store/{slug}/narrative_cache.json")
#     print(f"  4. Copilot Chat:  Ctrl+Shift+I  (Agent mode)")
#     print(f"  5. Copy the COPILOT TASK block (bottom of copilot_task.md)")
#     print(f"     and paste into Copilot Chat")
#     print(f"  6. Copilot writes narrative_cache.json")
#     print(f"  7. Run: python generate_report.py --site \"{site}\" --month \"{month}\"")


# if __name__ == "__main__":
#     main()


# """
# prepare_copilot_task.py
# ────────────────────────
# Step 3 — Run AFTER prefetch_site.py and prepare_report_context.py.

# Creates two files in data_store/<slug>/:

#   copilot_task.md      ← Open this in VS Code, paste Section marked
#                           COPILOT TASK into Copilot Chat.
#                           Copilot writes the narrative JSON back.

#   narrative_cache.json ← Empty template. Copilot fills this in.
#                           generate_report.py reads from here.

# USAGE
# ─────
#     python prepare_copilot_task.py --site "Synthomer Chester SC (US)" --month "May 2026"

# WORKFLOW
# ────────
#     1. python prefetch_site.py          --site "..." --month "..."
#     2. python prepare_copilot_task.py   --site "..." --month "..."
#     3. Open VS Code → open copilot_task.md
#     4. Open Copilot Chat (Ctrl+Shift+I, Agent mode)
#     5. Paste the COPILOT TASK section into Copilot Chat
#     6. Copilot writes narrative_cache.json
#     7. python generate_report.py        --site "..." --month "..."
# """

# import argparse
# import json
# import re
# import sys
# from pathlib import Path

# ROOT       = Path(__file__).parent
# DATA_STORE = ROOT / "data_store"


# def parse_args():
#     p = argparse.ArgumentParser()
#     p.add_argument("--site",  required=True)
#     p.add_argument("--month", required=True)
#     return p.parse_args()


# def slugify(text):
#     return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


# def _load(path, default):
#     return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


# def fmt(v, d=2):
#     try:    return f"{float(v):.{d}f}" if v not in (None, "NULL", "") else "N/A"
#     except: return "N/A"


# def main():
#     args  = parse_args()
#     site  = args.site
#     month = args.month
#     slug  = slugify(f"{site}_{month}")
#     cache = DATA_STORE / slug

#     if not (cache / "manifest.json").exists():
#         print(f"[ERROR] No prefetch data at {cache}")
#         print(f"  Run first: python prefetch_site.py --site \"{site}\" --month \"{month}\"")
#         sys.exit(1)

#     # ── Load all data ─────────────────────────────────────────────────────────
#     controllers = _load(cache / "controllers.json", [])
#     scc         = _load(cache / "scc.json",          [])
#     ade         = _load(cache / "ade_data.json",     [])
#     notes       = _load(cache / "service_notes.json",[])

#     telem_sensors = {}
#     for f in (cache / "telemetry").glob("*_summary.json"):
#         d = json.loads(f.read_text())
#         for name, stats in d.get("sensors", {}).items():
#             telem_sensors[name.lower()] = stats

#     # ── Helper: find sensor by keywords ──────────────────────────────────────
#     def find(*kws):
#         for key, stats in telem_sensors.items():
#             if all(w in key for w in kws):
#                 return stats
#         return {}

#     def r20(stats):   return [round(float(v),4) for v in stats.get("recent_20",[])]
#     def smean(stats): v=stats.get("mean"); return float(v) if v is not None else None
#     def smin(stats):  v=stats.get("min");  return float(v) if v is not None else None
#     def smax(stats):  v=stats.get("max");  return float(v) if v is not None else None

#     ms_s   = find("corrosion_probe_1")
#     cu_s   = find("corrosion_probe_2")
#     ec_s   = find("electrode_conductivity")
#     tp_s   = find("fluorometer_ch_1") or find("fluorometer","ch1")
#     ph_s   = find("ph_probe") or find("ph")
#     orp_s  = find("orp")
#     turb_s = find("turbidity")
#     cf_s   = find("cellfouling") or find("cell_fouling")
#     rel_s  = find("relay3") or find("relay5") or find("relay1")

#     # ── Controller Setpoints ─────────────────────────────────────────────────────────
#     def scc_row(*kws):
#         for r in scc:
#             s = (str(r.get("Input Sensor",""))+str(r.get("Sensor Name",""))).lower()
#             if all(w in s for w in kws): return r
#         return {}

#     ec_r = scc_row("conductivity")
#     tp_r = scc_row("fluorometer_ch_1") or scc_row("fluorometer","ch1") or scc_row("traced")

#     def fv(row, key):
#         v = row.get(key)
#         try:    return float(v) if v not in (None,"NULL","") else None
#         except: return None

#     ec_sp = fv(ec_r,"SP"); ec_db = fv(ec_r,"DB")
#     tp_sp = fv(tp_r,"SP"); tp_db = fv(tp_r,"DB")
#     ec_ll = (ec_sp-ec_db) if ec_sp and ec_db else None
#     ec_ul = (ec_sp+ec_db) if ec_sp and ec_db else None
#     tp_ll = (tp_sp-tp_db) if tp_sp and tp_db else None
#     tp_ul = (tp_sp+tp_db) if tp_sp and tp_db else None
#     prod  = tp_r.get("Product Name") or "Traced Product"
#     if prod in ("None","none",None): prod = "Traced Product"

#     # ── % in range ────────────────────────────────────────────────────────────
#     def pct(vals, ll, ul):
#         if not vals or ll is None or ul is None: return None
#         return round(sum(1 for v in vals if ll<=v<=ul)/len(vals)*100,1)

#     tp_r20_vals = r20(tp_s); ec_r20_vals = r20(ec_s)
#     tp_pct = pct(tp_r20_vals, tp_ll, tp_ul)
#     ec_pct = pct(ec_r20_vals, ec_ll, ec_ul)

#     def status(p):
#         if p is None: return "Stable"
#         return "Good" if p>75 else ("Stable" if p>=25 else "Action Required")

#     ms_mean = smean(ms_s); cu_mean = smean(cu_s)
#     corr_ok = (ms_mean is not None and ms_mean<3.0) and (cu_mean is not None and cu_mean<0.5)
#     corr_status = "Good" if corr_ok else "Action Required"
#     tp_status   = status(tp_pct)
#     ec_status   = status(ec_pct)

#     tp_mean = smean(tp_s); ec_mean = smean(ec_s)
#     if tp_mean and tp_ul and tp_ll:
#         tp_dir = "HIGH" if tp_mean>tp_ul else ("LOW" if tp_mean<tp_ll else "OK")
#     else: tp_dir = "UNKNOWN"

#     frc_rows = [r for r in ade if any(w in str(r.get("Parameter","")).lower()
#                 for w in ("free residual","frc","halogen"))]
#     frc = float(frc_rows[0]["Value"]) if frc_rows else None
#     micro_status = "Good" if frc and frc>=0.2 else "Stable"

#     relay_r20 = r20(rel_s)
#     relay_triggered = bool(relay_r20 and any(v>0 for v in relay_r20))

#     notes_text = "No service notes were recorded for this reporting period." if not notes else \
#         "\n".join(f"Date: {str(n.get('CreatedDate',''))[:10]}\n"
#                   f"{n.get('ServiceNotePlain') or n.get('ServiceNote','')}"
#                   for n in notes)

#     # ═══════════════════════════════════════════════════════════════════════════
#     # Build copilot_task.md
#     # ═══════════════════════════════════════════════════════════════════════════
#     task_lines = [
#         f"# Copilot Task — {site} | {month}",
#         "",
#         "> **Instructions for Copilot Agent:**",
#         "> 1. Read ALL the data below carefully",
#         "> 2. Follow EVERY rule in the RULES section",
#         "> 3. Write the narrative_cache.json file at the path shown",
#         "> 4. Do not add markdown, do not truncate, write valid JSON",
#         "",
#         "---",
#         "",
#         "## RULES (follow exactly)",
#         "",
#         "**CORROSION CONTROL:**",
#         f"- Use this exact wording: 'The average mild steel corrosion rate was X MPY against",
#         f"  the target of within 3.0 MPY, and the average copper corrosion rate was X MPY",
#         f"  against the target of within 0.5 MPY.'",
#         f"- Status: {corr_status}",
#         "",
#         "**SCALE CONTROL:**",
#         f"- Write ONLY about {prod}. Do NOT mention conductivity, pH, turbidity, or anything else.",
#         f"- Status MUST be: {tp_status} (because {tp_pct}% of recent readings are in Controller Setpoint range)",
#         f"- {tp_pct}% in range means: Good>75%, Stable 25-75%, Action Required<25%",
#         f"- Product is {tp_dir} (HIGH=above upper limit, LOW=below lower limit, OK=in range)",
#     ]

#     if tp_dir == "HIGH":
#         task_lines += [
#             f"- MUST include Observation: '{prod} concentration was above the Controller Setpoint upper",
#             f"  control limit of {fmt(tp_ul,1)} ppm, indicating overfeeding.'",
#             f"- MUST include Recommendation: 'Check dosing pump rate and reduce if running",
#             f"  above setpoint. Verify fluorometer calibration with a grab sample. Review",
#             f"  the dosing schedule and confirm the relay is not in manual override.'",
#         ]
#     elif tp_dir == "LOW":
#         task_lines += [
#             f"- MUST include Observation: '{prod} concentration was below the Controller Setpoint lower",
#             f"  control limit of {fmt(tp_ll,1)} ppm.'",
#             f"- MUST include Recommendation: 'Verify dosing pump operation and confirm it",
#             f"  is primed. Check product inventory level. Inspect the chemical feed line",
#             f"  for blockage or air lock. Verify fluorometer calibration with a grab sample.'",
#         ]

#     root_cause = ("Conductivity was stable during the same period, indicating this is a "
#                   "product feed or calibration issue, not a water loss event."
#                   if (ec_pct or 0) >= 75 else
#                   "Conductivity also declined during the same period, suggesting water loss, "
#                   "dilution, or excess blowdown as a contributing factor.")
#     task_lines += [
#         f"- Root cause to include: '{root_cause}'",
#         "",
#         "**MICROBIAL CONTROL:**",
#         f"- Write ONLY about FRC and ORP. Do NOT mention pH, turbidity, cell fouling, or anything else.",
#         f"- Status: {micro_status}",
#     ]

#     if frc is not None:
#         task_lines.append(f"- FRC from field test data: {frc} ppm. Comment on whether this is adequate.")
#     else:
#         task_lines.append(
#             "- FRC: NOT in field test data. Write: 'FRC data was not available in the field test data "
#             "for this reporting period and will be checked during the upcoming service visit.'")

#     task_lines += [
#         f"- Biocide relay was triggered: {relay_triggered}",
#         f"- MANDATORY ORP sentence: 'ORP spike response after timer-controlled biocide feed "
#         f"{'was consistent, indicating the system responded to treatment.' if relay_triggered else 'was not consistent. Possible causes include low oxidizing biocide residual, biocide inventory issue, dosing pump lost prime, or incorrect timer schedule. These will be investigated at the upcoming service visit.'}'",
#         "- NEVER write absolute ORP values anywhere. Relative/spike language only.",
#         "",
#         "**WATER EFFICIENCY:**",
#         f"- Discuss conductivity and COC here (NOT in Scale Control).",
#         f"- Controller Setpoint conductivity: {fmt(ec_sp,0)} µS/cm, range {fmt(ec_ll,0)}–{fmt(ec_ul,0)} µS/cm",
#         f"- {ec_pct}% of recent readings within Controller Setpoint control range",
#         f"- 90-day average: {fmt(ec_mean,1)} µS/cm",
#         f"- Makeup water conductivity not available — state COC cannot be calculated,",
#         f"  should be captured at next service visit.",
#         "",
#         "**PRODUCT EFFICIENCY:**",
#         f"- Product name: {prod}",
#         f"- Mean: {fmt(tp_mean,1)} ppm vs Controller Setpoint target {fmt(tp_sp,1)} ppm",
#         f"- {tp_pct}% in range",
#         f"- Actual consumption not available — state this.",
#         "",
#         "**PROACTIVE SYSTEM SUPPORT:**",
#         "- Section title MUST be exactly: Proactive System Support (never 'Alarms')",
#         "- No alarm data available — state Ackumen average is 6 alarms per controller",
#         "- Incorporate any service note Actions Completed below",
#         "",
#         "**CHART COMMENTS (one sentence each — describe the trend shown in the chart):**",
#         "- corrosion_chart_comment: describe MS and Cu trend across W1-W4",
#         f"- scale_chart_comment: describe {prod} trend vs Controller Setpoint range {fmt(tp_ll,1)}–{fmt(tp_ul,1)} ppm",
#         "- orp_chart_comment: describe ORP spike pattern relative to biocide relay activity",
#         f"- conductivity_chart_comment: describe conductivity trend vs setpoint {fmt(ec_sp,0)} µS/cm",
#         "",
#         "---",
#         "",
#         "## SITE DATA",
#         "",
#         f"**Site:** {site}",
#         f"**Month:** {month}",
#         f"**Controller:** {controllers[0].get('SerialNumber','N/A') if controllers else 'N/A'}",
#         "",
#         "### Corrosion",
#         f"| Parameter | Mean | Min | Max | Target | Status |",
#         f"|---|---|---|---|---|---|",
#         f"| Mild Steel (MPY) | {fmt(ms_mean)} | {fmt(smin(ms_s))} | {fmt(smax(ms_s))} | <3.0 | {corr_status} |",
#         f"| Copper (MPY) | {fmt(cu_mean,4)} | {fmt(smin(cu_s),4)} | {fmt(smax(cu_s),4)} | <0.5 | {corr_status} |",
#         "",
#         "**Mild Steel recent 20 readings (MPY):**",
#         f"`{r20(ms_s)}`",
#         "",
#         "**Copper recent 20 readings (MPY):**",
#         f"`{r20(cu_s)}`",
#         "",
#         f"### {prod} (Scale Control)",
#         f"| Parameter | Value |",
#         f"|---|---|",
#         f"| Controller Setpoint (SP) | {fmt(tp_sp,1)} ppm |",
#         f"| Dead Band (DB) | {fmt(tp_db,1)} ppm |",
#         f"| Controller Setpoint Range | {fmt(tp_ll,1)} – {fmt(tp_ul,1)} ppm |",
#         f"| 90-day Mean | {fmt(tp_mean,1)} ppm |",
#         f"| % Recent in Controller Setpoint Range | {tp_pct}% ({status(tp_pct)}) |",
#         f"| Direction | {tp_dir} |",
#         "",
#         f"**{prod} recent 20 readings (ppm):**",
#         f"`{tp_r20_vals}`",
#         "",
#         "### Conductivity (Water Efficiency)",
#         f"| Parameter | Value |",
#         f"|---|---|",
#         f"| Controller Setpoint (SP) | {fmt(ec_sp,0)} µS/cm |",
#         f"| Dead Band (DB) | {fmt(ec_db,0)} µS/cm |",
#         f"| Controller Setpoint Range | {fmt(ec_ll,0)} – {fmt(ec_ul,0)} µS/cm |",
#         f"| 90-day Mean | {fmt(ec_mean,1)} µS/cm |",
#         f"| % Recent in Controller Setpoint Range | {ec_pct}% ({status(ec_pct)}) |",
#         "",
#         "**Conductivity recent 20 readings (µS/cm):**",
#         f"`{ec_r20_vals}`",
#         "",
#         "### Microbial",
#         f"| Parameter | Value |",
#         f"|---|---|",
#         f"| FRC (from field test data) | {'Not available' if frc is None else f'{frc} ppm'} |",
#         f"| Biocide relay triggered | {relay_triggered} |",
#         f"| Microbial status | {micro_status} |",
#         "",
#         "**Biocide relay recent 20 readings (1=ON, 0=OFF):**",
#         f"`{relay_r20}`",
#         "",
#         "**ORP recent 20 readings (DO NOT report these values — use spike language only):**",
#         f"`{r20(orp_s)}`",
#         "",
#         "### Supporting parameters (for Performance Summary table only — do not use in narrative sections)",
#         f"| Parameter | Mean | Min | Max |",
#         f"|---|---|---|---|",
#         f"| pH | {fmt(smean(ph_s),2)} | {fmt(smin(ph_s),2)} | {fmt(smax(ph_s),2)} |",
#         f"| Turbidity (NTU) | {fmt(smean(turb_s),2)} | {fmt(smin(turb_s),2)} | {fmt(smax(turb_s),2)} |",
#         f"| Cell Fouling (%) | {fmt(smean(cf_s),2)} | {fmt(smin(cf_s),2)} | {fmt(smax(cf_s),2)} |",
#         "",
#         "### Service Notes",
#         "",
#         notes_text,
#         "",
#         "---",
#         "",
#         "## COPILOT TASK",
#         "",
#         "> **Copy everything in the box below and paste into Copilot Chat.**",
#         "> **Make sure this file (copilot_task.md) is open in the editor.**",
#         "",
#         "```",
#         f"Read copilot_task.md carefully.",
#         f"",
#         f"Write the narrative for the {site} {month} cooling water performance report.",
#         f"Follow ALL rules in the RULES section exactly.",
#         f"",
#         f"Save your response as valid JSON to this exact file:",
#         f"data_store/{slug}/narrative_cache.json",
#         f"",
#         f"The JSON must have exactly these keys:",
#         f"{{",
#         f'  "corrosion_narrative": "2-3 sentences using exact SME wording",',
#         f'  "corrosion_chart_comment": "1 sentence describing the corrosion trend chart",',
#         f'  "scale_narrative": "3-5 sentences about {prod} ONLY — no other parameters",',
#         f'  "scale_chart_comment": "1 sentence describing the {prod} trend chart",',
#         f'  "microbial_narrative": "2-3 sentences about FRC and ORP ONLY — no pH/turbidity",',
#         f'  "orp_chart_comment": "1 sentence describing the ORP spike pattern chart",',
#         f'  "water_efficiency_narrative": "2-3 sentences about conductivity and COC",',
#         f'  "conductivity_chart_comment": "1 sentence describing the conductivity trend chart",',
#         f'  "product_efficiency_narrative": "2-3 sentences about {prod} consumption",',
#         f'  "proactive_support_narrative": "2-3 sentences about alarms and service notes",',
#         f'  "closing_summary": "2-3 sentences summarising the month overall"',
#         f"}}",
#         f"",
#         f"Rules:",
#         f"- Corrosion: use exact wording 'average mild steel corrosion rate was X MPY against the target of within 3.0 MPY'",
#         f"- Scale Control: {prod} ONLY. Status MUST be {tp_status} ({tp_pct}% in range).",
#         f"- {'Include Observation and Recommendation for ' + tp_dir + ' product level.' if tp_dir in ('HIGH','LOW') else 'Product is within range — no observation/recommendation needed.'}",
#         f"- Microbial: FRC and ORP ONLY. No pH, turbidity, cell fouling.",
#         f"- NEVER write absolute ORP values.",
#         f"- Proactive Support title: exactly 'Proactive System Support'",
#         f"- Write professional customer-facing language",
#         f"- Return ONLY valid JSON — no markdown, no explanation outside the JSON",
#         "```",
#         "",
#     ]

#     task_path = cache / "copilot_task.md"
#     task_path.write_text("\n".join(task_lines), encoding="utf-8")
#     print(f"✅  copilot_task.md  → {task_path}")

#     # ═══════════════════════════════════════════════════════════════════════════
#     # Create empty narrative_cache.json template
#     # ═══════════════════════════════════════════════════════════════════════════
#     empty = {
#         "corrosion_narrative":           "",
#         "corrosion_chart_comment":       "",
#         "scale_narrative":               "",
#         "scale_chart_comment":           "",
#         "microbial_narrative":           "",
#         "orp_chart_comment":             "",
#         "water_efficiency_narrative":    "",
#         "conductivity_chart_comment":    "",
#         "product_efficiency_narrative":  "",
#         "proactive_support_narrative":   "",
#         "closing_summary":               "",
#         "_status": "EMPTY — Copilot must fill this in",
#         "_site":   site,
#         "_month":  month,
#     }
#     narrative_path = cache / "narrative_cache.json"
#     narrative_path.write_text(json.dumps(empty, indent=2), encoding="utf-8")
#     print(f"✅  narrative_cache.json → {narrative_path}  (Copilot fills this in)")

#     print(f"")
#     print(f"Next steps:")
#     print(f"  1. Open VS Code:  code .")
#     print(f"  2. Open file:     data_store/{slug}/copilot_task.md")
#     print(f"  3. Also open:     data_store/{slug}/narrative_cache.json")
#     print(f"  4. Copilot Chat:  Ctrl+Shift+I  (Agent mode)")
#     print(f"  5. Copy the COPILOT TASK block (bottom of copilot_task.md)")
#     print(f"     and paste into Copilot Chat")
#     print(f"  6. Copilot writes narrative_cache.json")
#     print(f"  7. Run: python generate_report.py --site \"{site}\" --month \"{month}\"")


# if __name__ == "__main__":
#     main()


# """
# prepare_copilot_task.py
# ────────────────────────
# Step 3 — Run AFTER prefetch_site.py and prepare_report_context.py.

# Creates two files in data_store/<slug>/:

#   copilot_task.md      ← Open this in VS Code, paste Section marked
#                           COPILOT TASK into Copilot Chat.
#                           Copilot writes the narrative JSON back.

#   narrative_cache.json ← Empty template. Copilot fills this in.
#                           generate_report.py reads from here.

# USAGE
# ─────
#     python prepare_copilot_task.py --site "Synthomer Chester SC (US)" --month "May 2026"

# WORKFLOW
# ────────
#     1. python prefetch_site.py          --site "..." --month "..."
#     2. python prepare_copilot_task.py   --site "..." --month "..."
#     3. Open VS Code → open copilot_task.md
#     4. Open Copilot Chat (Ctrl+Shift+I, Agent mode)
#     5. Paste the COPILOT TASK section into Copilot Chat
#     6. Copilot writes narrative_cache.json
#     7. python generate_report.py        --site "..." --month "..."
# """

# import argparse
# import json
# import re
# import sys
# from pathlib import Path

# ROOT       = Path(__file__).parent
# DATA_STORE = ROOT / "data_store"


# def parse_args():
#     p = argparse.ArgumentParser()
#     p.add_argument("--site",  required=True)
#     p.add_argument("--month", required=True)
#     return p.parse_args()


# def slugify(text):
#     return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


# def _load(path, default):
#     return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


# def fmt(v, d=2):
#     try:    return f"{float(v):.{d}f}" if v not in (None, "NULL", "") else "N/A"
#     except: return "N/A"


# def _load_mu_conductivity(site):
#     """Read MU conductivity from data/MU_conductivity.xlsx if present. Returns float or None.

#     Kept in sync with generate_report.py's _load_mu_conductivity() — both scripts
#     need to agree on whether MU conductivity is available for a site, otherwise
#     the Copilot narrative and the generated COC table will contradict each other.
#     """
#     mu_file = ROOT / "data" / "MU_conductivity.xlsx"
#     if not mu_file.exists():
#         return None
#     try:
#         import openpyxl
#         wb = openpyxl.load_workbook(mu_file, data_only=True)
#         ws = wb.active
#         for row in ws.iter_rows(min_row=2, values_only=True):
#             if not row or not row[0]: continue
#             if str(row[0]).strip().lower() == site.strip().lower():
#                 val = row[3] if len(row) > 3 else None
#                 if val is None or str(val).lower() in ("no data","none","",None):
#                     return None
#                 try: return float(val)
#                 except: return None
#     except Exception as e:
#         print(f"  [WARN] Could not read MU_conductivity.xlsx: {e}")
#     return None


# def compute_coc(ec_sp, ec_mean, mu_cond):
#     """Same COC math as generate_report.py's compute_coc(), reduced to the two inputs
#     this script has on hand (Controller Setpoint conductivity + monthly mean conductivity)."""
#     if mu_cond is None or mu_cond == 0:
#         return {"mu_available": False, "mu_cond": None,
#                 "target_coc": None, "actual_coc": None,
#                 "deviation_pct": None, "coc_status": None}

#     target_coc = (ec_sp / mu_cond) if ec_sp else None
#     actual_coc = (ec_mean / mu_cond) if ec_mean else None

#     if target_coc and actual_coc:
#         dev = abs(actual_coc - target_coc) / target_coc * 100
#         if   dev <= 20: coc_status = "Good"
#         elif dev <= 50: coc_status = "Okay"
#         else:           coc_status = "Bad"
#     else:
#         dev, coc_status = None, None

#     return {
#         "mu_available": True, "mu_cond": round(mu_cond, 2),
#         "target_coc": round(target_coc, 2) if target_coc else None,
#         "actual_coc": round(actual_coc, 2) if actual_coc else None,
#         "deviation_pct": round(dev, 1) if dev is not None else None,
#         "coc_status": coc_status,
#     }


# def main():
#     args  = parse_args()
#     site  = args.site
#     month = args.month
#     slug  = slugify(f"{site}_{month}")
#     cache = DATA_STORE / slug

#     if not (cache / "manifest.json").exists():
#         print(f"[ERROR] No prefetch data at {cache}")
#         print(f"  Run first: python prefetch_site.py --site \"{site}\" --month \"{month}\"")
#         sys.exit(1)

#     # ── Load all data ─────────────────────────────────────────────────────────
#     controllers = _load(cache / "controllers.json", [])
#     scc         = _load(cache / "scc.json",          [])
#     ade         = _load(cache / "ade_data.json",     [])
#     notes       = _load(cache / "service_notes.json",[])

#     telem_sensors = {}
#     for f in (cache / "telemetry").glob("*_summary.json"):
#         d = json.loads(f.read_text())
#         for name, stats in d.get("sensors", {}).items():
#             telem_sensors[name.lower()] = stats

#     # ── Helper: find sensor by keywords ──────────────────────────────────────
#     def find(*kws):
#         for key, stats in telem_sensors.items():
#             if all(w in key for w in kws):
#                 return stats
#         return {}

#     def r20(stats):   return [round(float(v),4) for v in stats.get("recent_20",[])]
#     def smean(stats): v=stats.get("mean"); return float(v) if v is not None else None
#     def smin(stats):  v=stats.get("min");  return float(v) if v is not None else None
#     def smax(stats):  v=stats.get("max");  return float(v) if v is not None else None

#     ms_s   = find("corrosion_probe_1")
#     cu_s   = find("corrosion_probe_2")
#     ec_s   = find("electrode_conductivity")
#     tp_s   = find("fluorometer_ch_1") or find("fluorometer","ch1")
#     ph_s   = find("ph_probe") or find("ph")
#     orp_s  = find("orp")
#     turb_s = find("turbidity")
#     cf_s   = find("cellfouling") or find("cell_fouling")
#     rel_s  = find("relay3") or find("relay5") or find("relay1")

#     # ── Controller Setpoints ─────────────────────────────────────────────────────────
#     def scc_row(*kws):
#         for r in scc:
#             s = (str(r.get("Input Sensor",""))+str(r.get("Sensor Name",""))).lower()
#             if all(w in s for w in kws): return r
#         return {}

#     ec_r = scc_row("conductivity")
#     tp_r = scc_row("fluorometer_ch_1") or scc_row("fluorometer","ch1") or scc_row("traced")

#     def fv(row, key):
#         v = row.get(key)
#         try:    return float(v) if v not in (None,"NULL","") else None
#         except: return None

#     ec_sp = fv(ec_r,"SP"); ec_db = fv(ec_r,"DB")
#     tp_sp = fv(tp_r,"SP"); tp_db = fv(tp_r,"DB")
#     ec_ll = (ec_sp-ec_db) if ec_sp and ec_db else None
#     ec_ul = (ec_sp+ec_db) if ec_sp and ec_db else None
#     tp_ll = (tp_sp-tp_db) if tp_sp and tp_db else None
#     tp_ul = (tp_sp+tp_db) if tp_sp and tp_db else None
#     prod  = tp_r.get("Product Name") or "Traced Product"
#     if prod in ("None","none",None): prod = "Traced Product"

#     # ── % in range ────────────────────────────────────────────────────────────
#     def pct(vals, ll, ul):
#         if not vals or ll is None or ul is None: return None
#         return round(sum(1 for v in vals if ll<=v<=ul)/len(vals)*100,1)

#     tp_r20_vals = r20(tp_s); ec_r20_vals = r20(ec_s)
#     tp_pct = pct(tp_r20_vals, tp_ll, tp_ul)
#     ec_pct = pct(ec_r20_vals, ec_ll, ec_ul)

#     def status(p):
#         if p is None: return "Stable"
#         return "Good" if p>75 else ("Stable" if p>=25 else "Action Required")

#     ms_mean = smean(ms_s); cu_mean = smean(cu_s)
#     corr_ok = (ms_mean is not None and ms_mean<3.0) and (cu_mean is not None and cu_mean<0.5)
#     corr_status = "Good" if corr_ok else "Action Required"
#     tp_status   = status(tp_pct)
#     ec_status   = status(ec_pct)

#     tp_mean = smean(tp_s); ec_mean = smean(ec_s)
#     if tp_mean and tp_ul and tp_ll:
#         tp_dir = "HIGH" if tp_mean>tp_ul else ("LOW" if tp_mean<tp_ll else "OK")
#     else: tp_dir = "UNKNOWN"

#     frc_rows = [r for r in ade if any(w in str(r.get("Parameter","")).lower()
#                 for w in ("free residual","frc","halogen"))]
#     frc = float(frc_rows[0]["Value"]) if frc_rows else None
#     micro_status = "Good" if frc and frc>=0.2 else "Stable"

#     relay_r20 = r20(rel_s)
#     relay_triggered = bool(relay_r20 and any(v>0 for v in relay_r20))

#     notes_text = "No service notes were recorded for this reporting period." if not notes else \
#         "\n".join(f"Date: {str(n.get('CreatedDate',''))[:10]}\n"
#                   f"{n.get('ServiceNotePlain') or n.get('ServiceNote','')}"
#                   for n in notes)

#     # ═══════════════════════════════════════════════════════════════════════════
#     # Build copilot_task.md
#     # ═══════════════════════════════════════════════════════════════════════════
#     task_lines = [
#         f"# Copilot Task — {site} | {month}",
#         "",
#         "> **Instructions for Copilot Agent:**",
#         "> 1. Read ALL the data below carefully",
#         "> 2. Follow EVERY rule in the RULES section",
#         "> 3. Write the narrative_cache.json file at the path shown",
#         "> 4. Do not add markdown, do not truncate, write valid JSON",
#         "",
#         "---",
#         "",
#         "## RULES (follow exactly)",
#         "",
#         "**CORROSION CONTROL:**",
#         f"- Use this exact wording: 'The average mild steel corrosion rate was X MPY against",
#         f"  the target of within 3.0 MPY, and the average copper corrosion rate was X MPY",
#         f"  against the target of within 0.5 MPY.'",
#         f"- Status: {corr_status}",
#         "",
#         "**SCALE CONTROL:**",
#         f"- Write ONLY about {prod}. Do NOT mention conductivity, pH, turbidity, or anything else.",
#         f"- Status MUST be: {tp_status} (because {tp_pct}% of recent readings are in Controller Setpoint range)",
#         f"- {tp_pct}% in range means: Good>75%, Stable 25-75%, Action Required<25%",
#         f"- Product is {tp_dir} (HIGH=above upper limit, LOW=below lower limit, OK=in range)",
#     ]

#     if tp_dir == "HIGH":
#         task_lines += [
#             f"- MUST include Observation: '{prod} concentration was above the Controller Setpoint upper",
#             f"  control limit of {fmt(tp_ul,1)} ppm, indicating overfeeding.'",
#             f"- MUST include Recommendation: 'Check dosing pump rate and reduce if running",
#             f"  above setpoint. Verify fluorometer calibration with a grab sample. Review",
#             f"  the dosing schedule and confirm the relay is not in manual override.'",
#         ]
#     elif tp_dir == "LOW":
#         task_lines += [
#             f"- MUST include Observation: '{prod} concentration was below the Controller Setpoint lower",
#             f"  control limit of {fmt(tp_ll,1)} ppm.'",
#             f"- MUST include Recommendation: 'Verify dosing pump operation and confirm it",
#             f"  is primed. Check product inventory level. Inspect the chemical feed line",
#             f"  for blockage or air lock. Verify fluorometer calibration with a grab sample.'",
#         ]

#     root_cause = ("Conductivity was stable during the same period, indicating this is a "
#                   "product feed or calibration issue, not a water loss event."
#                   if (ec_pct or 0) >= 75 else
#                   "Conductivity also declined during the same period, suggesting water loss, "
#                   "dilution, or excess blowdown as a contributing factor.")
#     task_lines += [
#         f"- Root cause to include: '{root_cause}'",
#         "",
#         "**MICROBIAL CONTROL:**",
#         f"- Write ONLY about FRC and ORP. Do NOT mention pH, turbidity, cell fouling, or anything else.",
#         f"- Status: {micro_status}",
#     ]

#     if frc is not None:
#         task_lines.append(f"- FRC from field test data: {frc} ppm. Comment on whether this is adequate.")
#     else:
#         task_lines.append(
#             "- FRC: NOT in field test data. Write: 'FRC data was not available in the field test data "
#             "for this reporting period and will be checked during the upcoming service visit.'")

#     task_lines += [
#         f"- Biocide relay was triggered: {relay_triggered}",
#         f"- MANDATORY ORP sentence: 'ORP spike response after timer-controlled biocide feed "
#         f"{'was consistent, indicating the system responded to treatment.' if relay_triggered else 'was not consistent. Possible causes include low oxidizing biocide residual, biocide inventory issue, dosing pump lost prime, or incorrect timer schedule. These will be investigated at the upcoming service visit.'}'",
#         "- NEVER write absolute ORP values anywhere. Relative/spike language only.",
#         "",
#         "**WATER EFFICIENCY:**",
#         f"- Discuss conductivity and COC here (NOT in Scale Control).",
#         f"- Controller Setpoint conductivity: {fmt(ec_sp,0)} µS/cm, range {fmt(ec_ll,0)}–{fmt(ec_ul,0)} µS/cm",
#         f"- {ec_pct}% of recent readings within Controller Setpoint control range",
#         f"- 90-day average: {fmt(ec_mean,1)} µS/cm",
#     ]

#     mu_cond = _load_mu_conductivity(site)
#     coc = compute_coc(ec_sp, ec_mean, mu_cond)
#     mu_row_text  = f"{coc['mu_cond']} µS/cm" if coc["mu_available"] else "Not available"
#     coc_dev_text = f"{coc['deviation_pct']}%" if coc["deviation_pct"] is not None else "N/A"
#     if coc["mu_available"] and coc["target_coc"] is not None and coc["actual_coc"] is not None:
#         task_lines += [
#             f"- Makeup water conductivity: {coc['mu_cond']} µS/cm",
#             f"- Target COC (Controller Setpoint / MU conductivity): {coc['target_coc']}",
#             f"- Actual COC (90-day average conductivity / MU conductivity): {coc['actual_coc']}",
#             f"- COC deviation from target: {coc['deviation_pct']}%  →  Status: {coc['coc_status']}",
#             f"- State the actual COC value and deviation explicitly — do NOT say COC cannot be calculated.",
#         ]
#     else:
#         task_lines += [
#             f"- Makeup water conductivity not available — state COC cannot be calculated,",
#             f"  should be captured at next service visit.",
#         ]

#     task_lines += [
#         "",
#         "**PRODUCT EFFICIENCY:**",
#         f"- Product name: {prod}",
#         f"- Mean: {fmt(tp_mean,1)} ppm vs Controller Setpoint target {fmt(tp_sp,1)} ppm",
#         f"- {tp_pct}% in range",
#         f"- Actual consumption not available — state this.",
#         "",
#         "**PROACTIVE SYSTEM SUPPORT:**",
#         "- Section title MUST be exactly: Proactive System Support (never 'Alarms')",
#         "- No alarm data available — state Ackumen average is 6 alarms per controller",
#         "- Incorporate any service note Actions Completed below",
#         "",
#         "**CHART COMMENTS (one sentence each — describe the trend shown in the chart):**",
#         "- corrosion_chart_comment: describe MS and Cu trend across W1-W4",
#         f"- scale_chart_comment: describe {prod} trend vs Controller Setpoint range {fmt(tp_ll,1)}–{fmt(tp_ul,1)} ppm",
#         "- orp_chart_comment: describe ORP spike pattern relative to biocide relay activity",
#         f"- conductivity_chart_comment: describe conductivity trend vs setpoint {fmt(ec_sp,0)} µS/cm",
#         "",
#         "---",
#         "",
#         "## SITE DATA",
#         "",
#         f"**Site:** {site}",
#         f"**Month:** {month}",
#         f"**Controller:** {controllers[0].get('SerialNumber','N/A') if controllers else 'N/A'}",
#         "",
#         "### Corrosion",
#         f"| Parameter | Mean | Min | Max | Target | Status |",
#         f"|---|---|---|---|---|---|",
#         f"| Mild Steel (MPY) | {fmt(ms_mean)} | {fmt(smin(ms_s))} | {fmt(smax(ms_s))} | <3.0 | {corr_status} |",
#         f"| Copper (MPY) | {fmt(cu_mean,4)} | {fmt(smin(cu_s),4)} | {fmt(smax(cu_s),4)} | <0.5 | {corr_status} |",
#         "",
#         "**Mild Steel recent 20 readings (MPY):**",
#         f"`{r20(ms_s)}`",
#         "",
#         "**Copper recent 20 readings (MPY):**",
#         f"`{r20(cu_s)}`",
#         "",
#         f"### {prod} (Scale Control)",
#         f"| Parameter | Value |",
#         f"|---|---|",
#         f"| Controller Setpoint (SP) | {fmt(tp_sp,1)} ppm |",
#         f"| Dead Band (DB) | {fmt(tp_db,1)} ppm |",
#         f"| Controller Setpoint Range | {fmt(tp_ll,1)} – {fmt(tp_ul,1)} ppm |",
#         f"| 90-day Mean | {fmt(tp_mean,1)} ppm |",
#         f"| % Recent in Controller Setpoint Range | {tp_pct}% ({status(tp_pct)}) |",
#         f"| Direction | {tp_dir} |",
#         "",
#         f"**{prod} recent 20 readings (ppm):**",
#         f"`{tp_r20_vals}`",
#         "",
#         "### Conductivity (Water Efficiency)",
#         f"| Parameter | Value |",
#         f"|---|---|",
#         f"| Controller Setpoint (SP) | {fmt(ec_sp,0)} µS/cm |",
#         f"| Dead Band (DB) | {fmt(ec_db,0)} µS/cm |",
#         f"| Controller Setpoint Range | {fmt(ec_ll,0)} – {fmt(ec_ul,0)} µS/cm |",
#         f"| 90-day Mean | {fmt(ec_mean,1)} µS/cm |",
#         f"| % Recent in Controller Setpoint Range | {ec_pct}% ({status(ec_pct)}) |",
#         f"| Makeup Water Conductivity | {mu_row_text} |",
#         f"| Target COC | {coc['target_coc'] if coc['target_coc'] is not None else 'N/A'} |",
#         f"| Actual COC | {coc['actual_coc'] if coc['actual_coc'] is not None else 'N/A'} |",
#         f"| COC Deviation | {coc_dev_text} |",
#         "",
#         "**Conductivity recent 20 readings (µS/cm):**",
#         f"`{ec_r20_vals}`",
#         "",
#         "### Microbial",
#         f"| Parameter | Value |",
#         f"|---|---|",
#         f"| FRC (from field test data) | {'Not available' if frc is None else f'{frc} ppm'} |",
#         f"| Biocide relay triggered | {relay_triggered} |",
#         f"| Microbial status | {micro_status} |",
#         "",
#         "**Biocide relay recent 20 readings (1=ON, 0=OFF):**",
#         f"`{relay_r20}`",
#         "",
#         "**ORP recent 20 readings (DO NOT report these values — use spike language only):**",
#         f"`{r20(orp_s)}`",
#         "",
#         "### Supporting parameters (for Performance Summary table only — do not use in narrative sections)",
#         f"| Parameter | Mean | Min | Max |",
#         f"|---|---|---|---|",
#         f"| pH | {fmt(smean(ph_s),2)} | {fmt(smin(ph_s),2)} | {fmt(smax(ph_s),2)} |",
#         f"| Turbidity (NTU) | {fmt(smean(turb_s),2)} | {fmt(smin(turb_s),2)} | {fmt(smax(turb_s),2)} |",
#         f"| Cell Fouling (%) | {fmt(smean(cf_s),2)} | {fmt(smin(cf_s),2)} | {fmt(smax(cf_s),2)} |",
#         "",
#         "### Service Notes",
#         "",
#         notes_text,
#         "",
#         "---",
#         "",
#         "## COPILOT TASK",
#         "",
#         "> **Copy everything in the box below and paste into Copilot Chat.**",
#         "> **Make sure this file (copilot_task.md) is open in the editor.**",
#         "",
#         "```",
#         f"Read copilot_task.md carefully.",
#         f"",
#         f"Write the narrative for the {site} {month} cooling water performance report.",
#         f"Follow ALL rules in the RULES section exactly.",
#         f"",
#         f"Save your response as valid JSON to this exact file:",
#         f"data_store/{slug}/narrative_cache.json",
#         f"",
#         f"The JSON must have exactly these keys:",
#         f"{{",
#         f'  "corrosion_narrative": "2-3 sentences using exact SME wording",',
#         f'  "corrosion_chart_comment": "1 sentence describing the corrosion trend chart",',
#         f'  "scale_narrative": "3-5 sentences about {prod} ONLY — no other parameters",',
#         f'  "scale_chart_comment": "1 sentence describing the {prod} trend chart",',
#         f'  "microbial_narrative": "2-3 sentences about FRC and ORP ONLY — no pH/turbidity",',
#         f'  "orp_chart_comment": "1 sentence describing the ORP spike pattern chart",',
#         f'  "water_efficiency_narrative": "2-3 sentences about conductivity and COC",',
#         f'  "conductivity_chart_comment": "1 sentence describing the conductivity trend chart",',
#         f'  "product_efficiency_narrative": "2-3 sentences about {prod} consumption",',
#         f'  "proactive_support_narrative": "2-3 sentences about alarms and service notes",',
#         f'  "closing_summary": "2-3 sentences summarising the month overall"',
#         f"}}",
#         f"",
#         f"Rules:",
#         f"- Corrosion: use exact wording 'average mild steel corrosion rate was X MPY against the target of within 3.0 MPY'",
#         f"- Scale Control: {prod} ONLY. Status MUST be {tp_status} ({tp_pct}% in range).",
#         f"- {'Include Observation and Recommendation for ' + tp_dir + ' product level.' if tp_dir in ('HIGH','LOW') else 'Product is within range — no observation/recommendation needed.'}",
#         f"- Microbial: FRC and ORP ONLY. No pH, turbidity, cell fouling.",
#         f"- NEVER write absolute ORP values.",
#         f"- Proactive Support title: exactly 'Proactive System Support'",
#         f"- Write professional customer-facing language",
#         f"- Return ONLY valid JSON — no markdown, no explanation outside the JSON",
#         "```",
#         "",
#     ]

#     task_path = cache / "copilot_task.md"
#     task_path.write_text("\n".join(task_lines), encoding="utf-8")
#     print(f"✅  copilot_task.md  → {task_path}")

#     # ═══════════════════════════════════════════════════════════════════════════
#     # Create empty narrative_cache.json template
#     # ═══════════════════════════════════════════════════════════════════════════
#     empty = {
#         "corrosion_narrative":           "",
#         "corrosion_chart_comment":       "",
#         "scale_narrative":               "",
#         "scale_chart_comment":           "",
#         "microbial_narrative":           "",
#         "orp_chart_comment":             "",
#         "water_efficiency_narrative":    "",
#         "conductivity_chart_comment":    "",
#         "product_efficiency_narrative":  "",
#         "proactive_support_narrative":   "",
#         "closing_summary":               "",
#         "_status": "EMPTY — Copilot must fill this in",
#         "_site":   site,
#         "_month":  month,
#     }
#     narrative_path = cache / "narrative_cache.json"
#     narrative_path.write_text(json.dumps(empty, indent=2), encoding="utf-8")
#     print(f"✅  narrative_cache.json → {narrative_path}  (Copilot fills this in)")

#     print(f"")
#     print(f"Next steps:")
#     print(f"  1. Open VS Code:  code .")
#     print(f"  2. Open file:     data_store/{slug}/copilot_task.md")
#     print(f"  3. Also open:     data_store/{slug}/narrative_cache.json")
#     print(f"  4. Copilot Chat:  Ctrl+Shift+I  (Agent mode)")
#     print(f"  5. Copy the COPILOT TASK block (bottom of copilot_task.md)")
#     print(f"     and paste into Copilot Chat")
#     print(f"  6. Copilot writes narrative_cache.json")
#     print(f"  7. Run: python generate_report.py --site \"{site}\" --month \"{month}\"")


# if __name__ == "__main__":
#     main()



# """
# prepare_copilot_task.py
# ────────────────────────
# Step 3 — Run AFTER prefetch_site.py and prepare_report_context.py.

# Creates two files in data_store/<slug>/:

#   copilot_task.md      ← Open this in VS Code, paste Section marked
#                           COPILOT TASK into Copilot Chat.
#                           Copilot writes the narrative JSON back.

#   narrative_cache.json ← Empty template. Copilot fills this in.
#                           generate_report.py reads from here.

# USAGE
# ─────
#     python prepare_copilot_task.py --site "Synthomer Chester SC (US)" --month "May 2026"

# WORKFLOW
# ────────
#     1. python prefetch_site.py          --site "..." --month "..."
#     2. python prepare_copilot_task.py   --site "..." --month "..."
#     3. Open VS Code → open copilot_task.md
#     4. Open Copilot Chat (Ctrl+Shift+I, Agent mode)
#     5. Paste the COPILOT TASK section into Copilot Chat
#     6. Copilot writes narrative_cache.json
#     7. python generate_report.py        --site "..." --month "..."
# """

# import argparse
# import json
# import re
# import sys
# from pathlib import Path

# ROOT       = Path(__file__).parent
# DATA_STORE = ROOT / "data_store"


# def parse_args():
#     p = argparse.ArgumentParser()
#     p.add_argument("--site",  required=True)
#     p.add_argument("--month", required=True)
#     return p.parse_args()


# def slugify(text):
#     return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


# def _load(path, default):
#     return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


# def fmt(v, d=2):
#     try:    return f"{float(v):.{d}f}" if v not in (None, "NULL", "") else "N/A"
#     except: return "N/A"


# def main():
#     args  = parse_args()
#     site  = args.site
#     month = args.month
#     slug  = slugify(f"{site}_{month}")
#     cache = DATA_STORE / slug

#     if not (cache / "manifest.json").exists():
#         print(f"[ERROR] No prefetch data at {cache}")
#         print(f"  Run first: python prefetch_site.py --site \"{site}\" --month \"{month}\"")
#         sys.exit(1)

#     # ── Load all data ─────────────────────────────────────────────────────────
#     controllers = _load(cache / "controllers.json", [])
#     scc         = _load(cache / "scc.json",          [])
#     ade         = _load(cache / "ade_data.json",     [])
#     notes       = _load(cache / "service_notes.json",[])

#     telem_sensors = {}
#     for f in (cache / "telemetry").glob("*_summary.json"):
#         d = json.loads(f.read_text())
#         for name, stats in d.get("sensors", {}).items():
#             telem_sensors[name.lower()] = stats

#     # ── Helper: find sensor by keywords ──────────────────────────────────────
#     def find(*kws):
#         for key, stats in telem_sensors.items():
#             if all(w in key for w in kws):
#                 return stats
#         return {}

#     def r20(stats):   return [round(float(v),4) for v in stats.get("recent_20",[])]
#     def smean(stats): v=stats.get("mean"); return float(v) if v is not None else None
#     def smin(stats):  v=stats.get("min");  return float(v) if v is not None else None
#     def smax(stats):  v=stats.get("max");  return float(v) if v is not None else None

#     ms_s   = find("corrosion_probe_1")
#     cu_s   = find("corrosion_probe_2")
#     ec_s   = find("electrode_conductivity")
#     tp_s   = find("fluorometer_ch_1") or find("fluorometer","ch1")
#     ph_s   = find("ph_probe") or find("ph")
#     orp_s  = find("orp")
#     turb_s = find("turbidity")
#     cf_s   = find("cellfouling") or find("cell_fouling")
#     rel_s  = find("relay3") or find("relay5") or find("relay1")

#     # ── Controller Setpoints ─────────────────────────────────────────────────────────
#     def scc_row(*kws):
#         for r in scc:
#             s = (str(r.get("Input Sensor",""))+str(r.get("Sensor Name",""))).lower()
#             if all(w in s for w in kws): return r
#         return {}

#     ec_r = scc_row("conductivity")
#     tp_r = scc_row("fluorometer_ch_1") or scc_row("fluorometer","ch1") or scc_row("traced")

#     def fv(row, key):
#         v = row.get(key)
#         try:    return float(v) if v not in (None,"NULL","") else None
#         except: return None

#     ec_sp = fv(ec_r,"SP"); ec_db = fv(ec_r,"DB")
#     tp_sp = fv(tp_r,"SP"); tp_db = fv(tp_r,"DB")
#     ec_ll = (ec_sp-ec_db) if ec_sp and ec_db else None
#     ec_ul = (ec_sp+ec_db) if ec_sp and ec_db else None
#     tp_ll = (tp_sp-tp_db) if tp_sp and tp_db else None
#     tp_ul = (tp_sp+tp_db) if tp_sp and tp_db else None
#     prod  = tp_r.get("Product Name") or "Traced Product"
#     if prod in ("None","none",None): prod = "Traced Product"

#     # ── % in range ────────────────────────────────────────────────────────────
#     def pct(vals, ll, ul):
#         if not vals or ll is None or ul is None: return None
#         return round(sum(1 for v in vals if ll<=v<=ul)/len(vals)*100,1)

#     tp_r20_vals = r20(tp_s); ec_r20_vals = r20(ec_s)
#     tp_pct = pct(tp_r20_vals, tp_ll, tp_ul)
#     ec_pct = pct(ec_r20_vals, ec_ll, ec_ul)

#     def status(p):
#         if p is None: return "Stable"
#         return "Good" if p>75 else ("Stable" if p>=25 else "Action Required")

#     ms_mean = smean(ms_s); cu_mean = smean(cu_s)
#     corr_ok = (ms_mean is not None and ms_mean<3.0) and (cu_mean is not None and cu_mean<0.5)
#     corr_status = "Good" if corr_ok else "Action Required"
#     tp_status   = status(tp_pct)
#     ec_status   = status(ec_pct)

#     tp_mean = smean(tp_s); ec_mean = smean(ec_s)
#     if tp_mean and tp_ul and tp_ll:
#         tp_dir = "HIGH" if tp_mean>tp_ul else ("LOW" if tp_mean<tp_ll else "OK")
#     else: tp_dir = "UNKNOWN"

#     frc_rows = [r for r in ade if any(w in str(r.get("Parameter","")).lower()
#                 for w in ("free residual","frc","halogen"))]
#     frc = float(frc_rows[0]["Value"]) if frc_rows else None
#     micro_status = "Good" if frc and frc>=0.2 else "Stable"

#     relay_r20 = r20(rel_s)
#     relay_triggered = bool(relay_r20 and any(v>0 for v in relay_r20))

#     notes_text = "No service notes were recorded for this reporting period." if not notes else \
#         "\n".join(f"Date: {str(n.get('CreatedDate',''))[:10]}\n"
#                   f"{n.get('ServiceNotePlain') or n.get('ServiceNote','')}"
#                   for n in notes)

#     # ═══════════════════════════════════════════════════════════════════════════
#     # Build copilot_task.md
#     # ═══════════════════════════════════════════════════════════════════════════
#     task_lines = [
#         f"# Copilot Task — {site} | {month}",
#         "",
#         "> **Instructions for Copilot Agent:**",
#         "> 1. Read ALL the data below carefully",
#         "> 2. Follow EVERY rule in the RULES section",
#         "> 3. Write the narrative_cache.json file at the path shown",
#         "> 4. Do not add markdown, do not truncate, write valid JSON",
#         "",
#         "---",
#         "",
#         "## RULES (follow exactly)",
#         "",
#         "**CORROSION CONTROL:**",
#         f"- Use this exact wording: 'The average mild steel corrosion rate was X MPY against",
#         f"  the target of within 3.0 MPY, and the average copper corrosion rate was X MPY",
#         f"  against the target of within 0.5 MPY.'",
#         f"- Status: {corr_status}",
#         "",
#         "**SCALE CONTROL:**",
#         f"- Write ONLY about {prod}. Do NOT mention conductivity, pH, turbidity, or anything else.",
#         f"- Status MUST be: {tp_status} (because {tp_pct}% of recent readings are in Controller Setpoint range)",
#         f"- {tp_pct}% in range means: Good>75%, Stable 25-75%, Action Required<25%",
#         f"- Product is {tp_dir} (HIGH=above upper limit, LOW=below lower limit, OK=in range)",
#     ]

#     if tp_dir == "HIGH":
#         task_lines += [
#             f"- MUST include Observation: '{prod} concentration was above the Controller Setpoint upper",
#             f"  control limit of {fmt(tp_ul,1)} ppm, indicating overfeeding.'",
#             f"- MUST include Recommendation: 'Check dosing pump rate and reduce if running",
#             f"  above setpoint. Verify fluorometer calibration with a grab sample. Review",
#             f"  the dosing schedule and confirm the relay is not in manual override.'",
#         ]
#     elif tp_dir == "LOW":
#         task_lines += [
#             f"- MUST include Observation: '{prod} concentration was below the Controller Setpoint lower",
#             f"  control limit of {fmt(tp_ll,1)} ppm.'",
#             f"- MUST include Recommendation: 'Verify dosing pump operation and confirm it",
#             f"  is primed. Check product inventory level. Inspect the chemical feed line",
#             f"  for blockage or air lock. Verify fluorometer calibration with a grab sample.'",
#         ]

#     root_cause = ("Conductivity was stable during the same period, indicating this is a "
#                   "product feed or calibration issue, not a water loss event."
#                   if (ec_pct or 0) >= 75 else
#                   "Conductivity also declined during the same period, suggesting water loss, "
#                   "dilution, or excess blowdown as a contributing factor.")
#     task_lines += [
#         f"- Root cause to include: '{root_cause}'",
#         "",
#         "**MICROBIAL CONTROL:**",
#         f"- Write ONLY about FRC and ORP. Do NOT mention pH, turbidity, cell fouling, or anything else.",
#         f"- Status: {micro_status}",
#     ]

#     if frc is not None:
#         task_lines.append(f"- FRC from field test data: {frc} ppm. Comment on whether this is adequate.")
#     else:
#         task_lines.append(
#             "- FRC: NOT in field test data. Write: 'FRC data was not available in the field test data "
#             "for this reporting period and will be checked during the upcoming service visit.'")

#     task_lines += [
#         f"- Biocide relay was triggered: {relay_triggered}",
#         f"- MANDATORY ORP sentence: 'ORP spike response after timer-controlled biocide feed "
#         f"{'was consistent, indicating the system responded to treatment.' if relay_triggered else 'was not consistent. Possible causes include low oxidizing biocide residual, biocide inventory issue, dosing pump lost prime, or incorrect timer schedule. These will be investigated at the upcoming service visit.'}'",
#         "- NEVER write absolute ORP values anywhere. Relative/spike language only.",
#         "",
#         "**WATER EFFICIENCY:**",
#         f"- Discuss conductivity and COC here (NOT in Scale Control).",
#         f"- Controller Setpoint conductivity: {fmt(ec_sp,0)} µS/cm, range {fmt(ec_ll,0)}–{fmt(ec_ul,0)} µS/cm",
#         f"- {ec_pct}% of recent readings within Controller Setpoint control range",
#         f"- 90-day average: {fmt(ec_mean,1)} µS/cm",
#         f"- Makeup water conductivity not available — state COC cannot be calculated,",
#         f"  should be captured at next service visit.",
#         "",
#         "**PRODUCT EFFICIENCY:**",
#         f"- Product name: {prod}",
#         f"- Mean: {fmt(tp_mean,1)} ppm vs Controller Setpoint target {fmt(tp_sp,1)} ppm",
#         f"- {tp_pct}% in range",
#         f"- Actual consumption not available — state this.",
#         "",
#         "**PROACTIVE SYSTEM SUPPORT:**",
#         "- Section title MUST be exactly: Proactive System Support (never 'Alarms')",
#         "- No alarm data available — state Ackumen average is 6 alarms per controller",
#         "- Incorporate any service note Actions Completed below",
#         "",
#         "**CHART COMMENTS (one sentence each — describe the trend shown in the chart):**",
#         "- corrosion_chart_comment: describe MS and Cu trend across W1-W4",
#         f"- scale_chart_comment: describe {prod} trend vs Controller Setpoint range {fmt(tp_ll,1)}–{fmt(tp_ul,1)} ppm",
#         "- orp_chart_comment: describe ORP spike pattern relative to biocide relay activity",
#         f"- conductivity_chart_comment: describe conductivity trend vs setpoint {fmt(ec_sp,0)} µS/cm",
#         "",
#         "---",
#         "",
#         "## SITE DATA",
#         "",
#         f"**Site:** {site}",
#         f"**Month:** {month}",
#         f"**Controller:** {controllers[0].get('SerialNumber','N/A') if controllers else 'N/A'}",
#         "",
#         "### Corrosion",
#         f"| Parameter | Mean | Min | Max | Target | Status |",
#         f"|---|---|---|---|---|---|",
#         f"| Mild Steel (MPY) | {fmt(ms_mean)} | {fmt(smin(ms_s))} | {fmt(smax(ms_s))} | <3.0 | {corr_status} |",
#         f"| Copper (MPY) | {fmt(cu_mean,4)} | {fmt(smin(cu_s),4)} | {fmt(smax(cu_s),4)} | <0.5 | {corr_status} |",
#         "",
#         "**Mild Steel recent 20 readings (MPY):**",
#         f"`{r20(ms_s)}`",
#         "",
#         "**Copper recent 20 readings (MPY):**",
#         f"`{r20(cu_s)}`",
#         "",
#         f"### {prod} (Scale Control)",
#         f"| Parameter | Value |",
#         f"|---|---|",
#         f"| Controller Setpoint (SP) | {fmt(tp_sp,1)} ppm |",
#         f"| Dead Band (DB) | {fmt(tp_db,1)} ppm |",
#         f"| Controller Setpoint Range | {fmt(tp_ll,1)} – {fmt(tp_ul,1)} ppm |",
#         f"| 90-day Mean | {fmt(tp_mean,1)} ppm |",
#         f"| % Recent in Controller Setpoint Range | {tp_pct}% ({status(tp_pct)}) |",
#         f"| Direction | {tp_dir} |",
#         "",
#         f"**{prod} recent 20 readings (ppm):**",
#         f"`{tp_r20_vals}`",
#         "",
#         "### Conductivity (Water Efficiency)",
#         f"| Parameter | Value |",
#         f"|---|---|",
#         f"| Controller Setpoint (SP) | {fmt(ec_sp,0)} µS/cm |",
#         f"| Dead Band (DB) | {fmt(ec_db,0)} µS/cm |",
#         f"| Controller Setpoint Range | {fmt(ec_ll,0)} – {fmt(ec_ul,0)} µS/cm |",
#         f"| 90-day Mean | {fmt(ec_mean,1)} µS/cm |",
#         f"| % Recent in Controller Setpoint Range | {ec_pct}% ({status(ec_pct)}) |",
#         "",
#         "**Conductivity recent 20 readings (µS/cm):**",
#         f"`{ec_r20_vals}`",
#         "",
#         "### Microbial",
#         f"| Parameter | Value |",
#         f"|---|---|",
#         f"| FRC (from field test data) | {'Not available' if frc is None else f'{frc} ppm'} |",
#         f"| Biocide relay triggered | {relay_triggered} |",
#         f"| Microbial status | {micro_status} |",
#         "",
#         "**Biocide relay recent 20 readings (1=ON, 0=OFF):**",
#         f"`{relay_r20}`",
#         "",
#         "**ORP recent 20 readings (DO NOT report these values — use spike language only):**",
#         f"`{r20(orp_s)}`",
#         "",
#         "### Supporting parameters (for Performance Summary table only — do not use in narrative sections)",
#         f"| Parameter | Mean | Min | Max |",
#         f"|---|---|---|---|",
#         f"| pH | {fmt(smean(ph_s),2)} | {fmt(smin(ph_s),2)} | {fmt(smax(ph_s),2)} |",
#         f"| Turbidity (NTU) | {fmt(smean(turb_s),2)} | {fmt(smin(turb_s),2)} | {fmt(smax(turb_s),2)} |",
#         f"| Cell Fouling (%) | {fmt(smean(cf_s),2)} | {fmt(smin(cf_s),2)} | {fmt(smax(cf_s),2)} |",
#         "",
#         "### Service Notes",
#         "",
#         notes_text,
#         "",
#         "---",
#         "",
#         "## COPILOT TASK",
#         "",
#         "> **Copy everything in the box below and paste into Copilot Chat.**",
#         "> **Make sure this file (copilot_task.md) is open in the editor.**",
#         "",
#         "```",
#         f"Read copilot_task.md carefully.",
#         f"",
#         f"Write the narrative for the {site} {month} cooling water performance report.",
#         f"Follow ALL rules in the RULES section exactly.",
#         f"",
#         f"Save your response as valid JSON to this exact file:",
#         f"data_store/{slug}/narrative_cache.json",
#         f"",
#         f"The JSON must have exactly these keys:",
#         f"{{",
#         f'  "corrosion_narrative": "2-3 sentences using exact SME wording",',
#         f'  "corrosion_chart_comment": "1 sentence describing the corrosion trend chart",',
#         f'  "scale_narrative": "3-5 sentences about {prod} ONLY — no other parameters",',
#         f'  "scale_chart_comment": "1 sentence describing the {prod} trend chart",',
#         f'  "microbial_narrative": "2-3 sentences about FRC and ORP ONLY — no pH/turbidity",',
#         f'  "orp_chart_comment": "1 sentence describing the ORP spike pattern chart",',
#         f'  "water_efficiency_narrative": "2-3 sentences about conductivity and COC",',
#         f'  "conductivity_chart_comment": "1 sentence describing the conductivity trend chart",',
#         f'  "product_efficiency_narrative": "2-3 sentences about {prod} consumption",',
#         f'  "proactive_support_narrative": "2-3 sentences about alarms and service notes",',
#         f'  "closing_summary": "2-3 sentences summarising the month overall"',
#         f"}}",
#         f"",
#         f"Rules:",
#         f"- Corrosion: use exact wording 'average mild steel corrosion rate was X MPY against the target of within 3.0 MPY'",
#         f"- Scale Control: {prod} ONLY. Status MUST be {tp_status} ({tp_pct}% in range).",
#         f"- {'Include Observation and Recommendation for ' + tp_dir + ' product level.' if tp_dir in ('HIGH','LOW') else 'Product is within range — no observation/recommendation needed.'}",
#         f"- Microbial: FRC and ORP ONLY. No pH, turbidity, cell fouling.",
#         f"- NEVER write absolute ORP values.",
#         f"- Proactive Support title: exactly 'Proactive System Support'",
#         f"- Write professional customer-facing language",
#         f"- Return ONLY valid JSON — no markdown, no explanation outside the JSON",
#         "```",
#         "",
#     ]

#     task_path = cache / "copilot_task.md"
#     task_path.write_text("\n".join(task_lines), encoding="utf-8")
#     print(f"✅  copilot_task.md  → {task_path}")

#     # ═══════════════════════════════════════════════════════════════════════════
#     # Create empty narrative_cache.json template
#     # ═══════════════════════════════════════════════════════════════════════════
#     empty = {
#         "corrosion_narrative":           "",
#         "corrosion_chart_comment":       "",
#         "scale_narrative":               "",
#         "scale_chart_comment":           "",
#         "microbial_narrative":           "",
#         "orp_chart_comment":             "",
#         "water_efficiency_narrative":    "",
#         "conductivity_chart_comment":    "",
#         "product_efficiency_narrative":  "",
#         "proactive_support_narrative":   "",
#         "closing_summary":               "",
#         "_status": "EMPTY — Copilot must fill this in",
#         "_site":   site,
#         "_month":  month,
#     }
#     narrative_path = cache / "narrative_cache.json"
#     narrative_path.write_text(json.dumps(empty, indent=2), encoding="utf-8")
#     print(f"✅  narrative_cache.json → {narrative_path}  (Copilot fills this in)")

#     print(f"")
#     print(f"Next steps:")
#     print(f"  1. Open VS Code:  code .")
#     print(f"  2. Open file:     data_store/{slug}/copilot_task.md")
#     print(f"  3. Also open:     data_store/{slug}/narrative_cache.json")
#     print(f"  4. Copilot Chat:  Ctrl+Shift+I  (Agent mode)")
#     print(f"  5. Copy the COPILOT TASK block (bottom of copilot_task.md)")
#     print(f"     and paste into Copilot Chat")
#     print(f"  6. Copilot writes narrative_cache.json")
#     print(f"  7. Run: python generate_report.py --site \"{site}\" --month \"{month}\"")


# if __name__ == "__main__":
#     main()


"""
prepare_copilot_task.py
────────────────────────
Step 3 — Run AFTER prefetch_site.py and prepare_report_context.py.

Creates two files in data_store/<slug>/:

  copilot_task.md      ← Open this in VS Code, paste Section marked
                          COPILOT TASK into Copilot Chat.
                          Copilot writes the narrative JSON back.

  narrative_cache.json ← Empty template. Copilot fills this in.
                          generate_report.py reads from here.

USAGE
─────
    python prepare_copilot_task.py --site "Synthomer Chester SC (US)" --month "May 2026"

WORKFLOW
────────
    1. python prefetch_site.py          --site "..." --month "..."
    2. python prepare_copilot_task.py   --site "..." --month "..."
    3. Open VS Code → open copilot_task.md
    4. Open Copilot Chat (Ctrl+Shift+I, Agent mode)
    5. Paste the COPILOT TASK section into Copilot Chat
    6. Copilot writes narrative_cache.json
    7. python generate_report.py        --site "..." --month "..."
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT       = Path(__file__).parent
DATA_STORE = ROOT / "data_store"


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--site",  required=True)
    p.add_argument("--month", required=True)
    return p.parse_args()


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def fmt(v, d=2):
    try:    return f"{float(v):.{d}f}" if v not in (None, "NULL", "") else "N/A"
    except: return "N/A"


def _load_mu_conductivity(site):
    """Read MU conductivity from data/MU_conductivity.xlsx if present. Returns float or None.

    Kept in sync with generate_report.py's _load_mu_conductivity() — both scripts
    need to agree on whether MU conductivity is available for a site, otherwise
    the Copilot narrative and the generated COC table will contradict each other.
    """
    mu_file = ROOT / "data" / "MU_conductivity.xlsx"
    if not mu_file.exists():
        return None
    try:
        import openpyxl
        wb = openpyxl.load_workbook(mu_file, data_only=True)
        ws = wb.active
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or not row[0]: continue
            if str(row[0]).strip().lower() == site.strip().lower():
                val = row[3] if len(row) > 3 else None
                if val is None or str(val).lower() in ("no data","none","",None):
                    return None
                try: return float(val)
                except: return None
    except Exception as e:
        print(f"  [WARN] Could not read MU_conductivity.xlsx: {e}")
    return None


def compute_coc(ec_sp, ec_mean, mu_cond):
    """Same COC math as generate_report.py's compute_coc(), reduced to the two inputs
    this script has on hand (Controller Setpoint conductivity + monthly mean conductivity)."""
    if mu_cond is None or mu_cond == 0:
        return {"mu_available": False, "mu_cond": None,
                "target_coc": None, "actual_coc": None,
                "deviation_pct": None, "coc_status": None}

    target_coc = (ec_sp / mu_cond) if ec_sp else None
    actual_coc = (ec_mean / mu_cond) if ec_mean else None

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


def main():
    args  = parse_args()
    site  = args.site
    month = args.month
    slug  = slugify(f"{site}_{month}")
    cache = DATA_STORE / slug

    if not (cache / "manifest.json").exists():
        print(f"[ERROR] No prefetch data at {cache}")
        print(f"  Run first: python prefetch_site.py --site \"{site}\" --month \"{month}\"")
        sys.exit(1)

    # ── Load all data ─────────────────────────────────────────────────────────
    controllers = _load(cache / "controllers.json", [])
    scc         = _load(cache / "scc.json",          [])
    ade         = _load(cache / "ade_data.json",     [])
    notes       = _load(cache / "service_notes.json",[])

    telem_sensors = {}
    for f in (cache / "telemetry").glob("*_summary.json"):
        d = json.loads(f.read_text())
        for name, stats in d.get("sensors", {}).items():
            telem_sensors[name.lower()] = stats

    # ── Helper: find sensor by keywords ──────────────────────────────────────
    def find(*kws):
        for key, stats in telem_sensors.items():
            if all(w in key for w in kws):
                return stats
        return {}

    def r20(stats):   return [round(float(v),4) for v in stats.get("recent_20",[])]
    def smean(stats): v=stats.get("mean"); return float(v) if v is not None else None
    def smin(stats):  v=stats.get("min");  return float(v) if v is not None else None
    def smax(stats):  v=stats.get("max");  return float(v) if v is not None else None

    ms_s   = find("corrosion_probe_1")
    cu_s   = find("corrosion_probe_2")
    ec_s   = find("electrode_conductivity")
    tp_s   = find("fluorometer_ch_1") or find("fluorometer","ch1")
    ph_s   = find("ph_probe") or find("ph")
    orp_s  = find("orp")
    turb_s = find("turbidity")
    cf_s   = find("cellfouling") or find("cell_fouling")
    rel_s  = find("relay3") or find("relay5") or find("relay1")

    # ── Controller Setpoints ─────────────────────────────────────────────────────────
    def scc_row(*kws):
        for r in scc:
            s = (str(r.get("Input Sensor",""))+str(r.get("Sensor Name",""))).lower()
            if all(w in s for w in kws): return r
        return {}

    ec_r = scc_row("conductivity")
    tp_r = scc_row("fluorometer_ch_1") or scc_row("fluorometer","ch1") or scc_row("traced")

    def fv(row, key):
        v = row.get(key)
        try:    return float(v) if v not in (None,"NULL","") else None
        except: return None

    ec_sp = fv(ec_r,"SP"); ec_db = fv(ec_r,"DB")
    tp_sp = fv(tp_r,"SP"); tp_db = fv(tp_r,"DB")
    ec_ll = (ec_sp-ec_db) if ec_sp and ec_db else None
    ec_ul = (ec_sp+ec_db) if ec_sp and ec_db else None
    tp_ll = (tp_sp-tp_db) if tp_sp and tp_db else None
    tp_ul = (tp_sp+tp_db) if tp_sp and tp_db else None
    prod  = tp_r.get("Product Name") or "Traced Product"
    if prod in ("None","none",None): prod = "Traced Product"

    # ── % in range ────────────────────────────────────────────────────────────
    def pct(vals, ll, ul):
        if not vals or ll is None or ul is None: return None
        return round(sum(1 for v in vals if ll<=v<=ul)/len(vals)*100,1)

    tp_r20_vals = r20(tp_s); ec_r20_vals = r20(ec_s)
    tp_pct = pct(tp_r20_vals, tp_ll, tp_ul)
    ec_pct = pct(ec_r20_vals, ec_ll, ec_ul)

    def status(p):
        if p is None: return "Stable"
        return "Good" if p>75 else ("Stable" if p>=25 else "Action Required")

    ms_mean = smean(ms_s); cu_mean = smean(cu_s)
    corr_ok = (ms_mean is not None and ms_mean<3.0) and (cu_mean is not None and cu_mean<0.5)
    corr_status = "Good" if corr_ok else "Action Required"
    tp_status   = status(tp_pct)
    ec_status   = status(ec_pct)

    tp_mean = smean(tp_s); ec_mean = smean(ec_s)
    if tp_mean and tp_ul and tp_ll:
        tp_dir = "HIGH" if tp_mean>tp_ul else ("LOW" if tp_mean<tp_ll else "OK")
    else: tp_dir = "UNKNOWN"

    frc_rows = [r for r in ade if any(w in str(r.get("Parameter","")).lower()
                for w in ("free residual","frc","halogen"))]
    frc = float(frc_rows[0]["Value"]) if frc_rows else None
    micro_status = "Good" if frc and frc>=0.2 else "Stable"

    relay_r20 = r20(rel_s)
    relay_triggered = bool(relay_r20 and any(v>0 for v in relay_r20))

    notes_text = "No service notes were recorded for this reporting period." if not notes else \
        "\n".join(f"Date: {str(n.get('CreatedDate',''))[:10]}\n"
                  f"{n.get('ServiceNotePlain') or n.get('ServiceNote','')}"
                  for n in notes)

    # ═══════════════════════════════════════════════════════════════════════════
    # Build copilot_task.md
    # ═══════════════════════════════════════════════════════════════════════════
    task_lines = [
        f"# Copilot Task — {site} | {month}",
        "",
        "> **Instructions for Copilot Agent:**",
        "> 1. Read ALL the data below carefully",
        "> 2. Follow EVERY rule in the RULES section",
        "> 3. Write the narrative_cache.json file at the path shown",
        "> 4. Do not add markdown, do not truncate, write valid JSON",
        "",
        "---",
        "",
        "## RULES (follow exactly)",
        "",
        "**LANGUAGE RULES — apply everywhere:**",
        "- Never say 'relay firing' or 'relay was firing'. Say 'dosing was triggered',",
        "  'biocide pump was activated', or 'blowdown valve was triggered'.",
        "- Never say 'relay firing' for product dosing. Say 'product dosing pump was active'.",
        "",
        "**CORROSION CONTROL:**",
        f"- Use this exact wording with two decimal places before mpy: 'During the reporting period, the system remained under good control. The mild steel and copper corrosion rates averaged X.XX mpy and X.XX mpy, respectively, both of which are well within the recommended limits of <5 mpy and <0.5 mpy.'",
        f"- Do not include status wording in the narrative sentence; the report template adds Status separately.",
        f"- Do not add trend-comparison sentences about mild steel/copper movement or comparing movement with product residual/ORP trends.",
        f"- Status: {corr_status}",
        "",
        "**SCALE CONTROL:**",
        f"- Write about {prod} and state how much Conductivity was within the recommended range. Do NOT mention pH, turbidity, or anything else.",
        f"- Calculate polymer consumption internally where data supports it. Mention polymer consumption rate only when Traced Product is higher than Tagged Polymer; if Tagged Polymer is higher, omit polymer consumption from customer-facing text.",
        f"- Status MUST be: {tp_status} (because {tp_pct}% of recent readings are in Controller Setpoint range)",
        f"- {tp_pct}% in range means: Excellent>75%, Acceptable 25-75%, Critical<25%",
        f"- Product is {tp_dir} (HIGH=above upper limit, LOW=below lower limit, OK=in range)",
        f"- First line must state how much Traced Product was within the recommended range.",
        f"- If trace was higher only in the initial days and later moved closer to the control band, mention that detail.",
        f"- If end-of-month control is maintained well, highlight that product is now maintained well; otherwise state it is not yet consistently maintained well.",
        f"- If end-of-month trace is higher than setpoint by up to 5%, do not write the exact deviation; mention that the deviation is minimal and the control logic will be optimised.",
        f"- If polymer consumption increased by more than 5%, the last Scale Control line must state that phosphate residual will be checked during the upcoming service visit.",
        f"- If end-of-month trace is higher than setpoint by more than 5%, mention the pump stroke will be reduced during the upcoming service visit.",
        f"- If product control was good initially and later decreased, compare conductivity: product decreased with conductivity decreased = water loss in the system; product decreased while conductivity was maintained well = possible lack of inventory or dosing pump lost prime.",
        f"- If conductivity was below its setpoint configuration range for most of the same period, state that water loss, dilution, or blowdown/makeup behavior should be inspected during the upcoming service visit.",
        f"- If product control was good initially and later increased, state that feed control settings and fluorometer calibration should be reviewed during the upcoming service visit.",
    ]

    if tp_dir == "HIGH":
        task_lines += [
            f"- MUST include Observation: '{prod} concentration was above the Controller Setpoint upper",
            f"  control limit of {fmt(tp_ul,1)} ppm, indicating overfeeding.'",
            f"- MUST include Recommendation: 'Check dosing pump rate and reduce if running",
            f"  above setpoint. Verify fluorometer calibration with a grab sample. Review",
            f"  the dosing schedule and confirm the relay is not in manual override.'",
        ]
    elif tp_dir == "LOW":
        task_lines += [
            f"- MUST include Observation: '{prod} concentration was below the Controller Setpoint lower",
            f"  control limit of {fmt(tp_ll,1)} ppm.'",
            f"- MUST include Recommendation: 'Verify dosing pump operation and confirm it",
            f"  is primed. Check product inventory level. Inspect the chemical feed line",
            f"  for blockage or air lock. Verify fluorometer calibration with a grab sample.'",
        ]

    root_cause = ("Conductivity was stable during the same period, indicating this is a "
                  "product feed or calibration issue, not a water loss event."
                  if (ec_pct or 0) >= 75 else
                  "Conductivity also declined during the same period, suggesting water loss, "
                  "dilution, or excess blowdown as a contributing factor.")
    task_lines += [
        f"- Root cause to include: '{root_cause}'",
        "",
        "**MICROBIAL CONTROL:**",
        f"- Write ONLY about FRC, ORP spike response, and dip-slide CFU analysis. Do NOT mention pH, turbidity, cell fouling, or anything else.",
        f"- Do NOT mention copper corrosion or write 'No copper corrosion within target' in this section.",
        f"- Status: {micro_status}",
    ]

    if frc is not None:
        task_lines.append(f"- FRC from field test data: {frc} ppm. Comment on whether this is adequate.")
    else:
        task_lines.append(
            "- FRC: NOT in field test data. If dip-slide is also missing, write only: 'FRC and dip-slide will be analysed in the upcoming visit to ensure good microbial control.' "
            "Do not mention ADE/MDE data availability in customer-facing content.")

    task_lines += [
        f"- Biocide relay was triggered: {relay_triggered}",
        "- MANDATORY ORP rule: if ORP spike response increases by at least 50 mV at least two times per week during oxidizing biocide application, state that it indicates good microbial dosage. Otherwise write: 'Insufficient ORP spike was observed during oxidizing biocide application, so oxidizing biocide feed response should be reviewed during the upcoming service visit.'",
        "- The FRC sentence and dip-slide sentence must be the last statements in Microbial Control, in that order.",
        "- NEVER write absolute ORP values in the microbial_narrative or orp_chart_comment",
        "  fields (or any other narrative text). Relative/spike language only in narrative prose.",
        "- EXCEPTION — this restriction does NOT apply to the Performance Summary table on",
        "  Page 4 of the final report. That table MUST show the actual numeric ORP",
        "  Mean/Min/Max from the 'Supporting parameters' section below, the same way it",
        "  shows every other sensor. Do not write 'Not reported' or 'See chart' for ORP",
        "  in that table.",
        "",
        "**WATER EFFICIENCY:**",
        f"- Discuss conductivity and COC here (NOT in Scale Control).",
        f"- Controller Setpoint conductivity: {fmt(ec_sp,0)} µS/cm, range {fmt(ec_ll,0)}–{fmt(ec_ul,0)} µS/cm",
        f"- {ec_pct}% of recent readings within the recommended range",
        f"- 90-day average: {fmt(ec_mean,1)} µS/cm",
    ]

    mu_cond = _load_mu_conductivity(site)
    coc = compute_coc(ec_sp, ec_mean, mu_cond)
    mu_row_text  = f"{coc['mu_cond']} µS/cm" if coc["mu_available"] else "Not available"
    coc_dev_text = f"{coc['deviation_pct']}%" if coc["deviation_pct"] is not None else "N/A"
    if coc["mu_available"] and coc["target_coc"] is not None and coc["actual_coc"] is not None:
        task_lines += [
            f"- Makeup water conductivity: {coc['mu_cond']} µS/cm",
            f"- Target COC (Controller Setpoint / MU conductivity): {coc['target_coc']}",
            f"- Actual COC (90-day average conductivity / MU conductivity): {coc['actual_coc']}",
            f"- COC deviation from target: {coc['deviation_pct']}%  →  Status: {coc['coc_status']}",
            f"- State the actual COC value and deviation explicitly — do NOT say COC cannot be calculated.",
        ]
    else:
        task_lines += [
            f"- Makeup water conductivity not available — state COC cannot be calculated,",
            f"  should be captured at next service visit.",
        ]

    task_lines += [
        "",
        "**PRODUCT EFFICIENCY — must explain WHY performance is good or bad:**",
        f"- Product name: {prod}",
        f"- Mean: {fmt(tp_mean,1)} ppm vs Controller Setpoint target {fmt(tp_sp,1)} ppm (range {fmt(tp_ll,1)}–{fmt(tp_ul,1)} ppm)",
        f"- {tp_pct}% in range",
        f"- Product direction: {tp_dir}",
        f"- Calculate polymer consumption internally where data supports it. Mention polymer consumption rate only when Traced Product is higher than Tagged Polymer; if Tagged Polymer is higher, omit polymer consumption from customer-facing text.",
        f"- If product is HIGH (overdosing): state the product is being overdosed.",
        f"  Explain: dosing pump rate may be too high, fluorometer may need recalibration.",
        f"  Recommend: decrease the pump stroke, verify fluorometer calibration with a grab",
        f"  sample, check the dosing valve, inspect the probe. State this will be addressed",
        f"  at the next service visit.",
        f"- If product is LOW (underdosing): state the product is being underdosed.",
        f"  Explain: dosing pump may have lost prime, inventory may be low, feed line may be blocked.",
        f"  Recommend: check pump prime, verify inventory, inspect feed line for blockage or air lock,",
        f"  calibrate fluorometer. State this will be addressed at the next service visit.",
        f"- If product is OK (in range): state dosing efficiency was well maintained.",
        f"- Actual consumption not available — state this.",
        "",
        "**PROACTIVE SYSTEM SUPPORT:**",
        "- Section title MUST be exactly: Proactive System Support (never 'Alarms')",
        "- Mention polymer consumption in proactive support or recommendations only when Traced Product is higher than Tagged Polymer.",
        "- No alarm data available — state Ackumen average is 6 alarms per controller",
        "- Incorporate any service note Actions Completed below",
        "",
        "**CHART COMMENTS — must be specific and actionable (not vague):**",
        "  Each chart comment MUST be 3-4 short lines explaining the visible pattern.",
        "  Every chart comment MUST include:",
        "  1. Start-to-end direction or spike/stability pattern shown by the chart",
        "  2. Relationship to the configured control range, target, or corrosion limit",
        "  3. What the pattern means operationally: overdosing, underdosing, good control, water loss, or stable control",
        "  4. A specific follow-up action if the pattern is out of range or unstable",
        "",
        "- corrosion_chart_comment: state MS and Cu averages and whether within targets.",
        "  If approaching limit: recommend inspecting probes and reviewing inhibitor dosing.",
        f"- scale_chart_comment: state {prod} mean vs range {fmt(tp_ll,1)}–{fmt(tp_ul,1)} ppm.",
        f"  State the exact % above or below range. If HIGH: 'indicates overdosing —",
        f"  recommend decreasing pump stroke and verifying fluorometer calibration.'",
        f"  If LOW: 'indicates underdosing — check pump prime and inspect feed line.'",
        "- orp_chart_comment: describe ORP spike pattern relative to biocide dosing events.",
        "  Never say 'relay firing'. Say 'biocide dosing was triggered' or 'pump was activated'.",
        f"- conductivity_chart_comment: state conductivity vs setpoint {fmt(ec_sp,0)} µS/cm.",
        "  If deviating: recommend reviewing blowdown valve operation and checking for water losses.",
        "",
        "---",
        "",
        "## SITE DATA",
        "",
        f"**Site:** {site}",
        f"**Month:** {month}",
        f"**Controller:** {controllers[0].get('SerialNumber','N/A') if controllers else 'N/A'}",
        "",
        "### Corrosion",
        f"| Parameter | Mean | Min | Max | Target | Status |",
        f"|---|---|---|---|---|---|",
        f"| Mild Steel (MPY) | {fmt(ms_mean)} | {fmt(smin(ms_s))} | {fmt(smax(ms_s))} | <3.0 | {corr_status} |",
        f"| Copper (MPY) | {fmt(cu_mean,4)} | {fmt(smin(cu_s),4)} | {fmt(smax(cu_s),4)} | <0.5 | {corr_status} |",
        "",
        "**Mild Steel recent 20 readings (MPY):**",
        f"`{r20(ms_s)}`",
        "",
        "**Copper recent 20 readings (MPY):**",
        f"`{r20(cu_s)}`",
        "",
        f"### {prod} (Scale Control)",
        f"| Parameter | Value |",
        f"|---|---|",
        f"| Controller Setpoint (SP) | {fmt(tp_sp,1)} ppm |",
        f"| Dead Band (DB) | {fmt(tp_db,1)} ppm |",
        f"| Controller Setpoint Range | {fmt(tp_ll,1)} – {fmt(tp_ul,1)} ppm |",
        f"| 90-day Mean | {fmt(tp_mean,1)} ppm |",
        f"| % Recent in Controller Setpoint Range | {tp_pct}% ({status(tp_pct)}) |",
        f"| Direction | {tp_dir} |",
        "",
        f"**{prod} recent 20 readings (ppm):**",
        f"`{tp_r20_vals}`",
        "",
        "### Conductivity (Water Efficiency)",
        f"| Parameter | Value |",
        f"|---|---|",
        f"| Controller Setpoint (SP) | {fmt(ec_sp,0)} µS/cm |",
        f"| Dead Band (DB) | {fmt(ec_db,0)} µS/cm |",
        f"| Controller Setpoint Range | {fmt(ec_ll,0)} – {fmt(ec_ul,0)} µS/cm |",
        f"| 90-day Mean | {fmt(ec_mean,1)} µS/cm |",
        f"| % Recent in Controller Setpoint Range | {ec_pct}% ({status(ec_pct)}) |",
        f"| Makeup Water Conductivity | {mu_row_text} |",
        f"| Target COC | {coc['target_coc'] if coc['target_coc'] is not None else 'N/A'} |",
        f"| Actual COC | {coc['actual_coc'] if coc['actual_coc'] is not None else 'N/A'} |",
        f"| COC Deviation | {coc_dev_text} |",
        "",
        "**Conductivity recent 20 readings (µS/cm):**",
        f"`{ec_r20_vals}`",
        "",
        "### Microbial",
        f"| Parameter | Value |",
        f"|---|---|",
        f"| FRC (from field test data) | {'Not available' if frc is None else f'{frc} ppm'} |",
        f"| Biocide relay triggered | {relay_triggered} |",
        f"| Microbial status | {micro_status} |",
        "",
        "**Biocide relay recent 20 readings (1=ON, 0=OFF):**",
        f"`{relay_r20}`",
        "",
        "**ORP recent 20 readings (DO NOT report these values — use spike language only):**",
        f"`{r20(orp_s)}`",
        "",
        "### Supporting parameters (for Performance Summary table ONLY — do not use in narrative prose sections)",
        "> These values (including ORP) MUST appear as real numbers in the Page 4",
        "> Performance Summary table. The 'no absolute ORP values' rule above applies",
        "> only to narrative text, not to this table.",
        f"| Parameter | Mean | Min | Max |",
        f"|---|---|---|---|",
        f"| pH | {fmt(smean(ph_s),2)} | {fmt(smin(ph_s),2)} | {fmt(smax(ph_s),2)} |",
        f"| Turbidity (NTU) | {fmt(smean(turb_s),2)} | {fmt(smin(turb_s),2)} | {fmt(smax(turb_s),2)} |",
        f"| Cell Fouling (%) | {fmt(smean(cf_s),2)} | {fmt(smin(cf_s),2)} | {fmt(smax(cf_s),2)} |",
        f"| ORP (mV) | {fmt(smean(orp_s),1)} | {fmt(smin(orp_s),1)} | {fmt(smax(orp_s),1)} |",
        "",
        "### Service Notes",
        "",
        notes_text,
        "",
        "---",
        "",
        "## COPILOT TASK",
        "",
        "> **Copy everything in the box below and paste into Copilot Chat.**",
        "> **Make sure this file (copilot_task.md) is open in the editor.**",
        "",
        "```",
        f"Read copilot_task.md carefully.",
        f"",
        f"Write the narrative for the {site} {month} cooling water performance report.",
        f"Follow ALL rules in the RULES section exactly.",
        f"",
        f"Save your response as valid JSON to this exact file:",
        f"data_store/{slug}/narrative_cache.json",
        f"",
        f"The JSON must have exactly these keys:",
        f"{{",
        f'  "corrosion_narrative": "2-3 sentences using exact SME wording",',
        f'  "corrosion_chart_comment": "3-4 short lines explaining the corrosion pattern",',
        f'  "scale_narrative": "3-5 sentences about {prod} ONLY — no other parameters",',
        f'  "scale_chart_comment": "3-4 short lines explaining the {prod} pattern",',
        f'  "microbial_narrative": "2-3 sentences about FRC and ORP ONLY — no pH/turbidity",',
        f'  "orp_chart_comment": "3-4 short lines explaining the ORP spike pattern versus copper corrosion",',
        f'  "water_efficiency_narrative": "2-3 sentences about conductivity and COC",',
        f'  "conductivity_chart_comment": "3-4 short lines explaining the conductivity pattern",',
        f'  "product_efficiency_narrative": "2-3 sentences about {prod} consumption",',
        f'  "proactive_support_narrative": "2-3 sentences about alarms and service notes",',
        f'  "closing_summary": "2-3 sentences summarising the month overall"',
        f"}}",
        f"",
        f"Rules:",
        f"- Corrosion: use exact wording with two decimal places: 'During the reporting period, the system remained under good control. The mild steel and copper corrosion rates averaged X.XX mpy and X.XX mpy, respectively, both of which are well within the recommended limits of <5 mpy and <0.5 mpy.'",
        f"- Scale Control: {prod} ONLY. Status MUST be {tp_status} ({tp_pct}% in range).",
        f"- {'Include Observation and Recommendation for ' + tp_dir + ' product level.' if tp_dir in ('HIGH','LOW') else 'Product is within range — no observation/recommendation needed.'}",
        f"- Microbial: FRC and ORP ONLY. No pH, turbidity, cell fouling.",
        f"- NEVER write absolute ORP values in narrative text (microbial_narrative, orp_chart_comment).",
        f"- Proactive Support title: exactly 'Proactive System Support'",
        f"- Performance Summary table (Page 4 of the report, separate from this JSON) MUST include",
        f"  actual numeric Mean/Min/Max for pH, Turbidity, Cell Fouling, AND ORP — pulled from the",
        f"  'Supporting parameters' table in SITE DATA above. Never write N/A, 'Not reported',",
        f"  or 'See chart' for these rows when the data is present in that section.",
        f"- Write professional customer-facing language",
        f"- Return ONLY valid JSON — no markdown, no explanation outside the JSON",
        "```",
        "",
    ]

    task_path = cache / "copilot_task.md"
    task_path.write_text("\n".join(task_lines), encoding="utf-8")
    print(f"✅  copilot_task.md  → {task_path}")

    # ═══════════════════════════════════════════════════════════════════════════
    # Create empty narrative_cache.json template
    # ═══════════════════════════════════════════════════════════════════════════
    empty = {
        "corrosion_narrative":           "",
        "corrosion_chart_comment":       "",
        "scale_narrative":               "",
        "scale_chart_comment":           "",
        "microbial_narrative":           "",
        "orp_chart_comment":             "",
        "water_efficiency_narrative":    "",
        "conductivity_chart_comment":    "",
        "product_efficiency_narrative":  "",
        "proactive_support_narrative":   "",
        "closing_summary":               "",
        "_status": "EMPTY — Copilot must fill this in",
        "_site":   site,
        "_month":  month,
    }
    narrative_path = cache / "narrative_cache.json"
    narrative_path.write_text(json.dumps(empty, indent=2), encoding="utf-8")
    print(f"✅  narrative_cache.json → {narrative_path}  (Copilot fills this in)")

    print(f"")
    print(f"Next steps:")
    print(f"  1. Open VS Code:  code .")
    print(f"  2. Open file:     data_store/{slug}/copilot_task.md")
    print(f"  3. Also open:     data_store/{slug}/narrative_cache.json")
    print(f"  4. Copilot Chat:  Ctrl+Shift+I  (Agent mode)")
    print(f"  5. Copy the COPILOT TASK block (bottom of copilot_task.md)")
    print(f"     and paste into Copilot Chat")
    print(f"  6. Copilot writes narrative_cache.json")
    print(f"  7. Run: python generate_report.py --site \"{site}\" --month \"{month}\"")


if __name__ == "__main__":
    main()