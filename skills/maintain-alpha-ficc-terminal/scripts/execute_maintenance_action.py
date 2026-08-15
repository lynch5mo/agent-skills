"""Execute one fixed, policy-locked A1 Alpha-FICC maintenance action."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import importlib
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

_SCRIPT_DIRECTORY = str(Path(__file__).parent)
if _SCRIPT_DIRECTORY not in sys.path:
    sys.path.insert(0, _SCRIPT_DIRECTORY)

_maintenance_contract = importlib.import_module("maintenance_contract")
sanitize = _maintenance_contract.sanitize
SENSITIVE_KEY_FRAGMENTS = _maintenance_contract.SENSITIVE_KEY_FRAGMENTS


POLICY_PATH = Path(__file__).parents[1] / "references/repair-policy.json"
HARD_TIMEOUT_SECONDS = 60
MAX_OUTPUT_BYTES = 16384
_POLICY_TIMEOUT_SECONDS = 60
_POLICY_MAX_OUTPUT_BYTES = 16384
_REFRESH_SCRIPT = Path("scripts/run_incremental_refresh_cron.sh")
_SAFE_ENV = {"PATH": os.defpath, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
_EXECUTABLE_PATHS = {"bash": "/bin/bash", "docker": "/usr/bin/docker"}
_FIXED_ACTIONS: dict[str, tuple[str, ...]] = {
    "refresh_daily": ("bash", "scripts/run_incremental_refresh_cron.sh", "daily"),
    "refresh_low_frequency": (
        "bash",
        "scripts/run_incremental_refresh_cron.sh",
        "low-frequency",
    ),
    "refresh_catchup": ("bash", "scripts/run_incremental_refresh_cron.sh", "catchup"),
    "restart_api": ("docker", "restart", "alpha-ficc-api"),
    "restart_web": ("docker", "restart", "alpha-ficc-web"),
    "restart_hermes_relay": ("docker", "restart", "alpha-ficc-hermes-relay"),
}
_POST_ACTION_CHECK_IDS: dict[str, tuple[str, ...]] = {
    "refresh_daily": ("refresh.health", "data_catalog.series"),
    "refresh_low_frequency": (
        "refresh.health",
        "refresh.low_frequency",
        "data_catalog.series",
    ),
    "refresh_catchup": ("refresh.health", "data_catalog.series"),
    "restart_api": ("api.health", "data_catalog.series"),
    "restart_web": ("api.health",),
    "restart_hermes_relay": ("api.health",),
}
_ACTION_VERSION = "a1-v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _policy_matches_fixed_contract(policy: Mapping[str, Any]) -> bool:
    return (
        policy.get("a1_actions")
        == {action_id: list(argv) for action_id, argv in _FIXED_ACTIONS.items()}
        and policy.get("a1_executor")
        == {
            "version": _ACTION_VERSION,
            "timeout_seconds": _POLICY_TIMEOUT_SECONDS,
            "post_action_check_ids": {
                action_id: list(checks)
                for action_id, checks in _POST_ACTION_CHECK_IDS.items()
            },
        }
        and policy.get("limits", {}).get("max_command_output_bytes")
        == _POLICY_MAX_OUTPUT_BYTES
        and policy.get("a1_executables")
        == {name: {"path": path} for name, path in _EXECUTABLE_PATHS.items()}
    )


def _load_policy() -> None:
    try:
        policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("fixed A1 contract is unavailable") from error
    if not isinstance(policy, Mapping) or not _policy_matches_fixed_contract(policy):
        raise ValueError("fixed A1 contract does not match the allowlisted policy")


def _open_flags(*, directory: bool = False) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("safe fd execution is unavailable")
    flags |= os.O_NOFOLLOW
    if directory:
        if not hasattr(os, "O_DIRECTORY"):
            raise ValueError("safe fd execution is unavailable")
        flags |= os.O_DIRECTORY
    return flags


def _open_anchored_directory(repo_root: Path) -> int:
    root = Path(os.path.abspath(os.fspath(repo_root)))
    if not root.is_absolute():
        raise ValueError("repo root must be absolute")
    current_fd = os.open(root.anchor, _open_flags(directory=True))
    try:
        for component in root.parts[1:]:
            next_fd = os.open(component, _open_flags(directory=True), dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except OSError as error:
        os.close(current_fd)
        raise ValueError("repo root must be a non-symlink directory") from error


def _open_regular_at(directory_fd: int, name: str, label: str) -> int:
    try:
        file_fd = os.open(name, _open_flags(), dir_fd=directory_fd)
    except OSError as error:
        raise ValueError(f"{label} must be a regular, non-symlink file") from error
    try:
        metadata = os.fstat(file_fd)
        unsafe_mode = metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid not in {0, os.geteuid()}
            or unsafe_mode
        ):
            raise ValueError(f"{label} must be a trusted single-link regular file")
        return file_fd
    except BaseException:
        os.close(file_fd)
        raise


def _open_refresh_script(root_fd: int) -> int:
    try:
        scripts_fd = os.open("scripts", _open_flags(directory=True), dir_fd=root_fd)
    except OSError as error:
        raise ValueError("refresh script must be a regular, non-symlink file") from error
    try:
        return _open_regular_at(
            scripts_fd, _REFRESH_SCRIPT.name, "refresh script"
        )
    finally:
        os.close(scripts_fd)


def _open_executable(executable_name: str) -> int:
    path = _EXECUTABLE_PATHS[executable_name]
    try:
        executable_fd = os.open(path, _open_flags())
    except OSError as error:
        raise ValueError("trusted executable is unavailable") from error
    try:
        metadata = os.fstat(executable_fd)
        unsafe_mode = metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid not in {0, os.geteuid()}
            or unsafe_mode
        ):
            raise ValueError("trusted executable must be a single-link regular file")
        return executable_fd
    except BaseException:
        os.close(executable_fd)
        raise


def _fd_execution_path(file_fd: int) -> str:
    for directory in ("/proc/self/fd", "/dev/fd"):
        candidate = f"{directory}/{file_fd}"
        if os.path.exists(candidate):
            return candidate
    raise ValueError("safe fd execution is unavailable")


def _anchored_cwd(root_fd: int) -> tuple[str | None, Any | None]:
    linux_fd_path = f"/proc/self/fd/{root_fd}"
    if os.path.exists(linux_fd_path):
        return linux_fd_path, None
    if os.path.exists(f"/dev/fd/{root_fd}"):
        return None, lambda: os.fchdir(root_fd)
    raise ValueError("safe fd execution is unavailable")


def _same_identity(file_fd: int, identity: os.stat_result) -> bool:
    current = os.fstat(file_fd)
    return current.st_dev == identity.st_dev and current.st_ino == identity.st_ino


def _logical_argv(action_id: str, repo_root: Path) -> list[str]:
    action = _FIXED_ACTIONS.get(action_id)
    if action is None:
        raise ValueError("action is not allowlisted")
    if action[0] == "bash":
        root = Path(os.path.abspath(os.fspath(repo_root)))
        return [action[0], str(root / _REFRESH_SCRIPT), action[2]]
    return list(action)


def _action_result(action_id: str, argv: list[str]) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "version": _ACTION_VERSION,
        "argv_category": "fixed_allowlisted",
        "argv": argv,
        "post_action_check_ids": list(_POST_ACTION_CHECK_IDS[action_id]),
    }


def _read_output_until_exit(
    process: subprocess.Popen[bytes], timeout_seconds: float
) -> tuple[bytes, bool, bool]:
    """Drain process output while retaining no more than the evidence cap."""
    if process.stdout is None:
        return b"", False, False
    captured = bytearray()
    truncated = False
    timed_out = False
    deadline = time.monotonic() + timeout_seconds
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            for key, _ in selector.select(remaining):
                chunk = os.read(key.fd, 8192)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                available = MAX_OUTPUT_BYTES - len(captured)
                if available > 0:
                    captured.extend(chunk[:available])
                if len(chunk) > available:
                    truncated = True
        return bytes(captured), truncated, timed_out
    finally:
        selector.close()


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    finally:
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


class _MaintenanceCancellation(BaseException):
    """Signal wrapper that lets the action cleanup run before cancellation escapes."""


@contextmanager
def _cancellation_guard():
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous_handlers = {signum: signal.getsignal(signum) for signum in (signal.SIGINT, signal.SIGTERM)}

    def request_cancel(signum: int, _frame: Any) -> None:
        raise _MaintenanceCancellation(signum)

    try:
        for signum in previous_handlers:
            signal.signal(signum, request_cancel)
        yield
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


_BEARER_VALUE = re.compile(r"(?i)(\bbearer\s+)[^\s,;]+")
_OUTPUT_SENSITIVE_FRAGMENTS = "|".join(
    "api[_ -]?key" if fragment == "api_key" else re.escape(fragment)
    for fragment in (*SENSITIVE_KEY_FRAGMENTS, "cookie")
)
_SENSITIVE_VALUE = re.compile(
    rf"(?i)((?:\"[A-Za-z0-9_. -]*?(?:{_OUTPUT_SENSITIVE_FRAGMENTS})[A-Za-z0-9_. -]*?\"|"
    rf"'[A-Za-z0-9_. -]*?(?:{_OUTPUT_SENSITIVE_FRAGMENTS})[A-Za-z0-9_. -]*?'|"
    rf"[A-Za-z0-9_. -]*?(?:{_OUTPUT_SENSITIVE_FRAGMENTS})[A-Za-z0-9_. -]*)\s*[:=]\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)


def _safe_output(output: bytes) -> str:
    text = output.decode("utf-8", errors="replace")
    text = _BEARER_VALUE.sub(r"\1<redacted>", text)
    text = _SENSITIVE_VALUE.sub(r"\1<redacted>", text)
    return str(sanitize(text))


def execute_action(action_id: str, repo_root: Path, dry_run: bool) -> dict[str, Any]:
    """Execute exactly one static A1 action, or return a no-side-effect plan."""
    _load_policy()
    argv = _logical_argv(action_id, repo_root)
    result = _action_result(action_id, argv)
    root_fd: int | None = None
    script_fd: int | None = None
    executable_fd: int | None = None
    try:
        root_fd = _open_anchored_directory(repo_root)
        if action_id.startswith("refresh_"):
            script_fd = _open_refresh_script(root_fd)
        if dry_run:
            return {**result, "status": "planned", "executable_validation": "pending"}

        result["started_at"] = _utc_now()
        executable_name = "bash" if script_fd is not None else "docker"
        executable_fd = _open_executable(executable_name)
        root_identity = os.fstat(root_fd)
        executable_identity = os.fstat(executable_fd)
        script_identity = os.fstat(script_fd) if script_fd is not None else None
        execution_argv = [_EXECUTABLE_PATHS[executable_name]]
        if script_fd is not None:
            execution_argv.extend([_fd_execution_path(script_fd), argv[2]])
        else:
            execution_argv.extend(argv[1:])
        cwd, preexec_fn = _anchored_cwd(root_fd)
        process: subprocess.Popen[bytes] | None = None
        try:
            with _cancellation_guard():
                process = subprocess.Popen(
                    execution_argv,
                    cwd=cwd,
                    env=_SAFE_ENV,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    preexec_fn=preexec_fn,
                    pass_fds=tuple(
                        fd for fd in (root_fd, script_fd, executable_fd) if fd is not None
                    ),
                )
                identities_match = _same_identity(root_fd, root_identity) and _same_identity(
                    executable_fd, executable_identity
                ) and (script_identity is None or _same_identity(script_fd, script_identity))
                if not identities_match:
                    _kill_process_group(process)
                    result.update(
                        {
                            "status": "failed",
                            "exit_code": None,
                            "output": "",
                            "output_truncated": False,
                            "executable_validation": "failed",
                        }
                    )
                    return result
                output, truncated, timed_out = _read_output_until_exit(process, HARD_TIMEOUT_SECONDS)
                if timed_out:
                    _kill_process_group(process)
                    result.update(
                        {
                            "status": "timed_out",
                            "exit_code": None,
                            "timeout_seconds": HARD_TIMEOUT_SECONDS,
                            "output": _safe_output(output),
                            "output_truncated": truncated,
                            "executable_validation": "passed",
                        }
                    )
                else:
                    exit_code = process.wait()
                    result.update(
                        {
                            "status": "succeeded" if exit_code == 0 else "failed",
                            "exit_code": exit_code,
                            "output": _safe_output(output),
                            "output_truncated": truncated,
                            "executable_validation": "passed",
                        }
                    )
        finally:
            if process is not None and process.poll() is None:
                _kill_process_group(process)
    except (OSError, ValueError):
        if dry_run:
            raise
        result.update(
            {
                "status": "failed",
                "exit_code": None,
                "output": "",
                "output_truncated": False,
                "executable_validation": "failed",
            }
        )
    finally:
        for file_fd in (script_fd, executable_fd, root_fd):
            if file_fd is not None:
                os.close(file_fd)
    if "started_at" in result:
        result["ended_at"] = _utc_now()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", required=True)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        result = execute_action(args.action, args.repo_root, args.dry_run)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
