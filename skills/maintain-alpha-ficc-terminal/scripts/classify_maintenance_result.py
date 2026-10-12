"""Deterministically classify read-only Alpha-FICC maintenance checks."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def _failed(check: Mapping[str, Any]) -> bool:
    return str(check.get("status", "")) in {"failed", "timeout"}


def classify_checks(checks: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """Return an advisory severity; the Skill retains final authority checks."""
    items = list(checks)
    if any(
        _failed(check)
        and (bool(check.get("critical")) or str(check.get("id")) in {"api.health", "providers.connectivity"})
        for check in items
    ):
        return {"severity": "P0", "authority_candidate": "A3", "reason": "critical_service_unavailable"}

    low_frequency_failed = any(
        str(check.get("id")) == "refresh.low_frequency" and _failed(check) for check in items
    )
    critical_stale_tail = any(
        str(check.get("status")) == "stale_tail" and bool(check.get("critical")) for check in items
    )
    if low_frequency_failed and critical_stale_tail:
        return {
            "severity": "P1",
            "authority_candidate": "A2",
            "reason": "refresh_failure_with_data_impact",
        }

    if any(_failed(check) and bool(check.get("critical")) for check in items) or critical_stale_tail:
        return {"severity": "P2", "authority_candidate": "A2", "reason": "critical_data_degradation"}
    if any(str(check.get("status", "")) in {"warning", "failed", "timeout", "stale_tail"} for check in items):
        return {"severity": "P3", "authority_candidate": "A1", "reason": "observation_required"}
    return {"severity": "healthy", "authority_candidate": "A0", "reason": "all_checks_healthy"}
