from __future__ import annotations

STATUS_EXCELLENT = "Excellent"
STATUS_ACCEPTABLE = "Acceptable"
STATUS_CRITICAL = "Critical"

STATUS_PATTERN = (
    r"Excellent|Acceptable|Critical|Good|Stable|Action Required|"
    r"Need Attention|Needs Attention|Need attention|Needs attention|Okay|Bad"
)

_LEGACY_TO_DISPLAY = {
    "excellent": STATUS_EXCELLENT,
    "good": STATUS_EXCELLENT,
    "acceptable": STATUS_ACCEPTABLE,
    "stable": STATUS_ACCEPTABLE,
    "okay": STATUS_ACCEPTABLE,
    "critical": STATUS_CRITICAL,
    "action required": STATUS_CRITICAL,
    "need attention": STATUS_CRITICAL,
    "needs attention": STATUS_CRITICAL,
    "bad": STATUS_CRITICAL,
}


def display_status(status: str | None) -> str:
    if status is None:
        return STATUS_ACCEPTABLE
    cleaned = str(status).strip()
    return _LEGACY_TO_DISPLAY.get(cleaned.lower(), cleaned)


def status_from_percent(percent: float | None) -> str:
    if percent is None:
        return STATUS_ACCEPTABLE
    return STATUS_EXCELLENT if percent > 75 else (STATUS_ACCEPTABLE if percent >= 25 else STATUS_CRITICAL)


def status_from_limits(in_limits: bool) -> str:
    return STATUS_EXCELLENT if in_limits else STATUS_CRITICAL


def status_matches(reported: str | None, expected: str | None) -> bool:
    return display_status(reported).lower() == display_status(expected).lower()
