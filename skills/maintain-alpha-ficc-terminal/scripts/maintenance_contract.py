"""Maintenance-run records with durable-report and redaction guards."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Mapping, Sequence


REQUIRED_BASE_FIELDS = {
    "run_id",
    "executor",
    "role",
    "trigger",
    "started_at",
    "checks",
    "actions",
    "verification",
    "report_targets",
    "final_status",
}
SENSITIVE_KEY_FRAGMENTS = (
    "token",
    "password",
    "secret",
    "authorization",
    "credential",
    "api_key",
    "hash",
    "length",
    "prefix",
    "fragment",
)
A3_PUBLICATION_STATUS = {
    "builder_required": "remote_visible",
    "handoff_push_failed": "handoff_push_failed",
    "remote_not_visible": "remote_not_visible",
}
_A3_CANONICAL_PATH = re.compile(
    r"^outputs/review/agent_task_summaries/Hermes/"
    r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}/"
    r"TASK-[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.md$"
)
_A3_PATH_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$")


def _iso8601(value: datetime) -> str:
    return value.isoformat()


def new_run_record(run_id: str, now: datetime) -> dict[str, Any]:
    """Create the smallest auditable record for a scoped Hermes maintenance run."""
    return {
        "run_id": run_id,
        "executor": "hermes",
        "role": "scoped_agent",
        "trigger": "maintenance",
        "started_at": _iso8601(now),
        "checks": [],
        "actions": [],
        "verification": [],
        "report_targets": {},
        "final_status": "failed",
    }


def _sensitive_key(key: Any) -> bool:
    normalized = str(key).casefold()
    return any(fragment in normalized for fragment in SENSITIVE_KEY_FRAGMENTS)


def _redact_secret_values(value: str, secrets: Sequence[str]) -> str:
    redacted = value
    for secret in secrets:
        redacted = redacted.replace(secret, "<redacted>")
    return redacted


def sanitize(value: Any, secret_values: Sequence[str] = ()) -> Any:
    """Return a JSON-safe copy with sensitive keys and supplied secret values redacted."""
    secrets = tuple(secret for secret in secret_values if secret)
    if isinstance(value, datetime):
        return _iso8601(value)
    if isinstance(value, Mapping):
        return {
            _redact_secret_values(str(key), secrets): (
                "<redacted>" if _sensitive_key(key) else sanitize(item, secrets)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize(item, secrets) for item in value]
    if isinstance(value, tuple):
        return [sanitize(item, secrets) for item in value]
    if isinstance(value, str):
        return _redact_secret_values(value, secrets)
    return value


def _contains_raw_command_environment(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            _is_raw_command_environment_key(key)
            or _contains_raw_command_environment(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_raw_command_environment(item) for item in value)
    return False


def _is_raw_command_environment_key(key: Any) -> bool:
    normalized = "".join(character for character in str(key).casefold() if character.isalnum())
    return "command" in normalized and "env" in normalized


def _is_iso8601(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _valid_a3_canonical_path(value: Any) -> bool:
    return isinstance(value, str) and _A3_CANONICAL_PATH.fullmatch(value) is not None


def _valid_a3_local_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or len(value) > 240:
        return False
    segments = value.removeprefix("/").split("/")
    if any(_A3_PATH_SEGMENT.fullmatch(segment) is None for segment in segments):
        return False
    return len(segments) >= 6 and _valid_a3_canonical_path("/".join(segments[-6:]))


def validate_agent_kb_publication(record: Mapping[str, Any]) -> list[str]:
    """Validate final A3 status and its instance-aware publication path."""
    final_status = str(record.get("final_status") or "")
    publication = record.get("agent_kb")
    if final_status not in A3_PUBLICATION_STATUS and (
        publication is None or publication == {}
    ):
        return []
    if not isinstance(publication, Mapping):
        return ["invalid A3 publication"]

    publication_status = publication.get("status")
    if publication_status != A3_PUBLICATION_STATUS.get(final_status):
        return ["invalid A3 publication"]
    if publication_status == "remote_visible":
        valid = "local_path" not in publication and _valid_a3_canonical_path(
            publication.get("canonical_path")
        )
    else:
        valid = "canonical_path" not in publication and _valid_a3_local_path(
            publication.get("local_path")
        )
    return [] if valid else ["invalid A3 publication"]


def validate_run_record(record: Mapping[str, Any]) -> list[str]:
    """Return contract violations without echoing potentially sensitive data."""
    errors: list[str] = []
    for field in sorted(REQUIRED_BASE_FIELDS):
        if field not in record or record[field] is None:
            errors.append(f"missing required field: {field}")

    if record.get("executor") != "hermes":
        errors.append("executor must be hermes")
    if record.get("role") != "scoped_agent":
        errors.append("role must be scoped_agent")

    if "started_at" in record and not _is_iso8601(record["started_at"]):
        errors.append("started_at must be ISO-8601")
    if _contains_raw_command_environment(record):
        errors.append("raw command environment must not be stored")

    actions = record.get("actions", [])
    if not isinstance(actions, list):
        errors.append("actions must be a list")
        actions = []
    for action in actions:
        if not isinstance(action, Mapping) or not action.get("id"):
            errors.append("each action requires an id")
        if not isinstance(action, Mapping) or not action.get("version"):
            errors.append("each action requires an action version")

    repaired = str(record.get("final_status") or "") in {"repaired", "completed"}
    if actions or repaired:
        if not record.get("verification"):
            errors.append("modified runs require verification")
        if not record.get("report_targets"):
            errors.append("modified runs require report_targets")
    if repaired and not actions:
        errors.append("repaired runs require actions")

    report_targets = record.get("report_targets", {})
    if isinstance(report_targets, Mapping) and "discord" in report_targets:
        discord = report_targets["discord"]
        discord_status = discord.get("status") if isinstance(discord, Mapping) else None
        if not isinstance(discord, Mapping) or discord_status not in {"prepared", "unconfigured"}:
            errors.append("discord status must be prepared or unconfigured")

    errors.extend(validate_agent_kb_publication(record))

    try:
        json.dumps(sanitize(record))
    except (TypeError, ValueError):
        errors.append("record must be JSON-serializable")
    return errors


def completion_status(
    record: Mapping[str, Any], *, ledger_persisted: bool = False
) -> str:
    """Derive outward status only after all four reporting surfaces are ready."""
    status = str(record.get("final_status") or "failed")
    repaired = status in {"repaired", "completed"}
    if validate_agent_kb_publication(record):
        return "repaired_reporting_failed" if repaired else "reporting_failed"
    report_targets = record.get("report_targets", {})
    if not isinstance(report_targets, Mapping):
        report_targets = {}
    local_report = report_targets.get("local_report", {})
    cron_output = report_targets.get("cron_output", {})
    discord = report_targets.get("discord", {})
    reporting_complete = (
        ledger_persisted is True
        and isinstance(local_report, Mapping)
        and local_report.get("status") == "persisted"
        and isinstance(cron_output, Mapping)
        and cron_output.get("status") == "persisted"
        and isinstance(discord, Mapping)
        and discord.get("status") in {"prepared", "unconfigured"}
    )
    if not reporting_complete:
        return "repaired_reporting_failed" if repaired else "reporting_failed"
    if repaired:
        return "repaired_report_ready"
    if status == "healthy":
        return "healthy_report_ready"
    if status == "observed":
        return "observed_report_ready"
    return status
