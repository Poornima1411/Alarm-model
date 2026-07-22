# Copilot Task — St. Joseph's Hospital Savannah GA (US) | May 2026

> **Instructions for Copilot Agent:**
> 1. Read ALL the data below carefully
> 2. Follow EVERY rule in the RULES section
> 3. Write the narrative_cache.json file at the path shown
> 4. Do not add markdown, do not truncate, write valid JSON

---

## RULES (follow exactly)

**LANGUAGE RULES — apply everywhere:**
- Never say 'relay firing' or 'relay was firing'. Say 'dosing was triggered',
  'biocide pump was activated', or 'blowdown valve was triggered'.
- Never say 'relay firing' for product dosing. Say 'product dosing pump was active'.

**CORROSION CONTROL:**
- Use this exact wording: 'The average mild steel corrosion rate was X MPY against
  the target of within 3.0 MPY, and the average copper corrosion rate was X MPY
  against the target of within 0.5 MPY.'
- Status: Good

**SCALE CONTROL:**
- Write ONLY about Traced Product. Do NOT mention conductivity, pH, turbidity, or anything else.
- Status MUST be: Action Required (because 20.0% of recent readings are in Controller Setpoint range)
- 20.0% in range means: Good>75%, Stable 25-75%, Action Required<25%
- Product is OK (HIGH=above upper limit, LOW=below lower limit, OK=in range)
- Root cause to include: 'Conductivity was stable during the same period, indicating this is a product feed or calibration issue, not a water loss event.'

**MICROBIAL CONTROL:**
- Write ONLY about FRC and ORP. Do NOT mention pH, turbidity, cell fouling, or anything else.
- Status: Stable
- FRC: NOT in field test data. Write: 'FRC data was not available in the field test data for this reporting period and will be checked during the upcoming service visit.'
- Biocide relay was triggered: True
- MANDATORY ORP sentence: 'ORP spike response after timer-controlled biocide feed was consistent, indicating the system responded to treatment.'
- NEVER write absolute ORP values in the microbial_narrative or orp_chart_comment
  fields (or any other narrative text). Relative/spike language only in narrative prose.
- EXCEPTION — this restriction does NOT apply to the Performance Summary table on
  Page 4 of the final report. That table MUST show the actual numeric ORP
  Mean/Min/Max from the 'Supporting parameters' section below, the same way it
  shows every other sensor. Do not write 'Not reported' or 'See chart' for ORP
  in that table.

**WATER EFFICIENCY:**
- Discuss conductivity and COC here (NOT in Scale Control).
- Controller Setpoint conductivity: 600 µS/cm, range 570–630 µS/cm
- 90.0% of recent readings within Controller Setpoint control range
- 90-day average: 651.4 µS/cm
- Makeup water conductivity: 224.4 µS/cm
- Target COC (Controller Setpoint / MU conductivity): 2.67
- Actual COC (90-day average conductivity / MU conductivity): 2.9
- COC deviation from target: 8.6%  →  Status: Good
- State the actual COC value and deviation explicitly — do NOT say COC cannot be calculated.

**PRODUCT EFFICIENCY — must explain WHY performance is good or bad:**
- Product name: Traced Product
- Mean: 44.5 ppm vs Controller Setpoint target 43.0 ppm (range 40.9–45.1 ppm)
- 20.0% in range
- Product direction: OK
- If product is HIGH (overdosing): state the product is being overdosed.
  Explain: dosing pump rate may be too high, fluorometer may need recalibration.
  Recommend: decrease the pump stroke, verify fluorometer calibration with a grab
  sample, check the dosing valve, inspect the probe. State this will be addressed
  at the next service visit.
- If product is LOW (underdosing): state the product is being underdosed.
  Explain: dosing pump may have lost prime, inventory may be low, feed line may be blocked.
  Recommend: check pump prime, verify inventory, inspect feed line for blockage or air lock,
  calibrate fluorometer. State this will be addressed at the next service visit.
