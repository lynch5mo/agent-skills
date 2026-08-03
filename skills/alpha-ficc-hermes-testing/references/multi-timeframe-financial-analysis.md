# Multi-Timeframe Financial Analysis Methodology

*Session: 2026-06-08 — CSI300 五阶段行情分析*

## Core Principle

**Always start analysis from the structural beginning of a trend, not the most recent leg.** When a research article analyzes a market move using only the most recent 2-3 months, interrogate what happened in the preceding months — the driver hierarchy often shifts across phases.

## The Multi-Phase Attribution Framework

When analyzing a sustained market move (equity rally, currency trend, etc.):

1. **Find the absolute low and high** of the full move, not just the window in question
2. **Identify natural phase boundaries** by looking for regime shifts in the key drivers:
   - Policy events (stimulus announcements, elections)
   - Spread/correlation regime changes
   - Dollar trend reversals
3. **Attribute each phase separately** — the driver of Phase I may not be the driver of Phase V
4. **Test whether the claimed causal chain holds in earlier phases** — if "RMB strength via current account explains A-share rally," it should show up in ALL phases, not just the final leg
5. **Flag when the article's logic only works in the most recent phase** — this is a red flag for cherry-picked analysis

## Attribution Decomposition Technique

### Currency Attribution
To decompose a currency move into passive (USD-driven) and active (local-driven) components:

```python
# Normalize both to 100 at a common start date
usdcnh_norm = usdcnh / usdcnh[start_date] * 100
dxy_norm = dxy / dxy[start_date] * 100

# For each phase:
usdcnh_chg_pct = (usdcnh[phase_end] / usdcnh[phase_start] - 1) * 100
dxy_chg_pct = (dxy[phase_end] / dxy[phase_start] - 1) * 100

# USD contribution ≈ dxy_chg_pct / usdcnh_chg_pct (when both move same direction)
# Local contribution ≈ 1 - USD_contribution
```

### Phase-by-Phase Correlation
```python
for phase_start, phase_end in phases:
    phase_data = daily[phase_start:phase_end]
    corr = phase_data["spread"].corr(phase_data["csi300"])
    # Track how the spread-equity relationship changes across phases
```

## Chart Generation Workflow

When producing proof charts for financial analysis:

1. **Pull data from Alpha-FICC terminal** via `GET /api/comparison/current/chart-data`
2. **Save as CSV** to `/tmp/` for reuse
3. **Generate with matplotlib** (not plotext) for publication-quality PNGs:
   - Use `Arial Unicode MS` for Chinese text rendering
   - Multi-panel layouts with shared x-axis for time alignment
   - Phase backgrounds (`axvspan`) with alpha for regime identification
   - Key level annotations (highs, lows, 50-line for PMI)
4. **Deliver as MEDIA attachments** in the chat, plus reference from the article markdown

```python
# Template for multi-panel financial chart
fig, axes = plt.subplots(n_panels, 1, figsize=(16, 4 * n_panels), sharex=True)

# Panel 1: Primary asset (equity index)
axes[0].plot(dates, csi300, color="#1a237e", linewidth=1.2)

# Panel 2: FX rate (inverted so up = local currency stronger)
axes[1].plot(dates, usdcnh, color="#c62828", linewidth=1.2)
axes[1].invert_yaxis()

# Panel 3: Dollar index
axes[2].plot(dxy_dates, dxy_values, color="#e65100", linewidth=1.2)

# Panel 4: Spread or rate differential
axes[3].plot(dates, spread, color="#1565c0", linewidth=1.2)
axes[3].axhline(y=0, color="black", linewidth=0.5)

# Apply phase backgrounds to all panels
for ax in axes:
    for start, end, label, color in phases:
        ax.axvspan(start, end, alpha=0.08, color=color)
```

## Common Analytical Errors to Watch For

1. **Cherry-picked time windows**: Author uses absolute low→high for the asset but narrow start→end for the explanatory variable
2. **Missing key explanatory variables**: Analysis of RMB strength that never mentions DXY
3. **Treating tail phenomenon as whole-story explanation**: Using the final 10% of a move to explain the entire 100%
4. **Smoothing over intermediate extremes**: Citing spread at two narrow points while it went much wider in between
5. **Single-variable attribution for multi-phase moves**: Markets are multi-factor; no single variable explains 20 months

## Pitfall: execute_code String Escaping

**`execute_code` cannot handle Python scripts with nested quote characters** (e.g., `strip('"')` or `strip("'")`). The tool mangles the heredoc and produces `SyntaxError: unterminated string literal`.

**Always use this pattern instead:**

```python
# Step 1: write_file to /tmp/script.py
# Step 2: terminal("python3 /tmp/script.py")
# Step 3: (optionally) terminal("rm /tmp/script.py")
```

Or for quick exploration, use `terminal` with a Python heredoc:
```bash
python3 << 'PYEOF'
... script content with any quotes ...
PYEOF
```

The `<< 'PYEOF'` (single-quoted delimiter) prevents shell expansion inside the heredoc.
