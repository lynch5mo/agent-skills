#!/usr/bin/env python3
"""Verify written outputs against a small expected JSON manifest.

Checks each manifest item under --root for existence, byte size,
SHA-256, and required sections. stdout is exactly one compact JSON
line. Exit codes: 0 = all verified, 1 = artifact mismatch, 2 =
manifest/usage error. File content and secrets are never printed.
"""

import hashlib
import json
import os
import re
import sys
from pathlib import Path


SCHEMA_VERSION = "1"
MANIFEST_FIELDS = ("schema_version", "files")
FILE_FIELDS = ("path", "expected_size", "sha256", "required_sections")
SHA256_RE = re.compile(r"[0-9a-fA-F]{64}")


class UsageError(Exception):
    pass


class ManifestError(Exception):
    pass


def parse_args(argv):
    args = {"manifest": None, "root": None, "max_samples": 10}
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in ("--manifest", "--root", "--max-samples"):
            if index + 1 >= len(argv):
                raise UsageError(f"{arg} requires a value")
            value = argv[index + 1]
            if arg == "--manifest":
                args["manifest"] = value
            elif arg == "--root":
                args["root"] = value
            else:
                try:
                    args["max_samples"] = int(value)
                except ValueError as exc:
                    raise UsageError("--max-samples must be an integer") from exc
                if args["max_samples"] < 0:
                    raise UsageError("--max-samples must be >= 0")
            index += 2
        else:
            raise UsageError(f"unknown argument: {arg}")
    if args["manifest"] is None:
        raise UsageError("--manifest is required")
    if args["root"] is None:
        raise UsageError("--root is required")
    return args


def load_manifest(path):
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestError(f"cannot read manifest {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError("manifest root must be an object")
    unknown = set(data) - set(MANIFEST_FIELDS)
    if unknown:
        raise ManifestError(f"unknown manifest fields: {sorted(unknown)}")
    schema_version = data.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ManifestError(f"unsupported schema_version: {schema_version!r}")
    files = data.get("files")
    if not isinstance(files, list):
        raise ManifestError("files must be an array")

    items = []
    seen_paths = set()
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            raise ManifestError(f"files[{index}] must be an object")
        unknown_fields = set(item) - set(FILE_FIELDS)
        if unknown_fields:
            raise ManifestError(
                f"files[{index}] unknown fields: {sorted(unknown_fields)}"
            )
        path = item.get("path")
        if not isinstance(path, str) or not path or "\x00" in path:
            raise ManifestError(f"files[{index}].path must be a non-empty string")
        if os.path.isabs(path) or any(part == ".." for part in Path(path).parts):
            raise ManifestError(f"files[{index}].path escapes root: {path!r}")
        expected_size = item.get("expected_size")
        if (
            isinstance(expected_size, bool)
            or not isinstance(expected_size, int)
            or expected_size < 0
        ):
            raise ManifestError(
                f"files[{index}].expected_size must be a non-negative integer"
            )
        sha256 = item.get("sha256")
        if not isinstance(sha256, str) or not SHA256_RE.fullmatch(sha256):
            raise ManifestError(
                f"files[{index}].sha256 must be 64 hex characters"
            )
        required_sections = item.get("required_sections")
        if not isinstance(required_sections, list) or not all(
            isinstance(section, str) for section in required_sections
        ):
            raise ManifestError(
                f"files[{index}].required_sections must be an array of strings"
            )
        if path in seen_paths:
            raise ManifestError(f"duplicate path in manifest: {path!r}")
        seen_paths.add(path)
        items.append(
            {
                "path": path,
                "expected_size": expected_size,
                "sha256": sha256.lower(),
                "required_sections": required_sections,
            }
        )
    return {"schema_version": schema_version, "files": items}


def resolve_items(root, items):
    root_resolved = Path(root).resolve()
    resolved = []
    seen = set()
    for item in items:
        candidate = (root_resolved / item["path"]).resolve()
        if not candidate.is_relative_to(root_resolved):
            raise ManifestError(
                f"path escapes root after resolution: {item['path']!r}"
            )
        if candidate in seen:
            raise ManifestError(
                f"duplicate resolved path in manifest: {item['path']!r}"
            )
        seen.add(candidate)
        resolved.append(candidate)
    return resolved


def verify_items(root, items, max_samples):
    resolved = resolve_items(root, items)
    counts = {
        "missing": 0,
        "size_mismatch": 0,
        "hash_mismatch": 0,
        "section_mismatch": 0,
    }
    samples = []
    verified = 0

    def add_sample(kind, path, **extra):
        if len(samples) < max_samples:
            sample = {"path": path, "kind": kind}
            sample.update(extra)
            samples.append(sample)

    for item, candidate in zip(items, resolved):
        rel_path = item["path"]
        if not candidate.is_file():
            counts["missing"] += 1
            add_sample("missing", rel_path)
            continue
        data = candidate.read_bytes()
        ok = True
        if len(data) != item["expected_size"]:
            counts["size_mismatch"] += 1
            ok = False
            add_sample(
                "size_mismatch",
                rel_path,
                expected_size=item["expected_size"],
                actual_size=len(data),
            )
        actual_sha = hashlib.sha256(data).hexdigest()
        if actual_sha != item["sha256"]:
            counts["hash_mismatch"] += 1
            ok = False
            add_sample("hash_mismatch", rel_path)
        text = data.decode("utf-8", errors="replace")
        missing_sections = [
            section
            for section in item["required_sections"]
            if section not in text
        ]
        if missing_sections:
            counts["section_mismatch"] += 1
            ok = False
            add_sample(
                "section_mismatch",
                rel_path,
                missing_sections=missing_sections,
            )
        if ok:
            verified += 1
    return counts, samples, verified


def main(argv):
    try:
        args = parse_args(argv)
        manifest = load_manifest(args["manifest"])
        counts, samples, verified = verify_items(
            args["root"], manifest["files"], args["max_samples"]
        )
        expected = len(manifest["files"])
        payload = {
            "schema_version": manifest["schema_version"],
            "ok": verified == expected,
            "expected": expected,
            "verified": verified,
            "errors": {
                "missing": counts["missing"],
                "size_mismatch": counts["size_mismatch"],
                "hash_mismatch": counts["hash_mismatch"],
                "section_mismatch": counts["section_mismatch"],
                "manifest_error": 0,
            },
            "samples": samples[: args["max_samples"]],
        }
        print(json.dumps(payload, sort_keys=True))
        return 0 if verified == expected else 1
    except (UsageError, ManifestError) as exc:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "expected": 0,
            "verified": 0,
            "errors": {
                "missing": 0,
                "size_mismatch": 0,
                "hash_mismatch": 0,
                "section_mismatch": 0,
                "manifest_error": 1,
            },
            "samples": [{"kind": "manifest_error"}],
        }
        print(json.dumps(payload, sort_keys=True))
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
