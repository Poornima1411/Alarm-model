# Grading Task — Synthomer Chester SC (US) | May 2026

> **Instructions for Copilot Agent:**
> 1. Read the GENERATED REPORT below
> 2. Compare it against the EXPECTED VALUES and GRADING RUBRIC
> 3. Check every rule violation
> 4. Write your grade as JSON to copilot_grade.json

---

## EXPECTED VALUES (ground truth from source data)

These are the correct values computed from the raw telemetry, SCC, and ADE data.
The generated report must match these — any discrepancy is a factual error.

### Corrosion
| Parameter | Expected Value | Target | Expected Status |
|---|---|---|---|
| Mild Steel (MPY) | 0.24 | <3.0 MPY | Good |
| Copper (MPY) | 0.2200 | <0.5 MPY | Good |

### Traced Product (Scale Control)
| Parameter | Expected Value |
|---|---|
| Controller Setpoint (SP) | 100.0 ppm |
| Dead Band (DB) | 5.0 ppm |
| Control Range | 95.0 – 105.0 ppm |
| Mean | 106.8 ppm |
| % in Range (recent_20) | 10.0% |
| Expected Status | Action Required |
| Direction | HIGH |

### Conductivity (Water Efficiency)
| Parameter | Expected Value |
|---|---|
| Controller Setpoint (SP) | 1000 µS/cm |
| Control Range | 950 – 1050 µS/cm |
| % in Range (recent_20) | 100.0% |
| Expected Status | Good |

### Microbial
| Parameter | Expected Value |
|---|---|
| FRC | Not available |
| Biocide relay active | Yes |
| Expected Status | Stable |

### Service Notes
Service notes present: No (0 note(s))

---

## GENERATED NARRATIVE (from narrative_cache.json)

This is what the AI wrote. Grade each field.

### corrosion_narrative

> The average mild steel corrosion rate was 0.24 MPY against the target of within 3.0 MPY, and the average copper corrosion rate was 0.2200 MPY against the target of within 0.5 MPY. Corrosion control status was Good, with both metals operating within the program targets for the reporting period.

### corrosion_chart_comment

> Mild steel averaged 0.24 MPY and copper averaged 0.2200 MPY, both within their targets, indicating good corrosion control with no corrective action required at this time.

### scale_narrative

> Scale Control status is Action Required because only 10.0% of recent Traced Product readings were within the Controller Setpoint range. Observation: Traced Product concentration was above the Controller Setpoint upper control limit of 105.0 ppm, indicating overfeeding. The Traced Product mean was 106.8 ppm compared with the Controller Setpoint target of 100.0 ppm and range of 95.0-105.0 ppm. Conductivity was stable during the same period, indicating this is a product feed or calibration issue, not a water loss event. Recommendation: Check dosing pump rate and reduce if running above setpoint. Verify fluorometer calibration with a grab sample. Review the dosing schedule and confirm the relay is not in manual override.

### scale_chart_comment

> Traced Product averaged 106.8 ppm versus the 95.0-105.0 ppm Controller Setpoint range, which is 1.7% above the upper limit and indicates overdosing - recommend decreasing pump stroke and verifying fluorometer calibration; this will be reviewed during the upcoming service visit.

### microbial_narrative

> Microbial Control status was Stable. FRC data was not available in the field test data for this reporting period and will be checked during the upcoming service visit. ORP spike response after timer-controlled biocide feed was consistent, indicating the system responded to treatment.

### orp_chart_comment

> The ORP chart showed a consistent spike pattern after timer-controlled biocide dosing was triggered, indicating treatment response and good control with no corrective action required at this time.

### water_efficiency_narrative

> Water Efficiency status was Good, with 100.0% of recent conductivity readings within the 950-1050 µS/cm Controller Setpoint range. The 90-day average conductivity was 910.5 µS/cm against a 1000 µS/cm Controller Setpoint, and the actual COC was 9.11 compared with the target COC of 10.0. This represents an 8.9% deviation from target COC, which remains within acceptable performance for the period.

### conductivity_chart_comment

> Conductivity averaged 910.5 µS/cm versus the 950-1050 µS/cm Controller Setpoint range, which is 4.2% below the lower limit on the 90-day average while recent readings showed 100.0% in-range good control; continue monitoring blowdown settings and makeup water conditions.

### product_efficiency_narrative

> Product Efficiency requires attention because Traced Product averaged 106.8 ppm versus the 100.0 ppm Controller Setpoint target and only 10.0% of recent readings were in range, indicating the product is being overdosed. Actual consumption was not available for this reporting period. The dosing pump rate may be too high or the fluorometer may need recalibration; decrease the pump stroke, verify fluorometer calibration with a grab sample, check the dosing valve, and inspect the probe, which will be addressed at the next service visit.

