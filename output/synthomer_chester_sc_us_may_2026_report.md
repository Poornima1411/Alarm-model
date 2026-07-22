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