- If product is OK (in range): state dosing efficiency was well maintained.
- Actual consumption not available — state this.

**PROACTIVE SYSTEM SUPPORT:**
- Section title MUST be exactly: Proactive System Support (never 'Alarms')
- No alarm data available — state Ackumen average is 6 alarms per controller
- Incorporate any service note Actions Completed below

**CHART COMMENTS — must be specific and actionable (not vague):**
  Every chart comment MUST include:
  1. The exact % deviation from the Controller Setpoint range
  2. What this means: overdosing / underdosing / good control / water loss
  3. A specific action if out of range: decrease pump stroke, check valve,
     inspect probe, verify calibration, review blowdown settings, etc.
  4. If action needed: 'This will be reviewed during the upcoming service visit.'

- corrosion_chart_comment: state MS and Cu averages and whether within targets.
  If approaching limit: recommend inspecting probes and reviewing inhibitor dosing.
- scale_chart_comment: state Traced Product mean vs range 40.9–45.1 ppm.
  State the exact % above or below range. If HIGH: 'indicates overdosing —
  recommend decreasing pump stroke and verifying fluorometer calibration.'
  If LOW: 'indicates underdosing — check pump prime and inspect feed line.'
- orp_chart_comment: describe ORP spike pattern relative to biocide dosing events.
  Never say 'relay firing'. Say 'biocide dosing was triggered' or 'pump was activated'.
- conductivity_chart_comment: state conductivity vs setpoint 600 µS/cm.
  If deviating: recommend reviewing blowdown valve operation and checking for water losses.

---

## SITE DATA

**Site:** St. Joseph's Hospital Savannah GA (US)
**Month:** May 2026
**Controller:** 84253FAB8CC5

### Corrosion
| Parameter | Mean | Min | Max | Target | Status |
|---|---|---|---|---|---|
| Mild Steel (MPY) | 0.10 | 0.10 | 0.11 | <3.0 | Good |
| Copper (MPY) | 0.0474 | 0.0000 | 0.1178 | <0.5 | Good |

**Mild Steel recent 20 readings (MPY):**
`[0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]`

**Copper recent 20 readings (MPY):**
`[0.0249, 0.0246, 0.0246, 0.0246, 0.0246, 0.0246, 0.0251, 0.0251, 0.0251, 0.0251, 0.0251, 0.0249, 0.0248, 0.0248, 0.0248, 0.0248, 0.0248, 0.0248, 0.0248, 0.0248]`

### Traced Product (Scale Control)
| Parameter | Value |
|---|---|
| Controller Setpoint (SP) | 43.0 ppm |
| Dead Band (DB) | 2.1 ppm |
| Controller Setpoint Range | 40.9 – 45.1 ppm |
| 90-day Mean | 44.5 ppm |
| % Recent in Controller Setpoint Range | 20.0% (Action Required) |
| Direction | OK |

**Traced Product recent 20 readings (ppm):**
`[47.8084, 48.2865, 44.42, 40.9076, 45.0709, 41.5716, 48.2977, 49.8347, 49.3038, 48.0969, 49.3857, 48.3316, 48.844, 50.1904, 47.5769, 48.5407, 50.1482, 48.0618, 47.8958, 49.4273]`

### Conductivity (Water Efficiency)
| Parameter | Value |
|---|---|
| Controller Setpoint (SP) | 600 µS/cm |
| Dead Band (DB) | 30 µS/cm |
| Controller Setpoint Range | 570 – 630 µS/cm |
| 90-day Mean | 651.4 µS/cm |
| % Recent in Controller Setpoint Range | 90.0% (Good) |
| Makeup Water Conductivity | 224.4 µS/cm |
| Target COC | 2.67 |
| Actual COC | 2.9 |
| COC Deviation | 8.6% |

