# Copilot Task — Synthomer Chester SC (US) | May 2026

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
- Status MUST be: Action Required (because 10.0% of recent readings are in Controller Setpoint range)
- 10.0% in range means: Good>75%, Stable 25-75%, Action Required<25%
- Product is HIGH (HIGH=above upper limit, LOW=below lower limit, OK=in range)
- MUST include Observation: 'Traced Product concentration was above the Controller Setpoint upper
  control limit of 105.0 ppm, indicating overfeeding.'
- MUST include Recommendation: 'Check dosing pump rate and reduce if running
  above setpoint. Verify fluorometer calibration with a grab sample. Review
  the dosing schedule and confirm the relay is not in manual override.'
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
- Controller Setpoint conductivity: 1000 µS/cm, range 950–1050 µS/cm
- 100.0% of recent readings within Controller Setpoint control range
- 90-day average: 910.5 µS/cm
- Makeup water conductivity: 100.0 µS/cm
- Target COC (Controller Setpoint / MU conductivity): 10.0
- Actual COC (90-day average conductivity / MU conductivity): 9.11
- COC deviation from target: 8.9%  →  Status: Good
- State the actual COC value and deviation explicitly — do NOT say COC cannot be calculated.

**PRODUCT EFFICIENCY — must explain WHY performance is good or bad:**
- Product name: Traced Product
- Mean: 106.8 ppm vs Controller Setpoint target 100.0 ppm (range 95.0–105.0 ppm)
- 10.0% in range
- Product direction: HIGH
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
- scale_chart_comment: state Traced Product mean vs range 95.0–105.0 ppm.
  State the exact % above or below range. If HIGH: 'indicates overdosing —
  recommend decreasing pump stroke and verifying fluorometer calibration.'
  If LOW: 'indicates underdosing — check pump prime and inspect feed line.'
- orp_chart_comment: describe ORP spike pattern relative to biocide dosing events.
  Never say 'relay firing'. Say 'biocide dosing was triggered' or 'pump was activated'.
- conductivity_chart_comment: state conductivity vs setpoint 1000 µS/cm.
  If deviating: recommend reviewing blowdown valve operation and checking for water losses.

---

## SITE DATA

**Site:** Synthomer Chester SC (US)
**Month:** May 2026
**Controller:** 84253f5ee2c1

### Corrosion
| Parameter | Mean | Min | Max | Target | Status |
|---|---|---|---|---|---|
| Mild Steel (MPY) | 0.24 | 0.10 | 0.69 | <3.0 | Good |
| Copper (MPY) | 0.2200 | 0.0000 | 2.1605 | <0.5 | Good |

**Mild Steel recent 20 readings (MPY):**
`[0.3653, 0.3653, 0.3653, 0.3653, 0.4571, 0.4571, 0.4571, 0.4571, 0.4571, 0.4571, 0.4571, 0.4712, 0.4712, 0.4712, 0.4712, 0.4712, 0.3789, 0.3789, 0.3789, 0.3789]`

**Copper recent 20 readings (MPY):**
`[0.3509, 0.3509, 0.3882, 0.3882, 0.3882, 0.3882, 0.3882, 0.4108, 0.4108, 0.4108, 0.4108, 0.4108, 0.4108, 0.4108, 0.405, 0.405, 0.405, 0.405, 0.405, 0.4093]`

### Traced Product (Scale Control)
| Parameter | Value |
|---|---|
| Controller Setpoint (SP) | 100.0 ppm |
| Dead Band (DB) | 5.0 ppm |
| Controller Setpoint Range | 95.0 – 105.0 ppm |
| 90-day Mean | 106.8 ppm |
| % Recent in Controller Setpoint Range | 10.0% (Action Required) |
| Direction | HIGH |

**Traced Product recent 20 readings (ppm):**
`[117.4343, 115.7319, 105.9274, 103.4144, 104.5747, 109.1079, 105.9771, 107.7875, 111.0493, 109.2296, 110.8329, 111.9109, 118.3287, 114.4415, 112.4449, 112.5415, 113.0441, 116.996, 119.1442, 113.3044]`

### Conductivity (Water Efficiency)
| Parameter | Value |
|---|---|
| Controller Setpoint (SP) | 1000 µS/cm |
| Dead Band (DB) | 50 µS/cm |
| Controller Setpoint Range | 950 – 1050 µS/cm |
| 90-day Mean | 910.5 µS/cm |
| % Recent in Controller Setpoint Range | 100.0% (Good) |
| Makeup Water Conductivity | 100.0 µS/cm |
| Target COC | 10.0 |
| Actual COC | 9.11 |
| COC Deviation | 8.9% |

**Conductivity recent 20 readings (µS/cm):**
`[1034.0346, 1012.7648, 976.3503, 954.1241, 964.1927, 967.2164, 975.5385, 981.6506, 988.1744, 986.869, 989.2113, 993.4252, 995.729, 1001.314, 1014.1687, 1017.9613, 1025.8738, 1032.3566, 1036.4142, 1013.4669]`

### Microbial
| Parameter | Value |
|---|---|
| FRC (from field test data) | Not available |
| Biocide relay triggered | True |
| Microbial status | Stable |

**Biocide relay recent 20 readings (1=ON, 0=OFF):**
`[6.0, 0.0, 6.0, 0.0, 6.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0]`

**ORP recent 20 readings (DO NOT report these values — use spike language only):**
`[527.0263, 526.7227, 527.8765, 529.6108, 530.3602, 530.6698, 530.482, 530.0795, 529.4794, 529.3257, 529.3296, 529.3135, 529.3099, 529.0474, 528.662, 528.5317, 528.637, 528.0401, 527.8354, 528.3025]`

### Supporting parameters (for Performance Summary table ONLY — do not use in narrative prose sections)
> These values (including ORP) MUST appear as real numbers in the Page 4
> Performance Summary table. The 'no absolute ORP values' rule above applies
> only to narrative text, not to this table.
| Parameter | Mean | Min | Max |
|---|---|---|---|
| pH | 9.71 | 8.34 | 10.12 |
| Turbidity (NTU) | 9.93 | 2.41 | 19.94 |
| Cell Fouling (%) | 7.45 | 2.16 | 14.38 |
| ORP (mV) | 547.0 | 480.5 | 849.7 |

### Service Notes

No service notes were recorded for this reporting period.

---

## COPILOT TASK

> **Copy everything in the box below and paste into Copilot Chat.**
> **Make sure this file (copilot_task.md) is open in the editor.**

```
Read copilot_task.md carefully.

Write the narrative for the Synthomer Chester SC (US) May 2026 cooling water performance report.
Follow ALL rules in the RULES section exactly.

Save your response as valid JSON to this exact file:
data_store/synthomer_chester_sc_us_may_2026/narrative_cache.json

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
- Scale Control: Traced Product ONLY. Status MUST be Action Required (10.0% in range).
- Include Observation and Recommendation for HIGH product level.
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
