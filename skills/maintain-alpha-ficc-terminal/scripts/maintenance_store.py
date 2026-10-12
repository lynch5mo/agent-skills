"""Crash-tolerant local state for scoped Hermes maintenance runs.

Run and delivery histories are intentionally append-only.  Small mutable
indexes (lease, snapshot, and incident lookup) are written by atomic replace.
"""

from __future__ import annotations

import fcntl
import base64
import errno
import hmac
import json
import os
import stat
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(SCRIPT_DIR))

from maintenance_contract import sanitize, validate_run_record


class MaintenanceStoreError(ValueError):
    """Raised when durable state cannot be safely read or written."""


class MaintenanceStore:
    """Own the append-only Hermes run history and its small mutable indexes."""

    DELIVERY_TERMINAL_STATUSES = frozenset({"delivered", "failed"})

    def __init__(self, root: Path):
        self.root = Path(root)
        if not self.root.is_absolute():
            self.root = Path.cwd() / self.root
        self._ensure_root()

    def ledger_path(self, when: datetime | None = None) -> Path:
        """Return the UTC-day run ledger path (today when no date is supplied)."""
        current = self._as_utc(when or datetime.now(timezone.utc))
        return self.root / "ledger" / f"{current.date().isoformat()}.jsonl"

    def delivery_path(self) -> Path:
        return self.root / "delivery-events.jsonl"

    def lease_history_path(self) -> Path:
        return self.root / "lease-events.jsonl"

    def snapshot_path(self) -> Path:
        return self.root / "current-health.json"

    def lease_path(self) -> Path:
        return self.root / "current-lease.json"

    def incident_index_path(self) -> Path:
        return self.root / "incidents.json"

    def append_run(self, record: Mapping[str, Any]) -> Path:
        """Validate and append an immutable run record to its UTC-day ledger."""
        safe = self._safe_run_record(record)
        started_at = self._parse_datetime(safe["started_at"])
        path = self.ledger_path(started_at)
        with self._locked():
            if self._run_for_id(safe["run_id"]) is not None:
                raise MaintenanceStoreError("run_id already exists")
            self._append_jsonl(path, safe)
        return path

    def write_snapshot(self, snapshot: Mapping[str, Any]) -> Path:
        """Atomically replace the latest health snapshot after sanitization."""
        safe = self._safe_mapping(snapshot, "snapshot")
        with self._locked():
            self._atomic_write_json(self.snapshot_path(), safe)
        return self.snapshot_path()

    def acquire_lease(self, run_id: str, now: datetime, ttl: timedelta) -> bool:
        """Acquire the sole active lease, recording an expired holder as abandoned."""
        if not isinstance(run_id, str) or not run_id:
            raise MaintenanceStoreError("run_id must be a non-empty string")
        if ttl <= timedelta(0):
            raise MaintenanceStoreError("lease ttl must be positive")
        acquired_at = self._as_utc(now)
        expires_at = acquired_at + ttl
        with self._locked():
            existing = self._read_json_object(self.lease_path())
            if existing:
                holder = existing.get("run_id")
                try:
                    held_until = self._parse_datetime(existing["expires_at"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise MaintenanceStoreError("lease state is invalid") from exc
                if held_until > acquired_at:
                    return holder == run_id
                if isinstance(holder, str) and holder:
                    self._append_jsonl(
                        self.lease_history_path(),
                        {
                            "event": "abandoned",
                            "run_id": holder,
                            "abandoned_at": self._iso(acquired_at),
                        },
                    )
            self._atomic_write_json(
                self.lease_path(),
                {
                    "run_id": run_id,
                    "acquired_at": self._iso(acquired_at),
                    "expires_at": self._iso(expires_at),
                },
            )
        return True

    def open_incident(self, dedupe_key: str, record: Mapping[str, Any]) -> tuple[str, bool]:
        """Return a stable opaque incident id without persisting its source key."""
        if not isinstance(dedupe_key, str) or not dedupe_key:
            raise MaintenanceStoreError("dedupe key must be a non-empty string")
        safe_record = self._safe_mapping(record, "incident record", (dedupe_key,))
        with self._locked():
            index = self._read_incident_index()
            incidents = index["incidents"]
            incident_id = self._opaque_incident_id(dedupe_key)
            if incident_id in incidents:
                return incident_id, False
            incidents[incident_id] = {"record": safe_record}
            self._atomic_write_json(self.incident_index_path(), index)
        return incident_id, True

    def append_delivery_event(self, run_id: str, status: str, error: str = "") -> Path:
        """Append a later Hermes delivery result; never rewrite the original run."""
        if not isinstance(run_id, str) or not run_id:
            raise MaintenanceStoreError("run_id must be a non-empty string")
        if status not in self.DELIVERY_TERMINAL_STATUSES:
            raise MaintenanceStoreError("delivery status is not allowed")
        if not isinstance(error, str):
            raise MaintenanceStoreError("delivery error must be a string")
        with self._locked():
            run = self._run_for_id(run_id)
            if run is None:
                raise MaintenanceStoreError("delivery run does not exist")
            started_at = self._parse_datetime(run["started_at"])
            occurred_at = self._as_utc(datetime.now(timezone.utc))
            if occurred_at <= started_at:
                raise MaintenanceStoreError("delivery event must follow the run")
            current_status = self._delivery_status_for_run(run)
            if current_status == status:
                return self.delivery_path()
            if current_status is not None:
                raise MaintenanceStoreError("delivery run already has a terminal status")
            event = {
                "event_id": f"delivery-{uuid.uuid4().hex}",
                "run_id": run_id,
                "run_started_at": self._iso(started_at),
                "status": status,
                "error": "delivery_failed" if error else "",
                "occurred_at": self._iso(occurred_at),
            }
            self._append_jsonl(self.delivery_path(), event)
        return self.delivery_path()

    def pending_delivery_run_id(self) -> str | None:
        """Find the newest prepared Discord run that has no reconciliation event."""
        with self._locked():
            candidates: list[tuple[datetime, int, str]] = []
            ordinal = 0
            for record in self.read_runs():
                ordinal += 1
                report_targets = record.get("report_targets")
                discord = report_targets.get("discord") if isinstance(report_targets, Mapping) else None
                if (
                    isinstance(discord, Mapping)
                    and discord.get("status") == "prepared"
                    and isinstance(record.get("run_id"), str)
                    and self._delivery_status_for_run(record) is None
                ):
                    candidates.append((self._parse_datetime(record["started_at"]), ordinal, record["run_id"]))
        return max(candidates, default=None, key=lambda item: (item[0], item[1]))[2] if candidates else None

    def read_runs(self) -> list[dict[str, Any]]:
        """Read complete JSONL run entries, ignoring an interrupted partial tail."""
        records: list[dict[str, Any]] = []
        try:
            ledger_fd = self._open_directory_at(self._root_fd, "ledger", "ledger")
        except FileNotFoundError:
            return records
        try:
            for name in sorted(name for name in os.listdir(ledger_fd) if name.endswith(".jsonl")):
                records.extend(self._read_jsonl_at(ledger_fd, name, "ledger"))
        finally:
            os.close(ledger_fd)
        return records

    def _run_for_id(self, run_id: str) -> dict[str, Any] | None:
        for record in self.read_runs():
            if record.get("run_id") == run_id:
                return record
        return None

    def _delivery_status_for_run(self, run: Mapping[str, Any]) -> str | None:
        """Return the only valid later terminal state for a persisted run."""
        run_id = run.get("run_id")
        if not isinstance(run_id, str):
            raise MaintenanceStoreError("run record is missing run_id")
        started_at = self._parse_datetime(run.get("started_at"))
        canonical_started_at = self._iso(started_at)
        status: str | None = None
        previous_occurrence: datetime | None = None
        for event in self._read_jsonl(self.delivery_path()):
            if event.get("run_id") != run_id:
                continue
            if not self._is_valid_delivery_event(event, canonical_started_at, started_at):
                continue
            occurred_at = self._parse_datetime(event["occurred_at"])
            if previous_occurrence is not None and occurred_at <= previous_occurrence:
                raise MaintenanceStoreError("delivery events are not ordered")
            previous_occurrence = occurred_at
            event_status = event["status"]
            if status is None:
                status = event_status
            elif status != event_status:
                raise MaintenanceStoreError("delivery events have conflicting terminal states")
        return status

    def _is_valid_delivery_event(
        self, event: Mapping[str, Any], canonical_started_at: str, started_at: datetime
    ) -> bool:
        if not isinstance(event.get("event_id"), str) or not event["event_id"].startswith("delivery-"):
            return False
        if event.get("status") not in self.DELIVERY_TERMINAL_STATUSES:
            return False
        if event.get("error") not in {"", "delivery_failed"}:
            return False
        if event.get("run_started_at") != canonical_started_at:
            return False
        try:
            occurred_at = self._parse_datetime(event.get("occurred_at"))
        except MaintenanceStoreError:
            return False
        return occurred_at > started_at

    def _safe_run_record(self, record: Mapping[str, Any]) -> dict[str, Any]:
        safe = self._safe_mapping(record, "run record")
        errors = validate_run_record(safe)
        if errors:
            raise ValueError("; ".join(errors))
        return safe

    @staticmethod
    def _safe_mapping(
        value: Mapping[str, Any], label: str, secret_values: tuple[str, ...] = ()
    ) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise MaintenanceStoreError(f"{label} must be a mapping")
        safe = sanitize(value, secret_values)
        try:
            json.dumps(safe, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise MaintenanceStoreError(f"{label} must be JSON-serializable") from exc
        return dict(safe)

    def _ensure_root(self) -> None:
        if not getattr(os, "O_NOFOLLOW", 0) or not getattr(os, "O_DIRECTORY", 0):
            raise MaintenanceStoreError("safe directory opens are unavailable")
        self.root.parent.mkdir(parents=True, exist_ok=True)
        self._root_parent_fd = self._open_directory_path(self.root.parent, "store root parent")
        try:
            os.mkdir(self.root.name, mode=0o700, dir_fd=self._root_parent_fd)
            os.fsync(self._root_parent_fd)
        except FileExistsError:
            pass
        self._root_fd = self._open_directory_at(self._root_parent_fd, self.root.name, "store root")

    @contextmanager
    def _locked(self) -> Iterator[None]:
        descriptor = self._open_regular_at(
            self._root_fd,
            ".maintenance-store.lock",
            os.O_RDWR | os.O_CREAT,
            "lock",
            mode=0o600,
        )
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    def _append_jsonl(self, path: Path, value: Mapping[str, Any]) -> None:
        payload = json.dumps(sanitize(value), ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
        parent_fd, name = self._state_parent_fd(path, create=True)
        try:
            if self._jsonl_has_partial_tail(parent_fd, name, "ledger"):
                raise MaintenanceStoreError("JSONL partial tail requires explicit recovery")
            created = False
            try:
                descriptor = os.open(
                    name,
                    os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=parent_fd,
                )
                created = True
            except FileExistsError:
                descriptor = self._open_regular_at(
                    parent_fd, name, os.O_WRONLY | os.O_APPEND, "ledger"
                )
            try:
                self._validate_regular(descriptor, "ledger")
                self._write_all(descriptor, payload)
                os.fsync(descriptor)
                if created:
                    os.fsync(parent_fd)
            finally:
                os.close(descriptor)
        finally:
            os.close(parent_fd)

    def _atomic_write_json(self, path: Path, value: Mapping[str, Any]) -> None:
        payload = (json.dumps(sanitize(value), ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
            "utf-8"
        )
        parent_fd, name = self._state_parent_fd(path, create=True)
        temporary = f".{name}-{uuid.uuid4().hex}.tmp"
        descriptor = -1
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent_fd,
            )
            self._write_all(descriptor, payload)
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            os.replace(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            os.fsync(parent_fd)
        except Exception:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            raise
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            os.close(parent_fd)

    def _read_incident_index(self) -> dict[str, Any]:
        index = self._read_json_object(self.incident_index_path())
        if not index:
            return {"version": 2, "incidents": {}}
        incidents = index.get("incidents")
        if index.get("version") != 2 or not isinstance(incidents, Mapping):
            raise MaintenanceStoreError("incident index is invalid")
        return {"version": 2, "incidents": dict(incidents)}

    def _read_json_object(self, path: Path) -> dict[str, Any]:
        try:
            parent_fd, name = self._state_parent_fd(path, create=False)
        except FileNotFoundError:
            return {}
        try:
            try:
                descriptor = self._open_regular_at(parent_fd, name, os.O_RDONLY, "state JSON")
            except FileNotFoundError:
                return {}
            try:
                value = json.loads(self._read_all(descriptor).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise MaintenanceStoreError("state JSON is invalid") from exc
            finally:
                os.close(descriptor)
            if not isinstance(value, Mapping):
                raise MaintenanceStoreError("state JSON must be an object")
            return dict(value)
        finally:
            os.close(parent_fd)

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        try:
            parent_fd, name = self._state_parent_fd(path, create=False)
        except FileNotFoundError:
            return []
        try:
            return self._read_jsonl_at(parent_fd, name, "JSONL")
        except FileNotFoundError:
            return []
        finally:
            os.close(parent_fd)

    def _read_jsonl_at(self, parent_fd: int, name: str, label: str) -> list[dict[str, Any]]:
        """Parse durable entries strictly; only an unfinished final line is ignored."""
        descriptor = self._open_regular_at(parent_fd, name, os.O_RDONLY, label)
        try:
            raw = self._read_all(descriptor)
        finally:
            os.close(descriptor)
        records: list[dict[str, Any]] = []
        lines = raw.splitlines(keepends=True)
        for index, line in enumerate(lines):
            is_partial_tail = index == len(lines) - 1 and not line.endswith(b"\n")
            if is_partial_tail:
                break
            if not line.strip():
                raise MaintenanceStoreError("JSONL contains an empty complete line")
            try:
                value = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise MaintenanceStoreError("JSONL contains malformed complete line") from exc
            if not isinstance(value, Mapping):
                raise MaintenanceStoreError("JSONL entries must be objects")
            records.append(dict(value))
        return records

    @staticmethod
    def _parse_datetime(value: Any) -> datetime:
        if not isinstance(value, str):
            raise MaintenanceStoreError("timestamp must be ISO-8601")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise MaintenanceStoreError("timestamp must be ISO-8601") from exc
        return MaintenanceStore._as_utc(parsed)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise MaintenanceStoreError("timestamp must be timezone-aware")
        return value.astimezone(timezone.utc)

    @staticmethod
    def _iso(value: datetime) -> str:
        return MaintenanceStore._as_utc(value).isoformat()

    @staticmethod
    def _write_all(descriptor: int, payload: bytes) -> None:
        """Write every byte or fail so an interrupted append is never reported as durable."""
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise MaintenanceStoreError("JSONL short write")
            offset += written

    def _state_parent_fd(self, path: Path, *, create: bool) -> tuple[int, str]:
        """Anchor fixed state paths below the already-open trusted store root."""
        relative = path.relative_to(self.root)
        if not relative.parts:
            raise MaintenanceStoreError("state path must name a file")
        descriptor = os.dup(self._root_fd)
        try:
            for part in relative.parts[:-1]:
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=descriptor)
                    except FileExistsError:
                        pass
                next_descriptor = self._open_directory_at(descriptor, part, "state directory")
                os.close(descriptor)
                descriptor = next_descriptor
            return descriptor, relative.name
        except Exception:
            os.close(descriptor)
            raise

    @staticmethod
    def _open_directory_path(path: Path, label: str) -> int:
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError as exc:
            raise MaintenanceStoreError(f"{label} must not be a symlink") from exc
        try:
            if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                raise MaintenanceStoreError(f"{label} must be a directory")
            return descriptor
        except Exception:
            os.close(descriptor)
            raise

    @staticmethod
    def _open_directory_at(parent_fd: int, name: str, label: str) -> int:
        try:
            descriptor = os.open(
                name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd
            )
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                raise FileNotFoundError(name) from exc
            raise MaintenanceStoreError(f"{label} must not be a symlink") from exc
        try:
            if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                raise MaintenanceStoreError(f"{label} must be a directory")
            return descriptor
        except Exception:
            os.close(descriptor)
            raise

    @staticmethod
    def _open_regular_at(
        parent_fd: int, name: str, flags: int, label: str, *, mode: int = 0o600, private: bool = False
    ) -> int:
        try:
            descriptor = os.open(name, flags | os.O_NOFOLLOW, mode, dir_fd=parent_fd)
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                raise FileNotFoundError(name) from exc
            raise MaintenanceStoreError(f"{label} must not be a symlink") from exc
        try:
            MaintenanceStore._validate_regular(descriptor, label, private=private)
            return descriptor
        except Exception:
            os.close(descriptor)
            raise

    @staticmethod
    def _validate_regular(descriptor: int, label: str, *, private: bool = False) -> None:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise MaintenanceStoreError(f"{label} must be one regular file")
        if private:
            if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600:
                raise MaintenanceStoreError("incident key permissions or owner are invalid")

    @staticmethod
    def _read_all(descriptor: int) -> bytes:
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)

    def _jsonl_has_partial_tail(self, parent_fd: int, name: str, label: str) -> bool:
        try:
            descriptor = self._open_regular_at(parent_fd, name, os.O_RDONLY, label)
        except FileNotFoundError:
            return False
        try:
            size = os.fstat(descriptor).st_size
            if not size:
                return False
            os.lseek(descriptor, -1, os.SEEK_END)
            return os.read(descriptor, 1) != b"\n"
        finally:
            os.close(descriptor)

    def _opaque_incident_id(self, dedupe_key: str) -> str:
        key = self._load_or_create_incident_key()
        opaque = base64.urlsafe_b64encode(hmac.digest(key, dedupe_key.encode("utf-8"), "sha256"))
        return "incident-" + opaque.rstrip(b"=").decode("ascii")

    def _load_or_create_incident_key(self) -> bytes:
        name = f".{self.root.name}.incident-key"
        try:
            descriptor = self._open_regular_at(
                self._root_parent_fd,
                name,
                os.O_RDONLY,
                "incident key",
                private=True,
            )
        except FileNotFoundError:
            try:
                descriptor = os.open(
                    name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=self._root_parent_fd,
                )
            except FileExistsError:
                descriptor = self._open_regular_at(
                    self._root_parent_fd,
                    name,
                    os.O_RDONLY,
                    "incident key",
                    private=True,
                )
            else:
                try:
                    self._validate_regular(descriptor, "incident key", private=True)
                    key = os.urandom(32)
                    self._write_all(descriptor, key)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                os.fsync(self._root_parent_fd)
                return key
        try:
            key = os.read(descriptor, 64)
        finally:
            os.close(descriptor)
        if len(key) != 32:
            raise MaintenanceStoreError("incident key is invalid")
        return key
