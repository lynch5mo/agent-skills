# Data Source Patterns for Alpha-FICC Analysis (2026-06-03)

## CoinGecko API — BTC Volume Data Fallback

When `yfinance` is blocked by Cloudflare (common on this server), CoinGecko's public API works for BTC trading volume:

```python
import requests
resp = requests.get(
    "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
    params={"vs_currency": "usd", "days": "90", "interval": "daily"},
    timeout=10
)
data = resp.json()
volumes = data.get('total_volumes', [])  # [[timestamp_ms, volume_usd], ...]
```

- No API key needed for basic endpoints
- Returns daily volume in USD
- Rate limit: ~10-30 req/min (free tier)
- Useful for: volume trend analysis, liquidity assessment

## Alpha-FICC Chart-Data for ETF Comparison

The `/api/comparison/current/chart-data` endpoint accepts arbitrary yfinance tickers:

```python
# Pull ETF data
resp = requests.get(
    "https://alpha-ficc.lynch5mo.xyz/api/comparison/current/chart-data",
    headers={"Authorization": f"Bearer {token}"},
    params={"series": "yfinance:IBIT", "window": "6M", "granularity": "D"},
    timeout=15
)
# Returns: {"series": [{"id": "yfinance:IBIT", "points": [{"date": "...", "value": ...}, ...]}]}
```

**Note**: This endpoint returns price data only (no volume). For volume, use CoinGecko.

### Available BTC ETF Tickers (verified 2026-06-03)
- `yfinance:IBIT` — iShares Bitcoin Trust (BlackRock)
- `yfinance:FBTC` — Fidelity Wise Origin Bitcoin Fund
- `yfinance:GBTC` — Grayscale Bitcoin Trust
- `yfinance:ARKB` — ARK 21Shares Bitcoin ETF
- `yfinance:BITB` — Bitwise Bitcoin ETF

### Pattern: Multi-ETF Performance Comparison

```python
etfs = ["IBIT", "FBTC", "GBTC", "ARKB", "BITB"]
for etf in etfs:
    resp = requests.get(
        f"{api}/comparison/current/chart-data",
        headers=headers,
        params={"series": f"yfinance:{etf}", "window": "6M", "granularity": "D"},
        timeout=10
    )
    data = resp.json()
    for s in data.get('series', []):
        points = s.get('points', [])
        first, last = points[0]['value'], points[-1]['value']
        change = (last - first) / first * 100
        print(f"{etf}: {first:.2f} → {last:.2f} ({change:+.1f}%)")
```

## BTC Volume Trend Analysis (CoinGecko)

```python
# Get 90-day volume
resp = requests.get(
    "https://api.coingcko.com/api/v3/coins/bitcoin/market_chart",
    params={"vs_currency": "usd", "days": "90", "interval": "daily"},
    timeout=10
)
volumes = resp.json().get('total_volumes', [])

# Compare 30-day vs 90-day average
from datetime import datetime
recent_30 = [v for v in volumes if (datetime.now().timestamp() - v[0]/1000) < 30*86400]
avg_30 = sum(v[1] for v in recent_30) / len(recent_30)
avg_90 = sum(v[1] for v in volumes) / len(volumes)
print(f"30d avg: ${avg_30:,.0f}")
print(f"90d avg: ${avg_90:,.0f}")
print(f"Change: {((avg_30 - avg_90) / avg_90 * 100):.1f}%")
```

## Session-Specific Findings

### BTC Liquidity Crisis Data (2026-06-03)

Key data points from this analysis session:

| Metric | Value | Source |
|--------|-------|--------|
| BTC 6-month decline | -27.3% | Alpha-FICC chart-data |
| IBIT 6-month decline | -26.4% | Alpha-FICC chart-data |
| FBTC 6-month decline | -26.3% | Alpha-FICC chart-data |
| GBTC 6-month decline | -26.8% | Alpha-FICC chart-data |
| BTC 30d avg volume | $34.8B | CoinGecko |
| BTC 90d avg volume | $39.0B | CoinGecko |
| Volume decline | -10.6% | Calculated |

All BTC spot ETFs declined ~26-27% in 6 months, confirming institutional outflow.
Volume declined 10.6% (30d vs 90d average), confirming liquidity squeeze.

### terminal-chart-actions API Status (2026-06-03)

After Codex annotation rendering fix, the nested `target.annotations` format returns `INVALID_TARGET`. However, a **simplified flat format works**:

```python
# WORKS (flat format)
payload = {
    "action": "add_chart_annotations",
    "workspaceId": ws_id,  # from GET /api/comparison/current/context
    "annotations": [{"type": "vertical-line", "panelId": "...", ...}]
}
# Returns: {"ok": true, "action": {"status": "success", ...}}

# BROKEN (nested format — returns INVALID_TARGET)
payload = {
    "action": "add_chart_annotations",
    "target": {
        "workspaceId": ws_id,
        "annotations": [{"type": "vertical-line", ...}]
    }
}
```

**Diagnostic**: `GET /api/workspaces` lists active workspaces. If the target workspace is not in this list, it will be rejected by `terminal-chart-actions` even if annotations exist for it.

**Error code pattern**: `INVALID_ANNOTATION_TEXT_N` means annotation at index N is missing required `text` field. `trend-line` type always requires `text`.
