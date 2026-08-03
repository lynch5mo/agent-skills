---
name: hermes-desktop-troubleshooting
description: "Debug Hermes Desktop Electron app when it won't start, hangs at connecting, crashes, or can't find the backend. Covers log analysis, boot flow, asar patching, and common version-mismatch fixes."
license: MIT
metadata:
  version: "1.0.0"
  author: Hermes Agent
  platforms: [macos]
  hermes:
    tags: [debugging, desktop, electron, hermes]
    related_skills: [software-development]
---

# Hermes Desktop Troubleshooting

Hermes Desktop is an Electron app (v0.17.0+) that spawns a local Python backend (`hermes serve`) and connects a web UI renderer to it via WebSocket.

## Boot Flow

1. Electron main process starts, reads `connection.json` (mode: local|remote)
2. In **local mode**: resolves Python backend via `resolveHermesBackend()`
3. Spawns: `python -m hermes_cli.main serve --host 127.0.0.1 --port 0`
4. Backend binds an OS-assigned ephemeral port, prints `HERMES_BACKEND_READY port=<N>` to stdout
5. Main process catches this line via `waitForDashboardPortAnnouncement()`
6. Main process fetches `http://127.0.0.1:<port>/` for dashboard token
7. Renderer connects via WebSocket to backend
8. UI is fully loaded

## Diagnosis Entry Points

### Check which logging layer has the error

| Layer | Log File | What It Shows |
|-------|----------|---------------|
| Electron main | `~/.hermes/logs/desktop.log` | Boot timeline, backend stdout/stderr, errors |
| Backend Python | `~/.hermes/profiles/codex/logs/agent.log` | Plugin loading, cron, serve events |
| Backend errors | `~/.hermes/profiles/codex/logs/errors.log` | Warnings, stack traces |
| Backend GUI WS | `~/.hermes/profiles/codex/logs/gui.log` | Old TUI WebSocket sessions |
| Gateway | `~/.hermes/profiles/codex/logs/gateway.log` | Gateway events (separate from Desktop) |

### Check process state

```bash
ps aux | grep -i [H]ermes
```

Look for:
- Desktop main process (`Hermes.app/Contents/MacOS/Hermes`)
- Renderer helper (`Hermes Helper (Renderer)`)
- Backend Python (`python -m hermes_cli.main serve`)
- Gateway Python (`python -m hermes_cli.main ... gateway run`)

### Check Singletons (Electron lock)

If Desktop won't open a new window, stale singleton socket may block it:

```bash
ls -la ~/Library/Application\ Support/Hermes/Singleton*
```

Kill stale process and clean:
```bash
kill <PID>  # stale Desktop PID
rm -f ~/Library/Application\ Support/Hermes/Singleton{Lock,Socket,Cookie}
```

## Common Issues

### 1. "Timed out waiting for Hermes backend port announcement"

**Symptom**: Desktop stuck at "connecting", backend IS running and listening.

**Root cause**: Regex mismatch — `backend-ready.cjs` watches for `HERMES_DASHBOARD_READY` but backend prints `HERMES_BACKEND_READY`.

**Fix**: See `references/backend-ready-regex-mismatch.md`.

### 2. "Hermes couldn't start" then Desktop shows error screen

**Symptom**: Desktop opens brief error dialog then quits.

**Check**: Stale singleton lock from a previous crashed instance prevents new Electron instance from starting.

**Fix**: Kill the stale process, clean singleton files, relaunch.

### 3. Backend exits immediately

**Symptom**: Backend Python process starts and exits with non-zero code.

**Check**: `~/.hermes/profiles/codex/logs/errors.log` for ModuleNotFoundError or Python runtime errors.

### 4. Wrong Hermes.app launched

**Symptom**: User opens "Hermes.app" but gets Setup tool, not Desktop.

**Check**: There are two apps:
- `/Applications/Hermes.app` — **Setup tool** (v0.0.1, bundle `com.nousresearch.hermes.setup`)
- `~/.hermes/hermes-agent/apps/desktop/release/mac-arm64/Hermes.app` — **Actual Desktop** (v0.17.0+)

**Fix**: Symlink the real one:
```bash
ln -sf ~/.hermes/hermes-agent/apps/desktop/release/mac-arm64/Hermes.app /Applications/Hermes-Desktop.app
```

## Asar Patching Quick Reference

When the Desktop app.asar needs modification:

```bash
# Extract
npx asar extract <path>/app.asar /tmp/code

# Modify files (*.cjs, *.js, *.json)
# (edit files under /tmp/code/electron/ or /tmp/code/dist/)

# Repack
cd /tmp/code && npx asar pack . <original-path>/app.asar

# Verify
npx asar extract-file <path>/app.asar <file> /tmp/check

# Always back up first:
cp app.asar app.asar.bak
```
