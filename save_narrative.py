"""
save_narrative.py
─────────────────
Paste the JSON from Copilot Chat and this script saves it to
data_store/<slug>/narrative_cache.json so generate_report.py can use it.

USAGE
─────
    python save_narrative.py --site "Synthomer Chester SC (US)" --month "May 2026"

The script opens a text editor window where you paste the JSON Copilot gave you,
then saves it automatically when you close.

OR pipe it directly:
    python save_narrative.py --site "..." --month "..." --paste

Then paste the JSON and press Ctrl+Z (Windows) then Enter to finish.
"""

import argparse
import json
import re
import sys
import tempfile
import os
import subprocess
from pathlib import Path

ROOT       = Path(__file__).parent
DATA_STORE = ROOT / "data_store"


def slugify(t):
    return re.sub(r"[^a-z0-9]+", "_", t.lower()).strip("_")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--site",  required=True)
    p.add_argument("--month", required=True)
    p.add_argument("--paste", action="store_true",
                   help="Read JSON from stdin (paste mode)")
    return p.parse_args()


def validate(data):
    required = [
        "corrosion_narrative", "corrosion_chart_comment",
        "scale_narrative", "scale_chart_comment",
        "microbial_narrative", "orp_chart_comment",
        "water_efficiency_narrative", "conductivity_chart_comment",
        "product_efficiency_narrative", "proactive_support_narrative",
        "closing_summary",
    ]
    missing = [k for k in required if k not in data or not str(data[k]).strip()]
    return missing


def main():
    args  = parse_args()
    site  = args.site
    month = args.month
    slug  = slugify(f"{site}_{month}")
    cache = DATA_STORE / slug

    if not cache.exists():
        print(f"[ERROR] No prefetch data at {cache}")
        print(f"  Run: python prefetch_site.py --site \"{site}\" --month \"{month}\"")
        sys.exit(1)

    out_path = cache / "narrative_cache.json"

    print(f"\n{'='*60}")
    print(f"  Save Narrative  —  {site}  |  {month}")
    print(f"{'='*60}\n")

    if args.paste:
        # ── Stdin / pipe mode ─────────────────────────────────────────────────
        print("Paste the JSON from Copilot Chat below.")
        print("When done, press Ctrl+Z then Enter (Windows) or Ctrl+D (Mac/Linux):\n")
        raw = sys.stdin.read().strip()
    else:
        # ── Open notepad so user can paste ────────────────────────────────────
        template = json.dumps({
            "corrosion_narrative": "",
            "corrosion_chart_comment": "",
            "scale_narrative": "",
            "scale_chart_comment": "",
            "microbial_narrative": "",
            "orp_chart_comment": "",
            "water_efficiency_narrative": "",
            "conductivity_chart_comment": "",
            "product_efficiency_narrative": "",
            "proactive_support_narrative": "",
            "closing_summary": "",
            "_instructions": "DELETE THIS LINE. Paste Copilot JSON here — replace ALL empty strings with the text Copilot gave you. Save and close Notepad."
        }, indent=2)

        # Write template to temp file
        tmp = Path(tempfile.gettempdir()) / "narrative_input.json"
        tmp.write_text(template, encoding="utf-8")

        print("Opening Notepad — paste the JSON from Copilot Chat,")
        print("then save (Ctrl+S) and close Notepad.\n")
        subprocess.run(["notepad.exe", str(tmp)])

        raw = tmp.read_text(encoding="utf-8").strip()

    # ── Strip markdown fences if Copilot added them ───────────────────────────
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    # ── Parse JSON ────────────────────────────────────────────────────────────
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON: {e}")
        print("Make sure you copied the complete JSON including the opening {{ and closing }}")
        sys.exit(1)

    # Remove instruction key if present
    data.pop("_instructions", None)
    data.pop("_status", None)
    data.pop("_site", None)
    data.pop("_month", None)

    # ── Validate ──────────────────────────────────────────────────────────────
    missing = validate(data)
    if missing:
        print(f"[WARNING] These keys are empty: {missing}")
        print("The report will generate but some sections will be blank.")

    # ── Save ──────────────────────────────────────────────────────────────────
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n✅  narrative_cache.json saved → {out_path}")
    print(f"\nNow run:")
    print(f'    python generate_report.py --site "{site}" --month "{month}"\n')


if __name__ == "__main__":
    main()