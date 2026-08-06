from __future__ import annotations

import json
import re
from pathlib import Path


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def normalize_controller_ids(controller_ids: list[str] | None) -> list[str]:
    if not controller_ids:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for value in controller_ids:
        for part in str(value).split(","):
            controller_id = part.strip()
            if not controller_id:
                continue
            key = controller_id.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(controller_id)
    return normalized


def build_cache_slug(
    site_name: str,
    reporting_month: str,
    controller_ids: list[str] | None = None,
) -> str:
    ids = normalize_controller_ids(controller_ids)
    if ids:
        return slugify(f"{site_name}_controllers_{'_'.join(ids)}_{reporting_month}")
    return slugify(f"{site_name}_{reporting_month}")


def find_cache_by_controller_ids(
    data_store: Path,
    reporting_month: str,
    controller_ids: list[str],
) -> tuple[Path, dict]:
    requested = {controller_id.lower() for controller_id in normalize_controller_ids(controller_ids)}
    if not requested:
        raise ValueError("At least one controller ID is required.")

    matches: list[tuple[Path, dict]] = []
    for manifest_path in data_store.glob("*/manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        if manifest.get("reporting_month") != reporting_month:
            continue

        cached = {str(controller).lower() for controller in manifest.get("controllers", [])}
        if cached == requested:
            matches.append((manifest_path.parent, manifest))

    if not matches:
        raise FileNotFoundError(
            "No prefetched cache found for controller ID(s) "
            f"{', '.join(controller_ids)} and month {reporting_month}."
        )
    if len(matches) > 1:
        choices = ", ".join(str(path) for path, _ in matches)
        raise RuntimeError(f"Multiple matching caches found: {choices}")
    return matches[0]