**Conductivity recent 20 readings (µS/cm):**
`[597.7449, 604.1445, 593.1188, 583.4911, 574.0902, 565.2564, 569.4635, 578.6168, 580.3257, 581.4413, 590.1326, 589.5799, 596.4386, 606.031, 598.9799, 606.3427, 615.2377, 610.0243, 613.9779, 622.6806]`

### Microbial
| Parameter | Value |
|---|---|
| FRC (from field test data) | Not available |
| Biocide relay triggered | True |
| Microbial status | Stable |

**Biocide relay recent 20 readings (1=ON, 0=OFF):**
`[1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0]`

**ORP recent 20 readings (DO NOT report these values — use spike language only):**
`[17.2162, 21.1615, 23.8624, 25.8962, 24.9555, 26.2646, 27.06, 28.722, 29.1394, 29.6206, 30.8251, 30.8557, 33.4513, 34.7596, 35.2331, 37.2067, 36.2212, 32.5158, 31.5693, 31.8894]`

### Supporting parameters (for Performance Summary table ONLY — do not use in narrative prose sections)
> These values (including ORP) MUST appear as real numbers in the Page 4
> Performance Summary table. The 'no absolute ORP values' rule above applies
> only to narrative text, not to this table.
| Parameter | Mean | Min | Max |
|---|---|---|---|
| pH | 8.92 | 8.50 | 9.34 |
| Turbidity (NTU) | 0.01 | 0.00 | 8.19 |
| Cell Fouling (%) | 4.28 | 0.87 | 14.12 |
| ORP (mV) | 147.4 | 15.4 | 367.0 |

### Service Notes

No service notes were recorded for this reporting period.

---

## COPILOT TASK

> **Copy everything in the box below and paste into Copilot Chat.**
> **Make sure this file (copilot_task.md) is open in the editor.**

```
Read copilot_task.md carefully.

Write the narrative for the St. Joseph's Hospital Savannah GA (US) May 2026 cooling water performance report.
Follow ALL rules in the RULES section exactly.

Save your response as valid JSON to this exact file:
data_store/st_joseph_s_hospital_savannah_ga_us_may_2026/narrative_cache.json

The JSON must have exactly these keys:
{
  "corrosion_narrative": "2-3 sentences using exact SME wording",
  "corrosion_chart_comment": "1 sentence describing the corrosion trend chart",
  "scale_narrative": "3-5 sentences about Traced Product ONLY — no other parameters",
  "scale_chart_comment": "1 sentence describing the Traced Product trend chart",
  "microbial_narrative": "2-3 sentences about FRC and ORP ONLY — no pH/turbidity",
  "orp_chart_comment": "1 sentence describing the ORP spike pattern chart",
  "water_efficiency_narrative": "2-3 sentences about conductivity and COC",
  "conductivity_chart_comment": "1 sentence describing the conductivity trend chart",
  "product_efficiency_narrative": "2-3 sentences about Traced Product consumption",
  "proactive_support_narrative": "2-3 sentences about alarms and service notes",
  "closing_summary": "2-3 sentences summarising the month overall"
}

Rules:
- Corrosion: use exact wording 'average mild steel corrosion rate was X MPY against the target of within 3.0 MPY'
- Scale Control: Traced Product ONLY. Status MUST be Action Required (20.0% in range).
- Product is within range — no observation/recommendation needed.
- Microbial: FRC and ORP ONLY. No pH, turbidity, cell fouling.
- NEVER write absolute ORP values in narrative text (microbial_narrative, orp_chart_comment).
- Proactive Support title: exactly 'Proactive System Support'
- Performance Summary table (Page 4 of the report, separate from this JSON) MUST include
  actual numeric Mean/Min/Max for pH, Turbidity, Cell Fouling, AND ORP — pulled from the
  'Supporting parameters' table in SITE DATA above. Never write N/A, 'Not reported',
  or 'See chart' for these rows when the data is present in that section.
- Write professional customer-facing language
- Return ONLY valid JSON — no markdown, no explanation outside the JSON
```