### proactive_support_narrative

> Proactive System Support: No alarm data was available for this reporting period, so performance was reviewed against the Ackumen average of 6 alarms per controller. No service notes were recorded, and no completed service actions were documented for the month.

### closing_summary

> Overall, the system maintained good corrosion control, stable microbial response, and good water efficiency during May 2026. The primary follow-up item is Traced Product overfeeding, which points to product feed or fluorometer calibration review during the upcoming service visit. Addressing the dosing setup should help return product concentration to the Controller Setpoint range while maintaining the current corrosion, microbial, and water efficiency performance.

---

## GENERATED MARKDOWN REPORT

Full report text — check structure, sections, charts, table, checklist.

````markdown
# Synthomer Chester SC (US)
## Cooling Water Performance Report

**Reporting Month:** May 2026  
**System:** Cooling Tower  
**Plant System:** Cooling System  
**Controller:** 84253f5ee2c1  
**Prepared:** June 19, 2026  

---

<div style="page-break-after: always;"></div>

# Executive Summary

## System Health Check

### Corrosion Control

Mild steel and copper corrosion telemetry remained low during the reporting period. SCC Section 2 does not include programmed alarm or control limits for the corrosion probes, so no site-specific SCC corrosion limit comparison is available for May.

Recent corrosion readings were steady, with mild steel and copper readings remaining consistent near the end of the telemetry period. This indicates stable corrosion-control performance based on available controller data.

### Scale Control

Scale control was evaluated using the SCC programmed conductivity control range, not averages alone.

| Control Parameter | SCC Setpoint | SCC Dead Band | SCC Control Range | Recent Readings In Control |
|---|---:|---:|---:|---:|
| Electrode Conductivity | 1000.0 µS/cm | 50.0 µS/cm | 950.0-1050.0 µS/cm | 20 of 20 readings, 100% |

Conductivity was within the programmed SCC control range for all 20 recent readings provided in the report context. This indicates stable blowdown control relative to the active SCC conductivity program.

### Microbial Control

FRC was not available in the May ADE field-test data and will be checked at the upcoming service visit.

Delta ORP / ORP spike response appeared stable in the recent telemetry trend. No absolute ORP values are reported here. SCC Section 2 does not include programmed alarm or control limits for microbial-control parameters other than the available controller signals, so microbial conclusions are limited to the available FRC status, Delta ORP / ORP spike language, turbidity trend, and cell-fouling trend.

---

<div style="page-break-after: always;"></div>

# Executive Summary, Continued

## Water Efficiency

Actual cycles of concentration could not be calculated from the provided data because makeup water conductivity was not included in REPORT_CONTEXT.md.

The SCC conductivity control setpoint is 1000.0 µS/cm with a 50.0 µS/cm dead band, giving a programmed control range of 950.0-1050.0 µS/cm. Recent conductivity readings were within this SCC control range 100% of the time based on the 20 readings provided.

| Water Efficiency Item | May 2026 Result |
|---|---|
| Actual COC | Not available from provided data |
| Target COC | Not available as a COC value from provided data |
| SCC conductivity control target | 1000.0 µS/cm |
| SCC conductivity control range | 950.0-1050.0 µS/cm |
| Recent conductivity readings in SCC control | 100% |

## Product Efficiency

The SCC product field for the programmed treatment controls is listed as `None`. Therefore, this report uses the SCC sensor/control names rather than inventing product names.

| SCC Control | Product Name in SCC | SCC Setpoint | SCC Dead Band | SCC Control Range | Recent Readings In Control |
|---|---|---:|---:|---:|---:|
| Fluorometer Ch1 (Traced Product) | None | 100.0 ppm | 5.0 ppm | 95.0-105.0 ppm | 3 of 20 readings, 15% |
| Electrode Conductivity | None | 1000.0 µS/cm | 50.0 µS/cm | 950.0-1050.0 µS/cm | 20 of 20 readings, 100% |

The traced-product signal was above the SCC programmed control range for most recent readings, while conductivity remained within its SCC programmed range. Product efficiency should be reviewed against feed activity and field verification during the next service opportunity.

## Proactive System Support

SCC Section 2 lists all programmed alarm limits as `NULL` for the controller. Because no HH, H, L, or LL values are programmed in the SCC data provided, no SCC alarm-limit excursion can be calculated from the report context.

No service notes were found for May 2026. Therefore, no documented Actions Completed were available to include for this reporting period.

---

<div style="page-break-after: always;"></div>

# Performance Summary

SCC Section 2 is populated and is therefore used as the source for site-specific programmed control values. Section 6 standard limits were not used as site-specific SCC limits.

