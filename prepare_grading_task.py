"""
prepare_grading_task.py
────────────────────────
Step 5b — Run AFTER generate_report.py (and optionally after score_report.py).

Creates a grading task file that Copilot reads to evaluate the generated report
against the training-report standards and rules from report-agent.md.

Creates two files in data_store/<slug>/:

    grading_task.md       ← Open in VS Code, paste COPILOT TASK into Copilot Chat.
                            Copilot reads the report and writes a structured grade.

    copilot_grade.json    ← Empty template. Copilot fills this in.

USAGE
─────
    python prepare_grading_task.py --site "Synthomer Chester SC (US)" --month "May 2026"

WORKFLOW
────────
    1. python prefetch_site.py             --site "..." --month "..."
    2. python prepare_copilot_task.py      --site "..." --month "..."
    3. Copilot Chat → writes narrative_cache.json
    4. python generate_report.py           --site "..." --month "..."
    5. python score_report.py              --site "..." --month "..."   (rule-based)
    6. python prepare_grading_task.py      --site "..." --month "..."   ← THIS
    7. Open VS Code → open grading_task.md
    8. Open Copilot Chat (Ctrl+Shift+I, Agent mode)
    9. Paste the COPILOT TASK section into Copilot Chat
   10. Copilot writes copilot_grade.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT       = Path(__file__).parent
DATA_STORE = ROOT / "data_store"
OUTPUT_DIR = ROOT / "output"


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


def main():
    args  = parse_args()
    site  = args.site
    month = args.month
    slug  = slugify(f"{site}_{month}")
    cache = DATA_STORE / slug

    if not (cache / "manifest.json").exists():
        print(f"[ERROR] No prefetch data at {cache}")
        sys.exit(1)

    # ── Load generated report ────────────────────────────────────────────────
    narr_path = cache / "narrative_cache.json"
    if not narr_path.exists():
        print(f"[ERROR] narrative_cache.json not found — run generate_report.py first.")
        sys.exit(1)
    narr = _load(narr_path, {})
    if narr.get("_status", "").startswith("EMPTY"):
        print("[ERROR] narrative_cache.json is still empty — Copilot hasn't written it.")
        sys.exit(1)

    md_path = OUTPUT_DIR / f"{slug}_report.md"
    md_report = md_path.read_text(encoding="utf-8") if md_path.exists() else None

    # ── Load source data ─────────────────────────────────────────────────────
    controllers = _load(cache / "controllers.json", [])
    scc         = _load(cache / "scc.json", [])
    ade         = _load(cache / "ade_data.json", [])
    notes       = _load(cache / "service_notes.json", [])

    telem_sensors = {}
    tel_dir = cache / "telemetry"
    if tel_dir.exists():
        for f in tel_dir.glob("*_summary.json"):
            d = json.loads(f.read_text())
            for name, stats in d.get("sensors", {}).items():
                telem_sensors[name.lower()] = stats

    # ── Load rule-based scorecard (if available) ─────────────────────────────
    sc_path = OUTPUT_DIR / f"{slug}_scorecard.json"
    scorecard = _load(sc_path, None)

    # ── Compute expected values ──────────────────────────────────────────────
    def find(*kws):
        for key, stats in telem_sensors.items():
            if all(w in key for w in kws): return stats
        return {}

    def r20(stats):   return [round(float(v), 4) for v in stats.get("recent_20", [])]
    def smean(stats): v = stats.get("mean"); return float(v) if v is not None else None

    ms_s = find("corrosion_probe_1")
    cu_s = find("corrosion_probe_2")
    ec_s = find("electrode_conductivity")
    tp_s = find("fluorometer_ch_1") or find("fluorometer", "ch1")
    orp_s = find("orp")
    rel_s = find("relay3") or find("relay5") or find("relay1")

    def scc_row(*kws):
        for r in scc:
            s = (str(r.get("Input Sensor", "")) + str(r.get("Sensor Name", ""))).lower()
            if all(w in s for w in kws): return r
        return {}

    ec_r = scc_row("conductivity")
    tp_r = scc_row("fluorometer_ch_1") or scc_row("fluorometer", "ch1") or scc_row("traced")

    def fv(row, key):
        v = row.get(key)
        try:    return float(v) if v not in (None, "NULL", "") else None
        except: return None

    ec_sp = fv(ec_r, "SP"); ec_db = fv(ec_r, "DB")
    tp_sp = fv(tp_r, "SP"); tp_db = fv(tp_r, "DB")
    ec_ll = (ec_sp - ec_db) if ec_sp and ec_db else None
    ec_ul = (ec_sp + ec_db) if ec_sp and ec_db else None
    tp_ll = (tp_sp - tp_db) if tp_sp and tp_db else None
    tp_ul = (tp_sp + tp_db) if tp_sp and tp_db else None

    prod = tp_r.get("Product Name") or "Traced Product"
    if prod in ("None", "none", None): prod = "Traced Product"

    def pct(vals, ll, ul):
        if not vals or ll is None or ul is None: return None
        return round(sum(1 for v in vals if ll <= v <= ul) / len(vals) * 100, 1)

    tp_r20_vals = r20(tp_s); ec_r20_vals = r20(ec_s)
    tp_pct = pct(tp_r20_vals, tp_ll, tp_ul)
    ec_pct = pct(ec_r20_vals, ec_ll, ec_ul)

    def status(p):
        if p is None: return "Stable"
        return "Good" if p > 75 else ("Stable" if p >= 25 else "Action Required")

    ms_mean = smean(ms_s); cu_mean = smean(cu_s)
    corr_ok = (ms_mean is not None and ms_mean < 3.0) and (cu_mean is not None and cu_mean < 0.5)
    corr_status = "Good" if corr_ok else "Action Required"
    tp_status = status(tp_pct)
    ec_status = status(ec_pct)
    tp_mean = smean(tp_s)
    if tp_mean and tp_ul and tp_ll:
        tp_dir = "HIGH" if tp_mean > tp_ul else ("LOW" if tp_mean < tp_ll else "OK")
    else: tp_dir = "UNKNOWN"

    frc_rows = [r for r in ade if any(w in str(r.get("Parameter", "")).lower()
                for w in ("free residual", "frc", "halogen"))]
    frc = float(frc_rows[0]["Value"]) if frc_rows else None
    micro_status = "Good" if frc and frc >= 0.2 else "Stable"

    relay_r20 = r20(rel_s)

    # ═══════════════════════════════════════════════════════════════════════════
    # Build grading_task.md
    # ═══════════════════════════════════════════════════════════════════════════

    lines = [
        f"# Grading Task — {site} | {month}",
        "",
        "> **Instructions for Copilot Agent:**",
        "> 1. Read the GENERATED REPORT below",
        "> 2. Compare it against the EXPECTED VALUES and GRADING RUBRIC",
        "> 3. Check every rule violation",
        "> 4. Write your grade as JSON to copilot_grade.json",
        "",
        "---",
        "",
    ]

    # ── Section 1: Expected values from source data ──────────────────────────
    lines += [
        "## EXPECTED VALUES (ground truth from source data)",
        "",
        "These are the correct values computed from the raw telemetry, SCC, and ADE data.",
        "The generated report must match these — any discrepancy is a factual error.",
        "",
        "### Corrosion",
        f"| Parameter | Expected Value | Target | Expected Status |",
        f"|---|---|---|---|",
        f"| Mild Steel (MPY) | {fmt(ms_mean)} | <3.0 MPY | {corr_status} |",
        f"| Copper (MPY) | {fmt(cu_mean, 4)} | <0.5 MPY | {corr_status} |",
        "",
        f"### {prod} (Scale Control)",
        f"| Parameter | Expected Value |",
        f"|---|---|",
        f"| Controller Setpoint (SP) | {fmt(tp_sp, 1)} ppm |",
        f"| Dead Band (DB) | {fmt(tp_db, 1)} ppm |",
        f"| Control Range | {fmt(tp_ll, 1)} – {fmt(tp_ul, 1)} ppm |",
        f"| Mean | {fmt(tp_mean, 1)} ppm |",
        f"| % in Range (recent_20) | {tp_pct}% |",
        f"| Expected Status | {tp_status} |",
        f"| Direction | {tp_dir} |",
        "",
        f"### Conductivity (Water Efficiency)",
        f"| Parameter | Expected Value |",
        f"|---|---|",
        f"| Controller Setpoint (SP) | {fmt(ec_sp, 0)} µS/cm |",
        f"| Control Range | {fmt(ec_ll, 0)} – {fmt(ec_ul, 0)} µS/cm |",
        f"| % in Range (recent_20) | {ec_pct}% |",
        f"| Expected Status | {ec_status} |",
        "",
        f"### Microbial",
        f"| Parameter | Expected Value |",
        f"|---|---|",
        f"| FRC | {'Not available' if frc is None else f'{frc} ppm'} |",
        f"| Biocide relay active | {'Yes' if any(v > 0 for v in relay_r20) else 'No'} |",
        f"| Expected Status | {micro_status} |",
        "",
        f"### Service Notes",
        f"Service notes present: {'Yes' if notes else 'No'} ({len(notes)} note(s))",
        "",
        "---",
        "",
    ]

    # ── Section 2: The generated narrative ───────────────────────────────────
    lines += [
        "## GENERATED NARRATIVE (from narrative_cache.json)",
        "",
        "This is what the AI wrote. Grade each field.",
        "",
    ]
    for key in [
        "corrosion_narrative", "corrosion_chart_comment",
        "scale_narrative", "scale_chart_comment",
        "microbial_narrative", "orp_chart_comment",
        "water_efficiency_narrative", "conductivity_chart_comment",
        "product_efficiency_narrative", "proactive_support_narrative",
        "closing_summary",
    ]:
        val = narr.get(key, "")
        lines += [f"### {key}", "", f"> {val}", ""]

    lines += ["---", ""]

    # ── Section 3: The generated markdown report (if exists) ─────────────────
    if md_report:
        lines += [
            "## GENERATED MARKDOWN REPORT",
            "",
            "Full report text — check structure, sections, charts, table, checklist.",
            "",
            "````markdown",
            md_report,
            "````",
            "",
            "---",
            "",
        ]

    # ── Section 4: Rule-based scorecard results (if available) ───────────────
    if scorecard:
        lines += [
            "## RULE-BASED SCORECARD (automated checks already run)",
            "",
            f"Overall: {scorecard['total_score']:.1f}/{scorecard['total_max']:.1f} "
            f"({scorecard['percentage']}%) — Grade: {scorecard['grade']}",
            "",
        ]
        if scorecard.get("failed_checks"):
            lines += ["**Failed checks:**", ""]
            for fc in scorecard["failed_checks"]:
                lines.append(f"- ✗ {fc['check']}: {fc.get('detail', '')}")
            lines += [""]
        lines += [
            "Use this as a starting point. You may agree or disagree with the automated",
            "scores, but you must explain your reasoning when you differ.",
            "",
            "---",
            "",
        ]

    # ── Section 5: Grading rubric ────────────────────────────────────────────
    lines += [
        "## GRADING RUBRIC",
        "",
        "Grade the report on these dimensions. Each dimension is scored 1-10.",
        "",
        "### 1. Factual Accuracy (weight: 25%)",
        "- Are the MS and Cu corrosion values correct?",
        "- Is the traced product % in range correct?",
        "- Is the conductivity % in range correct?",
        "- Is FRC correctly reported or stated as unavailable?",
        "- Are status labels (Good/Stable/Action Required) correct for each section?",
        "- Does % in range match the expected value from recent_20?",
        "- 10 = all values match source data exactly",
        "- 1 = multiple factual errors or invented data",
        "",
        "### 2. Rule Compliance (weight: 25%)",
        "- Exact corrosion wording format used?",
        "- Scale Control discusses Traced Product ONLY (no conductivity, pH, etc.)?",
        "- Microbial Control discusses FRC and ORP ONLY (no pH, turbidity)?",
        "- No absolute ORP values anywhere in narrative?",
        "- No 'relay firing' — uses 'biocide dosing was triggered' etc.?",
        "- ORP spike comment present?",
        "- Product Name from SCC used (not generic 'inhibitor'/'biocide')?",
        "- Proactive System Support title (not 'Alarms')?",
        "- Observation + Recommendation present when product HIGH or LOW?",
        "- Root cause uses conductivity comparison?",
        f"- 'Never in range' stated explicitly if 0% in range?",
        "- 10 = every rule followed perfectly",
        "- 1 = many rule violations",
        "",
        "### 3. Report Structure (weight: 15%)",
        "- Title page with all required fields?",
        "- Executive Summary as narrative prose (not KPI tiles)?",
        "- All 6 sections present: Corrosion, Scale, Microbial, Water Eff, Product Eff, Proactive?",
        "- Performance Summary table on Page 4?",
        "- Charts present with comments below each?",
        "- Final Release Approval checklist?",
        "- Within 8-page limit?",
        "- 10 = perfect structure matching training reports",
        "- 1 = missing major sections or wrong structure",
        "",
        "### 4. Writing Quality (weight: 15%)",
        "- Professional, customer-facing tone?",
        "- Factual and concise — not vague or generic?",
        "- Follows the 'what happened → why → what was done → status' pattern?",
        "- Chart comments are specific and actionable (not boilerplate)?",
        "- No placeholder text or generic filler?",
        "- 10 = reads like a polished SME-written report",
        "- 1 = vague, generic, or unprofessional",
        "",
        "### 5. Training Report Alignment (weight: 20%)",
        "- Does the tone match the Flowserve / St Joseph / Synthomer training reports?",
        "- Are deviations explained with root cause like the training examples?",
        "- Is the narrative depth similar (not too short, not too verbose)?",
        "- Does it follow the 'observation → recommendation → current status' pattern?",
        "- Would a Buckman engineer accept this as a final report with minor edits?",
        "- 10 = indistinguishable from training report quality",
        "- 1 = clearly machine-generated, wouldn't pass review",
        "",
        "---",
        "",
    ]

    # ── Section 6: Copilot Task ──────────────────────────────────────────────
    lines += [
        "## COPILOT TASK",
        "",
        "> **Copy everything in the box below and paste into Copilot Chat.**",
        "> **Make sure this file (grading_task.md) is open in the editor.**",
        "",
        "```",
        f"Read grading_task.md carefully.",
        f"",
        f"Grade the {site} {month} cooling water performance report.",
        f"Compare the GENERATED NARRATIVE and GENERATED MARKDOWN REPORT against the",
        f"EXPECTED VALUES and GRADING RUBRIC.",
        f"",
        f"Check every rule. Check every expected value. Be strict but fair.",
        f"",
        f"Save your response as valid JSON to this exact file:",
        f"data_store/{slug}/copilot_grade.json",
        f"",
        f"The JSON must have exactly this structure:",
        f"{{",
        f'  "site": "{site}",',
        f'  "month": "{month}",',
        f'  "graded_at": "<current ISO timestamp>",',
        f'  "dimensions": {{',
        f'    "factual_accuracy": {{',
        f'      "score": <1-10>,',
        f'      "weight": 0.25,',
        f'      "findings": [',
        f'        "Finding 1: what was correct or incorrect",',
        f'        "Finding 2: ..."',
        f'      ]',
        f'    }},',
        f'    "rule_compliance": {{',
        f'      "score": <1-10>,',
        f'      "weight": 0.25,',
        f'      "findings": ["..."]',
        f'    }},',
        f'    "report_structure": {{',
        f'      "score": <1-10>,',
        f'      "weight": 0.15,',
        f'      "findings": ["..."]',
        f'    }},',
        f'    "writing_quality": {{',
        f'      "score": <1-10>,',
        f'      "weight": 0.15,',
        f'      "findings": ["..."]',
        f'    }},',
        f'    "training_report_alignment": {{',
        f'      "score": <1-10>,',
        f'      "weight": 0.20,',
        f'      "findings": ["..."]',
        f'    }}',
        f'  }},',
        f'  "weighted_score": <computed: sum of score*weight for each dimension>,',
        f'  "grade": "<A if >=9.0 | B if >=8.0 | C if >=7.0 | D if >=6.0 | F otherwise>",',
        f'  "critical_issues": [',
        f'    "List any issues that would block report release (factual errors, rule violations)"',
        f'  ],',
        f'  "improvement_suggestions": [',
        f'    "Specific, actionable suggestions to improve the report"',
        f'  ],',
        f'  "overall_assessment": "2-3 sentence summary of report quality"',
        f"}}",
        f"",
        f"Rules:",
        f"- Be specific in findings — cite exact text from the report",
        f"- Flag every factual error (wrong value, wrong status, wrong %)",
        f"- Flag every rule violation (see GRADING RUBRIC section 2)",
        f"- Compare tone and depth to Buckman training reports",
        f"- weighted_score = sum of (score * weight) across all 5 dimensions",
        f"- Return ONLY valid JSON — no markdown, no explanation outside the JSON",
        "```",
        "",
    ]

    # ── Write grading_task.md ────────────────────────────────────────────────
    task_path = cache / "grading_task.md"
    task_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅  grading_task.md  → {task_path}")

    # ── Create empty copilot_grade.json template ─────────────────────────────
    empty_grade = {
        "site": site,
        "month": month,
        "graded_at": "",
        "dimensions": {
            "factual_accuracy":          {"score": 0, "weight": 0.25, "findings": []},
            "rule_compliance":           {"score": 0, "weight": 0.25, "findings": []},
            "report_structure":          {"score": 0, "weight": 0.15, "findings": []},
            "writing_quality":           {"score": 0, "weight": 0.15, "findings": []},
            "training_report_alignment": {"score": 0, "weight": 0.20, "findings": []},
        },
        "weighted_score": 0,
        "grade": "",
        "critical_issues": [],
        "improvement_suggestions": [],
        "overall_assessment": "",
        "_status": "EMPTY — Copilot must fill this in",
    }
    grade_path = cache / "copilot_grade.json"
    grade_path.write_text(json.dumps(empty_grade, indent=2), encoding="utf-8")
    print(f"✅  copilot_grade.json → {grade_path}  (Copilot fills this in)")

    print()
    print(f"Next steps:")
    print(f"  1. Open VS Code:  code .")
    print(f"  2. Open file:     data_store/{slug}/grading_task.md")
    print(f"  3. Also open:     data_store/{slug}/copilot_grade.json")
    print(f"  4. Copilot Chat:  Ctrl+Shift+I  (Agent mode)")
    print(f"  5. Copy the COPILOT TASK block (bottom of grading_task.md)")
    print(f"     and paste into Copilot Chat")
    print(f"  6. Copilot writes copilot_grade.json")
    print(f"  7. View the combined scores:")
    print(f"       Rule-based:  output/{slug}_scorecard.json")
    print(f"       AI-graded:   data_store/{slug}/copilot_grade.json")


if __name__ == "__main__":
    main()
