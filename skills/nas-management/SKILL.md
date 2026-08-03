---
name: nas-management
description: Manage the user's TrueNAS and Synology systems safely, including reachability checks, scoped file recovery, cross-NAS synchronization, NAS-hosted Git maintenance, large media inventory, and duplicate planning.
license: MIT
metadata:
  version: "1.0.0"
  author: lynch5mo
  category: devops
  triggers: [NAS maintenance, TrueNAS recovery, Synology recovery, NAS git sync, media inventory, duplicate scan]
---

# NAS Management

Use this Skill for the user's own NAS systems and mounted media storage. Treat every path, host, mount, credential location, and destructive target as runtime configuration that must be verified before use.

## Security contract

- Never embed or print passwords, tokens, private keys, cookies, hashes, prefixes, or credential lengths.
- Prefer SSH keys and strict host-key checking. Do not use `sshpass`.
- Read credentials only from the user's local secret store or approved environment files; those files must never be committed.
- Do not disable SSH host-key checks.
- Do not display complete Docker Compose files or environment dumps when they may contain secrets.
- A public installation of this Skill contains no credentials. The operator must configure local access separately.

## Runtime configuration

Before any operation, resolve these values from local configuration rather than assuming they are current:

```text
NAS_PRIMARY_HOST       primary TrueNAS hostname or LAN address
NAS_SECONDARY_HOST     secondary Synology hostname or LAN address
NAS_SSH_USER           approved SSH user
NAS_SSH_KEY            approved private-key path
NAS_PRIMARY_MOUNT      primary mounted-volume path
NAS_SECONDARY_MOUNT    secondary mounted-volume path
```

If any required value is missing, limit work to local read-only inspection and report the missing configuration.

## Preflight

1. Identify the exact NAS, share, dataset, container, or repository in scope.
2. Verify LAN reachability and SSH host identity.
3. Confirm the mounted path points to the intended remote share, not an empty local fallback directory.
4. Record current filesystem capacity, mount type, and target size.
5. For Git work, run `git status --short --branch`, verify the repository root, and fetch before changing history.
6. For recovery or cleanup, create a read-only inventory and a reversible operation plan first.

## File recovery

Use the least invasive source in this order:

1. NAS recycle bin or snapshot.
2. Dataset snapshot clone or read-only snapshot path.
3. Secondary NAS copy.
4. Verified backup.

Restore into a staging directory first. Compare size and checksum before moving restored files into the live library. Never overwrite a live file merely because the name matches.

## Cross-NAS synchronization

1. Establish source and destination roles explicitly.
2. Run a dry-run with item counts and total bytes.
3. Exclude recycle bins, snapshots, temporary files, and system metadata.
4. Preserve timestamps where required.
5. Perform the scoped transfer.
6. Compare source/destination counts and sample hashes.

Do not add `--delete` or an equivalent deletion flag unless the user explicitly authorized mirror semantics and a verified rollback exists.

## Git repositories on NAS

- Prefer a local working clone with the NAS hosting a bare remote.
- Avoid editing a working tree over SMB when a local clone is available.
- When network filesystems cause `mmap`, lock, or index failures, clone locally, verify object integrity, then push to the NAS bare repository.
- Never run history-rewriting commands without explicit authorization.

## Large media inventory

Use a staged workflow:

```text
read-only listing
-> extension and size classification
-> exact duplicate candidates
-> focused hash verification
-> decision pack
-> reversible operation
-> post-operation verification
```

Avoid full-library hashing as the first step. Start with path, filename, size, and category grouping, then hash only narrowed candidates.

## Destructive-operation gate

Before moving, replacing, or deleting material:

- Resolve every source and destination to an explicit absolute path.
- Verify neither path is a mount root, home directory, repository root, or unresolved variable.
- Produce a manifest containing source, target, reason, size, and rollback action.
- Prefer quarantine or move-to-review over deletion.
- Verify results from both the NAS host and the client mount.

## Reporting

Report:

- Device and share/dataset operated on.
- Whether the action was read-only, dry-run, reversible mutation, or destructive mutation.
- Counts and byte totals before and after.
- Verification performed.
- Rollback location or known recovery path.
- Any configuration or authentication gap, without exposing secrets.
