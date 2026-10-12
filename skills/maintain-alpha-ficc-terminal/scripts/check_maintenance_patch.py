#!/usr/bin/env python3
"""Canonical A2 Git trust and verifier-generated patch gate.

The gate deliberately has no caller-evidence API.  A privileged launcher loads
an immutable control plane and this module derives the only test path from the
candidate diff, executes the fixed verifier contract, and persists a signed
gate artifact for the deployer.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import datetime as _dt
import fcntl
import hashlib
import hmac
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


POLICY_PATH = Path(__file__).parents[1] / "references/repair-policy.json"
GIT_BIN = "/usr/bin/git"
PYTHON_BIN = "/usr/bin/python3"
MAX_JSON_BYTES = 128 * 1024
MAX_OUTPUT_BYTES = 32 * 1024
MAX_BLOB_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 4 * 1024 * 1024
GIT_TIMEOUT_SECONDS = 30
CANONICAL_REMOTE = "git@github.com:lynch5mo/alpha-ficc.git"
CANONICAL_REF = "main"
A2_ROOT = Path("/var/lib/alpha-ficc-maintainer/a2")
POLICY_KEYS = (
    "a2_allowed_production_globs",
    "a2_allowed_test_globs",
    "forbidden_globs",
    "limits",
    "a2_candidate_gate",
)
_OID_RE = re.compile(r"^[0-9a-f]+$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_JSON_REJECT = object()


def _normalize_stable_alias(path: Path) -> Path:
    """Resolve only the macOS system aliases that openat cannot follow safely."""

    absolute = Path(os.path.abspath(os.fspath(path)))
    for alias in (Path("/var"), Path("/tmp")):
        if absolute != alias and alias not in absolute.parents:
            continue
        try:
            metadata = os.lstat(alias)
            resolved = Path(os.path.realpath(alias))
        except OSError:
            return absolute
        if stat.S_ISLNK(metadata.st_mode) and str(resolved).startswith("/private/"):
            return resolved / absolute.relative_to(alias)
    return absolute


class GateError(RuntimeError):
    """Sanitized fail-closed gate error."""


class GateArtifact(dict):
    """Mapping result with the typed attributes used by privileged callers."""

    @property
    def allowed(self) -> bool:
        return bool(self.get("allowed"))

    @property
    def gate_id(self) -> str | None:
        value = self.get("gate_id")
        return value if isinstance(value, str) else None


class PushResult(dict):
    @property
    def pushed(self) -> bool:
        return bool(self.get("pushed"))


@contextlib.contextmanager
def _exclusive_control_lock(control: A2ControlPlane) -> Any:
    """Use the same privileged A2 lock for gate and push transactions."""

    lock_path = control.a2_root / "locks" / "a2.lock"
    try:
        metadata = os.lstat(lock_path)
        owner = getattr(control, "expected_owner_uid", os.getuid())
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_uid != owner or stat.S_IMODE(metadata.st_mode) != 0o600:
            raise GateError("A2 lock is unsafe")
        descriptor = _open_regular(lock_path, "A2 lock", read_only=False, mode=0o600, create=False)
        opened = os.fstat(descriptor)
        if opened.st_uid != owner or stat.S_IMODE(opened.st_mode) != 0o600 or opened.st_nlink != 1:
            os.close(descriptor)
            raise GateError("A2 lock is unsafe")
    except OSError as error:
        raise GateError("A2 lock is unavailable") from error
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise GateError("another A2 transaction holds the lock") from error
        yield descriptor
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GateError("JSON contains duplicate keys")
        result[key] = value
    return result


def _reject_constants(value: str) -> Any:
    raise GateError("JSON contains a non-finite number")


def _strict_json_bytes(payload: bytes, label: str, maximum: int = MAX_JSON_BYTES) -> Any:
    if len(payload) > maximum:
        raise GateError(f"{label} exceeds size limit")
    try:
        return json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constants,
        )
    except GateError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GateError(f"{label} is not valid strict JSON") from error


def _strict_json_file(
    path: Path,
    label: str,
    maximum: int = MAX_JSON_BYTES,
    *,
    owner_uid: int | None = None,
    expected_mode: int | None = None,
) -> Any:
    descriptor = _open_regular(path, label, read_only=True, maximum=maximum)
    try:
        metadata = os.fstat(descriptor)
        if owner_uid is not None and metadata.st_uid != owner_uid:
            raise GateError(f"{label} owner mismatch")
        if expected_mode is not None and stat.S_IMODE(metadata.st_mode) != expected_mode:
            raise GateError(f"{label} mode mismatch")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            block = os.read(descriptor, min(65536, remaining))
            if not block:
                break
            chunks.append(block)
            remaining -= len(block)
    finally:
        os.close(descriptor)
    return _strict_json_bytes(b"".join(chunks), label, maximum)


def _open_regular(
    path: Path,
    label: str,
    *,
    read_only: bool,
    maximum: int | None = None,
    mode: int = 0o600,
    exclusive: bool = False,
    create: bool = True,
) -> int:
    absolute = _normalize_stable_alias(path)
    if not absolute.is_absolute():
        raise GateError(f"{label} must be absolute")
    current = Path(absolute.anchor)
    try:
        expected_dev = os.lstat(absolute.anchor).st_dev
    except OSError as error:
        raise GateError(f"{label} is unavailable") from error
    try:
        components = absolute.parts[1:]
        for index, component in enumerate(components):
            current = current / component
            try:
                metadata = os.lstat(current)
            except FileNotFoundError:
                if not read_only and index == len(components) - 1:
                    break
                raise
            if stat.S_ISLNK(metadata.st_mode):
                # macOS exposes /var and /tmp as stable system aliases.  The
                # caller-controlled portion below those aliases remains
                # strictly no-follow; production Linux paths do not use this
                # exception.
                resolved = Path(os.path.realpath(current))
                if not (str(current) in {"/var", "/tmp"} and str(resolved).startswith("/private/")):
                    raise GateError(f"{label} contains a symlink")
            if metadata.st_dev != expected_dev:
                raise GateError(f"{label} crosses a filesystem boundary")
    except OSError as error:
        raise GateError(f"{label} is unavailable") from error
    flags = os.O_RDONLY if read_only else os.O_WRONLY
    if not read_only and create:
        flags |= os.O_CREAT
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    if exclusive:
        flags |= os.O_EXCL
    parent_fd: int | None = None
    current_fd: int | None = None
    try:
        parent_fd = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
        current_fd = parent_fd
        for component in components[:-1]:
            next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), dir_fd=current_fd)
            if os.fstat(next_fd).st_dev != expected_dev:
                os.close(next_fd)
                raise GateError(f"{label} crosses a filesystem boundary")
            if current_fd != parent_fd:
                os.close(current_fd)
            current_fd = next_fd
        descriptor = os.open(components[-1], flags, mode, dir_fd=current_fd)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            os.close(descriptor)
            raise GateError(f"{label} must be a single-link regular file")
        if maximum is not None and metadata.st_size > maximum:
            os.close(descriptor)
            raise GateError(f"{label} exceeds size limit")
        return descriptor
    except GateError:
        raise
    except OSError as error:
        raise GateError(f"{label} is unavailable") from error
    finally:
        if parent_fd is not None:
            try:
                if current_fd is not None and current_fd != parent_fd:
                    os.close(current_fd)
            except OSError:
                pass
            os.close(parent_fd)


def _hmac(key: bytes, value: Mapping[str, Any]) -> str:
    return hmac.new(key, _canonical_json(value), hashlib.sha256).hexdigest()


def _unsigned(value: Mapping[str, Any], *fields: str) -> dict[str, Any]:
    result = dict(value)
    for field_name in fields:
        result.pop(field_name, None)
    return result


def _artifact_digest(artifact: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(_unsigned(artifact, "artifact_digest", "artifact_mac", "gate_id"))).hexdigest()


def _valid_full_oid(value: Any, object_format: str) -> bool:
    if not isinstance(value, str) or value != value.lower() or not _OID_RE.fullmatch(value):
        return False
    expected = 40 if object_format == "sha1" else 64 if object_format == "sha256" else 0
    return expected > 0 and len(value) == expected


def _safe_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    env = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "HOME": "/nonexistent",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_ASKPASS": "/usr/bin/false",
        "SSH_ASKPASS": "/usr/bin/false",
        "GIT_SSH_COMMAND": "/usr/bin/ssh -oBatchMode=yes -oStrictHostKeyChecking=yes",
    }
    if extra:
        for key, value in extra.items():
            if key not in {"PATH", "LANG", "LC_ALL", "HOME"}:
                env[key] = value
    return env


def _kill_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _run(
    command: Sequence[str],
    *,
    env: Mapping[str, str],
    operation: str,
    timeout: float = GIT_TIMEOUT_SECONDS,
    maximum: int = MAX_OUTPUT_BYTES,
    cwd: Path | None = None,
) -> tuple[int, bytes]:
    if not command or any("\x00" in str(part) for part in command):
        raise GateError(f"{operation} command is invalid")
    try:
        process = subprocess.Popen(
            list(command),
            cwd=os.fspath(cwd) if cwd else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=dict(env),
            start_new_session=True,
        )
    except OSError as error:
        raise GateError(f"{operation} unavailable") from error
    assert process.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _kill_group(process)
                raise GateError(f"{operation} timed out")
            events = selector.select(min(remaining, 0.1))
            if not events and process.poll() is not None:
                break
            for _key, _mask in events:
                block = os.read(process.stdout.fileno(), min(65536, maximum + 1 - total))
                if block:
                    chunks.append(block)
                    total += len(block)
                if total > maximum:
                    _kill_group(process)
                    raise GateError(f"{operation} exceeded output limit")
            if process.poll() is not None:
                # drain until EOF without allowing output growth
                tail = os.read(process.stdout.fileno(), min(4096, maximum + 1 - total))
                if tail:
                    chunks.append(tail)
                    total += len(tail)
                    if total > maximum:
                        _kill_group(process)
                        raise GateError(f"{operation} exceeded output limit")
                else:
                    break
        return_code = process.wait(timeout=max(0.1, deadline - time.monotonic()))
    except (subprocess.TimeoutExpired, OSError) as error:
        _kill_group(process)
        raise GateError(f"{operation} failed") from error
    finally:
        selector.close()
        process.stdout.close()
        if process.poll() is None:
            _kill_group(process)
            process.wait()
    return return_code, b"".join(chunks)


def _run_git(repo: Path, args: Sequence[str], operation: str, *, timeout: float = GIT_TIMEOUT_SECONDS, known_hosts: Path | None = None) -> bytes:
    command = [GIT_BIN, "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "credential.helper=", "-C", os.fspath(repo), *args]
    env = _safe_env()
    if known_hosts is not None:
        env["GIT_SSH_COMMAND"] = f"/usr/bin/ssh -oBatchMode=yes -oStrictHostKeyChecking=yes -oUserKnownHostsFile={os.fspath(known_hosts)}"
    code, output = _run(command, env=env, operation=operation, timeout=timeout)
    if code != 0:
        raise GateError(f"{operation} failed")
    return output


def _decode(payload: bytes, label: str) -> str:
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise GateError(f"{label} returned invalid UTF-8") from error


def _canonical_path(path: Any) -> bool:
    if not isinstance(path, str) or not path or "\\" in path or "\x00" in path or path.startswith("/"):
        return False
    return all(segment not in {"", ".", ".."} for segment in path.split("/")) and all(ord(c) >= 32 for c in path)


def _segment_match(pattern: str, path: str) -> bool:
    p = pattern.split("/")
    q = path.split("/")

    def walk(i: int, j: int) -> bool:
        if i == len(p):
            return j == len(q)
        if p[i] == "**":
            return walk(i + 1, j) or (j < len(q) and walk(i, j + 1))
        if j >= len(q):
            return False
        regex = "".join(".*" if c == "*" else re.escape(c) for c in p[i])
        return re.fullmatch(regex, q[j]) is not None and walk(i + 1, j + 1)

    return walk(0, 0)


def _load_policy() -> dict[str, Any]:
    value = _strict_json_file(POLICY_PATH, "A2 policy", 256 * 1024)
    if not isinstance(value, dict):
        raise GateError("A2 policy must be an object")
    for key in POLICY_KEYS:
        if key not in value:
            raise GateError("A2 policy is incomplete")
    _verify_policy_vectors(value)
    return value


def _facts_decision(facts: Mapping[str, Any], policy: Mapping[str, Any]) -> tuple[str, str]:
    status = facts.get("diff_status")
    path = facts.get("path")
    if status != "M":
        return "reject", "unsupported_diff_status"
    if not _canonical_path(path):
        return "reject", "non_canonical_path"
    if facts.get("base_tracked", True) is not True:
        return "reject", "not_tracked_at_base"
    if facts.get("git_mode", "100644") == "160000":
        return "reject", "submodule"
    if facts.get("git_object_type", "blob") != "blob":
        return "reject", "not_tracked_blob"
    git_mode = facts.get("git_mode", "100644")
    if git_mode not in {"100644", "100755"}:
        return "reject", "unsupported_git_mode"
    if facts.get("symlink_component"):
        return "reject", "symlink_component"
    if facts.get("symlink_leaf") or facts.get("lstat_type", "regular_file") != "regular_file" or facts.get("hardlink_count", 1) != 1:
        return "reject", "not_regular_single_link_file"
    if facts.get("binary"):
        return "reject", "binary"
    if any(_segment_match(pattern, path) for pattern in policy["forbidden_globs"]):
        return "reject", "forbidden_match"
    if any(_segment_match(pattern, path) for pattern in policy["a2_allowed_production_globs"]):
        if git_mode != "100644":
            return "reject", "production_mode_must_be_100644"
        return "allow_production", "allowed"
    if any(_segment_match(pattern, path) for pattern in policy["a2_allowed_test_globs"]):
        return "allow_test", "allowed"
    return "reject", "allowlist_miss"


def _verify_policy_vectors(policy: Mapping[str, Any]) -> None:
    gate = policy["a2_candidate_gate"]
    for vector in gate.get("negative_test_vectors", []):
        decision, reason = _facts_decision(vector["input"], policy)
        if (decision, reason) != (vector["decision"], vector["reason"]):
            raise GateError("A2 negative policy vector failed")
    for vector in gate.get("positive_test_vectors", []):
        decision, _ = _facts_decision(vector["input"], policy)
        if decision != vector["decision"]:
            raise GateError("A2 positive policy vector failed")


class A2ControlPlane:
    def __init__(
        self,
        a2_root: Path,
        locked_config: dict[str, Any],
        readiness: dict[str, Any],
        baseline_manifest: dict[str, Any],
        key: bytes,
        source_repo: Path,
        deploy_root: Path,
        canonical_remote: str = CANONICAL_REMOTE,
        canonical_ref: str = CANONICAL_REF,
        known_hosts: Path | None = None,
        verifier_runner: Callable[[Path, Path, str, str, "A2ControlPlane"], Mapping[str, Any]] | None = None,
        verifier_executor: Callable[[Sequence[str], Mapping[str, str], Path, str], int] | None = None,
        expected_owner_uid: int = 0,
        policy_fingerprint: str = "",
    ) -> None:
        self.a2_root = a2_root
        self.locked_config = locked_config
        self.readiness = readiness
        self.baseline_manifest = baseline_manifest
        self.key = key
        self.source_repo = source_repo
        self.deploy_root = deploy_root
        self.canonical_remote = canonical_remote
        self.canonical_ref = canonical_ref
        self.known_hosts = known_hosts
        self.verifier_runner = verifier_runner
        self.verifier_executor = verifier_executor
        self.expected_owner_uid = expected_owner_uid
        self.policy_fingerprint = policy_fingerprint

    @property
    def verifier_image(self) -> str:
        return str(self.locked_config.get("verifier_image_digest", self.readiness.get("verifier_image_digest", "")))

    @property
    def gate_dir(self) -> Path:
        return self.a2_root / "gates"


def _safe_root(path: Path, label: str, owner_uid: int, *, create: bool = False) -> Path:
    absolute = _normalize_stable_alias(path)
    if not absolute.is_absolute():
        raise GateError(f"{label} must be absolute")
    current = Path(absolute.anchor)
    try:
        for component in absolute.parts[1:]:
            current = current / component
            metadata = os.lstat(current)
            if stat.S_ISLNK(metadata.st_mode):
                resolved = Path(os.path.realpath(current))
                if not (str(current) in {"/var", "/tmp"} and str(resolved).startswith("/private/")):
                    raise GateError(f"{label} contains a symlink")
    except FileNotFoundError:
        if not create:
            raise GateError(f"{label} is unavailable")
    except OSError as error:
        raise GateError(f"{label} is unavailable") from error
    if create:
        absolute.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        metadata = os.lstat(absolute)
    except OSError as error:
        raise GateError(f"{label} is unavailable") from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise GateError(f"{label} must be a regular directory")
    if metadata.st_uid != owner_uid:
        raise GateError(f"{label} owner mismatch")
    return absolute


def _validate_file_owner(path: Path, label: str, owner_uid: int, mode: int | None = None) -> None:
    metadata = os.lstat(path)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise GateError(f"{label} must be a single-link regular file")
    if metadata.st_uid != owner_uid:
        raise GateError(f"{label} owner mismatch")
    if mode is not None and stat.S_IMODE(metadata.st_mode) != mode:
        raise GateError(f"{label} mode mismatch")


def _reject_production_test_hook_config(
    locked: Mapping[str, Any],
    expected_owner_uid: int,
    readiness: Mapping[str, Any] | None = None,
) -> None:
    if expected_owner_uid == 0 and (locked.get("test_only") is True or (readiness is not None and readiness.get("test_only") is True)):
        raise GateError("production A2 control must not enable test_only")


def load_control_plane(a2_root: Path, expected_owner_uid: int = 0) -> A2ControlPlane:
    """Load only root-owned, installer-provisioned A2 state."""

    root = _safe_root(Path(a2_root), "A2 root", expected_owner_uid)
    readiness_dir = _safe_root(root / "readiness", owner_uid=expected_owner_uid, label="readiness")
    keys_dir = _safe_root(root / "keys", owner_uid=expected_owner_uid, label="keys")
    for name in ("gates", "deployments", "locks"):
        _safe_root(root / name, owner_uid=expected_owner_uid, label=name, create=expected_owner_uid != 0)
    locked = _strict_json_file(readiness_dir / "locked-a2-config.json", "locked A2 config", owner_uid=expected_owner_uid, expected_mode=0o600)
    readiness = _strict_json_file(readiness_dir / "a2.json", "A2 readiness", owner_uid=expected_owner_uid, expected_mode=0o600)
    baseline = _strict_json_file(readiness_dir / "baseline-manifest.json", "baseline manifest", owner_uid=expected_owner_uid, expected_mode=0o600)
    if not isinstance(locked, dict) or not isinstance(readiness, dict) or not isinstance(baseline, dict):
        raise GateError("A2 control-plane JSON must be objects")
    _validate_file_owner(readiness_dir / "locked-a2-config.json", "locked A2 config", expected_owner_uid, 0o600)
    _validate_file_owner(readiness_dir / "a2.json", "A2 readiness", expected_owner_uid, 0o600)
    _validate_file_owner(readiness_dir / "baseline-manifest.json", "baseline manifest", expected_owner_uid, 0o600)
    key_fd_value = os.environ.get("ALPHA_FICC_A2_KEY_FD")
    if expected_owner_uid == 0 and not key_fd_value:
        raise GateError("production A2 key must be supplied through an inherited FD")
    key_path = keys_dir / "bundle-hmac.key"
    if key_fd_value:
        try:
            inherited_descriptor = int(key_fd_value)
            metadata = os.fstat(inherited_descriptor)
            if metadata.st_uid != expected_owner_uid or stat.S_IMODE(metadata.st_mode) != 0o600 or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise GateError("inherited A2 key FD is unsafe")
            descriptor = os.dup(inherited_descriptor)
        except (ValueError, OSError) as error:
            raise GateError("inherited A2 key FD is invalid") from error
    else:
        _validate_file_owner(key_path, "bundle HMAC key", expected_owner_uid, 0o600)
        descriptor = _open_regular(key_path, "bundle HMAC key", read_only=True, maximum=4096)
    try:
        key = os.read(descriptor, 4097)
    finally:
        os.close(descriptor)
    if not 16 <= len(key) <= 4096:
        raise GateError("bundle HMAC key length is invalid")
    canonical_remote = str(locked.get("canonical_remote", readiness.get("canonical_remote", "")))
    canonical_ref = str(locked.get("canonical_ref", readiness.get("canonical_ref", CANONICAL_REF)))
    _reject_production_test_hook_config(locked, expected_owner_uid, readiness)
    test_mode = expected_owner_uid != 0
    if canonical_remote != CANONICAL_REMOTE and not test_mode:
        raise GateError("canonical remote is not locked")
    if canonical_ref != CANONICAL_REF:
        raise GateError("canonical ref is not locked")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", str(locked.get("verifier_image_digest", ""))):
        raise GateError("verifier image digest is not immutable")
    known_hosts_value = locked.get("ssh_known_hosts")
    known_hosts: Path | None = None
    if known_hosts_value is not None:
        if not isinstance(known_hosts_value, str) or not Path(known_hosts_value).is_absolute() or any(char in known_hosts_value for char in "\x00\r\n \t"):
            raise GateError("SSH known-hosts path is not fixed")
        known_hosts = Path(known_hosts_value)
        try:
            metadata = os.lstat(known_hosts)
        except OSError as error:
            raise GateError("SSH known-hosts file is unavailable") from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_uid != expected_owner_uid or stat.S_IMODE(metadata.st_mode) not in {0o600, 0o644}:
            raise GateError("SSH known-hosts file is unsafe")
    elif not test_mode:
        raise GateError("SSH known-hosts path is not locked")
    if readiness.get("enabled") is not True:
        raise GateError("A2 readiness is not enabled")
    expires = readiness.get("expires_at")
    if not isinstance(expires, str):
        raise GateError("A2 readiness expiry is missing")
    try:
        if _dt.datetime.fromisoformat(expires.replace("Z", "+00:00")) <= _dt.datetime.now(_dt.timezone.utc):
            raise GateError("A2 readiness has expired")
    except ValueError as error:
        raise GateError("A2 readiness expiry is invalid") from error
    fingerprint = hashlib.sha256(_canonical_json({key: locked.get(key) for key in ("canonical_remote", "canonical_ref", "verifier_image_digest", "docker_context", "policy_fingerprint")})).hexdigest()
    configured_control_fingerprint = str(locked.get("control_plane_fingerprint", ""))
    if not test_mode:
        if not re.fullmatch(r"[0-9a-f]{64}", configured_control_fingerprint) or configured_control_fingerprint != fingerprint:
            raise GateError("A2 control-plane fingerprint mismatch")
        if readiness.get("control_plane_fingerprint") != fingerprint:
            raise GateError("A2 readiness control-plane fingerprint mismatch")
    configured_fingerprint = str(locked.get("policy_fingerprint", ""))
    policy = _load_policy()
    actual_policy = hashlib.sha256(_canonical_json({key: policy[key] for key in POLICY_KEYS})).hexdigest()
    if configured_fingerprint and configured_fingerprint != actual_policy:
        raise GateError("A2 policy fingerprint mismatch")
    baseline_fingerprint = hashlib.sha256(_canonical_json(baseline)).hexdigest()
    bindings = {
        "canonical_remote": canonical_remote,
        "canonical_protocol": "ssh",
        "canonical_ref": canonical_ref,
        "verifier_image_digest": locked.get("verifier_image_digest"),
        "docker_bin": locked.get("docker_bin"),
        "docker_context": locked.get("docker_context"),
        "policy_fingerprint": actual_policy,
        "baseline_manifest_digest": baseline_fingerprint,
        "health_contract": locked.get("health_contract"),
        "control_plane_fingerprint": fingerprint,
    }
    for field_name, expected in bindings.items():
        if field_name in readiness and expected is not None and readiness.get(field_name) != expected:
            raise GateError(f"A2 readiness binding mismatch: {field_name}")
    for field_name in ("verifier_identity", "verifier_version", "argv_contract_version", "base_image_digest", "docker_host", "health_contract", "control_plane_fingerprint"):
        if field_name in readiness:
            if field_name not in locked or readiness.get(field_name) != locked.get(field_name):
                raise GateError(f"A2 readiness binding mismatch: {field_name}")
    if not test_mode:
        docker_context = locked.get("docker_context")
        docker_host = locked.get("docker_host")
        if not isinstance(docker_context, str) or not docker_context or any(char.isspace() for char in docker_context):
            raise GateError("Docker context binding is not locked")
        if not isinstance(docker_host, str) or not re.fullmatch(r"(?:unix|npipe|tcp)://[^\s]+", docker_host):
            raise GateError("Docker host binding is not locked")
        required_readiness = (
            "canonical_remote",
            "canonical_protocol",
            "canonical_ref",
            "verifier_image_digest",
            "docker_bin",
            "docker_context",
            "policy_fingerprint",
            "baseline_manifest_digest",
            "verifier_identity",
            "verifier_version",
            "base_image_digest",
            "argv_contract_version",
            "docker_host",
            "health_contract",
        )
        if any(field_name not in readiness for field_name in required_readiness):
            raise GateError("A2 readiness bindings are incomplete")
    source_repo = Path(str(locked.get("source_repo", "")))
    deploy_root = Path(str(locked.get("deploy_root", "")))
    if not source_repo.is_absolute() or not deploy_root.is_absolute():
        raise GateError("source/deploy root must be absolute")
    return A2ControlPlane(
        root,
        locked,
        readiness,
        baseline,
        key,
        source_repo,
        deploy_root,
        canonical_remote,
        canonical_ref,
        known_hosts=known_hosts,
        expected_owner_uid=expected_owner_uid,
        policy_fingerprint=actual_policy,
    )


def _git_dir(repo: Path) -> Path:
    metadata = os.lstat(repo / ".git")
    if stat.S_ISLNK(metadata.st_mode):
        raise GateError(".git must not be a symlink")
    if stat.S_ISDIR(metadata.st_mode):
        return repo / ".git"
    if stat.S_ISREG(metadata.st_mode):
        raise GateError("linked worktree metadata is not trusted")
    raise GateError("source clone has invalid Git metadata")


def _check_git_metadata(repo: Path, *, known_hosts: Path | None = None) -> None:
    git_dir = _git_dir(repo)
    forbidden = (
        git_dir / "refs/replace",
        git_dir / "info/grafts",
        git_dir / "objects/info/alternates",
        git_dir / "commondir",
        git_dir / "shallow",
    )
    for path in forbidden:
        if path.exists() or path.is_symlink():
            raise GateError("source clone contains unsafe Git metadata")
    # Any replace ref, including an empty directory, is a rejection.
    replace_root = git_dir / "refs/replace"
    if replace_root.exists() and any(replace_root.rglob("*")):
        raise GateError("source clone contains replace refs")
    packed_replace = _run_git(repo, ("for-each-ref", "--format=%(refname)", "refs/replace"), "Git replace refs", known_hosts=known_hosts)
    if packed_replace.strip():
        raise GateError("source clone contains packed replace refs")
    config = _run_git(repo, ("config", "--local", "--null", "--list"), "Git local config", known_hosts=known_hosts)
    values: dict[str, str] = {}
    tokens = config.split(b"\0")
    for token in tokens:
        if not token:
            continue
        if b"\n" not in token:
            raise GateError("Git local config output is malformed")
        key, value = token.split(b"\n", 1)
        values[_decode(key, "Git config")] = _decode(value, "Git config")
    allowed_keys = {
        "core.repositoryformatversion",
        "core.filemode",
        "core.bare",
        "core.logallrefupdates",
        "core.ignorecase",
        "core.precomposeunicode",
        "user.email",
        "user.name",
        "branch.main.remote",
        "branch.main.merge",
        "remote.origin.url",
        "remote.origin.fetch",
    }
    for key, value in values.items():
        if key not in allowed_keys:
            raise GateError("unexpected local Git config")
        if key == "remote.origin.url" and (value.startswith("ext::") or value.startswith("helper::") or value.startswith("file://")):
            raise GateError("remote helper or local remote is forbidden")
    for path in (git_dir / "objects", git_dir / "refs", git_dir / "HEAD"):
        try:
            metadata = os.lstat(path)
            if stat.S_ISLNK(metadata.st_mode):
                raise GateError("Git metadata path is a symlink")
        except OSError as error:
            raise GateError("Git metadata is unavailable") from error


def _remote_url(repo: Path, *, known_hosts: Path | None = None) -> str:
    return _decode(_run_git(repo, ("config", "--get", "remote.origin.url"), "origin URL", known_hosts=known_hosts), "origin URL").strip()


def _check_fixed_ref_config(repo: Path, *, known_hosts: Path | None = None) -> None:
    fetch = _decode(_run_git(repo, ("config", "--get-all", "remote.origin.fetch"), "origin refspec", known_hosts=known_hosts), "origin refspec").strip().splitlines()
    if fetch != ["+refs/heads/*:refs/remotes/origin/*"]:
        raise GateError("unexpected origin refspec")
    branch_remote = _decode(_run_git(repo, ("config", "--get", "branch.main.remote"), "main branch remote", known_hosts=known_hosts), "main branch remote").strip()
    branch_merge = _decode(_run_git(repo, ("config", "--get", "branch.main.merge"), "main branch ref", known_hosts=known_hosts), "main branch ref").strip()
    if branch_remote != "origin" or branch_merge != "refs/heads/main":
        raise GateError("main branch config is not fixed")


def _resolve_oid(repo: Path, value: str, label: str, object_format: str, *, known_hosts: Path | None = None) -> str:
    if not _valid_full_oid(value, object_format):
        raise GateError(f"{label} must be a lowercase full OID")
    resolved = _decode(_run_git(repo, ("rev-parse", "--verify", f"{value}^{{commit}}"), label, known_hosts=known_hosts), label).strip()
    if resolved != value or not _valid_full_oid(resolved, object_format):
        raise GateError(f"{label} is not a canonical full OID")
    return resolved


def _tree_entry(repo: Path, commit: str, path: str, *, known_hosts: Path | None = None) -> tuple[str, str, str]:
    payload = _run_git(repo, ("ls-tree", "-z", commit, "--", f":(literal){path}"), "Git tree lookup", known_hosts=known_hosts)
    records = [record for record in payload.split(b"\0") if record]
    if len(records) != 1 or b"\t" not in records[0]:
        raise GateError("Git tree entry is missing or ambiguous")
    metadata, encoded = records[0].split(b"\t", 1)
    fields = metadata.split(b" ")
    decoded_path = _decode(encoded, "Git tree path")
    if len(fields) != 3 or decoded_path != path:
        raise GateError("Git tree entry is malformed")
    return tuple(_decode(field, "Git tree entry") for field in fields)  # type: ignore[return-value]


def _parse_name_status(payload: bytes) -> list[tuple[str, str]]:
    tokens = payload.split(b"\0")
    if tokens and tokens[-1] == b"":
        tokens.pop()
    records: list[tuple[str, str]] = []
    index = 0
    while index < len(tokens):
        status = _decode(tokens[index], "Git diff status")
        index += 1
        count = 2 if status.startswith(("R", "C")) else 1
        if index + count > len(tokens):
            raise GateError("Git diff status output is malformed")
        paths = [_decode(token, "Git diff path") for token in tokens[index:index + count]]
        index += count
        records.append((status, paths[0]))
    return records


def _numstat(repo: Path, base: str, candidate: str, path: str, *, known_hosts: Path | None = None) -> tuple[int, bool]:
    payload = _run_git(repo, ("diff", "--no-ext-diff", "--numstat", "-z", base, candidate, "--", f":(literal){path}"), "Git numstat", known_hosts=known_hosts)
    records = [record for record in payload.split(b"\0") if record]
    if len(records) != 1:
        raise GateError("Git numstat output is malformed")
    fields = records[0].split(b"\t", 2)
    if len(fields) != 3 or _decode(fields[2], "Git numstat") != path:
        raise GateError("Git numstat output is malformed")
    if b"-" in fields[:2]:
        return 0, True
    try:
        return int(fields[0]) + int(fields[1]), False
    except ValueError as error:
        raise GateError("Git numstat output is malformed") from error


def _inspect_worktree(repo: Path, path: str, object_format: str, expected_mode: str, maximum: int) -> tuple[str, str, int]:
    if not _canonical_path(path):
        raise GateError("candidate path is not canonical")
    segments = path.split("/")
    root_fd = os.open(_normalize_stable_alias(repo), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    directory_fd = root_fd
    try:
        for component in segments[:-1]:
            next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
            if directory_fd != root_fd:
                os.close(directory_fd)
            directory_fd = next_fd
        fd = os.open(segments[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        try:
            before = os.fstat(fd)
            required_mode = 0o755 if expected_mode == "100755" else 0o644
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or stat.S_IMODE(before.st_mode) != required_mode:
                raise GateError("candidate file metadata does not match Git mode")
            if before.st_size > maximum:
                raise GateError("candidate blob exceeds byte limit")
            sha256 = hashlib.sha256()
            git_hash = hashlib.new(object_format)
            git_hash.update(f"blob {before.st_size}\0".encode("ascii"))
            total = 0
            while True:
                block = os.read(fd, min(65536, maximum + 1 - total))
                if not block:
                    break
                total += len(block)
                if total > maximum:
                    raise GateError("candidate blob exceeds byte limit")
                sha256.update(block)
                git_hash.update(block)
            after = os.fstat(fd)
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_nlink) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_nlink):
                raise GateError("candidate file changed during inspection")
            return sha256.hexdigest(), git_hash.hexdigest(), total
        finally:
            os.close(fd)
    except OSError as error:
        raise GateError("candidate path is unsafe") from error
    finally:
        if directory_fd != root_fd:
            os.close(directory_fd)
        os.close(root_fd)


def _junit_summary(xml_payload: Any, label: str) -> dict[str, int]:
    if isinstance(xml_payload, str):
        raw = xml_payload.encode("utf-8")
    elif isinstance(xml_payload, bytes):
        raw = xml_payload
    else:
        raise GateError(f"{label} JUnit is missing")
    if len(raw) > MAX_OUTPUT_BYTES:
        raise GateError(f"{label} JUnit exceeds size limit")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise GateError(f"{label} JUnit is malformed") from error
    try:
        tests = int(root.attrib.get("tests", "0"))
        failures = int(root.attrib.get("failures", "0"))
        errors = int(root.attrib.get("errors", "0"))
    except ValueError as error:
        raise GateError(f"{label} JUnit counts are invalid") from error
    if tests <= 0 or failures < 0 or errors < 0 or failures + errors > tests:
        raise GateError(f"{label} JUnit counts are invalid")
    return {"tests": tests, "failures": failures, "errors": errors}


def _fixed_test_argv(test_path: str, junit_path: str) -> list[str]:
    return [PYTHON_BIN, "-I", "-m", "pytest", "-q", test_path, f"--junitxml={junit_path}"]


def _verifier_contract(control: A2ControlPlane) -> dict[str, Any]:
    config = control.locked_config.get("verifier", {})
    if not isinstance(config, Mapping):
        config = {}
    if config.get("command") is not None:
        raise GateError("arbitrary verifier.command is forbidden")
    contract = {
        "network": config.get("network", "none"),
        "rootfs": config.get("rootfs", "read-only"),
        "uid": config.get("uid", 65532),
        "cap_drop": config.get("cap_drop", ["ALL"]),
        "no_new_privileges": config.get("no_new_privileges", True),
        "sockets": config.get("sockets", False),
        "secrets": config.get("secrets", False),
        "cpus": config.get("cpus", "1"),
        "memory": config.get("memory", "512m"),
        "pids_limit": config.get("pids_limit", 128),
        "timeout_seconds": config.get("timeout_seconds", 300),
        "output_bytes": config.get("output_bytes", MAX_OUTPUT_BYTES),
        "identity": config.get("identity", control.readiness.get("verifier_identity", "locked-verifier")),
        "version": config.get("version", control.readiness.get("verifier_version", "locked-verifier-v1")),
    }
    if (
        contract["network"] != "none"
        or contract["rootfs"] != "read-only"
        or not isinstance(contract["uid"], int)
        or contract["uid"] <= 0
        or contract["cap_drop"] != ["ALL"]
        or contract["no_new_privileges"] is not True
        or contract["sockets"] is not False
        or contract["secrets"] is not False
        or not isinstance(contract["identity"], str)
        or not contract["identity"]
        or not isinstance(contract["version"], str)
        or not contract["version"]
    ):
        raise GateError("verifier sandbox binding mismatch")
    if control.readiness.get("verifier_identity") is not None and contract["identity"] != control.readiness.get("verifier_identity"):
        raise GateError("verifier identity readiness mismatch")
    if control.readiness.get("verifier_version") is not None and contract["version"] != control.readiness.get("verifier_version"):
        raise GateError("verifier version readiness mismatch")
    docker_bin = control.locked_config.get("docker_bin", "/usr/bin/docker")
    if not isinstance(docker_bin, str) or not docker_bin.startswith("/"):
        raise GateError("verifier Docker executable is not fixed")
    if getattr(control, "expected_owner_uid", os.getuid()) == 0:
        try:
            metadata = os.lstat(docker_bin)
        except OSError as error:
            raise GateError("verifier Docker executable is unavailable") from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) & 0o111 == 0:
            raise GateError("verifier Docker executable is unsafe")
    return contract


def _require_test_only_hook(control: A2ControlPlane, hook_name: str) -> None:
    if getattr(control, hook_name, None) is not None and control.locked_config.get("test_only") is not True:
        raise GateError(f"{hook_name} is permitted only for test-only control")


def _verifier_argv(control: A2ControlPlane, tree: Path, artifact_dir: Path, test_path: str, junit_path: str) -> list[str]:
    contract = _verifier_contract(control)
    docker = control.locked_config.get("docker_bin", "/usr/bin/docker")
    if not isinstance(docker, str) or not docker.startswith("/"):
        raise GateError("verifier Docker executable is not fixed")
    return [
        docker,
        "run",
        "--rm",
        "--network=none",
        "--read-only",
        "--user",
        str(contract["uid"]),
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--cpus",
        str(contract["cpus"]),
        "--memory",
        str(contract["memory"]),
        "--pids-limit",
        str(contract["pids_limit"]),
        "--mount",
        f"type=bind,src={os.fspath(tree)},dst=/workspace,readonly",
        "--mount",
        f"type=bind,src={os.fspath(artifact_dir)},dst=/artifacts",
        control.verifier_image,
        *_fixed_test_argv(test_path, junit_path),
    ]


def _run_verifier_phase(control: A2ControlPlane, tree: Path, test_path: str, phase: str) -> tuple[dict[str, int], list[str], str]:
    _require_test_only_hook(control, "verifier_executor")
    if control.verifier_runner is not None:
        raise GateError("self-reported verifier evidence is forbidden")
    contract = _verifier_contract(control)
    with tempfile.TemporaryDirectory(prefix="alpha-ficc-verifier-") as temp:
        result_dir = Path(temp)
        junit_path = f"/artifacts/{phase}.xml"
        argv = _verifier_argv(control, tree, result_dir, test_path, junit_path)
        env = _safe_env({"COMPOSE_DISABLE_ENV_FILE": "1"})
        executor = getattr(control, "verifier_executor", None)
        if executor is not None:
            if not callable(executor):
                raise GateError("verifier executor is invalid")
            try:
                code = executor(argv, env, result_dir, phase)
            except Exception as error:
                raise GateError("verifier executor failed") from error
            output = b""
        else:
            code, output = _run(argv, env=env, operation=f"immutable verifier {phase}", timeout=float(contract["timeout_seconds"]), maximum=int(contract["output_bytes"]))
        if code != 0:
            raise GateError("verifier runner/infrastructure error")
        artifact = result_dir / f"{phase}.xml"
        payload = _read_bounded_verifier(artifact, f"{phase} JUnit")
        summary = _junit_summary(payload, phase.upper())
        return summary, argv, hashlib.sha256(output).hexdigest()


def _read_bounded_verifier(path: Path, label: str) -> bytes:
    try:
        metadata = os.lstat(path)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_size > MAX_OUTPUT_BYTES:
            raise GateError(f"{label} artifact is unsafe")
        return path.read_bytes()
    except OSError as error:
        raise GateError(f"{label} artifact is missing") from error


def _materialize_tree(repo: Path, commit: str, *, overlay_test: str | None = None, test_path: str | None = None, overlay_commit: str | None = None, overlay_blob_oid: str | None = None, object_format: str = "sha1") -> Path:
    directory = Path(tempfile.mkdtemp(prefix="alpha-ficc-tree-"))
    # Use git archive through a bounded subprocess directly into tar extraction.
    process = subprocess.Popen([GIT_BIN, "-C", os.fspath(repo), "archive", "--format=tar", commit], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_safe_env(), start_new_session=True)
    assert process.stdout is not None
    import tarfile
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|*") as archive:
            archive.extractall(directory, filter="data" if sys.version_info >= (3, 12) else None)
        if process.wait(timeout=60) != 0:
            raise GateError("Git archive failed")
    except (OSError, tarfile.TarError, subprocess.TimeoutExpired) as error:
        _kill_group(process)
        raise GateError("Git archive extraction failed") from error
    if overlay_test and test_path:
        destination = directory / test_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not overlay_commit:
            raise GateError("candidate test overlay commit is missing")
        code, payload = _run(
            [GIT_BIN, "-C", os.fspath(repo), "cat-file", "blob", f"{overlay_commit}:{test_path}"],
            env=_safe_env(),
            operation="candidate test blob",
            timeout=GIT_TIMEOUT_SECONDS,
            maximum=MAX_BLOB_BYTES,
        )
        if code != 0:
            raise GateError("candidate test blob is unavailable")
        if overlay_blob_oid:
            digest = hashlib.new(object_format)
            digest.update(f"blob {len(payload)}\0".encode("ascii"))
            digest.update(payload)
            if digest.hexdigest() != overlay_blob_oid:
                raise GateError("candidate test blob changed during materialization")
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        try:
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                if written <= 0:
                    raise GateError("candidate test overlay short write")
                offset += written
            os.fchmod(descriptor, 0o644)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return directory


def _new_result(base: str, candidate: str) -> GateArtifact:
    return GateArtifact({
        "kind": "alpha-ficc-a2-patch-gate-v2",
        "allowed": False,
        "base_oid": base,
        "candidate_oid": candidate,
        "origin_main_oid": None,
        "files": [],
        "reasons": [],
        "policy_fingerprint": None,
        "test_path": None,
        "verifier": None,
    })


def _persist_gate(artifact: GateArtifact, control: A2ControlPlane) -> GateArtifact:
    # The explicit stages keep the durable write auditable and make fault
    # injection able to identify the exact boundary (digest, HMAC, file, dir).
    unsigned = _unsigned(artifact, "artifact_digest", "artifact_mac")
    artifact["artifact_digest"] = hashlib.sha256(_canonical_json(unsigned)).hexdigest()
    gate_id = hashlib.sha256((artifact["base_oid"] + artifact["candidate_oid"] + artifact["artifact_digest"]).encode()).hexdigest()[:32]
    artifact["gate_id"] = gate_id
    artifact["artifact_mac"] = _hmac(control.key, _unsigned(artifact, "artifact_mac"))
    control.gate_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = control.gate_dir / f"{gate_id}.json"
    if not control.gate_dir.exists():
        raise GateError("gate directory is unavailable")
    descriptor = _open_regular(path, "gate artifact", read_only=False, mode=0o600, exclusive=True)
    try:
        payload = _canonical_json(artifact)
        if len(payload) > MAX_JSON_BYTES:
            raise GateError("gate artifact exceeds size limit")
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise GateError("gate artifact short write")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory_fd = os.open(control.gate_dir, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return artifact


def _evaluate_with_control(base_oid: str, candidate_oid: str, control: A2ControlPlane) -> GateArtifact:
    result = _new_result(base_oid, candidate_oid)
    reasons: list[str] = result["reasons"]
    temp_paths: list[Path] = []
    try:
        root = _safe_root(control.source_repo, "source clone", control.expected_owner_uid, create=False)
        _check_git_metadata(root, known_hosts=control.known_hosts)
        _check_fixed_ref_config(root, known_hosts=control.known_hosts)
        policy = _load_policy()
        result["policy_fingerprint"] = control.policy_fingerprint
        object_format = _decode(_run_git(root, ("rev-parse", "--show-object-format"), "object format"), "object format").strip()
        base = _resolve_oid(root, base_oid, "base OID", object_format, known_hosts=control.known_hosts)
        candidate = _resolve_oid(root, candidate_oid, "candidate OID", object_format, known_hosts=control.known_hosts)
        result["base_oid"] = base
        result["candidate_oid"] = candidate
        url = _remote_url(root, known_hosts=control.known_hosts)
        if url != control.canonical_remote:
            reasons.append("canonical origin URL mismatch")
        status = _run_git(root, ("status", "--porcelain=v1", "--untracked-files=all"), "Git status", known_hosts=control.known_hosts)
        if status.strip():
            reasons.append("source clone is not clean")
        if not control.locked_config.get("dry_run_no_fetch", False):
            fetch_ref = f"refs/heads/{control.canonical_ref}:refs/remotes/origin/{control.canonical_ref}"
            _run_git(root, ("fetch", "--no-tags", "--prune", control.canonical_remote, fetch_ref), "canonical Git fetch", known_hosts=control.known_hosts)
        origin = _decode(_run_git(root, ("rev-parse", "--verify", "refs/remotes/origin/main^{commit}"), "origin/main", known_hosts=control.known_hosts), "origin/main").strip()
        result["origin_main_oid"] = origin
        if origin != base:
            reasons.append("canonical origin/main does not equal base OID")
        head = _decode(_run_git(root, ("rev-parse", "--verify", "HEAD^{commit}"), "HEAD", known_hosts=control.known_hosts), "HEAD").strip()
        if head != candidate:
            reasons.append("source clone HEAD does not equal candidate OID")
        parents = _decode(_run_git(root, ("rev-list", "--parents", "-n", "1", candidate), "candidate parents", known_hosts=control.known_hosts), "candidate parents").strip().split()
        if parents != [candidate, base]:
            reasons.append("candidate must be exactly one descendant commit of base")
        payload = _run_git(root, ("diff", "--no-ext-diff", "--name-status", "-z", "--find-renames", "--find-copies", base, candidate, "--"), "Git diff", known_hosts=control.known_hosts)
        records = _parse_name_status(payload)
        if not records:
            reasons.append("candidate has no changed files")
        files: list[dict[str, Any]] = []
        production: list[str] = []
        tests: list[str] = []
        total_bytes = 0
        limits = policy["limits"]
        for status_value, path in records:
            if status_value != "M" or not _canonical_path(path):
                reasons.append(f"unsupported or non-canonical diff:{path}")
                continue
            try:
                base_mode, base_type, base_blob = _tree_entry(root, base, path, known_hosts=control.known_hosts)
                cand_mode, cand_type, cand_blob = _tree_entry(root, candidate, path, known_hosts=control.known_hosts)
                if base_type != "blob" or cand_type != "blob" or base_mode not in {"100644", "100755"} or cand_mode != base_mode:
                    reasons.append(f"Git mode/type mismatch:{path}")
                    continue
                decision, reason = _facts_decision({"diff_status": status_value, "path": path, "git_mode": base_mode, "git_object_type": base_type}, policy)
                if decision == "reject":
                    reasons.append(f"{reason}:{path}")
                    continue
                changed_lines, binary = _numstat(root, base, candidate, path, known_hosts=control.known_hosts)
                if binary:
                    reasons.append(f"binary:{path}")
                    continue
                sha256, worktree_blob, size = _inspect_worktree(root, path, object_format, cand_mode, MAX_BLOB_BYTES)
                if worktree_blob != cand_blob:
                    reasons.append(f"candidate worktree blob mismatch:{path}")
                    continue
                total_bytes += size
                if decision == "allow_production":
                    production.append(path)
                else:
                    tests.append(path)
                files.append({"path": path, "role": "production" if decision == "allow_production" else "test", "git_mode": cand_mode, "base_blob_oid": base_blob, "candidate_blob_oid": cand_blob, "sha256": sha256, "size": size, "changed_lines": changed_lines})
            except GateError as error:
                reasons.append(str(error))
        if len(records) > limits.get("max_a2_changed_files", 2):
            reasons.append("changed files exceed A2 limit")
        if len(production) != 1 or len(tests) != 1:
            reasons.append("candidate must contain exactly one production file and one test file")
        if sum(item["changed_lines"] for item in files) > limits.get("max_a2_changed_lines", 120):
            reasons.append("changed lines exceed A2 limit")
        if total_bytes > limits.get("max_a2_total_bytes", MAX_TOTAL_BYTES):
            reasons.append("candidate bytes exceed A2 limit")
        result["files"] = sorted(files, key=lambda item: item["path"])
        if len(tests) == 1:
            result["test_path"] = tests[0]
        if reasons:
            result["reasons"] = list(dict.fromkeys(reasons))
            result["allowed"] = False
            return result
        test_path = tests[0]
        candidate_test_blob = next(item["candidate_blob_oid"] for item in files if item.get("path") == test_path)
        # Verifier trees are private, bounded, and never written to deploy root.
        # RED is the base production tree with the candidate test overlaid.
        # The same immutable test path is then used by GREEN on the candidate
        # tree, so a modified test cannot silently disappear from RED.
        base_tree = _materialize_tree(root, base, overlay_test=test_path, test_path=test_path, overlay_commit=candidate, overlay_blob_oid=candidate_test_blob, object_format=object_format)
        candidate_tree = _materialize_tree(root, candidate)
        temp_paths.extend((base_tree, candidate_tree))
        red, red_argv, red_output_digest = _run_verifier_phase(control, base_tree, test_path, "red")
        green, green_argv, green_output_digest = _run_verifier_phase(control, candidate_tree, test_path, "green")
        if red["failures"] <= 0 or red["errors"] != 0 or green["failures"] != 0 or green["errors"] != 0:
            raise GateError("verifier JUnit does not prove RED then GREEN")
        result["verifier"] = {
            "image_digest": control.verifier_image,
            "runner_identity": _verifier_contract(control)["identity"],
            "verifier_version": control.readiness.get("verifier_version", control.locked_config.get("verifier_version", "locked-verifier-v1")),
            "red_argv": red_argv,
            "green_argv": green_argv,
            "argv_contract_version": control.readiness.get("argv_contract_version", control.locked_config.get("argv_contract_version", "a2-verifier-v1")),
            "network": "none",
            "rootfs": "read-only",
            "non_root": True,
            "docker_socket": False,
            "host_secrets": False,
            "cap_drop": ["ALL"],
            "no_new_privileges": True,
            "red": red,
            "green": green,
            "output_digests": {"red": red_output_digest, "green": green_output_digest},
            "base_oid": base,
            "candidate_oid": candidate,
            "test_path": test_path,
            "policy_fingerprint": control.policy_fingerprint,
            "verified_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        }
        result["allowed"] = True
    except GateError as error:
        reasons.append(str(error))
    except (KeyError, TypeError, ValueError, OSError) as error:
        reasons.append("A2 gate encountered invalid or unsafe input")
    finally:
        for path in temp_paths:
            try:
                import shutil
                shutil.rmtree(path)
            except OSError:
                pass
    result["reasons"] = list(dict.fromkeys(reasons))
    result["allowed"] = not result["reasons"] and result.get("allowed") is True
    if result["allowed"]:
        _persist_gate(result, control)
    return result


def evaluate_patch(*args: Any) -> GateArtifact:
    """Evaluate ``(base_oid, candidate_oid, control_plane)`` only.

    A four-argument legacy ``(repo, base, candidate, evidence)`` call is
    rejected intentionally; caller supplied RED/GREEN evidence is not trusted.
    """

    if len(args) != 3:
        raise GateError("legacy caller evidence API is disabled")
    base_oid, candidate_oid, control = args
    if not isinstance(base_oid, str) or not isinstance(candidate_oid, str) or not isinstance(control, A2ControlPlane):
        raise GateError("evaluate_patch requires base/candidate OID and control plane")
    with _exclusive_control_lock(control):
        return _evaluate_with_control(base_oid, candidate_oid, control)


def _read_artifact(gate_id: str, control: A2ControlPlane) -> GateArtifact:
    if not re.fullmatch(r"[0-9a-f]{32}", gate_id):
        raise GateError("gate id is invalid")
    value = _strict_json_file(control.gate_dir / f"{gate_id}.json", "gate artifact", owner_uid=getattr(control, "expected_owner_uid", os.getuid()), expected_mode=0o600)
    if not isinstance(value, dict):
        raise GateError("gate artifact is invalid")
    claimed_digest = value.get("artifact_digest")
    if claimed_digest != _artifact_digest(value):
        raise GateError("gate artifact digest mismatch")
    claimed_mac = value.pop("artifact_mac", None)
    if not isinstance(claimed_mac, str) or not hmac.compare_digest(claimed_mac, _hmac(control.key, value)):
        raise GateError("gate artifact authorization failed")
    value["artifact_mac"] = claimed_mac
    return GateArtifact(value)


def finalize_non_force_push(gate_id: str, control_plane: A2ControlPlane, *, deployment_id: str | None = None, _lock_already_held: bool = False) -> PushResult:
    if not deployment_id:
        raise GateError("deployment transaction is required for publishing")
    lock_context = contextlib.nullcontext() if _lock_already_held else _exclusive_control_lock(control_plane)
    with lock_context:
        return _finalize_non_force_push(gate_id, control_plane, deployment_id)


def _finalize_non_force_push(gate_id: str, control_plane: A2ControlPlane, deployment_id: str) -> PushResult:
    journal_path = control_plane.a2_root / "deployments" / deployment_id / "journal.jsonl"
    if not journal_path.exists():
        raise GateError("deployment transaction journal is missing")
    raw = journal_path.read_bytes()
    lines = [line for line in raw.splitlines() if line]
    if not lines:
        raise GateError("deployment transaction journal is empty")
    try:
        records = [json.loads(line.decode("utf-8")) for line in lines]
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GateError("deployment transaction journal is invalid") from error
    if records[-1].get("state") != "publishing" or records[-1].get("deployment_id") != deployment_id:
        raise GateError("deployment transaction is not in publishing state")
    for record in records:
        if not isinstance(record, dict) or record.get("deployment_id") != deployment_id:
            raise GateError("deployment journal identity mismatch")
        claimed_record_mac = record.pop("record_mac", None)
        if not isinstance(claimed_record_mac, str) or not hmac.compare_digest(claimed_record_mac, _hmac(control_plane.key, record)):
            raise GateError("deployment journal authorization failed")
        record["record_mac"] = claimed_record_mac
    artifact = _read_artifact(gate_id, control_plane)
    prepared = next((record for record in records if record.get("state") == "prepared"), None)
    verifying = next((record for record in reversed(records) if record.get("state") == "verifying"), None)
    if not isinstance(prepared, Mapping) or prepared.get("gate_id") != gate_id:
        raise GateError("deployment journal gate binding mismatch")
    if not isinstance(verifying, Mapping) or not isinstance(verifying.get("health"), Mapping) or verifying["health"].get("status") != "ok":
        raise GateError("deployment journal health binding is missing")
    expected_image = records[-1].get("image_digest")
    if not isinstance(expected_image, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_image):
        image_record = next((record.get("image_digest") for record in reversed(records) if isinstance(record.get("image_digest"), str)), None)
        expected_image = image_record
    if not isinstance(expected_image, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", expected_image):
        raise GateError("deployment journal image binding is missing")
    try:
        state_image = (control_plane.deploy_root / ".api-image-digest").read_text(encoding="ascii").strip()
    except OSError as error:
        raise GateError("deployment image state is unavailable") from error
    if state_image != expected_image:
        raise GateError("deployment image state does not match publishing journal")
    production = [item for item in artifact.get("files", []) if item.get("role") == "production"]
    if len(production) != 1:
        raise GateError("deployment production binding is invalid")
    target = control_plane.deploy_root / str(production[0].get("path", ""))
    try:
        target_digest = hashlib.sha256(target.read_bytes()).hexdigest()
    except OSError as error:
        raise GateError("deployment production state is unavailable") from error
    if target_digest != production[0].get("sha256"):
        raise GateError("deployment production state does not match gate")
    if artifact.get("allowed") is not True:
        return PushResult({"pushed": False, "reason": "gate artifact is not approved"})
    repo = _safe_root(control_plane.source_repo, "source clone", control_plane.expected_owner_uid)
    _check_git_metadata(repo, known_hosts=control_plane.known_hosts)
    _check_fixed_ref_config(repo, known_hosts=control_plane.known_hosts)
    if _run_git(repo, ("status", "--porcelain=v1", "--untracked-files=all"), "final Git status", known_hosts=control_plane.known_hosts).strip():
        return PushResult({"pushed": False, "reason": "source clone is not clean"})
    object_format = _decode(_run_git(repo, ("rev-parse", "--show-object-format"), "object format", known_hosts=control_plane.known_hosts), "object format").strip()
    base = _resolve_oid(repo, artifact["base_oid"], "base OID", object_format, known_hosts=control_plane.known_hosts)
    candidate = _resolve_oid(repo, artifact["candidate_oid"], "candidate OID", object_format, known_hosts=control_plane.known_hosts)
    head = _decode(_run_git(repo, ("rev-parse", "--verify", "HEAD^{commit}"), "final HEAD", known_hosts=control_plane.known_hosts), "final HEAD").strip()
    if head != candidate:
        return PushResult({"pushed": False, "reason": "source HEAD does not equal candidate"})
    if base != artifact["base_oid"] or candidate != artifact["candidate_oid"]:
        return PushResult({"pushed": False, "reason": "artifact OID mismatch"})
    _run_git(repo, ("fetch", "--no-tags", "--prune", control_plane.canonical_remote, "refs/heads/main:refs/remotes/origin/main"), "final canonical fetch", known_hosts=control_plane.known_hosts)
    remote = _decode(_run_git(repo, ("rev-parse", "--verify", "refs/remotes/origin/main^{commit}"), "final origin/main", known_hosts=control_plane.known_hosts), "final origin/main").strip()
    if remote != base:
        return PushResult({"pushed": False, "reason": "canonical main drift", "remote_main_oid": remote})
    push_env = _safe_env()
    if control_plane.known_hosts is not None:
        push_env["GIT_SSH_COMMAND"] = f"/usr/bin/ssh -oBatchMode=yes -oStrictHostKeyChecking=yes -oUserKnownHostsFile={os.fspath(control_plane.known_hosts)}"
    code, output = _run([GIT_BIN, "-C", os.fspath(repo), "push", control_plane.canonical_remote, f"{candidate}:refs/heads/main"], env=push_env, operation="non-force push", timeout=60, maximum=MAX_OUTPUT_BYTES)
    if code != 0:
        return PushResult({"pushed": False, "reason": "non-force push failed"})
    _run_git(repo, ("fetch", "--no-tags", "--prune", control_plane.canonical_remote, "refs/heads/main:refs/remotes/origin/main"), "post-push canonical fetch", known_hosts=control_plane.known_hosts)
    confirmed = _decode(_run_git(repo, ("rev-parse", "--verify", "refs/remotes/origin/main^{commit}"), "post-push origin/main", known_hosts=control_plane.known_hosts), "post-push origin/main").strip()
    if confirmed != candidate:
        return PushResult({"pushed": False, "reason": "canonical main confirmation failed"})
    return PushResult({"pushed": True, "base_oid": base, "candidate_oid": candidate, "output_digest": hashlib.sha256(output).hexdigest()})


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Alpha-FICC privileged A2 gate")
    sub = parser.add_subparsers(dest="command", required=True)
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--base-oid", required=True)
    evaluate.add_argument("--candidate-oid", required=True)
    evaluate.add_argument("--output-id", required=False)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parse_args(argv)
        control = load_control_plane(A2_ROOT, expected_owner_uid=os.geteuid())
        result = evaluate_patch(args.base_oid, args.candidate_oid, control)
        payload = json.dumps(result, sort_keys=True, ensure_ascii=False, allow_nan=False)
        if len(payload.encode("utf-8")) > MAX_OUTPUT_BYTES:
            raise GateError("gate output exceeds size limit")
        print(payload)
        return 0 if (result.get("allowed") is True or result.get("pushed") is True) else 1
    except (GateError, SystemExit) as error:
        if isinstance(error, SystemExit):
            raise
        print(json.dumps({"kind": "alpha-ficc-a2-gate-error", "allowed": False, "reasons": [str(error)]}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
