#!/usr/bin/env python3
"""Privileged A2 deployer: immutable delta image, durable journal, offline rollback.

This module is the only policy-bearing deploy entrypoint.  The repository Bash
file is intentionally a clean-environment launcher and contains no strategy.
All tests use disposable roots and fake command binaries supplied by the locked
control plane; no command below is allowed to inherit the caller environment.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import hmac
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

try:  # Direct execution from this directory.
    from check_maintenance_patch import (
        A2ControlPlane,
        GateArtifact,
        GateError,
        _artifact_digest,
        _canonical_json,
        _hmac,
        _open_regular,
        _persist_gate,
        _read_artifact,
        _normalize_stable_alias,
        _run,
        _run_git,
        _safe_env,
        load_control_plane,
    )
except ImportError:  # Test modules loaded by file path.
    import importlib.util

    _gate_path = Path(__file__).with_name("check_maintenance_patch.py")
    _spec = importlib.util.spec_from_file_location("check_maintenance_patch", _gate_path)
    if not _spec or not _spec.loader:
        raise
    _gate_module = importlib.util.module_from_spec(_spec)
    sys.modules.setdefault("check_maintenance_patch", _gate_module)
    _spec.loader.exec_module(_gate_module)
    A2ControlPlane = _gate_module.A2ControlPlane
    GateArtifact = _gate_module.GateArtifact
    GateError = _gate_module.GateError
    _artifact_digest = _gate_module._artifact_digest
    _canonical_json = _gate_module._canonical_json
    _hmac = _gate_module._hmac
    _open_regular = _gate_module._open_regular
    _persist_gate = _gate_module._persist_gate
    _read_artifact = _gate_module._read_artifact
    _normalize_stable_alias = _gate_module._normalize_stable_alias
    _run = _gate_module._run
    _run_git = _gate_module._run_git
    _safe_env = _gate_module._safe_env
    load_control_plane = _gate_module.load_control_plane


MAX_JSON_BYTES = 128 * 1024
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 4 * 1024 * 1024
MAX_COMMAND_OUTPUT = 32 * 1024
OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
IMAGE_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
A2_ROOT = Path("/var/lib/alpha-ficc-maintainer/a2")
JOURNAL_STATES = {
    "prepared",
    "bundle_ready",
    "image_built",
    "files_applying",
    "container_switching",
    "verifying",
    "publishing",
    "committed",
    "rolling_back",
    "rollback_failed",
}
NORMAL_ORDER = (
    "prepared",
    "bundle_ready",
    "image_built",
    "files_applying",
    "container_switching",
    "verifying",
    "publishing",
    "committed",
)


class DeployerError(RuntimeError):
    """Sanitized fail-closed deployer error."""


class DeploymentInterrupted(DeployerError):
    """Signal interruption deferred to the lock-held deployment state machine."""

    def __init__(self, signum: int, phase: str) -> None:
        super().__init__(f"deployment interrupted by signal {signum}")
        self.signum = signum
        self.phase = phase


class RollbackFailure(DeployerError):
    """Rollback error carrying sanitized per-file progress."""

    def __init__(self, message: str, files: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.files = files


def _require_test_hook(control: A2ControlPlane, hook_name: str) -> None:
    if getattr(control, hook_name, None) is not None and control.locked_config.get("test_only") is not True:
        raise DeployerError(f"{hook_name} is permitted only for test-only control")


def _validate_no_symlink_components(path: Path, label: str, *, allow_missing: bool = False) -> None:
    absolute = _normalize_stable_alias(path)
    current = Path(absolute.anchor)
    try:
        expected_dev = os.lstat(absolute.anchor).st_dev
    except OSError as error:
        raise DeployerError(f"{label} parent is unavailable") from error
    components = absolute.parts[1:]
    for index, component in enumerate(components):
        current = current / component
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            if allow_missing or index == len(components) - 1:
                return
            raise DeployerError(f"{label} parent is unavailable")
        if stat.S_ISLNK(metadata.st_mode):
            resolved = Path(os.path.realpath(current))
            if not (str(current) in {"/var", "/tmp"} and str(resolved).startswith("/private/")):
                raise DeployerError(f"{label} contains a symlink")
        if metadata.st_dev != expected_dev:
            raise DeployerError(f"{label} crosses a filesystem boundary")


def _ensure_directory(path: Path, *, mode: int = 0o700) -> None:
    """Create a directory path through pinned no-follow directory FDs."""

    absolute = _normalize_stable_alias(path)
    if not absolute.is_absolute():
        raise DeployerError("directory path must be absolute")
    try:
        root_fd = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
    except OSError as error:
        raise DeployerError("directory root is unavailable") from error
    current_fd = root_fd
    try:
        expected_dev = os.fstat(root_fd).st_dev
    except OSError as error:
        os.close(root_fd)
        raise DeployerError("directory root is unavailable") from error
    try:
        for component in absolute.parts[1:]:
            try:
                next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), dir_fd=current_fd)
            except FileNotFoundError:
                try:
                    os.mkdir(component, mode, dir_fd=current_fd)
                    next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), dir_fd=current_fd)
                except OSError as error:
                    raise DeployerError("directory creation failed") from error
            except OSError as error:
                raise DeployerError("directory path is unsafe") from error
            if os.fstat(next_fd).st_dev != expected_dev:
                os.close(next_fd)
                raise DeployerError("directory crosses a filesystem boundary")
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
    finally:
        if current_fd != root_fd:
            os.close(current_fd)
        os.close(root_fd)


def _open_directory_pinned(path: Path, label: str = "directory") -> int:
    """Open a directory by walking each component from the filesystem root."""

    absolute = _normalize_stable_alias(path)
    try:
        current_fd = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
    except OSError as error:
        raise DeployerError(f"{label} is unavailable") from error
    root_fd = current_fd
    try:
        expected_dev = os.fstat(root_fd).st_dev
    except OSError as error:
        os.close(root_fd)
        raise DeployerError(f"{label} is unavailable") from error
    try:
        for component in absolute.parts[1:]:
            try:
                next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), dir_fd=current_fd)
            except OSError as error:
                raise DeployerError(f"{label} is unavailable") from error
            if os.fstat(next_fd).st_dev != expected_dev:
                os.close(next_fd)
                raise DeployerError(f"{label} crosses a filesystem boundary")
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
        if current_fd != root_fd:
            os.close(root_fd)
            root_fd = current_fd
        return current_fd
    except BaseException:
        if current_fd != root_fd:
            os.close(current_fd)
        os.close(root_fd)
        raise


def _open_pinned(path: Path, flags: int, *, mode: int = 0o600, label: str = "file") -> int:
    """Open a file by walking every component through no-follow dir FDs."""

    absolute = _normalize_stable_alias(path)
    try:
        current_fd = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
    except OSError as error:
        raise DeployerError(f"{label} is unavailable") from error
    root_fd = current_fd
    try:
        expected_dev = os.fstat(root_fd).st_dev
    except OSError as error:
        os.close(root_fd)
        raise DeployerError(f"{label} is unavailable") from error
    try:
        components = absolute.parts[1:]
        if not components:
            raise DeployerError(f"{label} is not a file")
        for component in components[:-1]:
            next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), dir_fd=current_fd)
            if os.fstat(next_fd).st_dev != expected_dev:
                os.close(next_fd)
                raise DeployerError(f"{label} crosses a filesystem boundary")
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
        descriptor = os.open(components[-1], flags | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), mode, dir_fd=current_fd)
        if os.fstat(descriptor).st_dev != expected_dev:
            os.close(descriptor)
            raise DeployerError(f"{label} crosses a filesystem boundary")
        return descriptor
    except OSError as error:
        raise DeployerError(f"{label} is unavailable") from error
    finally:
        if current_fd != root_fd:
            os.close(current_fd)
        os.close(root_fd)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DeployerError("JSON contains duplicate keys")
        result[key] = value
    return result


def _reject_constant(_value: str) -> Any:
    raise DeployerError("JSON contains a non-finite value")


def _strict_json(payload: bytes, label: str, maximum: int = MAX_JSON_BYTES) -> Any:
    if len(payload) > maximum:
        raise DeployerError(f"{label} exceeds size limit")
    try:
        return json.loads(payload.decode("utf-8"), object_pairs_hook=_reject_duplicate_pairs, parse_constant=_reject_constant)
    except DeployerError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DeployerError(f"{label} is not valid strict JSON") from error


def _read_json(path: Path, label: str, maximum: int = MAX_JSON_BYTES) -> Any:
    _validate_no_symlink_components(path, label)
    try:
        metadata = os.lstat(path)
    except OSError as error:
        raise DeployerError(f"{label} is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise DeployerError(f"{label} is not a regular single-link file")
    if metadata.st_size > maximum:
        raise DeployerError(f"{label} exceeds size limit")
    descriptor = _open_pinned(path, os.O_RDONLY, label=label)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_mode, opened.st_nlink, opened.st_size) != (metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_nlink, metadata.st_size):
            raise DeployerError(f"{label} changed during open")
        chunks: list[bytes] = []
        total = 0
        while True:
            block = os.read(descriptor, min(65536, maximum + 1 - total))
            if not block:
                break
            chunks.append(block)
            total += len(block)
            if total > maximum:
                raise DeployerError(f"{label} exceeds size limit")
        payload = b"".join(chunks)
    finally:
        os.close(descriptor)
    return _strict_json(payload, label, maximum)


def _validate_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value or value.startswith("/"):
        raise DeployerError("bundle path is not canonical")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise DeployerError("bundle path traversal is forbidden")
    return value


def _generated_dockerfile(previous_image_digest: str, repo_path: str, image_path: str) -> str:
    if not IMAGE_RE.fullmatch(previous_image_digest):
        raise DeployerError("previous image is not immutable")
    _validate_relative_path(repo_path)
    if not image_path.startswith("/") or "\n" in image_path or "\r" in image_path or "\x00" in image_path:
        raise DeployerError("image path is invalid")
    # No RUN/ADD/remote context/build secret is expressible in this template.
    return f"FROM {previous_image_digest}\nCOPY payload/{Path(repo_path).name} {image_path}\n"


def _fsync_directory(path: Path) -> None:
    descriptor = _open_directory_pinned(path, "directory for fsync")
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_bounded(path: Path, label: str, maximum: int = MAX_FILE_BYTES) -> bytes:
    _validate_no_symlink_components(path, label)
    descriptor = _open_pinned(path, os.O_RDONLY, label=label)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_size > maximum:
            raise DeployerError(f"{label} is unsafe or oversized")
        chunks: list[bytes] = []
        total = 0
        while True:
            block = os.read(descriptor, min(65536, maximum + 1 - total))
            if not block:
                break
            chunks.append(block)
            total += len(block)
            if total > maximum:
                raise DeployerError(f"{label} is oversized")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _safe_write(path: Path, payload: bytes, *, mode: int = 0o600, replace: bool = False) -> None:
    _validate_no_symlink_components(path, "write target", allow_missing=True)
    if len(payload) > MAX_JSON_BYTES and path.suffix == ".json":
        raise DeployerError("JSON output exceeds size limit")
    parent = path.parent
    _ensure_directory(parent)
    _validate_no_symlink_components(path, "write target")
    parent_fd: int | None = None
    temporary_name = f".{path.name}.tmp-{os.getpid()}-{time.monotonic_ns()}"
    descriptor: int | None = None
    try:
        parent_fd = _open_directory_pinned(parent, "write parent")
        descriptor = os.open(temporary_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=parent_fd)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise DeployerError("short write")
            offset += written
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
    except DeployerError:
        try:
            if parent_fd is not None:
                os.unlink(temporary_name, dir_fd=parent_fd)
        except OSError:
            pass
        if parent_fd is not None:
            os.close(parent_fd)
            parent_fd = None
        raise
    except OSError as error:
        if parent_fd is not None:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except OSError:
                pass
            os.close(parent_fd)
            parent_fd = None
        raise DeployerError("durable write failed") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    try:
        destination_exists = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False) if parent_fd is not None else None
    except FileNotFoundError:
        destination_exists = None
    if not replace and destination_exists is not None:
        try:
            if parent_fd is not None:
                os.unlink(temporary_name, dir_fd=parent_fd)
        except OSError:
            pass
        raise DeployerError("destination already exists")
    try:
        if parent_fd is None:
            raise DeployerError("write parent is unavailable")
        os.replace(temporary_name, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        os.fsync(parent_fd)
    except (OSError, TypeError) as error:
        try:
            if parent_fd is not None:
                os.unlink(temporary_name, dir_fd=parent_fd)
        except OSError:
            pass
        raise DeployerError("atomic rename failed") from error
    finally:
        if parent_fd is not None:
            os.close(parent_fd)


def _copy_fd(source: Path, destination: Path, *, expected_sha256: str | None = None, expected_mode: int = 0o644) -> dict[str, Any]:
    _validate_no_symlink_components(source, "copy source")
    _validate_no_symlink_components(destination, "copy destination", allow_missing=True)
    _validate_relative_path(source.as_posix()) if not source.is_absolute() else None
    source_fd = _open_pinned(source, os.O_RDONLY, label="copy source")
    parent_fd: int | None = None
    temporary_name: str | None = None
    try:
        source_meta = os.fstat(source_fd)
        if not stat.S_ISREG(source_meta.st_mode) or source_meta.st_nlink != 1 or source_meta.st_size > MAX_FILE_BYTES:
            raise DeployerError("source artifact metadata is unsafe")
        _ensure_directory(destination.parent)
        _validate_no_symlink_components(destination, "copy destination")
        parent_fd = _open_directory_pinned(destination.parent, "copy destination parent")
        temporary_name = f".{destination.name}.tmp-{os.getpid()}-{time.monotonic_ns()}"
        destination_fd = os.open(temporary_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, expected_mode, dir_fd=parent_fd)
        digest = hashlib.sha256()
        total = 0
        try:
            while True:
                block = os.read(source_fd, min(65536, MAX_FILE_BYTES + 1 - total))
                if not block:
                    break
                total += len(block)
                if total > MAX_FILE_BYTES:
                    raise DeployerError("artifact exceeds byte limit")
                digest.update(block)
                offset = 0
                while offset < len(block):
                    written = os.write(destination_fd, block[offset:])
                    if written <= 0:
                        raise DeployerError("short artifact write")
                    offset += written
            os.fchmod(destination_fd, expected_mode)
            os.fsync(destination_fd)
        finally:
            os.close(destination_fd)
        if expected_sha256 and digest.hexdigest() != expected_sha256:
            os.unlink(temporary_name, dir_fd=parent_fd)
            raise DeployerError("artifact SHA-256 mismatch")
        os.replace(temporary_name, destination.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        os.fsync(parent_fd)
        final_meta = os.stat(destination.name, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_IMODE(final_meta.st_mode) != expected_mode or final_meta.st_nlink != 1:
            raise DeployerError("artifact metadata drift")
        return {"sha256": digest.hexdigest(), "size": total, "mode": expected_mode, "uid": final_meta.st_uid, "gid": final_meta.st_gid}
    except DeployerError:
        if parent_fd is not None and temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except OSError:
                pass
        raise
    except (OSError, TypeError) as error:
        if parent_fd is not None and temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except OSError:
                pass
        raise DeployerError("fd-safe artifact copy failed") from error
    finally:
        if parent_fd is not None:
            os.close(parent_fd)
        os.close(source_fd)


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        try:
            written = os.write(descriptor, payload[offset:])
        except OSError as error:
            raise DeployerError("durable write failed") from error
        if written <= 0:
            raise DeployerError("short write")
        offset += written


def _journal_transition_valid(previous: str | None, current: str) -> bool:
    if current not in JOURNAL_STATES:
        return False
    if previous is None:
        return True
    if previous == "committed" and current == "rolling_back":
        return True
    if previous in {"committed", "rollback_failed"}:
        return False
    if current == "rolling_back":
        return previous in NORMAL_ORDER
    if previous == "rolling_back":
        return current == "committed"
    if current == "rollback_failed":
        return previous in NORMAL_ORDER or previous == "rolling_back"
    if current not in NORMAL_ORDER or previous not in NORMAL_ORDER:
        return False
    return NORMAL_ORDER.index(current) == NORMAL_ORDER.index(previous) + 1


def _append_journal(path: Path, deployment_id: str, state: str, *, _hmac_key: bytes | None = None, **details: Any) -> None:
    if state not in JOURNAL_STATES:
        raise DeployerError("unknown journal state")
    record = {"deployment_id": deployment_id, "state": state, "at": dt.datetime.now(dt.timezone.utc).isoformat(), **details}
    if _hmac_key is not None:
        record["record_mac"] = _hmac(_hmac_key, record)
    payload = _canonical_json(record) + b"\n"
    if len(payload) > MAX_JSON_BYTES:
        raise DeployerError("journal record exceeds size limit")
    _ensure_directory(path.parent)
    _validate_no_symlink_components(path, "deployment journal", allow_missing=True)
    try:
        existing = os.lstat(path)
    except FileNotFoundError:
        existing = None
    except OSError as error:
        raise DeployerError("deployment journal is unavailable") from error
    if existing is not None and (stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode) or existing.st_nlink != 1 or stat.S_IMODE(existing.st_mode) != 0o600):
        raise DeployerError("deployment journal is unsafe")
    if existing is not None:
        records = _journal_records(path, deployment_id=deployment_id)
        previous = records[-1].get("state") if records else None
        if not _journal_transition_valid(previous, state):
            raise DeployerError("illegal journal transition")
    descriptor: int | None = None
    parent_fd: int | None = None
    try:
        parent_fd = _open_directory_pinned(path.parent, "journal parent")
        descriptor = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600, dir_fd=parent_fd)
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        os.fsync(parent_fd)
    except OSError as error:
        raise DeployerError("durable journal write failed") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent_fd is not None:
            os.close(parent_fd)


def _journal_records(path: Path, *, deployment_id: str | None = None, hmac_key: bytes | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    raw = _read_bounded(path, "deployment journal", MAX_JSON_BYTES)
    records: list[dict[str, Any]] = []
    previous: str | None = None
    resolved_id = deployment_id
    for line in raw.splitlines():
        if not line:
            continue
        value = _strict_json(line, "journal line", MAX_JSON_BYTES)
        if not isinstance(value, dict) or value.get("state") not in JOURNAL_STATES:
            raise DeployerError("journal state is invalid")
        record_id = value.get("deployment_id")
        if not isinstance(record_id, str) or not record_id:
            raise DeployerError("journal deployment identity is invalid")
        if resolved_id is None:
            resolved_id = record_id
        if record_id != resolved_id or not _journal_transition_valid(previous, str(value["state"])):
            raise DeployerError("illegal journal transition")
        if hmac_key is not None:
            claimed_mac = value.pop("record_mac", None)
            if not isinstance(claimed_mac, str) or not hmac.compare_digest(claimed_mac, _hmac(hmac_key, value)):
                raise DeployerError("journal authorization failed")
            value["record_mac"] = claimed_mac
        previous = str(value["state"])
        records.append(value)
        if len(records) > 64:
            raise DeployerError("deployment journal exceeds record limit")
    return records


@contextlib.contextmanager
def _exclusive_lock(control: A2ControlPlane) -> Iterator[int]:
    lock_path = control.a2_root / "locks" / "a2.lock"
    try:
        metadata = os.lstat(lock_path)
        expected_owner = getattr(control, "expected_owner_uid", os.getuid())
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_uid != expected_owner or stat.S_IMODE(metadata.st_mode) != 0o600:
            raise DeployerError("A2 lock is unsafe")
        descriptor = _open_pinned(lock_path, os.O_RDWR, label="A2 lock")
        opened = os.fstat(descriptor)
        if opened.st_uid != expected_owner or stat.S_IMODE(opened.st_mode) != 0o600 or opened.st_nlink != 1 or not stat.S_ISREG(opened.st_mode):
            os.close(descriptor)
            raise DeployerError("A2 lock is unsafe")
    except OSError as error:
        raise DeployerError("A2 lock is unavailable") from error
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise DeployerError("another A2 deployment holds the lock") from error
        yield descriptor
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _validate_lease(control: A2ControlPlane, deployment_id: str) -> dict[str, Any]:
    lease_path = control.a2_root / "active-lease.json"
    if not lease_path.exists():
        if getattr(control, "expected_owner_uid", os.getuid()) == 0:
            raise DeployerError("active maintenance lease is missing")
        return {"lease_id": "test-lease", "deployment_id": deployment_id}
    expected_owner = getattr(control, "expected_owner_uid", os.getuid())
    if expected_owner == 0:
        try:
            metadata = os.lstat(lease_path)
        except OSError as error:
            raise DeployerError("active maintenance lease is unavailable") from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_uid != expected_owner or stat.S_IMODE(metadata.st_mode) != 0o600:
            raise DeployerError("active maintenance lease is unsafe")
    lease = _read_json(lease_path, "active maintenance lease")
    if not isinstance(lease, dict) or lease.get("active") is False:
        raise DeployerError("maintenance lease is not active")
    if lease.get("deployment_id") not in {None, deployment_id}:
        raise DeployerError("maintenance lease deployment mismatch")
    expires_at = lease.get("expires_at")
    if expires_at is not None:
        if not isinstance(expires_at, str):
            raise DeployerError("maintenance lease expiry is invalid")
        try:
            if dt.datetime.fromisoformat(expires_at.replace("Z", "+00:00")) <= dt.datetime.now(dt.timezone.utc):
                raise DeployerError("maintenance lease has expired")
        except ValueError as error:
            raise DeployerError("maintenance lease expiry is invalid") from error
    return lease


def _baseline_digest(control: A2ControlPlane) -> str:
    return hashlib.sha256(_canonical_json(control.baseline_manifest)).hexdigest()


def _state_paths(control: A2ControlPlane) -> tuple[Path, Path, Path]:
    root = control.deploy_root
    head = root / ".deployed-head"
    image = root / ".api-image-digest"
    manifest = root / ".baseline-manifest-digest"
    return head, image, manifest


def _read_oid_file(path: Path, label: str) -> str:
    value = _read_bounded(path, label, 256).decode("ascii").strip()
    if not OID_RE.fullmatch(value):
        raise DeployerError(f"{label} is not a lowercase full OID")
    return value


def _read_image(path: Path, label: str) -> str:
    value = _read_bounded(path, label, 128).decode("ascii").strip()
    if not IMAGE_RE.fullmatch(value):
        raise DeployerError(f"{label} is not immutable")
    return value


def _git_blob_oid(payload: bytes, expected_oid: str) -> str:
    if len(expected_oid) == 40:
        algorithm = "sha1"
    elif len(expected_oid) == 64:
        algorithm = "sha256"
    else:
        raise DeployerError("base blob OID is not a full object ID")
    digest = hashlib.new(algorithm)
    digest.update(f"blob {len(payload)}\0".encode("ascii"))
    digest.update(payload)
    return digest.hexdigest()


def _image_digest_write(path: Path, value: str) -> None:
    if not IMAGE_RE.fullmatch(value):
        raise DeployerError("image digest is not immutable")
    _safe_write(path, (value + "\n").encode("ascii"), mode=0o644, replace=True)


def _production_mapping(control: A2ControlPlane, artifact: Mapping[str, Any]) -> tuple[str, str]:
    production = [item for item in artifact.get("files", []) if item.get("role") == "production"]
    if len(production) != 1:
        raise DeployerError("gate artifact must contain one production file")
    relative = _validate_relative_path(str(production[0]["path"]))
    baseline = control.baseline_manifest
    mapping = baseline.get("files", {}).get(relative) if isinstance(baseline.get("files"), Mapping) else None
    if isinstance(mapping, Mapping):
        image_path = str(mapping.get("image_path", ""))
    else:
        image_path = str(baseline.get("production_image_path", ""))
    if not image_path.startswith("/") or "\n" in image_path:
        raise DeployerError("baseline image path is not locked")
    return relative, image_path


def _docker_command(control: A2ControlPlane) -> str:
    command = control.locked_config.get("docker_bin", "/usr/bin/docker")
    if not isinstance(command, str) or not command.startswith("/"):
        raise DeployerError("Docker executable is not fixed")
    if getattr(control, "expected_owner_uid", os.getuid()) == 0:
        try:
            metadata = os.lstat(command)
        except OSError as error:
            raise DeployerError("Docker executable is unavailable") from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_uid != 0 or not (metadata.st_mode & 0o111):
            raise DeployerError("Docker executable is unsafe")
    return command


def _compose_path(control: A2ControlPlane) -> Path:
    configured = control.locked_config.get("compose_template")
    if not isinstance(configured, str) or not Path(configured).is_absolute():
        raise DeployerError("trusted compose template is not fixed")
    path = Path(configured)
    _validate_no_symlink_components(path, "trusted compose")
    metadata = os.lstat(path)
    expected_owner = getattr(control, "expected_owner_uid", os.getuid())
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or (expected_owner == 0 and metadata.st_uid != 0):
        raise DeployerError("trusted compose template is unsafe")
    return path


def _command_env(control: A2ControlPlane) -> dict[str, str]:
    env = _safe_env()
    env["DOCKER_CONFIG"] = str(control.locked_config.get("docker_config", "/etc/docker"))
    env["DOCKER_CONTEXT"] = str(control.locked_config.get("docker_context", "default"))
    readiness = getattr(control, "readiness", {})
    docker_host = control.locked_config.get("docker_host", readiness.get("docker_host"))
    if docker_host is not None:
        if not isinstance(docker_host, str) or not re.fullmatch(r"(?:unix|npipe|tcp)://[^\s]+", docker_host):
            raise DeployerError("Docker host binding is invalid")
        env["DOCKER_HOST"] = docker_host
    env["COMPOSE_PROJECT_NAME"] = str(control.locked_config.get("compose_project", "alpha-ficc"))
    env["COMPOSE_DISABLE_ENV_FILE"] = "1"
    # Explicitly clear proxy/loader/config injection.
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy", "LD_PRELOAD", "PYTHONPATH", "PYTHONHOME", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_GLOBAL"):
        env.pop(key, None)
    return env


def _validate_docker_binding(control: A2ControlPlane) -> None:
    locked_host = control.locked_config.get("docker_host")
    readiness = getattr(control, "readiness", {})
    readiness_host = readiness.get("docker_host")
    if getattr(control, "expected_owner_uid", os.getuid()) == 0:
        if not isinstance(locked_host, str) or not isinstance(readiness_host, str) or locked_host != readiness_host:
            raise DeployerError("Docker host binding is incomplete")
        if not re.fullmatch(r"(?:unix|npipe|tcp)://[^\s]+", locked_host):
            raise DeployerError("Docker host binding is invalid")
    elif locked_host is not None and readiness_host is not None and locked_host != readiness_host:
        raise DeployerError("Docker host binding mismatch")
    locked_context = control.locked_config.get("docker_context")
    readiness_context = readiness.get("docker_context")
    if getattr(control, "expected_owner_uid", os.getuid()) == 0 and (
        not isinstance(locked_context, str)
        or not locked_context
        or any(char.isspace() for char in locked_context)
        or not isinstance(readiness_context, str)
        or readiness_context != locked_context
    ):
        raise DeployerError("Docker context binding is incomplete")
    if readiness_context is not None and readiness_context != locked_context:
        raise DeployerError("Docker context binding mismatch")


def _run_docker(control: A2ControlPlane, args: Sequence[str], operation: str, timeout: float = 600) -> tuple[int, bytes, list[str]]:
    command = [_docker_command(control), *args]
    code, output = _run(command, env=_command_env(control), operation=operation, timeout=timeout, maximum=MAX_COMMAND_OUTPUT)
    return code, output, command


def _fake_health(control: A2ControlPlane, deploy_root: Path, deployment_dir: Path) -> dict[str, Any]:
    required = ("health", "module_import", "data_freshness")
    contract = control.locked_config.get("health_contract", control.readiness.get("health_contract"))
    if contract is None and getattr(control, "expected_owner_uid", os.getuid()) != 0:
        contract = list(required)
    if not isinstance(contract, list) or tuple(contract) != required:
        raise DeployerError("health contract is incomplete")
    commands = control.locked_config.get("health_commands")
    if commands is None and getattr(control, "expected_owner_uid", os.getuid()) != 0:
        return {"status": "ok", "checks": list(required)}
    if not isinstance(commands, Mapping) or set(commands) != set(required):
        raise DeployerError("health commands are incomplete")
    digests: dict[str, str] = {}
    for check in required:
        configured = commands.get(check)
        if not isinstance(configured, list) or not configured or not all(isinstance(item, str) and item.startswith("/") for item in configured):
            raise DeployerError(f"health command is not fixed: {check}")
        if getattr(control, "expected_owner_uid", os.getuid()) == 0:
            for executable in configured[:1]:
                try:
                    metadata = os.lstat(executable)
                except OSError as error:
                    raise DeployerError("health executable is unavailable") from error
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_uid != 0 or not (metadata.st_mode & 0o111):
                    raise DeployerError("health executable is unsafe")
        code, output = _run(configured, env=_command_env(control), operation=f"fixed health verification:{check}", timeout=60, maximum=MAX_COMMAND_OUTPUT, cwd=deploy_root)
        digests[check] = hashlib.sha256(output).hexdigest()
        if code != 0:
            return {"status": "failed", "checks": list(required), "output_digests": digests, "failed_check": check}
    return {"status": "ok", "checks": list(required), "output_digests": digests}


def _build_context(control: A2ControlPlane, artifact: Mapping[str, Any], deployment_dir: Path, previous_image: str) -> tuple[Path, dict[str, Any]]:
    relative, image_path = _production_mapping(control, artifact)
    context = deployment_dir / "build-context"
    payload = context / "payload"
    _ensure_directory(payload)
    dockerfile = _generated_dockerfile(previous_image, relative, image_path)
    source = control.source_repo / relative
    production = [item for item in artifact["files"] if item["role"] == "production"][0]
    if production.get("git_mode") != "100644":
        raise DeployerError("delta image production file must be Git mode 100644")
    _copy_fd(source, payload / Path(relative).name, expected_sha256=str(production["sha256"]), expected_mode=0o644)
    _safe_write(context / "Dockerfile", dockerfile.encode("utf-8"), mode=0o600, replace=False)
    manifest = {"production_path": relative, "image_path": image_path, "candidate_sha": artifact["candidate_oid"], "previous_image": previous_image}
    _safe_write(context / "manifest.json", _canonical_json(manifest), mode=0o600, replace=False)
    files = sorted(path.relative_to(context).as_posix() for path in context.rglob("*") if path.is_file())
    if files != ["Dockerfile", "manifest.json", f"payload/{Path(relative).name}"]:
        raise DeployerError("delta build context contains unexpected files")
    return context, {"files": files, "dockerfile_sha256": hashlib.sha256(dockerfile.encode()).hexdigest(), "production_path": relative, "image_path": image_path}


def _bundle_manifest(control: A2ControlPlane, artifact: Mapping[str, Any], deployment_id: str, lease: Mapping[str, Any], previous_image: str, old_head: str, old_file: Mapping[str, Any], new_file: Mapping[str, Any], compose: Path, compose_sha256: str, old_override_sha256: str, old_override_present: bool) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "kind": "alpha-ficc-a2-bundle-v2",
        "deployment_id": deployment_id,
        "lease_id": str(lease.get("lease_id", "")),
        "gate_id": artifact.get("gate_id"),
        "base_oid": artifact["base_oid"],
        "candidate_oid": artifact["candidate_oid"],
        "previous_image_digest": previous_image,
        "old_head": old_head,
        "baseline_manifest_digest": _baseline_digest(control),
        "compose_template": os.fspath(compose),
        "compose_sha256": compose_sha256,
        "old_override_sha256": old_override_sha256,
        "old_override_present": old_override_present,
        "files": [{"path": old_file["path"], "sha256": old_file["sha256"], "mode": old_file["mode"], "uid": old_file["uid"], "gid": old_file["gid"], "new_sha256": new_file["sha256"]}],
        "consumed": False,
    }
    manifest["manifest_mac"] = _hmac(control.key, manifest)
    return manifest


def _validate_bundle(control: A2ControlPlane, deployment_dir: Path, deployment_id: str) -> tuple[dict[str, Any], Path]:
    manifest_path = deployment_dir / "bundle" / "manifest.json"
    manifest = _read_json(manifest_path, "rollback manifest")
    if not isinstance(manifest, dict) or manifest.get("kind") != "alpha-ficc-a2-bundle-v2" or manifest.get("deployment_id") != deployment_id:
        raise DeployerError("rollback deployment identity mismatch")
    claimed = manifest.pop("manifest_mac", None)
    if not isinstance(claimed, str) or not hmac.compare_digest(claimed, _hmac(control.key, manifest)):
        raise DeployerError("rollback bundle authorization failed")
    manifest["manifest_mac"] = claimed
    if manifest.get("consumed") is not False:
        raise DeployerError("rollback bundle replay is forbidden")
    if manifest.get("baseline_manifest_digest") != _baseline_digest(control):
        raise DeployerError("rollback baseline drift")
    files = manifest.get("files")
    if not isinstance(files, list) or len(files) != 1:
        raise DeployerError("rollback file manifest is invalid")
    for item in files:
        if not isinstance(item, dict):
            raise DeployerError("rollback file manifest is invalid")
        _validate_relative_path(str(item.get("path", "")))
        if not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", ""))) or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("new_sha256", ""))):
            raise DeployerError("rollback file digest is invalid")
        if item.get("mode") not in {0o644, 0o755} or not isinstance(item.get("uid"), int) or isinstance(item.get("uid"), bool) or not isinstance(item.get("gid"), int) or isinstance(item.get("gid"), bool) or item.get("uid") < 0 or item.get("gid") < 0:
            raise DeployerError("rollback file metadata is invalid")
    if not isinstance(manifest.get("lease_id"), str) or not manifest.get("lease_id"):
        raise DeployerError("rollback lease authorization is missing")
    if not re.fullmatch(r"[0-9a-f]{64}", str(manifest.get("compose_sha256", ""))) or not re.fullmatch(r"[0-9a-f]{64}", str(manifest.get("old_override_sha256", ""))) or not isinstance(manifest.get("old_override_present"), bool):
        raise DeployerError("rollback compose binding is invalid")
    if not IMAGE_RE.fullmatch(str(manifest.get("previous_image_digest", ""))):
        raise DeployerError("rollback image is not immutable")
    if not OID_RE.fullmatch(str(manifest.get("old_head", ""))):
        raise DeployerError("rollback head is not normalized")
    compose = deployment_dir / "bundle" / "compose.base.yml"
    old_override = deployment_dir / "bundle" / "old-override.yml"
    for path, expected, label in ((compose, manifest["compose_sha256"], "rollback compose"), (old_override, manifest["old_override_sha256"], "rollback old override")):
        payload = _read_bounded(path, label, MAX_FILE_BYTES)
        if hashlib.sha256(payload).hexdigest() != expected:
            raise DeployerError(f"{label} digest mismatch")
    return manifest, deployment_dir / "bundle"


def _result(status: str, mode: str, deployment_id: str, *, phase: str | None = None, **extra: Any) -> dict[str, Any]:
    payload = {"kind": "alpha-ficc-a2-deployment-v2", "status": status, "mode": mode, "deployment_id": deployment_id}
    if phase:
        payload["phase"] = phase
    payload.update(extra)
    return payload


def _install_signal_handlers(
    control: A2ControlPlane,
    deployment_id: str,
    *,
    publishing_state: dict[str, str] | None = None,
) -> dict[int, Any]:
    """Install signal handlers that defer stateful recovery to the main loop."""

    previous: dict[int, Any] = {}
    state = publishing_state if publishing_state is not None else {"phase": "pre-publishing"}

    def handler(signum: int, _frame: Any) -> None:
        raise DeploymentInterrupted(signum, state.get("phase", "pre-publishing"))

    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, handler)
    return previous


def _restore_signal_handlers(previous: Mapping[int, Any]) -> None:
    for signum, handler in previous.items():
        signal.signal(signum, handler)


def recover_incomplete(control_plane: A2ControlPlane) -> list[dict[str, Any]]:
    """Next-invocation recovery for durable journals (SIGKILL/power loss)."""

    recovered: list[dict[str, Any]] = []
    with _exclusive_lock(control_plane):
        deployments = control_plane.a2_root / "deployments"
        if not deployments.exists():
            return recovered
        for directory in sorted(deployments.iterdir()):
            if not directory.is_dir() or directory.is_symlink():
                continue
            records = _journal_records(directory / "journal.jsonl", hmac_key=control_plane.key)
            if not records:
                continue
            last = records[-1].get("state")
            if last in {"committed", "rollback_failed"}:
                continue
            if last == "publishing":
                recovered.append(_recover_publishing(directory, control_plane, records))
                continue
            recovered.append(rollback(directory.name, control_plane, _lock_already_held=True))
    return recovered


def _query_canonical_remote_head(control: A2ControlPlane) -> str:
    remote = control.canonical_remote
    ref = f"refs/heads/{control.canonical_ref}"
    env = _safe_env()
    known_hosts = getattr(control, "known_hosts", None)
    if known_hosts is not None:
        env["GIT_SSH_COMMAND"] = f"/usr/bin/ssh -oBatchMode=yes -oStrictHostKeyChecking=yes -oUserKnownHostsFile={os.fspath(known_hosts)}"
    code, output = _run(["/usr/bin/git", "ls-remote", remote, ref], env=env, operation="canonical remote reconciliation", timeout=60, maximum=MAX_COMMAND_OUTPUT)
    if code != 0:
        raise DeployerError("canonical remote reconciliation failed")
    lines = output.decode("ascii", "strict").splitlines()
    if len(lines) != 1:
        raise DeployerError("canonical remote reconciliation output is invalid")
    fields = lines[0].split("\t")
    if len(fields) != 2 or fields[1] != ref or not OID_RE.fullmatch(fields[0]):
        raise DeployerError("canonical remote reconciliation output is invalid")
    return fields[0]


def _reconciliation_state(control: A2ControlPlane) -> dict[str, Any]:
    """Capture durable local state without allowing a read failure to mask the phase."""

    state: dict[str, Any] = {
        "current_head": None,
        "current_image": None,
        "health": {"status": "unknown"},
        "files": [],
    }
    try:
        state["current_head"] = _read_oid_file(control.deploy_root / ".deployed-head", "current deployed head")
    except Exception:
        pass
    try:
        state["current_image"] = _read_image(control.deploy_root / ".api-image-digest", "current API image")
    except Exception:
        pass
    return state


def _publishing_failure(
    deployment_id: str,
    state: Mapping[str, Any],
    *,
    remote_state: str,
    reason_code: str,
    remote_oid: str | None = None,
) -> dict[str, Any]:
    """Return a phase-preserving publishing result with every known local field."""

    extra: dict[str, Any] = {
        "recovery_required": True,
        "remote_state": remote_state,
        "reason_code": reason_code,
        "current_head": state.get("current_head"),
        "current_image": state.get("current_image"),
        "health": state.get("health", {"status": "unknown"}),
        "files": state.get("files", []),
    }
    if remote_oid is not None:
        extra["remote_oid"] = remote_oid
    return _result("git_reconciliation_required", "recovery", deployment_id, phase="publishing", **extra)


def _reconcile_publishing(directory: Path, control: A2ControlPlane) -> dict[str, Any]:
    """Reconcile a durable publishing phase without guessing remote state."""

    deployment_id = directory.name
    state = _reconciliation_state(control)
    try:
        records = _journal_records(directory / "journal.jsonl", hmac_key=control.key)
        if not records or records[-1].get("state") != "publishing":
            return _publishing_failure(deployment_id, state, remote_state="unavailable", reason_code="journal_invalid")
        return _recover_publishing(directory, control, records)
    except Exception:
        return _publishing_failure(deployment_id, state, remote_state="unavailable", reason_code="journal_invalid")


def _recover_publishing(directory: Path, control: A2ControlPlane, records: list[dict[str, Any]]) -> dict[str, Any]:
    deployment_id = directory.name
    state = _reconciliation_state(control)
    prepared = next((record for record in records if isinstance(record, Mapping) and record.get("state") == "prepared"), None)
    if prepared is None:
        return _publishing_failure(deployment_id, state, remote_state="unavailable", reason_code="journal_invalid")
    base = str(prepared.get("base_oid", ""))
    candidate = str(prepared.get("candidate_oid", ""))
    if not OID_RE.fullmatch(base) or not OID_RE.fullmatch(candidate):
        return _publishing_failure(deployment_id, state, remote_state="unavailable", reason_code="journal_invalid")
    runner = getattr(control, "remote_inspect_runner", None)
    try:
        _require_test_hook(control, "remote_inspect_runner")
        if callable(runner):
            try:
                remote = runner(control, deployment_id, records)
            except TypeError:
                remote = runner(control)
        else:
            remote = _query_canonical_remote_head(control)
    except Exception:
        return _publishing_failure(deployment_id, state, remote_state="unavailable", reason_code="remote_query_failed")
    if not isinstance(remote, str) or not OID_RE.fullmatch(remote):
        return _publishing_failure(deployment_id, state, remote_state="unavailable", reason_code="remote_query_invalid")
    if remote == base:
        try:
            result = rollback(deployment_id, control, _lock_already_held=True)
        except Exception:
            return _publishing_failure(deployment_id, state, remote_state="base", reason_code="rollback_failed", remote_oid=remote)
        if not isinstance(result, dict):
            return _publishing_failure(deployment_id, state, remote_state="base", reason_code="rollback_result_invalid", remote_oid=remote)
        result.setdefault("remote_state", "base")
        result.setdefault("remote_oid", remote)
        return result
    if remote != candidate:
        return _publishing_failure(deployment_id, state, remote_state="other", reason_code="remote_other", remote_oid=remote)

    candidate_stage = "candidate_bundle_validation"
    try:
        try:
            _manifest, _bundle = _validate_bundle(control, directory, deployment_id)
        except Exception:
            return _publishing_failure(deployment_id, state, remote_state="candidate", reason_code="candidate_bundle_invalid", remote_oid=remote)

        candidate_stage = "candidate_image_validation"
        expected_image = ""
        for record in reversed(records):
            if isinstance(record, Mapping) and record.get("image_digest"):
                expected_image = str(record["image_digest"])
                break
        try:
            image = _read_image(control.deploy_root / ".api-image-digest", "current API image")
        except Exception:
            return _publishing_failure(deployment_id, state, remote_state="candidate", reason_code="candidate_local_image_unavailable", remote_oid=remote)
        state["current_image"] = image
        if not IMAGE_RE.fullmatch(expected_image) or image != expected_image:
            return _publishing_failure(deployment_id, state, remote_state="candidate", reason_code="candidate_local_image_mismatch", remote_oid=remote)

        candidate_stage = "candidate_gate_validation"
        gate_id = str(prepared.get("gate_id", ""))
        try:
            artifact = _read_gate(gate_id, control)
        except Exception:
            return _publishing_failure(deployment_id, state, remote_state="candidate", reason_code="candidate_gate_invalid", remote_oid=remote)
        production = [item for item in artifact.get("files", []) if isinstance(item, Mapping) and item.get("role") == "production"]
        if len(production) != 1:
            return _publishing_failure(deployment_id, state, remote_state="candidate", reason_code="candidate_file_binding_missing", remote_oid=remote)

        candidate_stage = "candidate_file_validation"
        file_status = {"path": str(production[0].get("path", "")), "status": "candidate_pending"}
        state["files"] = [file_status]
        try:
            relative = _validate_relative_path(file_status["path"])
            target = control.deploy_root / relative
            actual_sha = hashlib.sha256(_read_bounded(target, "candidate production artifact")).hexdigest()
            expected_sha = str(production[0].get("sha256", ""))
            if not re.fullmatch(r"[0-9a-f]{64}", expected_sha) or actual_sha != expected_sha:
                raise DeployerError("candidate production artifact digest mismatch")
        except Exception:
            file_status.update({"status": "failed", "reason": "candidate_file_mismatch"})
            return _publishing_failure(deployment_id, state, remote_state="candidate", reason_code="candidate_file_mismatch", remote_oid=remote)
        file_status["status"] = "verified"

        candidate_stage = "candidate_health_validation"
        try:
            health = _fake_health(control, control.deploy_root, directory)
        except Exception:
            return _publishing_failure(deployment_id, state, remote_state="candidate", reason_code="candidate_health_unavailable", remote_oid=remote)
        if not isinstance(health, Mapping):
            return _publishing_failure(deployment_id, state, remote_state="candidate", reason_code="candidate_health_unavailable", remote_oid=remote)
        state["health"] = dict(health)
        if health.get("status") != "ok":
            return _publishing_failure(deployment_id, state, remote_state="candidate", reason_code="candidate_health_failed", remote_oid=remote)

        candidate_stage = "local_head_persist"
        try:
            _head_digest_write(control.deploy_root / ".deployed-head", candidate)
        except Exception:
            state["current_head"] = _reconciliation_state(control).get("current_head")
            return _publishing_failure(deployment_id, state, remote_state="candidate", reason_code="local_head_persist_failed", remote_oid=remote)

        candidate_stage = "local_head_verify"
        try:
            state["current_head"] = _read_oid_file(control.deploy_root / ".deployed-head", "reconciled deployed head")
        except Exception:
            state["current_head"] = _reconciliation_state(control).get("current_head")
            return _publishing_failure(deployment_id, state, remote_state="candidate", reason_code="local_head_verify_failed", remote_oid=remote)
        if state["current_head"] != candidate:
            return _publishing_failure(deployment_id, state, remote_state="candidate", reason_code="local_head_verify_failed", remote_oid=remote)

        candidate_stage = "journal_commit"
        try:
            _append_journal(directory / "journal.jsonl", deployment_id, "committed", _hmac_key=control.key, image_digest=image, health=health, reconciled=True)
        except Exception:
            return _publishing_failure(deployment_id, state, remote_state="candidate", reason_code="journal_commit_failed", remote_oid=remote)
        return _result(
            "deployed",
            "recovery",
            deployment_id,
            phase="committed",
            remote_state="candidate",
            remote_oid=remote,
            current_head=state["current_head"],
            current_image=image,
            health=dict(health),
            files=list(state["files"]),
            recovery_required=False,
            reconciled=True,
        )
    except Exception:
        reason_code = {
            "candidate_bundle_validation": "candidate_bundle_invalid",
            "candidate_image_validation": "candidate_local_image_mismatch",
            "candidate_gate_validation": "candidate_gate_invalid",
            "candidate_file_validation": "candidate_file_mismatch",
            "candidate_health_validation": "candidate_health_unavailable",
            "local_head_persist": "local_head_persist_failed",
            "local_head_verify": "local_head_verify_failed",
            "journal_commit": "journal_commit_failed",
        }.get(candidate_stage, "candidate_reconciliation_failed")
        return _publishing_failure(deployment_id, state, remote_state="candidate", reason_code=reason_code, remote_oid=remote)


def _head_digest_write(path: Path, value: str) -> None:
    if not OID_RE.fullmatch(value) or value != value.lower():
        raise DeployerError("deployed head is not normalized")
    _safe_write(path, (value + "\n").encode("ascii"), mode=0o644, replace=True)


def _read_gate(gate_id: str, control: A2ControlPlane) -> GateArtifact:
    try:
        return _read_artifact(gate_id, control)
    except GateError as error:
        raise DeployerError(str(error)) from error


def _derive_id(gate_id: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{32}", gate_id):
        raise DeployerError("gate id is invalid")
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + gate_id


def _validate_preflight(control: A2ControlPlane, artifact: Mapping[str, Any], *, runtime_truth: bool = False) -> tuple[str, str, Path, Path, Path]:
    deploy_root = control.deploy_root
    _validate_no_symlink_components(deploy_root, "deployment root")
    try:
        deploy_metadata = os.lstat(deploy_root)
    except OSError as error:
        raise DeployerError("deployment root is unavailable") from error
    expected_owner = getattr(control, "expected_owner_uid", os.getuid())
    if stat.S_ISLNK(deploy_metadata.st_mode) or not stat.S_ISDIR(deploy_metadata.st_mode) or deploy_metadata.st_uid != expected_owner:
        raise DeployerError("deployment root is unsafe")
    head_path, image_path, baseline_path = _state_paths(control)
    old_head = _read_oid_file(head_path, "deployed head")
    previous_image = _read_image(image_path, "current API image")
    baseline_digest = _read_bounded(baseline_path, "baseline manifest digest", 128).decode("ascii").strip()
    if baseline_digest != _baseline_digest(control):
        raise DeployerError("baseline manifest digest mismatch")
    if old_head != artifact["base_oid"]:
        raise DeployerError("deployed head does not equal gate base")
    base_binding = control.locked_config.get("base_image_digest", getattr(control, "readiness", {}).get("base_image_digest"))
    if getattr(control, "expected_owner_uid", os.getuid()) == 0:
        if not isinstance(base_binding, str) or not IMAGE_RE.fullmatch(base_binding) or previous_image != base_binding:
            raise DeployerError("previous API image does not match fixed base image binding")
    elif base_binding is not None and previous_image != base_binding:
        raise DeployerError("previous API image does not match fixed base image binding")
    if runtime_truth:
        _validate_docker_binding(control)
        container = control.locked_config.get("api_container", "alpha-ficc-api")
        if not isinstance(container, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", container):
            raise DeployerError("API container identity is not fixed")
        code, output, _command = _run_docker(control, ["inspect", "--format={{.Image}}", container], "API image inspect", timeout=60)
        actual = output.decode("ascii", "strict").strip() if code == 0 else ""
        if code != 0 or not IMAGE_RE.fullmatch(actual) or actual != previous_image:
            raise DeployerError("running API image does not match durable state")
    if artifact.get("allowed") is not True:
        raise DeployerError("gate artifact is not approved")
    _compose_path(control)
    if getattr(control, "expected_owner_uid", os.getuid()) == 0:
        if tuple(control.locked_config.get("health_contract", ())) != ("health", "module_import", "data_freshness"):
            raise DeployerError("health contract is incomplete")
    relative, _image_path = _production_mapping(control, artifact)
    production = [item for item in artifact.get("files", []) if item.get("role") == "production"]
    if len(production) != 1:
        raise DeployerError("gate production file is not unique")
    target = control.deploy_root / relative
    _validate_no_symlink_components(target, "production artifact")
    try:
        target_metadata = os.lstat(target)
    except OSError as error:
        raise DeployerError("production artifact is unavailable") from error
    if production[0].get("git_mode") != "100644":
        raise DeployerError("production gate mode must be 100644")
    expected_mode = 0o644
    if stat.S_ISLNK(target_metadata.st_mode) or not stat.S_ISREG(target_metadata.st_mode) or target_metadata.st_nlink != 1 or stat.S_IMODE(target_metadata.st_mode) != expected_mode:
        raise DeployerError("production artifact metadata does not match gate")
    base_blob = str(production[0].get("base_blob_oid", ""))
    if _git_blob_oid(_read_bounded(target, "production artifact"), base_blob) != base_blob:
        raise DeployerError("production artifact does not match gate base blob")
    return old_head, previous_image, head_path, image_path, baseline_path


def _create_bundle(control: A2ControlPlane, artifact: Mapping[str, Any], deployment_id: str, lease: Mapping[str, Any], old_head: str, previous_image: str, deployment_dir: Path) -> dict[str, Any]:
    relative, _ = _production_mapping(control, artifact)
    target = control.deploy_root / relative
    _validate_no_symlink_components(target, "production artifact")
    target_meta = os.lstat(target)
    if stat.S_ISLNK(target_meta.st_mode) or not stat.S_ISREG(target_meta.st_mode) or target_meta.st_nlink != 1:
        raise DeployerError("production artifact metadata is unsafe")
    old_bytes = _read_bounded(target, "old production artifact")
    old_sha = hashlib.sha256(old_bytes).hexdigest()
    old_file = {"path": relative, "sha256": old_sha, "mode": stat.S_IMODE(target_meta.st_mode), "uid": target_meta.st_uid, "gid": target_meta.st_gid}
    new_file = [item for item in artifact["files"] if item["role"] == "production"][0]
    bundle_files = deployment_dir / "bundle" / "files"
    _ensure_directory(bundle_files)
    _copy_fd(target, bundle_files / relative, expected_sha256=old_sha, expected_mode=old_file["mode"])
    source = control.source_repo / relative
    _copy_fd(source, deployment_dir / "candidate-production.tmp", expected_sha256=str(new_file["sha256"]), expected_mode=0o644)
    _safe_write(deployment_dir / "bundle" / "old-head", (old_head + "\n").encode("ascii"), mode=0o600, replace=False)
    _safe_write(deployment_dir / "bundle" / "previous-image", (previous_image + "\n").encode("ascii"), mode=0o600, replace=False)
    compose = _compose_path(control)
    compose_copy = deployment_dir / "bundle" / "compose.base.yml"
    compose_info = _copy_fd(compose, compose_copy, expected_mode=0o644)
    old_override_source = control.deploy_root / "compose.override.generated.yml"
    old_override_copy = deployment_dir / "bundle" / "old-override.yml"
    old_override_present = old_override_source.exists()
    if old_override_present:
        old_override_info = _copy_fd(old_override_source, old_override_copy, expected_mode=0o600)
    else:
        _safe_write(old_override_copy, b"", mode=0o600, replace=False)
        old_override_info = {"sha256": hashlib.sha256(b"").hexdigest()}
    manifest = _bundle_manifest(control, artifact, deployment_id, lease, previous_image, old_head, old_file, new_file, compose, compose_info["sha256"], old_override_info["sha256"], old_override_present)
    _safe_write(deployment_dir / "bundle" / "manifest.json", _canonical_json(manifest), mode=0o600, replace=False)
    _fsync_directory(deployment_dir / "bundle")
    return {"manifest": manifest, "old_file": old_file, "new_file": new_file, "relative": relative}


def _switch_runtime(control: A2ControlPlane, deployment_dir: Path, image_digest: str, *, compose_path: Path | None = None, saved_override: Path | None = None) -> list[str]:
    override: Path | None = saved_override
    if override is None:
        override = deployment_dir / "compose.override.generated.yml"
        payload = f"services:\n  api:\n    image: {image_digest}\n"
        _safe_write(override, payload.encode("utf-8"), mode=0o600, replace=True)
    elif not override.exists():
        raise DeployerError("saved compose override is unavailable")
    compose = compose_path or _compose_path(control)
    _validate_no_symlink_components(compose, "compose input")
    project_directory = control.locked_config.get("compose_project_dir")
    if not isinstance(project_directory, str) or not Path(project_directory).is_absolute():
        project_directory = os.fspath(deployment_dir)
    args = ["compose", "--env-file", "/dev/null", "-f", os.fspath(compose)]
    if override.stat().st_size > 0:
        args.extend(["-f", os.fspath(override)])
    args.extend(["--project-directory", project_directory, "--no-build", "up", "-d", "api"])
    code, _output, command = _run_docker(control, args, "runtime switch", timeout=300)
    if code != 0:
        raise DeployerError("runtime switch failed")
    return command


def _build_image(control: A2ControlPlane, context: Path, deployment_id: str, previous_image: str) -> tuple[str, list[str]]:
    tag = f"alpha-ficc-a2:{deployment_id}"
    args = ["build", "--network=none", "--pull=false", "--file", os.fspath(context / "Dockerfile"), "--tag", tag, os.fspath(context)]
    code, _output, command = _run_docker(control, args, "immutable delta image build", timeout=600)
    if code != 0:
        raise DeployerError("immutable delta image build failed")
    inspect_code, inspect_output, inspect_command = _run_docker(
        control,
        ["image", "inspect", "--format={{.Id}}", tag],
        "built image inspect",
        timeout=60,
    )
    if inspect_code != 0:
        raise DeployerError("built image inspect failed")
    image = inspect_output.decode("ascii", "strict").strip()
    if not IMAGE_RE.fullmatch(image) or "\n" in image:
        raise DeployerError("builder did not return immutable image digest")
    return image, inspect_command


def _restore_bundle(control: A2ControlPlane, deployment_dir: Path, deployment_id: str, manifest: Mapping[str, Any]) -> dict[str, Any]:
    statuses: list[dict[str, Any]] = []
    for item in manifest.get("files", []):
        relative = _validate_relative_path(str(item["path"]))
        source = deployment_dir / "bundle" / "files" / relative
        target = control.deploy_root / relative
        try:
            metadata = os.lstat(source)
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                raise DeployerError("rollback source is unsafe")
            _copy_fd(source, target, expected_sha256=str(item["sha256"]), expected_mode=int(item["mode"]))
            parent_fd = _open_directory_pinned(target.parent, "deployed head parent")
            try:
                os.chown(target.name, int(item["uid"]), int(item["gid"]), dir_fd=parent_fd, follow_symlinks=False)
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
            statuses.append({"path": relative, "status": "restored"})
        except (OSError, DeployerError) as error:
            statuses.append({"path": relative, "status": "failed", "reason": type(error).__name__})
            raise RollbackFailure("rollback artifact restore failed", statuses) from error
    _image_digest_write(control.deploy_root / ".api-image-digest", str(manifest["previous_image_digest"]))
    if _read_image(control.deploy_root / ".api-image-digest", "restored API image") != str(manifest["previous_image_digest"]):
        raise RollbackFailure("rollback image restore verification failed", statuses)
    # The deployed head is the final state marker; write it only after all
    # artifact and image restoration has been durably completed.
    _head_digest_write(control.deploy_root / ".deployed-head", str(manifest["old_head"]))
    if _read_oid_file(control.deploy_root / ".deployed-head", "restored deployed head") != str(manifest["old_head"]):
        raise RollbackFailure("rollback head restore verification failed", statuses)
    old_override_target = control.deploy_root / "compose.override.generated.yml"
    saved_override = deployment_dir / "bundle" / "old-override.yml"
    if manifest.get("old_override_present") is True:
        _copy_fd(saved_override, old_override_target, expected_sha256=str(manifest["old_override_sha256"]), expected_mode=0o600)
    else:
        _validate_no_symlink_components(old_override_target, "old compose override", allow_missing=True)
        try:
            metadata = os.lstat(old_override_target)
        except FileNotFoundError:
            metadata = None
        if metadata is not None:
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                raise RollbackFailure("old compose override is unsafe", statuses)
            parent_fd = _open_directory_pinned(old_override_target.parent, "old compose override parent")
            try:
                os.unlink(old_override_target.name, dir_fd=parent_fd)
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
    return {"files": statuses, "head": str(manifest["old_head"]), "image": str(manifest["previous_image_digest"])}


def rollback(deployment_id: str, control_plane: A2ControlPlane, *, _lock_already_held: bool = False) -> dict[str, Any]:
    """Offline rollback; this branch intentionally never reads source or fetches Git."""

    control = control_plane
    lock_context = contextlib.nullcontext() if _lock_already_held else _exclusive_lock(control)
    with lock_context:
        deployment_dir = control.a2_root / "deployments" / deployment_id
        journal_path = deployment_dir / "journal.jsonl"
        phase = "bundle_validation"
        current_head: str | None = None
        current_image: str | None = None
        health: dict[str, Any] = {"status": "unknown"}
        file_statuses: list[dict[str, Any]] = []
        try:
            manifest, _bundle = _validate_bundle(control, deployment_dir, deployment_id)
            phase = "journal_rolling_back"
            _append_journal(journal_path, deployment_id, "rolling_back", _hmac_key=control.key, reason="manual")
            previous = str(manifest["previous_image_digest"])
            current_image = previous
            phase = "runtime_switching"
            saved_override = deployment_dir / "bundle" / "old-override.yml"
            _switch_runtime(control, deployment_dir, previous, compose_path=deployment_dir / "bundle" / "compose.base.yml", saved_override=saved_override)
            phase = "artifact_restoring"
            restored = _restore_bundle(control, deployment_dir, deployment_id, manifest)
            file_statuses = restored["files"]
            current_head = restored["head"]
            current_image = restored["image"]
            phase = "health_verifying"
            health = _fake_health(control, control.deploy_root, deployment_dir)
            if health.get("status") != "ok":
                raise DeployerError("rollback health verification failed")
            phase = "bundle_consuming"
            consumed = dict(manifest)
            consumed["consumed"] = True
            consumed["manifest_mac"] = _hmac(control.key, {key: value for key, value in consumed.items() if key != "manifest_mac"})
            _safe_write(deployment_dir / "bundle" / "manifest.json", _canonical_json(consumed), mode=0o600, replace=True)
            _append_journal(journal_path, deployment_id, "committed", _hmac_key=control.key, reason="rollback", health=health)
            return _result("rolled_back", "rollback", deployment_id, phase="committed", files=restored["files"], current_head=restored["head"], current_image=previous, health=health, recovery_required=False)
        except (DeployerError, GateError) as error:
            if isinstance(error, RollbackFailure):
                file_statuses = error.files
            try:
                _append_journal(journal_path, deployment_id, "rollback_failed", _hmac_key=control.key, reason=type(error).__name__)
            except Exception:
                pass
            return _result("rollback_failed", "rollback", deployment_id, phase=phase, files=file_statuses, current_head=current_head, current_image=current_image, health=health, recovery_required=True, reason=str(error))


def deploy(gate_id: str, control_plane: A2ControlPlane, mode: str = "apply") -> dict[str, Any]:
    if mode not in {"dry-run", "apply"}:
        raise DeployerError("deployment mode is invalid")
    control = control_plane
    with _exclusive_lock(control):
        artifact = _read_gate(gate_id, control)
        if artifact.get("allowed") is not True:
            raise DeployerError("gate artifact is not approved")
        # Dry-run consumes only already persisted state; it never reads source or calls Git/network/Docker.
        if mode == "dry-run":
            old_head, previous_image, _head, _image, _baseline = _validate_preflight(control, artifact)
            relative, image_path = _production_mapping(control, artifact)
            return _result("planned", "dry-run", "dry-run", base_oid=artifact["base_oid"], candidate_oid=artifact["candidate_oid"], current_head=old_head, previous_image_digest=previous_image, files=[relative], build_context={"production_path": relative, "image_path": image_path, "contains_test": False, "contains_source_clone": False, "contains_production_root": False}, build_network="none", docker_argv=[_docker_command(control), "build", "--network=none"], compose_argv=[_docker_command(control), "compose", "--no-build"], side_effects={"fetch": 0, "network": 0, "docker": 0, "source_writes": 0, "deploy_writes": 0, "a2_root_writes": 0})
        deployment_id = _derive_id(gate_id)
        deployment_dir = control.a2_root / "deployments" / deployment_id
        if deployment_dir.exists():
            raise DeployerError("deployment directory already exists")
        _ensure_directory(deployment_dir)
        journal_path = deployment_dir / "journal.jsonl"
        old_head, previous_image, _head_path, _image_path, _baseline = _validate_preflight(control, artifact, runtime_truth=True)
        lease = _validate_lease(control, deployment_id)
        previous_signals: dict[int, Any] = {}
        publishing_state = {"phase": "pre-publishing"}
        publishing_started = False
        push: Mapping[str, Any] | None = None
        try:
            _append_journal(journal_path, deployment_id, "prepared", _hmac_key=control.key, gate_id=gate_id, base_oid=artifact["base_oid"], candidate_oid=artifact["candidate_oid"])
            bundle = _create_bundle(control, artifact, deployment_id, lease, old_head, previous_image, deployment_dir)
            _append_journal(journal_path, deployment_id, "bundle_ready", _hmac_key=control.key, bundle_digest=hashlib.sha256(_canonical_json(bundle["manifest"])).hexdigest())
            previous_signals = _install_signal_handlers(control, deployment_id, publishing_state=publishing_state)
            context, context_meta = _build_context(control, artifact, deployment_dir, previous_image)
            image_digest, _build_command = _build_image(control, context, deployment_id, previous_image)
            _append_journal(journal_path, deployment_id, "image_built", _hmac_key=control.key, image_digest=image_digest, context=context_meta)
            _append_journal(journal_path, deployment_id, "files_applying", _hmac_key=control.key)
            relative = bundle["relative"]
            candidate_temp = deployment_dir / "candidate-production.tmp"
            _copy_fd(candidate_temp, control.deploy_root / relative, expected_sha256=str(bundle["new_file"]["sha256"]), expected_mode=0o644)
            _append_journal(journal_path, deployment_id, "container_switching", _hmac_key=control.key)
            compose_command = _switch_runtime(control, deployment_dir, image_digest)
            _image_digest_write(control.deploy_root / ".api-image-digest", image_digest)
            health = _fake_health(control, control.deploy_root, deployment_dir)
            _append_journal(journal_path, deployment_id, "verifying", _hmac_key=control.key, compose_argv=compose_command, image_digest=image_digest, health=health)
            if health.get("status") != "ok":
                raise DeployerError("post-deploy health verification failed")
            publishing_state["phase"] = "publishing"
            publishing_started = True
            _append_journal(journal_path, deployment_id, "publishing", _hmac_key=control.key)
            push_runner = getattr(control, "push_runner", None)
            if push_runner is not None:
                _require_test_hook(control, "push_runner")
            if callable(push_runner):
                push = push_runner(artifact["gate_id"], control)
            else:
                from check_maintenance_patch import finalize_non_force_push
                push = finalize_non_force_push(str(artifact["gate_id"]), control, deployment_id=deployment_id, _lock_already_held=True)
            if not isinstance(push, Mapping):
                raise DeployerError("publishing confirmation is invalid")
            if not push.get("pushed"):
                if previous_signals:
                    _restore_signal_handlers(previous_signals)
                    previous_signals = {}
                rolled = _reconcile_publishing(deployment_dir, control)
                rolled["mode"] = "apply"
                rolled["push"] = push
                rolled["phase"] = "publishing"
                return rolled
            _head_digest_write(control.deploy_root / ".deployed-head", artifact["candidate_oid"])
            _append_journal(journal_path, deployment_id, "committed", _hmac_key=control.key, image_digest=image_digest, health=health)
            result = _result("deployed", "apply", deployment_id, phase="committed", base_oid=artifact["base_oid"], candidate_oid=artifact["candidate_oid"], current_head=artifact["candidate_oid"], current_image=image_digest, health=health, push=push, rollback_bundle=os.fspath(deployment_dir / "bundle"), recovery_required=False)
            _restore_signal_handlers(previous_signals)
            return result
        except Exception as error:
            if previous_signals:
                _restore_signal_handlers(previous_signals)
                previous_signals = {}
            if publishing_started:
                reconciled = _reconcile_publishing(deployment_dir, control)
                reconciled["mode"] = "apply"
                reconciled["reason"] = str(error)
                if push is not None:
                    reconciled["push"] = push
                return reconciled
            if (deployment_dir / "bundle" / "manifest.json").exists():
                rolled = rollback(deployment_id, control, _lock_already_held=True)
                rolled["reason"] = str(error)
                return rolled
            try:
                _append_journal(journal_path, deployment_id, "rollback_failed", _hmac_key=control.key, reason=type(error).__name__)
            except Exception:
                pass
            raise


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Alpha-FICC privileged A2 deployer")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("dry-run", "apply"):
        item = sub.add_parser(command)
        item.add_argument("--gate-id", required=True)
    rollback_parser = sub.add_parser("rollback")
    rollback_parser.add_argument("--deployment-id", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        control = load_control_plane(A2_ROOT, expected_owner_uid=os.geteuid())
        if args.command == "apply":
            recover_incomplete(control)
        if args.command == "rollback":
            result = rollback(args.deployment_id, control)
        else:
            result = deploy(args.gate_id, control, args.command)
        payload = json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False)
        if len(payload.encode("utf-8")) > MAX_COMMAND_OUTPUT:
            raise DeployerError("deployment result exceeds size limit")
        print(payload)
        return 0 if result.get("status") in {"planned", "deployed", "rolled_back"} else 1
    except (DeployerError, GateError) as error:
        print(json.dumps({"kind": "alpha-ficc-a2-deployment-v2", "status": "failed", "reason": str(error), "recovery_required": True}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