| Parameter | SCC Programmed Limit / Setpoint | May Result From Provided Data | Performance Comment |
|---|---:|---:|---|
| Fluorometer Ch1 (Traced Product) | SP 100.0 ppm, DB 5.0 ppm | Mean 106.8 ppm; recent readings in control 15% | Recent readings were mostly above the SCC control range of 95.0-105.0 ppm. |
| Electrode Conductivity | SP 1000.0 µS/cm, DB 50.0 µS/cm | Mean 910.5 µS/cm; recent readings in control 100% | Recent readings were fully within the SCC control range of 950.0-1050.0 µS/cm. |
| Fluorometer Ch2 (Tagged Polymer) | No SCC alarm/control limit programmed | Mean 69.7 ppm | No SCC limit comparison available. |
| pH | No SCC alarm/control limit programmed | Mean 9.7 pH | No SCC limit comparison available. |
| Mild Steel Corrosion | No SCC alarm/control limit programmed | Mean 0.24 MPY | No SCC limit comparison available. |
| Copper Corrosion | No SCC alarm/control limit programmed | Mean 0.22 MPY | No SCC limit comparison available. |
| Turbidity | No SCC alarm/control limit programmed | Mean 9.9 NTU | No SCC limit comparison available. |
| Cell Fouling | No SCC alarm/control limit programmed | Mean 7.5% | No SCC limit comparison available. |
| FRC | No ADE value found | Not available | FRC will be checked during the upcoming service visit. |
| Delta ORP / ORP Spike Response | No SCC alarm/control limit programmed | Stable recent response language only | Absolute ORP values are intentionally not reported. |

---

<div style="page-break-after: always;"></div>

# Charts and Comments

## Traced Product Recent Control Trend

SCC control range: 95.0-105.0 ppm

| Recent Reading Group | Readings in SCC Control | Comment |
|---|---:|---|
| Readings 1-5 | 1 of 5 | Mostly above SCC control range. |
| Readings 6-10 | 1 of 5 | Mostly above SCC control range. |
| Readings 11-15 | 0 of 5 | Above SCC control range. |
| Readings 16-20 | 1 of 5 | Mostly above SCC control range. |
| Total Recent Readings | 3 of 20, 15% | Product control should be reviewed. |

**Comment:** Traced Product was within the SCC programmed control range for 15% of the recent readings provided. The available trend indicates the traced-product signal was generally above the SCC range, so feed control should be reviewed during the next service opportunity.

## Conductivity Recent Control Trend

SCC control range: 950.0-1050.0 µS/cm

| Recent Reading Group | Readings in SCC Control | Comment |
|---|---:|---|
| Readings 1-5 | 5 of 5 | Within SCC control range. |
| Readings 6-10 | 5 of 5 | Within SCC control range. |
| Readings 11-15 | 5 of 5 | Within SCC control range. |
| Readings 16-20 | 5 of 5 | Within SCC control range. |
| Total Recent Readings | 20 of 20, 100% | Conductivity control was stable. |

**Comment:** Conductivity remained within the SCC programmed control range for 100% of the recent readings provided, supporting stable scale-control performance against the active controller program.

---

<div style="page-break-after: always;"></div>

# Follow-Up Items

| Item | Basis | Follow-Up |
|---|---|---|
| FRC verification | FRC was not found in May ADE data. | Check FRC during the upcoming service visit. |
| Traced Product control review | Recent readings were in SCC control 15% of the time. | Review traced-product feed control and field calibration status. |
| COC calculation | Makeup water conductivity was not provided. | Capture makeup conductivity if actual COC reporting is required. |
| Service actions | No May service notes were found. | Include documented Actions Completed when service notes are available. |

# Closing Summary

The Cooling Tower showed stable conductivity control against the SCC programmed setpoint, with 100% of recent conductivity readings within the SCC control range. Traced Product control was less consistent, with 15% of recent readings within the SCC programmed range and most recent values above the target band.

FRC was not available from May ADE data and will be checked at the upcoming service visit. No documented May service-note actions were available, and no SCC alarm limits were programmed in the provided Section 2 data.
````

---

## RULE-BASED SCORECARD (automated checks already run)

Overall: 143.0/161.0 (88.8%) — Grade: B

**Failed checks:**

- ✗ Status label present: 
- ✗ Status matches % in range: No status label found in scale narrative
- ✗ Prepared Date / Prepared By present: 
- ✗ Report Status field present: 
- ✗ Final Release Approval checklist present: 

Use this as a starting point. You may agree or disagree with the automated
scores, but you must explain your reasoning when you differ.

---

## GRADING RUBRIC

Grade the report on these dimensions. Each dimension is scored 1-10.

