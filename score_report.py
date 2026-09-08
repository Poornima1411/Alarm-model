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

from src.report_cache import build_cache_slug, find_cache_by_controller_ids, normalize_controller_ids
from src.report_status import STATUS_ACCEPTABLE, STATUS_EXCELLENT, STATUS_PATTERN, display_status, status_from_limits, status_from_percent, status_matches

ROOT       = Path(__file__).parent
DATA_STORE = ROOT / "data_store"
OUTPUT_DIR = ROOT / "output"
CHECKLIST_PATH = ROOT / "Report Checklist" / "report checklist.xlsx"
OUTPUT_DIR.mkdir(exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser(description="Score a generated cooling water report.")
    site_group = p.add_mutually_exclusive_group(required=True)
    site_group.add_argument("--site", help='Site name e.g. "Flowserve US Raleigh NC (US)"')
    site_group.add_argument("--controller-id", "--controller-ids", nargs="+", dest="controller_ids",
                            help="One or more controller IDs used for the report cache")
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


def _extract_docx_text(path):
    if not path.exists():
        return None
    try:
        from docx import Document
    except ImportError:
        return None

    doc = Document(str(path))
    parts = []
    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()
        if text:
            parts.append(text)
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _narrative_text(narrative):
    return "\n".join(str(value) for value in narrative.values() if isinstance(value, str))


def _contains_any(text, phrases):
    text_lower = text.lower()
    return any(phrase.lower() in text_lower for phrase in phrases)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════

def load_data(site, month, controller_ids=None):
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
        slug = build_cache_slug(site, month)
        cache = DATA_STORE / slug
        manifest = _load(cache / "manifest.json", {})
        site = manifest.get("site_name", site)

    data = {
        "slug": slug,
        "site": site,
        "month": month,
        "cache_dir": cache,
        "controller_ids": controller_ids,
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

    # Generated Markdown / Word report text
    md_path = OUTPUT_DIR / f"{slug}_report.md"
    data["report_md"] = md_path.read_text(encoding="utf-8") if md_path.exists() else None
    docx_candidates = [path for path in OUTPUT_DIR.glob(f"{slug}_report*.docx") if path.is_file()]
    docx_path = max(docx_candidates, key=lambda path: path.stat().st_mtime) if docx_candidates else OUTPUT_DIR / f"{slug}_report.docx"
    data["report_docx"] = _extract_docx_text(docx_path)
    data["report_path"] = str(docx_path if docx_path.exists() else md_path)
    data["report_text"] = "\n\n".join(
        text for text in [data.get("report_md"), data.get("report_docx")] if text
    )

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
    tag_s = find("fluorometer_ch_2") or find("fluorometer", "ch2")
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

    ms_mean = smean(ms_s)
    cu_mean = smean(cu_s)
    corr_ok = (ms_mean is not None and ms_mean < 3.0) and (cu_mean is not None and cu_mean < 0.5)

    tp_mean = smean(tp_s)
    tag_mean = smean(tag_s)
    polymer_consumption_rate_pct = None
    if tp_mean is not None and tag_mean is not None and tp_mean > 0 and tp_mean > tag_mean:
        polymer_consumption_rate_pct = round((tp_mean - tag_mean) / tp_mean * 100, 1)
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
        "corr_status":  status_from_limits(corr_ok),
        "tp_sp": tp_sp, "tp_db": tp_db,
        "tp_ll": tp_ll, "tp_ul": tp_ul,
        "tp_pct": tp_pct,
        "tp_status": status_from_percent(tp_pct),
        "tp_dir": tp_dir,
        "tp_mean": tp_mean,
        "polymer_consumption_rate_pct": polymer_consumption_rate_pct,
        "ec_sp": ec_sp, "ec_db": ec_db,
        "ec_ll": ec_ll, "ec_ul": ec_ul,
        "ec_pct": ec_pct,
        "ec_status": status_from_percent(ec_pct),
        "ec_mean": smean(ec_s),
        "product_name": prod,
        "frc": frc,
        "micro_status": STATUS_EXCELLENT if frc and frc >= 0.2 else STATUS_ACCEPTABLE,
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


def _section_text(report_text, heading, next_headings):
    if not report_text:
        return ""
    paragraphs = [paragraph.strip() for paragraph in report_text.splitlines() if paragraph.strip()]
    heading_lower = heading.lower()
    start_index = next((index for index, paragraph in enumerate(paragraphs)
                        if paragraph.lower().rstrip(":") == heading_lower), None)
    if start_index is None:
        return ""
    end_index = len(paragraphs)
    for next_heading in next_headings:
        next_lower = next_heading.lower()
        for index in range(start_index + 1, len(paragraphs)):
            if paragraphs[index].lower().rstrip(":") == next_lower:
                end_index = min(end_index, index)
                break
    return "\n".join(paragraphs[start_index:end_index])


def run_narrative_checks(narr, expected, report_text=""):
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

    corr_text = _section_text(report_text, "Corrosion Control", ["Scale Control", "Microbial Control"]) or narr.get("corrosion_narrative", "")

    # ── 3. Exact MS wording ───────────────────────────────────────────────────
    ms_pattern = r"mild steel and copper corrosion rates averaged .+?mpy and .+?mpy"
    has_ms_wording = bool(re.search(ms_pattern, corr_text, re.IGNORECASE))
    checks.append(Check(cat, "Exact MS corrosion wording",
                        8, has_ms_wording,
                        "Must contain: 'mild steel and copper corrosion rates averaged X.XX mpy and X.XX mpy'"))

    # ── 4. Exact Cu wording ───────────────────────────────────────────────────
    cu_pattern = r"recommended limits of <5 mpy and <0\.5 mpy"
    has_cu_wording = bool(re.search(cu_pattern, corr_text, re.IGNORECASE))
    checks.append(Check(cat, "Exact Cu corrosion wording",
                        8, has_cu_wording,
                        "Must contain: 'recommended limits of <5 mpy and <0.5 mpy'"))

    corrosion_values_match = re.search(
        r"mild steel and copper corrosion rates averaged\s+([\d.]+)\s+mpy\s+and\s+([\d.]+)\s+mpy",
        corr_text,
        re.IGNORECASE,
    )

    # ── 5. MS mean value correct ──────────────────────────────────────────────
    if expected["ms_mean"] is not None:
        ms_val_match = corrosion_values_match or re.search(r"mild steel corrosion rate was\s+([\d.]+)", corr_text, re.IGNORECASE)
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
        cu_val_match = corrosion_values_match or re.search(r"copper corrosion rate was\s+([\d.]+)", corr_text, re.IGNORECASE)
        if cu_val_match:
            reported = float(cu_val_match.group(2) if corrosion_values_match else cu_val_match.group(1))
            expected_val = round(expected["cu_mean"], 2)
            close = abs(reported - expected_val) <= 0.05
            checks.append(Check(cat, "Cu mean value accuracy",
                                5, close,
                                f"Reported: {reported}, Expected: ~{expected_val}"))
        else:
            checks.append(Check(cat, "Cu mean value accuracy", 5, False, "Could not extract Cu value"))

    # ── 7. Corrosion status label present ─────────────────────────────────────
    has_status = bool(re.search(rf"\*?\*?Status\*?\*?:?\s*({STATUS_PATTERN})",
                                corr_text, re.IGNORECASE))
    checks.append(Check(cat, "Status label present", 3, has_status))

    # ══════════════════════════════════════════════════════════════════════════
    cat = "Scale Control"

    scale_text = narr.get("scale_narrative", "")
    scale_full_text = f"{scale_text} {_section_text(report_text, 'Scale Control', ['Microbial Control', 'Water Efficiency'])}"

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
    scale_status_match = re.search(rf"\*?\*?Status\*?\*?:?\s*({STATUS_PATTERN})",
                                   scale_text, re.IGNORECASE)
    if scale_status_match and expected["tp_status"]:
        reported_status = scale_status_match.group(1).strip()
        correct = status_matches(reported_status, expected["tp_status"])
        checks.append(Check(cat, "Status matches % in range",
                            8, correct,
                            f"Reported: {display_status(reported_status)}, Expected: {expected['tp_status']} "
                            f"({expected['tp_pct']}% in range)"))
    else:
        checks.append(Check(cat, "Status matches % in range", 8, False,
                            "No status label found in scale narrative"))

    # ── 10. Never-in-range rule ───────────────────────────────────────────────
    if expected["tp_pct"] == 0:
        has_never = "never within" in scale_full_text.lower() or "never in" in scale_full_text.lower()
        checks.append(Check(cat, "'Never in range' stated when 0%",
                            6, has_never,
                            "MANDATORY when 0% in range — must state explicitly"))
    elif expected["tp_pct"] is not None and expected["tp_pct"] < 25:
        has_action_lang = ("requires action" in scale_full_text.lower()
              or "action required" in scale_full_text.lower()
              or "critical" in scale_full_text.lower()
              or "need attention" in scale_full_text.lower()
              or "needs attention" in scale_full_text.lower()
                  or "below the acceptable" in scale_full_text.lower())
        checks.append(Check(cat, "Critical language when <25%",
                            4, has_action_lang))

    # ── 11. Observation & Recommendation when HIGH/LOW ────────────────────────
    if expected["tp_dir"] in ("HIGH", "LOW"):
        scale_lower = scale_full_text.lower()
        has_obs = any(w in scale_lower for w in ["observation", "higher than target", "below", "decreased", "initial part"])
        has_rec = any(w in scale_lower for w in ["recommendation", "recommend", "review", "inspect", "upcoming service"])
        checks.append(Check(cat, f"Observation present ({expected['tp_dir']} product)",
                            4, has_obs))
        checks.append(Check(cat, f"Recommendation present ({expected['tp_dir']} product)",
                            4, has_rec))

    # ── 12. Root cause uses conductivity comparison ───────────────────────────
    scale_lower = scale_full_text.lower()
    has_root_cause = ("conductivity" in scale_lower
             and any(w in scale_lower for w in
                 ["stable", "also", "remained", "declined", "decreased", "water loss", "cycles of concentration", "optimised"]))
    checks.append(Check(cat, "Root cause references conductivity behaviour",
                        4, has_root_cause,
                        "Scale Control must explain root cause using conductivity comparison"))

    # ══════════════════════════════════════════════════════════════════════════
    cat = "Microbial Control"

    micro_text = _section_text(report_text, "Microbial Control", ["Water Efficiency", "Product Efficiency"]) or narr.get("microbial_narrative", "")
    orp_comment = narr.get("orp_chart_comment", "")
    micro_full = micro_text + " " + orp_comment

    # ── 13. No absolute ORP values ────────────────────────────────────────────
    orp_abs = [
        value for value in re.findall(r"\b\d{2,4}\s*m[Vv]\b", micro_full)
        if value.lower() != "50 mv"
    ]
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
        micro_lower = micro_text.lower()
        has_not_avail = ("not available" in micro_lower
                or "will be checked" in micro_lower
                or "upcoming service visit" in micro_lower
                or "upcoming visit" in micro_lower
                or "will be analysed" in micro_lower)
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

    has_forbidden_copper = "no copper corrosion within target" in micro_text.lower()
    checks.append(Check(cat, "No copper corrosion target sentence",
                        3, not has_forbidden_copper,
                        "Remove 'No copper corrosion within target' from Microbial Control"))

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


def run_generated_report_checks(md_text, expected):
    """Check generated report text for structural compliance."""
    checks = []

    if md_text is None:
        checks.append(Check("Report Structure", "Generated report text exists", 5, False,
                            "No .md or .docx report found in output/"))
        return checks

    checks.append(Check("Report Structure", "Generated report text exists", 5, True))
    cat = "Report Structure"

    # ── Title page ────────────────────────────────────────────────────────────
    has_title = bool(re.search(r"^#\s+.+", md_text, re.MULTILINE)) or bool(md_text.strip().splitlines())
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
    real_orp = [v for v in orp_in_narr if not any(w in v.lower() for w in ["0 mv", "50 mv"])]
    checks.append(Check(cat, "No absolute ORP values in narrative text",
                        5, len(real_orp) == 0,
                        f"Found: {real_orp[:5]}" if real_orp else "Clean"))

    # ── Final Release Approval checklist ──────────────────────────────────────
    has_checklist = "final release" in md_lower or "release approval" in md_lower
    checks.append(Check(cat, "Final Release Approval checklist present", 2, has_checklist))

    return checks


def load_report_checklist(path=CHECKLIST_PATH):
    """Load numbered checklist rows from the report checklist workbook."""
    try:
        import openpyxl
    except ImportError as exc:
        raise RuntimeError("openpyxl is required to read the report checklist workbook") from exc

    if not path.exists():
        raise FileNotFoundError(f"Report checklist workbook not found: {path}")

    workbook = openpyxl.load_workbook(path, data_only=True)
    items = []
    for worksheet in workbook.worksheets:
        for row in worksheet.iter_rows(values_only=True):
            if not row or len(row) < 2:
                continue
            raw_id, raw_text = row[0], row[1]
            if raw_id is None or raw_text is None:
                continue
            item_id = str(raw_id).strip()
            item_text = str(raw_text).strip()
            if not item_id.isdigit() or not item_text:
                continue
            items.append({"id": item_id, "text": item_text, "sheet": worksheet.title})
    return items


def _percent_near_text(text, expected_pct):
    if expected_pct is None:
        return False
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*%", text):
        try:
            if abs(float(match.group(1)) - float(expected_pct)) <= 5:
                return True
        except ValueError:
            continue
    return False


def evaluate_checklist_item(item_text, data, expected):
    """Return (passed, detail) for one checklist item from the Excel workbook."""
    report_text = data.get("report_text") or ""
    narrative_text = _narrative_text(data.get("narrative", {}))
    all_text = f"{report_text}\n{narrative_text}"
    lower = all_text.lower()
    item_lower = item_text.lower()

    def present(*phrases):
        return _contains_any(all_text, phrases)

    def not_applicable(reason):
        return True, f"Not applicable: {reason}"

    if "title" in item_lower:
        return bool(re.search(r"(^|\n)#?\s*.+", report_text.strip())), "Title text found" if report_text else "No generated report text found"
    if "executive summary" in item_lower:
        return present("Executive Summary"), "Executive Summary section checked"
    if "under executive summary" in item_lower:
        required = ["Corrosion Control", "Scale Control", "Microbial Control", "Water Efficiency", "Product Efficiency", "Proactive"]
        found = [name for name in required if name.lower() in lower]
        return len(found) >= 4, f"Found executive sections: {len(found)}/{len(required)}"
    if "corrosion control" in item_lower and "status" not in item_lower:
        return present("Corrosion Control"), "Corrosion Control heading checked"
    if "corrosion control status" in item_lower:
        return bool(re.search(rf"corrosion.{{0,120}}status|status.{{0,120}}({STATUS_PATTERN})", lower, re.DOTALL | re.IGNORECASE)), "Corrosion status searched"
    if "avg ms" in item_lower or "avg ms and copper" in item_lower:
        has_ms = expected["ms_mean"] is not None and str(round(expected["ms_mean"], 2)) in all_text
        has_cu = expected["cu_mean"] is not None and str(round(expected["cu_mean"], 4)) in all_text
        return has_ms and has_cu, f"Expected MS {expected['ms_mean']}, Cu {expected['cu_mean']}"
    if "less than 3" in item_lower and "ms" in item_lower:
        if expected["ms_mean"] is None:
            return not_applicable("MS corrosion telemetry not available")
        return expected["ms_mean"] < 3.0 and present("3.0 MPY", "3 mpy", "within 3"), f"MS mean: {expected['ms_mean']}"
    if "less than 0.5" in item_lower and "cu" in item_lower:
        if expected["cu_mean"] is None:
            return not_applicable("Copper corrosion telemetry not available")
        return expected["cu_mean"] < 0.5 and present("0.5 MPY", "0.5 mpy", "within 0.5"), f"Cu mean: {expected['cu_mean']}"
    if "% of time" in item_lower and "range" in item_lower:
        return present("%", "percent", "in range"), "Corrosion in-range wording checked"
    if "95%" in item_lower and "corrosion" in item_lower:
        return present("95%", "well maintained", "within the required range"), "95% corrosion range language checked"
    if "initial 10 days" in item_lower and "corrosion" in item_lower:
        return not_applicable("Initial-10-day corrosion trend detection is not available in the current score inputs")
    if "last 10 days" in item_lower and "corrosion" in item_lower:
        return not_applicable("Last-10-day corrosion trend detection is not available in the current score inputs")
    if "ph has decreased" in item_lower and "corrosion" in item_lower:
        if present("process leak"):
            return True, "Process leak language found"
        return not_applicable("pH/corrosion process-leak condition was not detected by the current score inputs")

    if "scale control" in item_lower and "status" not in item_lower:
        return present("Scale Control"), "Scale Control heading checked"
    if "trace" in item_lower and "100" in item_lower and "range" in item_lower:
        return _percent_near_text(all_text, expected.get("tp_pct")), f"Expected traced product in range: {expected.get('tp_pct')}%"
    if "scale control status" in item_lower:
        return expected["tp_status"].lower() in lower, f"Expected scale status: {expected['tp_status']}"
    if "trace is decreased" in item_lower and "cond is less" in item_lower:
        if expected.get("tp_dir") != "LOW":
            return not_applicable("Traced product is not below range")
        return present("water loss", "upcoming service"), "Low trace with low conductivity wording checked"
    if "trace is decreased" in item_lower and "cond is maintained" in item_lower:
        if expected.get("tp_dir") != "LOW":
            return not_applicable("Traced product is not below range")
        return present("inventory", "pump", "prime", "discharge line"), "Low trace with stable conductivity wording checked"
    if "polymer consumption" in item_lower:
        if expected.get("polymer_consumption_rate_pct") is None:
            return "polymer consumption" not in lower, "Polymer consumption omitted because Tagged Polymer is higher than Traced Product"
        return present("polymer consumption"), "Polymer consumption wording checked"
    if "trace is higher" in item_lower:
        if expected.get("tp_dir") != "HIGH":
            return not_applicable("Traced product is not above range")
        return present("higher than the setpoint", "higher than target", "above"), "High trace wording checked without polymer consumption text"
    if "conductivity has increased" in item_lower and "cycles" in item_lower:
        return present("cycles", "cycles of concentration", "COC"), "Cycles language checked"

    if "microbial control" in item_lower and "status" not in item_lower:
        return present("Microbial Control"), "Microbial Control heading checked"
    if "microbial control status" in item_lower:
        return expected["micro_status"].lower() in lower or present("microbial", "status"), f"Expected microbial status: {expected['micro_status']}"
    if "biocide dosage" in item_lower or "control type" in item_lower:
        return present("timer", "on/off", "on off", "delta timer", "biocide feed"), "Biocide control type wording checked"
    if "biocide control" in item_lower and "on/off" in item_lower:
        if not present("on/off", "on off"):
            return not_applicable("Biocide control is not described as on/off in the generated report")
        return present("within control", "inventory", "pump", "discharge line"), "On/off biocide control wording checked"
    if "spikes in orp" in item_lower or "orp reading" in item_lower:
        return present("ORP spike", "Delta ORP", "spike response", "biocide feed"), "ORP spike language checked"
    if "frc level from ade" in item_lower:
        if expected["frc"] is None:
            return present("FRC", "not available", "upcoming service"), "FRC unavailable path checked"
        return str(round(expected["frc"], 1)) in all_text or str(round(expected["frc"], 2)) in all_text, f"Expected FRC: {expected['frc']}"
    if "frc level" in item_lower and "within range" in item_lower:
        if expected["frc"] is None:
            return not_applicable("FRC value not available")
        in_range = 0.2 <= expected["frc"] <= 0.5
        return ("0.2" in all_text or "0.5" in all_text or "within range" in lower) and (in_range or present("increase", "reduce", "dosage")), f"FRC: {expected['frc']}"
    if "frc level is not mentioned" in item_lower:
        if expected["frc"] is not None:
            return not_applicable("FRC value is available")
        return present("upcoming service", "will be measured", "will be checked"), "Missing FRC follow-up checked"
    if "dip slide" in item_lower or "dipslide" in item_lower or "cfu" in item_lower:
        return present("dip slide", "dipslide", "CFU", "upcoming visit", "upcoming service"), "Dip slide / CFU wording checked"

    if "water efficiency" in item_lower and "heading" in item_lower:
        return present("Water Efficiency"), "Water Efficiency heading checked"
    if "avg conduct" in item_lower or "makeup conductivity" in item_lower or "target coc" in item_lower or "current coc" in item_lower:
        return present("COC", "cycles of concentration", "makeup conductivity", "target COC", "current COC"), "COC wording checked"
    if "don't mention avg conductivity" in item_lower:
        return "average conductivity" not in lower and present("within range", "%"), "Average conductivity wording avoided and range wording checked"
    if "water loss" in item_lower:
        if display_status(expected.get("ec_status")) == STATUS_EXCELLENT:
            return not_applicable("Conductivity is in range")
        return present("water loss", "upcoming service", "inspect"), "Water loss wording checked"
    if "blowdown" in item_lower or "makeup valve" in item_lower:
        return present("blowdown", "makeup valve", "inspection", "inspect"), "Blowdown/makeup valve wording checked"

    if "product efficiency" in item_lower and "heading" in item_lower:
        return present("Product Efficiency"), "Product Efficiency heading checked"
    if "trace product" in item_lower and "within range" in item_lower:
        return _percent_near_text(all_text, expected.get("tp_pct")), f"Expected product in range: {expected.get('tp_pct')}%"
    if "actual consumption" in item_lower or "target consumption" in item_lower or "product consumption" in item_lower:
        return present("consumption", "not available", "product efficiency"), "Consumption wording checked"
    if "prod ll" in item_lower or "cond hhalarm" in item_lower:
        return present("LL", "low-low", "alarm", "conductivity", "product"), "Product LL / conductivity alarm wording checked"

    if "proactive" in item_lower:
        return present("Proactive System Support", "Proactive Summary"), "Proactive section checked"
    if "no.of alarms" in item_lower or "alarm" in item_lower and "recommendation" in item_lower:
        return present("alarm", "recommendation", "no alarms", "no active alarms"), "Alarm summary/recommendation checked"
    if item_lower.strip() == "insight":
        return present("Insight", "summary", "recommendation"), "Insight wording checked"
    if "asset preservation" in item_lower:
        if display_status(expected.get("corr_status")) == STATUS_EXCELLENT:
            return not_applicable("Corrosion status is Excellent")
        return present("asset preservation", "corrosion", "preservation"), "Asset preservation wording checked"

    if "performance summary" in item_lower:
        return present("Performance Summary"), "Performance Summary checked"
    if "hh and ll" in item_lower or "% of range" in item_lower:
        return present("HH", "LL", "%", "in range"), "Limits and percent range checked"
    if "charts" in item_lower or "plot" in item_lower or "graph" in item_lower:
        return present("chart", "trend", "graph", "Figure", "plot"), "Chart/graph wording checked"
    if "comment" in item_lower:
        return present("comment", "trend", "chart"), "Chart comment wording checked"

    return present(item_text), "Fallback text presence check"


def run_excel_checklist_checks(data, expected):
    checks = []
    cat = "Report Checklist"
    try:
        checklist_items = load_report_checklist()
    except (FileNotFoundError, RuntimeError) as exc:
        return [Check(cat, "Checklist workbook readable", 10, False, str(exc))]

    for item in checklist_items:
        passed, detail = evaluate_checklist_item(item["text"], data, expected)
        checks.append(Check(cat, f"{item['id']}. {item['text']}", 1, passed, detail))
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
        "slug":          data["slug"],
        "report_path":   data.get("report_path"),
        "checklist_path": str(CHECKLIST_PATH),
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

def score_generated_report(site, month, controller_ids=None, verbose=False, show_ai_guidance=True):
    controller_ids = normalize_controller_ids(controller_ids)
    label = site or ", ".join(controller_ids)

    print(f"\n{'=' * 60}")
    print(f"  Report Scorer  —  {label}  |  {month}")
    print(f"{'=' * 60}\n")

    print("Loading data …")
    data = load_data(site, month, controller_ids)

    print("Computing expected KPIs from source data …")
    expected = compute_expected(data)

    print(f"  MS: {expected['ms_mean']} MPY  |  Cu: {expected['cu_mean']} MPY  → {expected['corr_status']}")
    print(f"  {expected['product_name']}: {expected['tp_pct']}% in range → {expected['tp_status']}")
    print(f"  Conductivity: {expected['ec_pct']}% in range → {expected['ec_status']}")
    print(f"  FRC: {expected['frc']}  |  Microbial: {expected['micro_status']}")

    print("\nRunning checks …")
    checks = []
    checks.extend(run_narrative_checks(data["narrative"], expected, data.get("report_text", "")))
    checks.extend(run_generated_report_checks(data.get("report_text"), expected))
    checks.extend(run_excel_checklist_checks(data, expected))

    scorecard = build_scorecard(checks, data)
    print_scorecard(scorecard, verbose=verbose)

    out_path = OUTPUT_DIR / f"{data['slug']}_scorecard.json"
    out_path.write_text(json.dumps(scorecard, indent=2, default=str), encoding="utf-8")
    print(f"Scorecard saved → {out_path}")

    copilot_grade_path = data["cache_dir"] / "copilot_grade.json"
    copilot_grade = _load(copilot_grade_path, None)
    if copilot_grade and copilot_grade.get("_status", "") != "EMPTY — Copilot must fill this in":
        print_copilot_grade(copilot_grade)
        print_combined(scorecard, copilot_grade)
    elif show_ai_guidance:
        print(f"\nTo also get an AI-graded assessment, run:")
        if controller_ids:
            controller_args = " ".join(f'"{controller_id}"' for controller_id in controller_ids)
            print(f'  python prepare_grading_task.py --controller-ids {controller_args} --month "{month}"')
        else:
            print(f'  python prepare_grading_task.py --site "{data["site"]}" --month "{month}"')
        print(f"  Then paste the COPILOT TASK into Copilot Chat.")
        print(f"  Re-run this script after Copilot writes copilot_grade.json.\n")

    return scorecard, out_path


def main():
    args = parse_args()
    score_generated_report(args.site, args.month, args.controller_ids, verbose=args.verbose)


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
