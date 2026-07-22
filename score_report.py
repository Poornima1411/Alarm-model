"""
score_report.py
───────────────
Evaluate a generated report against the training-report standards and
the rules defined in report-agent.md.

Reads:
    data_store/<slug>/narrative_cache.json   (AI-generated narrative)
    data_store/<slug>/scc.json               (controller setpoints)
    data_store/<slug>/ade_data.json          (field test data)
    data_store/<slug>/controllers.json
    data_store/<slug>/telemetry/*_summary.json
    output/<slug>_report.md                  (optional — generated Markdown report)

Outputs a structured scorecard to stdout and saves it as:
    output/<slug>_scorecard.json

USAGE
─────
    python score_report.py --site "Flowserve US Raleigh NC (US)" --month "May 2026"
    python score_report.py --site "Synthomer Chester SC (US)"    --month "May 2026" --verbose
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT       = Path(__file__).parent
DATA_STORE = ROOT / "data_store"
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(description="Score a generated cooling water report.")
    p.add_argument("--site",    required=True, help='Site name e.g. "Flowserve US Raleigh NC (US)"')
    p.add_argument("--month",   required=True, help='Reporting month e.g. "May 2026"')
    p.add_argument("--verbose", action="store_true", help="Print detailed check results")
    return p.parse_args()


def slugify(t):
    return re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_")


def _load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


# ═══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════

def load_data(site, month):
    slug  = slugify(f"{site}_{month}")
    cache = DATA_STORE / slug

    data = {
        "slug": slug,
        "site": site,
        "month": month,
        "cache_dir": cache,
    }

    # Narrative cache (the AI output we're scoring)
    narr_path = cache / "narrative_cache.json"
    if not narr_path.exists():
        print(f"[ERROR] narrative_cache.json not found at {narr_path}")
        print(f"  The report must be generated before it can be scored.")
        sys.exit(1)

    data["narrative"] = _load(narr_path, {})
    if data["narrative"].get("_status", "").startswith("EMPTY"):
        print("[ERROR] narrative_cache.json is still the empty template — Copilot hasn't filled it.")
        sys.exit(1)

    # Source data for verification
    data["controllers"] = _load(cache / "controllers.json", [])
    data["scc"]         = _load(cache / "scc.json", [])
    data["ade"]         = _load(cache / "ade_data.json", [])
    data["notes"]       = _load(cache / "service_notes.json", [])

    # Telemetry summaries
    telem = {}
    tel_dir = cache / "telemetry"
    if tel_dir.exists():
        for f in tel_dir.glob("*_summary.json"):
            d = json.loads(f.read_text())
            for name, stats in d.get("sensors", {}).items():
                telem[name.lower()] = stats
    data["telem"] = telem

    # Generated markdown report (optional)
    md_path = OUTPUT_DIR / f"{slug}_report.md"
    data["report_md"] = md_path.read_text(encoding="utf-8") if md_path.exists() else None

    return data


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER: compute expected KPIs from source data
# ═══════════════════════════════════════════════════════════════════════════════

def compute_expected(data):
    """Compute the expected KPI values from the raw source data."""
    telem = data["telem"]
    scc   = data["scc"]
    ade   = data["ade"]

    def find(*kws):
        for key, stats in telem.items():
            if all(w in key for w in kws):
                return stats
        return {}

    def r20(stats):
        return [round(float(v), 4) for v in stats.get("recent_20", [])]

    def smean(stats):
        v = stats.get("mean")
        return float(v) if v is not None else None

    ms_s  = find("corrosion_probe_1")
    cu_s  = find("corrosion_probe_2")
    ec_s  = find("electrode_conductivity")
    tp_s  = find("fluorometer_ch_1") or find("fluorometer", "ch1")
    orp_s = find("orp")
    rel_s = find("relay3") or find("relay5") or find("relay1")

    # SCC rows
    def scc_row(*kws):
        for r in scc:
            s = (str(r.get("Input Sensor", "")) + str(r.get("Sensor Name", ""))).lower()
            if all(w in s for w in kws):
                return r
        return {}

    ec_r = scc_row("conductivity")
    tp_r = scc_row("fluorometer_ch_1") or scc_row("fluorometer", "ch1") or scc_row("traced")

    def fv(row, key):
        v = row.get(key)
        try:
            return float(v) if v not in (None, "NULL", "") else None
        except (ValueError, TypeError):
            return None

    ec_sp = fv(ec_r, "SP"); ec_db = fv(ec_r, "DB")
    tp_sp = fv(tp_r, "SP"); tp_db = fv(tp_r, "DB")
    ec_ll = (ec_sp - ec_db) if ec_sp and ec_db else None
    ec_ul = (ec_sp + ec_db) if ec_sp and ec_db else None
    tp_ll = (tp_sp - tp_db) if tp_sp and tp_db else None
    tp_ul = (tp_sp + tp_db) if tp_sp and tp_db else None

    prod = tp_r.get("Product Name") or "Traced Product"
    if prod in ("None", "none", None):
        prod = "Traced Product"

    # % in range
    def pct(vals, ll, ul):
        if not vals or ll is None or ul is None:
            return None
        return round(sum(1 for v in vals if ll <= v <= ul) / len(vals) * 100, 1)

    tp_r20 = r20(tp_s)
    ec_r20 = r20(ec_s)
    tp_pct = pct(tp_r20, tp_ll, tp_ul)
    ec_pct = pct(ec_r20, ec_ll, ec_ul)

    def status(p):
        if p is None:
            return "Stable"
        return "Good" if p > 75 else ("Stable" if p >= 25 else "Action Required")

    ms_mean = smean(ms_s)
    cu_mean = smean(cu_s)
    corr_ok = (ms_mean is not None and ms_mean < 3.0) and (cu_mean is not None and cu_mean < 0.5)

    tp_mean = smean(tp_s)
    if tp_mean and tp_ul and tp_ll:
        tp_dir = "HIGH" if tp_mean > tp_ul else ("LOW" if tp_mean < tp_ll else "OK")
    else:
        tp_dir = "UNKNOWN"

    frc_rows = [r for r in ade if any(w in str(r.get("Parameter", "")).lower()
                for w in ("free residual", "frc", "halogen"))]
    frc = float(frc_rows[0]["Value"]) if frc_rows else None

    relay_r20 = r20(rel_s)
    relay_firing = bool(relay_r20 and any(v > 0 for v in relay_r20))

    return {
        "ms_mean": ms_mean,
        "cu_mean": cu_mean,
        "corr_status":  "Good" if corr_ok else "Action Required",
        "tp_sp": tp_sp, "tp_db": tp_db,
        "tp_ll": tp_ll, "tp_ul": tp_ul,
        "tp_pct": tp_pct,
        "tp_status": status(tp_pct),
        "tp_dir": tp_dir,
        "tp_mean": tp_mean,
        "ec_sp": ec_sp, "ec_db": ec_db,
        "ec_ll": ec_ll, "ec_ul": ec_ul,
        "ec_pct": ec_pct,
        "ec_status": status(ec_pct),
        "ec_mean": smean(ec_s),
        "product_name": prod,
        "frc": frc,
        "micro_status": "Good" if frc and frc >= 0.2 else "Stable",
        "relay_firing": relay_firing,
        "has_service_notes": len(data["notes"]) > 0,
        "tp_r20": tp_r20,
        "ec_r20": ec_r20,
        "relay_r20": relay_r20,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SCORING CHECKS
# ═══════════════════════════════════════════════════════════════════════════════

class Check:
    """One scoring criterion."""
    def __init__(self, category, name, weight, passed, detail=""):
        self.category = category
        self.name     = name
        self.weight   = weight     # max points for this check
        self.passed   = passed     # True/False or float 0.0-1.0 for partial
        self.detail   = detail

    @property
    def score(self):
        if isinstance(self.passed, bool):
            return self.weight if self.passed else 0.0
        return round(self.weight * self.passed, 2)

    def to_dict(self):
        return {
            "category": self.category,
            "check":    self.name,
            "max":      self.weight,
            "score":    self.score,
            "passed":   self.passed if isinstance(self.passed, bool) else f"{self.passed:.0%}",
            "detail":   self.detail,
        }


def run_narrative_checks(narr, expected):
    """Check the narrative_cache.json content against rules."""
    checks = []
    cat = "Narrative Structure"

    # ── 1. All required keys present ──────────────────────────────────────────
    required_keys = [
        "corrosion_narrative", "corrosion_chart_comment",
        "scale_narrative", "scale_chart_comment",
        "microbial_narrative", "orp_chart_comment",
        "water_efficiency_narrative", "conductivity_chart_comment",
        "product_efficiency_narrative", "proactive_support_narrative",
        "closing_summary",
    ]
    present = [k for k in required_keys if narr.get(k, "").strip()]
    missing = [k for k in required_keys if not narr.get(k, "").strip()]
    frac = len(present) / len(required_keys)
    checks.append(Check(cat, "All narrative keys populated",
                        10, frac,
                        f"Present: {len(present)}/{len(required_keys)}."
                        + (f" Missing: {', '.join(missing)}" if missing else "")))

    # ── 2. No empty / placeholder text ────────────────────────────────────────
    placeholder_phrases = ["todo", "placeholder", "fill in", "tbd", "[insert", "xxx"]
    placeholders_found = []
    for key in required_keys:
        text = narr.get(key, "").lower()
        for ph in placeholder_phrases:
            if ph in text:
                placeholders_found.append(f"{key}: '{ph}'")
    checks.append(Check(cat, "No placeholder text",
                        5, len(placeholders_found) == 0,
                        f"Found: {placeholders_found}" if placeholders_found else "Clean"))

    # ══════════════════════════════════════════════════════════════════════════
    cat = "Corrosion Control"

    corr_text = narr.get("corrosion_narrative", "")

    # ── 3. Exact MS wording ───────────────────────────────────────────────────
    ms_pattern = r"mild steel corrosion rate was .+?MPY against the target of within 3\.0 MPY"
    has_ms_wording = bool(re.search(ms_pattern, corr_text, re.IGNORECASE))
    checks.append(Check(cat, "Exact MS corrosion wording",
                        8, has_ms_wording,
                        "Must contain: 'mild steel corrosion rate was X MPY against the target of within 3.0 MPY'"))

    # ── 4. Exact Cu wording ───────────────────────────────────────────────────
    cu_pattern = r"copper corrosion rate was .+?MPY against the target of within 0\.5 MPY"
    has_cu_wording = bool(re.search(cu_pattern, corr_text, re.IGNORECASE))
    checks.append(Check(cat, "Exact Cu corrosion wording",
                        8, has_cu_wording,
                        "Must contain: 'copper corrosion rate was X MPY against the target of within 0.5 MPY'"))

    # ── 5. MS mean value correct ──────────────────────────────────────────────
    if expected["ms_mean"] is not None:
        ms_val_match = re.search(r"mild steel corrosion rate was\s+([\d.]+)", corr_text, re.IGNORECASE)
        if ms_val_match:
            reported = float(ms_val_match.group(1))
            expected_val = round(expected["ms_mean"], 2)
            close = abs(reported - expected_val) <= 0.15
            checks.append(Check(cat, "MS mean value accuracy",
                                5, close,
                                f"Reported: {reported}, Expected: ~{expected_val}"))
        else:
            checks.append(Check(cat, "MS mean value accuracy", 5, False, "Could not extract MS value"))

    # ── 6. Cu mean value correct ──────────────────────────────────────────────
    if expected["cu_mean"] is not None:
        cu_val_match = re.search(r"copper corrosion rate was\s+([\d.]+)", corr_text, re.IGNORECASE)
        if cu_val_match:
            reported = float(cu_val_match.group(1))
            expected_val = round(expected["cu_mean"], 4)
            close = abs(reported - expected_val) <= 0.05
            checks.append(Check(cat, "Cu mean value accuracy",
                                5, close,
                                f"Reported: {reported}, Expected: ~{expected_val}"))
        else:
            checks.append(Check(cat, "Cu mean value accuracy", 5, False, "Could not extract Cu value"))

    # ── 7. Corrosion status label present ─────────────────────────────────────
    has_status = bool(re.search(r"\*?\*?Status\*?\*?:?\s*(Good|Stable|Action Required)",
                                corr_text, re.IGNORECASE))
    checks.append(Check(cat, "Status label present", 3, has_status))

    # ══════════════════════════════════════════════════════════════════════════
    cat = "Scale Control"

    scale_text = narr.get("scale_narrative", "")

    # ── 8. Scale Control only discusses traced product ────────────────────────
    forbidden_in_scale = ["conductivity", "ph ", "turbidity", "cell fouling", "cellfouling"]
    scale_leaks = [w for w in forbidden_in_scale
                   if w in scale_text.lower() and w != "conductivity"]
    # Allow conductivity only in root-cause context — check if it dominates
    cond_mentions = scale_text.lower().count("conductivity")
    if cond_mentions > 3:
        scale_leaks.append(f"conductivity ({cond_mentions} mentions — likely over-discussed)")
    checks.append(Check(cat, "Scale Control discusses Traced Product only",
                        6, len(scale_leaks) == 0,
                        f"Forbidden terms found: {scale_leaks}" if scale_leaks else "Clean"))

    # ── 9. Status reflects % in range ─────────────────────────────────────────
    scale_status_match = re.search(r"\*?\*?Status\*?\*?:?\s*(Good|Stable|Action Required)",
                                   scale_text, re.IGNORECASE)
    if scale_status_match and expected["tp_status"]:
        reported_status = scale_status_match.group(1).strip()
        correct = reported_status.lower() == expected["tp_status"].lower()
        checks.append(Check(cat, "Status matches % in range",
                            8, correct,
                            f"Reported: {reported_status}, Expected: {expected['tp_status']} "
                            f"({expected['tp_pct']}% in range)"))
    else:
        checks.append(Check(cat, "Status matches % in range", 8, False,
                            "No status label found in scale narrative"))

    # ── 10. Never-in-range rule ───────────────────────────────────────────────
    if expected["tp_pct"] == 0:
        has_never = "never within" in scale_text.lower() or "never in" in scale_text.lower()
        checks.append(Check(cat, "'Never in range' stated when 0%",
                            6, has_never,
                            "MANDATORY when 0% in range — must state explicitly"))
    elif expected["tp_pct"] is not None and expected["tp_pct"] < 25:
        has_action_lang = ("requires action" in scale_text.lower()
                          or "action required" in scale_text.lower()
                          or "below the acceptable" in scale_text.lower())
        checks.append(Check(cat, "Action Required language when <25%",
                            4, has_action_lang))

    # ── 11. Observation & Recommendation when HIGH/LOW ────────────────────────
    if expected["tp_dir"] in ("HIGH", "LOW"):
        has_obs = "observation" in scale_text.lower()
        has_rec = "recommendation" in scale_text.lower() or "recommend" in scale_text.lower()
        checks.append(Check(cat, f"Observation present ({expected['tp_dir']} product)",
                            4, has_obs))
        checks.append(Check(cat, f"Recommendation present ({expected['tp_dir']} product)",
                            4, has_rec))

    # ── 12. Root cause uses conductivity comparison ───────────────────────────
    has_root_cause = ("conductivity" in scale_text.lower()
                     and any(w in scale_text.lower() for w in
                             ["stable", "also", "remained", "declined", "water loss"]))
    checks.append(Check(cat, "Root cause references conductivity behaviour",
                        4, has_root_cause,
                        "Scale Control must explain root cause using conductivity comparison"))

    # ══════════════════════════════════════════════════════════════════════════
    cat = "Microbial Control"

    micro_text = narr.get("microbial_narrative", "")
    orp_comment = narr.get("orp_chart_comment", "")
    micro_full = micro_text + " " + orp_comment

    # ── 13. No absolute ORP values ────────────────────────────────────────────
    orp_abs = re.findall(r"\b\d{2,4}\s*m[Vv]\b", micro_full)
    checks.append(Check(cat, "No absolute ORP values in narrative",
                        8, len(orp_abs) == 0,
                        f"Found ORP values: {orp_abs}" if orp_abs else "Clean"))

    # ── 14. FRC from ADE data ─────────────────────────────────────────────────
    if expected["frc"] is not None:
        has_frc = bool(re.search(r"frc", micro_text, re.IGNORECASE))
        has_frc_val = str(round(expected["frc"], 1)) in micro_text or str(round(expected["frc"], 2)) in micro_text
        checks.append(Check(cat, "FRC value from ADE data cited",
                            5, has_frc and has_frc_val,
                            f"Expected FRC: {expected['frc']}"))
    else:
        has_not_avail = ("not available" in micro_text.lower()
                        or "will be checked" in micro_text.lower()
                        or "upcoming service visit" in micro_text.lower())
        checks.append(Check(cat, "FRC not-available statement present",
                            5, has_not_avail,
                            "Must state FRC will be checked at next service visit"))

    # ── 15. ORP spike comment mandatory ───────────────────────────────────────
    has_orp_spike = any(w in micro_full.lower() for w in
                       ["orp spike", "delta orp", "spike response", "biocide dosing was triggered",
                        "biocide pump was activated", "biocide feed"])
    checks.append(Check(cat, "ORP spike/Delta ORP comment present",
                        6, has_orp_spike,
                        "MANDATORY in every report"))

    # ── 16. No 'relay firing' language ────────────────────────────────────────
    has_relay_firing = "relay firing" in micro_full.lower()
    checks.append(Check(cat, "No 'relay firing' language",
                        3, not has_relay_firing,
                        "Must use 'biocide dosing was triggered' / 'pump was activated' instead"))

    # ── 17. Microbial doesn't discuss pH/turbidity/cell fouling ───────────────
    micro_leaks = [w for w in ["turbidity", "cell fouling", "cellfouling"]
                   if w in micro_text.lower()]
    # pH is borderline — only flag if discussed as a KPI, not incidentally
    if re.search(r"\bph\b.{0,20}(average|mean|reading|value|was\s+\d)", micro_text, re.IGNORECASE):
        micro_leaks.append("pH (as KPI)")
    checks.append(Check(cat, "Microbial doesn't discuss pH/turbidity/cell fouling",
                        4, len(micro_leaks) == 0,
                        f"Leaked: {micro_leaks}" if micro_leaks else "Clean"))

    # ══════════════════════════════════════════════════════════════════════════
    cat = "Water Efficiency"

    we_text = narr.get("water_efficiency_narrative", "")

    # ── 18. Discusses conductivity ────────────────────────────────────────────
    checks.append(Check(cat, "Conductivity discussed",
                        4, "conductivity" in we_text.lower()))

    # ── 19. Mentions COC or cycles ────────────────────────────────────────────
    has_coc = any(w in we_text.lower() for w in ["coc", "cycles of concentration", "cycles"])
    checks.append(Check(cat, "COC / cycles of concentration mentioned",
                        3, has_coc))

    # ══════════════════════════════════════════════════════════════════════════
    cat = "Product Efficiency"

    pe_text = narr.get("product_efficiency_narrative", "")

    # ── 20. Uses Product Name from SCC ────────────────────────────────────────
    prod = expected["product_name"]
    if prod and prod != "Traced Product":
        uses_name = prod.lower() in pe_text.lower() or prod.lower() in scale_text.lower()
        uses_generic = any(g in pe_text.lower() for g in ["inhibitor", "biocide"])
        checks.append(Check(cat, f"Uses SCC Product Name ('{prod}')",
                            5, uses_name and not uses_generic,
                            "Must use actual product name from SCC, not generic 'inhibitor'/'biocide'"))
    else:
        checks.append(Check(cat, "Product Name (generic OK — none in SCC)", 5, True))

    # ══════════════════════════════════════════════════════════════════════════
    cat = "Proactive System Support"

    ps_text = narr.get("proactive_support_narrative", "")

    # ── 21. Uses correct section title concept ────────────────────────────────
    # Can't check the title in the narrative JSON directly, but check it's not "Alarms"
    uses_alarm_title = ps_text.lower().startswith("alarms")
    checks.append(Check(cat, "Not titled 'Alarms'",
                        3, not uses_alarm_title,
                        "Section must be titled 'Proactive System Support'"))

    # ── 22. Service notes incorporated if present ─────────────────────────────
    if expected["has_service_notes"]:
        has_notes_ref = any(w in ps_text.lower() for w in
                           ["service visit", "actions completed", "service note",
                            "field visit", "engineer", "technician", "site visit"])
        checks.append(Check(cat, "Service notes incorporated",
                            4, has_notes_ref,
                            "Service notes exist in source data — must be referenced"))
    else:
        has_no_notes = "no service notes" in ps_text.lower() or "not recorded" in ps_text.lower()
        checks.append(Check(cat, "'No service notes' stated when none exist",
                            4, has_no_notes))

    return checks


def run_report_md_checks(md_text, expected):
    """Check the generated .md report for structural compliance."""
    checks = []

    if md_text is None:
        checks.append(Check("Report Structure", "Markdown report exists", 5, False,
                            "No .md report found in output/"))
        return checks

    checks.append(Check("Report Structure", "Markdown report exists", 5, True))
    cat = "Report Structure"

    # ── Title page ────────────────────────────────────────────────────────────
    has_title = bool(re.search(r"^#\s+.+", md_text, re.MULTILINE))
    checks.append(Check(cat, "Title page heading present", 3, has_title))

    has_prepared = "prepared" in md_text.lower() and ("date" in md_text.lower() or "by" in md_text.lower())
    checks.append(Check(cat, "Prepared Date / Prepared By present", 3, has_prepared))

    has_report_status = "report status" in md_text.lower()
    checks.append(Check(cat, "Report Status field present", 2, has_report_status))

    # ── Executive Summary sections ────────────────────────────────────────────
    sections = {
        "Corrosion Control":         ["corrosion control"],
        "Scale Control":             ["scale control"],
        "Microbial Control":         ["microbial control"],
        "Water Efficiency":          ["water efficiency"],
        "Product Efficiency":        ["product efficiency"],
        "Proactive System Support":  ["proactive system support"],
    }
    md_lower = md_text.lower()
    for sec_name, keywords in sections.items():
        found = any(kw in md_lower for kw in keywords)
        checks.append(Check(cat, f"Section present: {sec_name}", 2, found))

    # ── Performance Summary table ─────────────────────────────────────────────
    has_perf = "performance summary" in md_lower
    checks.append(Check(cat, "Performance Summary section present", 3, has_perf))

    has_table = "|" in md_text and ("parameter" in md_lower or "corrosion" in md_lower)
    checks.append(Check(cat, "Performance Summary table present", 3, has_table))

    # ── Charts ────────────────────────────────────────────────────────────────
    # ASCII charts have patterns like lines of dashes, asterisks, pipes
    chart_indicators = len(re.findall(r"\|[\s.*^-]{10,}\|", md_text))
    alt_chart = md_text.count("---") > 5  # dashed lines for limits
    has_charts = chart_indicators >= 2 or alt_chart
    checks.append(Check(cat, "At least 1 chart included", 4, has_charts,
                        f"Chart-like patterns found: {chart_indicators}"))

    # ── No absolute ORP in narrative (re-check in full report) ────────────────
    # Find ORP values NOT inside a table row
    non_table_lines = [l for l in md_text.split("\n") if not l.strip().startswith("|")]
    non_table = "\n".join(non_table_lines)
    # Exclude chart areas (lines with lots of special chars)
    narrative_lines = [l for l in non_table_lines
                       if not re.match(r"^\s*[\|*^.\-\s]{10,}$", l)]
    narrative_block = "\n".join(narrative_lines)
    orp_in_narr = re.findall(r"\b\d{2,4}\s*m[Vv]\b", narrative_block)
    # Filter out false positives from chart legends/labels
    real_orp = [v for v in orp_in_narr if not any(w in v.lower() for w in ["0 mv"])]
    checks.append(Check(cat, "No absolute ORP values in narrative text",
                        5, len(real_orp) == 0,
                        f"Found: {real_orp[:5]}" if real_orp else "Clean"))

    # ── Final Release Approval checklist ──────────────────────────────────────
    has_checklist = "final release" in md_lower or "release approval" in md_lower
    checks.append(Check(cat, "Final Release Approval checklist present", 2, has_checklist))

    return checks


# ═══════════════════════════════════════════════════════════════════════════════
# SCORECARD ASSEMBLY
# ═══════════════════════════════════════════════════════════════════════════════

def build_scorecard(checks, data):
    total_max   = sum(c.weight for c in checks)
    total_score = sum(c.score for c in checks)
    pct         = round(total_score / total_max * 100, 1) if total_max else 0

    # Grade
    if   pct >= 90: grade = "A"
    elif pct >= 80: grade = "B"
    elif pct >= 70: grade = "C"
    elif pct >= 60: grade = "D"
    else:           grade = "F"

    # Category breakdown
    cats = {}
    for c in checks:
        if c.category not in cats:
            cats[c.category] = {"max": 0, "score": 0, "checks": []}
        cats[c.category]["max"]   += c.weight
        cats[c.category]["score"] += c.score
        cats[c.category]["checks"].append(c.to_dict())

    cat_summary = {}
    for name, info in cats.items():
        cat_pct = round(info["score"] / info["max"] * 100, 1) if info["max"] else 0
        cat_summary[name] = {
            "score": info["score"],
            "max":   info["max"],
            "pct":   cat_pct,
            "checks": info["checks"],
        }

    failed = [c.to_dict() for c in checks if (isinstance(c.passed, bool) and not c.passed)
              or (isinstance(c.passed, (int, float)) and c.passed < 0.5)]

    return {
        "site":          data["site"],
        "month":         data["month"],
        "total_score":   total_score,
        "total_max":     total_max,
        "percentage":    pct,
        "grade":         grade,
        "failed_checks": failed,
        "categories":    cat_summary,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# DISPLAY
# ═══════════════════════════════════════════════════════════════════════════════

def print_scorecard(sc, verbose=False):
    print()
    print("=" * 70)
    print(f"  REPORT SCORECARD  —  {sc['site']}  |  {sc['month']}")
    print("=" * 70)
    print()
    print(f"  Overall Score:  {sc['total_score']:.1f} / {sc['total_max']:.1f}  "
          f"({sc['percentage']}%)  —  Grade: {sc['grade']}")
    print()
    print("-" * 70)
    print(f"  {'Category':<35} {'Score':>8}  {'%':>6}")
    print("-" * 70)
    for name, info in sc["categories"].items():
        bar_len = int(info["pct"] / 100 * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        print(f"  {name:<35} {info['score']:>5.1f}/{info['max']:<3.0f}  {info['pct']:>5.1f}%  {bar}")
    print("-" * 70)

    if sc["failed_checks"]:
        print()
        print(f"  FAILED / LOW-SCORING CHECKS ({len(sc['failed_checks'])}):")
        print()
        for f in sc["failed_checks"]:
            status = "✗ FAIL" if f["passed"] is False else f"⚠ {f['passed']}"
            print(f"    {status:<12}  {f['check']}")
            if f["detail"]:
                print(f"                  → {f['detail']}")
        print()

    if verbose:
        print()
        print("  DETAILED CHECK RESULTS:")
        print()
        for cat_name, info in sc["categories"].items():
            print(f"  ── {cat_name} ──")
            for ch in info["checks"]:
                icon = "✓" if ch["passed"] is True or (isinstance(ch["passed"], str) and ch["passed"] == "100%") else "✗"
                print(f"    {icon}  {ch['check']:<50}  {ch['score']:.1f}/{ch['max']:.0f}  {ch['detail']}")
            print()

    print("=" * 70)
    print()


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    args = parse_args()
    site = args.site
    month = args.month

    print(f"\n{'=' * 60}")
    print(f"  Report Scorer  —  {site}  |  {month}")
    print(f"{'=' * 60}\n")

    print("Loading data …")
    data = load_data(site, month)

    print("Computing expected KPIs from source data …")
    expected = compute_expected(data)

    print(f"  MS: {expected['ms_mean']} MPY  |  Cu: {expected['cu_mean']} MPY  → {expected['corr_status']}")
    print(f"  {expected['product_name']}: {expected['tp_pct']}% in range → {expected['tp_status']}")
    print(f"  Conductivity: {expected['ec_pct']}% in range → {expected['ec_status']}")
    print(f"  FRC: {expected['frc']}  |  Microbial: {expected['micro_status']}")

    print("\nRunning checks …")
    checks = []
    checks.extend(run_narrative_checks(data["narrative"], expected))
    checks.extend(run_report_md_checks(data.get("report_md"), expected))

    scorecard = build_scorecard(checks, data)
    print_scorecard(scorecard, verbose=args.verbose)

    # Save scorecard
    slug = slugify(f"{site}_{month}")
    out_path = OUTPUT_DIR / f"{slug}_scorecard.json"
    out_path.write_text(json.dumps(scorecard, indent=2, default=str), encoding="utf-8")
    print(f"Scorecard saved → {out_path}")

    # ── Show Copilot grade if available ───────────────────────────────────────
    copilot_grade_path = data["cache_dir"] / "copilot_grade.json"
    copilot_grade = _load(copilot_grade_path, None)
    if copilot_grade and copilot_grade.get("_status", "") != "EMPTY — Copilot must fill this in":
        print_copilot_grade(copilot_grade)
        print_combined(scorecard, copilot_grade)
    else:
        print(f"\nTo also get an AI-graded assessment, run:")
        print(f'  python prepare_grading_task.py --site "{site}" --month "{month}"')
        print(f"  Then paste the COPILOT TASK into Copilot Chat.")
        print(f"  Re-run this script after Copilot writes copilot_grade.json.\n")


def print_copilot_grade(cg):
    """Display the Copilot-written grade."""
    print()
    print("=" * 70)
    print(f"  COPILOT AI GRADE  —  {cg.get('site', '?')}  |  {cg.get('month', '?')}")
    print("=" * 70)
    print()
    ws = cg.get("weighted_score", 0)
    grade = cg.get("grade", "?")
    print(f"  Weighted Score: {ws:.1f} / 10.0  —  Grade: {grade}")
    print()
    print("-" * 70)
    print(f"  {'Dimension':<35} {'Score':>6}  {'Weight':>7}")
    print("-" * 70)
    for dim_name, dim in cg.get("dimensions", {}).items():
        label = dim_name.replace("_", " ").title()
        bar_len = int(dim.get("score", 0))
        bar = "█" * bar_len + "░" * (10 - bar_len)
        print(f"  {label:<35} {dim.get('score', 0):>4}/10  x{dim.get('weight', 0):.2f}  {bar}")
    print("-" * 70)

    if cg.get("critical_issues"):
        print()
        print("  CRITICAL ISSUES:")
        for issue in cg["critical_issues"]:
            print(f"    ✗ {issue}")

    if cg.get("improvement_suggestions"):
        print()
        print("  IMPROVEMENT SUGGESTIONS:")
        for sug in cg["improvement_suggestions"]:
            print(f"    → {sug}")

    if cg.get("overall_assessment"):
        print()
        print(f"  OVERALL: {cg['overall_assessment']}")
    print()


def print_combined(scorecard, copilot_grade):
    """Show the combined rule-based + AI grade."""
    rule_pct = scorecard["percentage"]
    ai_score = copilot_grade.get("weighted_score", 0)
    ai_pct   = ai_score * 10  # scale 1-10 to 0-100

    # Combined: 50% rule-based, 50% AI
    combined = (rule_pct + ai_pct) / 2
    if   combined >= 90: grade = "A"
    elif combined >= 80: grade = "B"
    elif combined >= 70: grade = "C"
    elif combined >= 60: grade = "D"
    else:                grade = "F"

    print("=" * 70)
    print("  COMBINED SCORE")
    print("=" * 70)
    print(f"  Rule-based:  {rule_pct:.1f}%  (Grade {scorecard['grade']})")
    print(f"  AI-graded:   {ai_pct:.1f}%  (Grade {copilot_grade.get('grade', '?')})")
    print(f"  ─────────────────────")
    print(f"  Combined:    {combined:.1f}%  (Grade {grade})")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