### 1. Factual Accuracy (weight: 25%)
- Are the MS and Cu corrosion values correct?
- Is the traced product % in range correct?
- Is the conductivity % in range correct?
- Is FRC correctly reported or stated as unavailable?
- Are status labels (Good/Stable/Action Required) correct for each section?
- Does % in range match the expected value from recent_20?
- 10 = all values match source data exactly
- 1 = multiple factual errors or invented data

### 2. Rule Compliance (weight: 25%)
- Exact corrosion wording format used?
- Scale Control discusses Traced Product ONLY (no conductivity, pH, etc.)?
- Microbial Control discusses FRC and ORP ONLY (no pH, turbidity)?
- No absolute ORP values anywhere in narrative?
- No 'relay firing' — uses 'biocide dosing was triggered' etc.?
- ORP spike comment present?
- Product Name from SCC used (not generic 'inhibitor'/'biocide')?
- Proactive System Support title (not 'Alarms')?
- Observation + Recommendation present when product HIGH or LOW?
- Root cause uses conductivity comparison?
- 'Never in range' stated explicitly if 0% in range?
- 10 = every rule followed perfectly
- 1 = many rule violations

### 3. Report Structure (weight: 15%)
- Title page with all required fields?
- Executive Summary as narrative prose (not KPI tiles)?
- All 6 sections present: Corrosion, Scale, Microbial, Water Eff, Product Eff, Proactive?
- Performance Summary table on Page 4?
- Charts present with comments below each?
- Final Release Approval checklist?
- Within 8-page limit?
- 10 = perfect structure matching training reports
- 1 = missing major sections or wrong structure

### 4. Writing Quality (weight: 15%)
- Professional, customer-facing tone?
- Factual and concise — not vague or generic?
- Follows the 'what happened → why → what was done → status' pattern?
- Chart comments are specific and actionable (not boilerplate)?
- No placeholder text or generic filler?
- 10 = reads like a polished SME-written report
- 1 = vague, generic, or unprofessional

### 5. Training Report Alignment (weight: 20%)
- Does the tone match the Flowserve / St Joseph / Synthomer training reports?
- Are deviations explained with root cause like the training examples?
- Is the narrative depth similar (not too short, not too verbose)?
- Does it follow the 'observation → recommendation → current status' pattern?
- Would a Buckman engineer accept this as a final report with minor edits?
- 10 = indistinguishable from training report quality
- 1 = clearly machine-generated, wouldn't pass review

---

## COPILOT TASK

> **Copy everything in the box below and paste into Copilot Chat.**
> **Make sure this file (grading_task.md) is open in the editor.**

```
Read grading_task.md carefully.

Grade the Synthomer Chester SC (US) May 2026 cooling water performance report.
Compare the GENERATED NARRATIVE and GENERATED MARKDOWN REPORT against the
EXPECTED VALUES and GRADING RUBRIC.

Check every rule. Check every expected value. Be strict but fair.

Save your response as valid JSON to this exact file:
data_store/synthomer_chester_sc_us_may_2026/copilot_grade.json

The JSON must have exactly this structure:
{
  "site": "Synthomer Chester SC (US)",
  "month": "May 2026",
  "graded_at": "<current ISO timestamp>",
  "dimensions": {
    "factual_accuracy": {
      "score": <1-10>,
      "weight": 0.25,
      "findings": [
        "Finding 1: what was correct or incorrect",
        "Finding 2: ..."
      ]
    },
    "rule_compliance": {
      "score": <1-10>,
      "weight": 0.25,
      "findings": ["..."]
    },
    "report_structure": {
      "score": <1-10>,
      "weight": 0.15,
      "findings": ["..."]
    },
    "writing_quality": {
      "score": <1-10>,
      "weight": 0.15,
      "findings": ["..."]
    },
    "training_report_alignment": {
      "score": <1-10>,
      "weight": 0.20,
      "findings": ["..."]
    }
  },
  "weighted_score": <computed: sum of score*weight for each dimension>,
  "grade": "<A if >=9.0 | B if >=8.0 | C if >=7.0 | D if >=6.0 | F otherwise>",
  "critical_issues": [
    "List any issues that would block report release (factual errors, rule violations)"
  ],
  "improvement_suggestions": [
    "Specific, actionable suggestions to improve the report"
  ],
  "overall_assessment": "2-3 sentence summary of report quality"
}

Rules:
- Be specific in findings — cite exact text from the report
- Flag every factual error (wrong value, wrong status, wrong %)
- Flag every rule violation (see GRADING RUBRIC section 2)
- Compare tone and depth to Buckman training reports
- weighted_score = sum of (score * weight) across all 5 dimensions
- Return ONLY valid JSON — no markdown, no explanation outside the JSON
```
