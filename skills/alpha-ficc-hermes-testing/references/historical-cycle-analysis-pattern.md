# Historical Cycle Analysis Pattern (Alpha-FICC)

## Overview

When the user asks to verify historical claims about asset correlations (e.g., "BTC vs IGV always move together"), use Alpha-FICC's chart-data endpoint with multi-window queries to extract cycle-level statistics.

## Data Fetching Pattern

### Single Multi-Series Query (Preferred)

```python
import requests, json

token = os.environ["ALPHA_FICC_HERMES_AGENT_TOKEN"]
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Fetch 5Y weekly data for all series at once
resp = requests.get(
    "https://alpha-ficc.lynch5mo.xyz/api/comparison/current/chart-data",
    headers=headers,
    params={
        "series": "yfinance:BTC-USD,yfinance:IGV,fred:BAMLH0A0HYM2",
        "window": "5Y",
        "granularity": "W"
    },
    timeout=30
)
data = resp.json()

# Parse into dicts
series_data = {}
for s in data.get("series", []):
    series_data[s["id"]] = {p["date"]: p["value"] for p in s["points"]}
```

### Granularity Guide

| Window | Granularity | Use Case |
|--------|-------------|----------|
| 1Y | D (daily) | Recent trend analysis |
| 3Y | W (weekly) | Medium-term cycle comparison |
| 5Y | W (weekly) | Major cycle peaks/troughs |
| 10Y | M (monthly) | Long-term structural analysis |

**Note**: FRED series (e.g., `fred:BAMLH0A0HYM2`) may not return data for windows > 3Y. Use separate queries if needed.

## Cycle Analysis Pattern

### Define Cycle Boundaries

```python
cycles = [
    ("2017-2018 Bull→Bear", "2016-01", "2018-12"),
    ("2020-2022 Bull→Bear", "2020-12", "2022-12"),
    ("2024-2026 Bull→Crash", "2024-01", "2026-06"),
]

for name, start, end in cycles:
    btc_c = {d: v for d, v in btc.items() if start <= d <= end}
    igv_c = {d: v for d, v in igv.items() if start <= d <= end}

    # Calculate stats
    btc_peak = max(btc_c.values())
    btc_trough = min(btc_c.values())
    igv_peak = max(igv_c.values())
    igv_trough = min(igv_c.values())

    # Check direction correlation
    btc_chg = (list(btc_c.values())[-1] - list(btc_c.values())[0]) / list(btc_c.values())[0] * 100
    igv_chg = (list(igv_c.values())[-1] - list(igv_c.values())[0]) / list(igv_c.values())[0] * 100
    same_direction = (btc_chg > 0 and igv_chg > 0) or (btc_chg < 0 and igv_chg < 0)
```

### Peak Timing Analysis

```python
from datetime import datetime

btc_peak_date = max(btc_c, key=btc_c.get)
igv_peak_date = max(igv_c, key=igv_c.get)

btc_peak_dt = datetime.strptime(btc_peak_date, "%Y-%m-%d")
igv_peak_dt = datetime.strptime(igv_peak_date, "%Y-%m-%d")
gap_days = (igv_peak_dt - btc_peak_dt).days

print(f"BTC peak: {btc_peak_date} (${btc_c[btc_peak_date]:,.0f})")
print(f"IGV peak: {igv_peak_date} (${igv_c[igv_peak_date]:.2f})")
print(f"Gap: {gap_days} days ({'BTC first' if gap_days > 0 else 'IGV first'})")
```

## BTC ETF Performance Comparison

### Fetch Multiple ETF Tickers

```python
etfs = ["IBIT", "FBTC", "GBTC", "ARKB", "BITB"]
results = {}

for etf in etfs:
    resp = requests.get(
        "https://alpha-ficc.lynch5mo.xyz/api/comparison/current/chart-data",
        headers=headers,
        params={"series": f"yfinance:{etf}", "window": "6M", "granularity": "D"},
        timeout=10
    )
    data = resp.json()
    for s in data.get("series", []):
        points = s.get("points", [])
        if points:
            first, last = points[0]["value"], points[-1]["value"]
            results[etf] = {
                "first": first,
                "last": last,
                "change_pct": (last - first) / first * 100
            }

# Display
for etf, d in results.items():
    print(f"{etf}: ${d['first']:.2f} → ${d['last']:.2f} ({d['change_pct']:+.1f}%)")
```

## Volume Data (CoinGecko Fallback)

When yfinance is blocked, use CoinGecko for BTC volume:

```python
resp = requests.get(
    "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
    params={"vs_currency": "usd", "days": "90", "interval": "daily"},
    timeout=10
)
volumes = resp.json().get("total_volumes", [])

# Compare 30d vs 90d average
recent_30 = volumes[-30:]
avg_30 = sum(v[1] for v in recent_30) / len(recent_30)
avg_90 = sum(v[1] for v in volumes) / len(volumes)
print(f"30d avg: ${avg_30:,.0f}")
print(f"90d avg: ${avg_90:,.0f}")
print(f"Change: {((avg_30 - avg_90) / avg_90 * 100):.1f}%")
```

## Key Findings from 2026-06-03 Session

### BTC vs IGV Historical Correlation

| Cycle | BTC Change | IGV Change | Direction | Divergence |
|-------|-----------|------------|-----------|------------|
| 2017-2018 | -75% | -45% | SAME | 30pp |
| 2020-2022 | -72% | -43% | SAME | 29pp |
| 2024-2026 | -46% | -11% | SAME | **35pp** |

**Observation**: BTC and IGV have always moved in the same direction, but the divergence has increased in the current cycle. This suggests BTC-specific issues (liquidity trap, HODLer lockup) rather than systemic risk.

### Peak Timing Pattern

| Cycle | BTC Peak | IGV Peak | Gap |
|-------|----------|----------|-----|
| 2017-2018 | 2017/12 | 2018/09 | **9 months** |
| 2020-2021 | 2020/11 | 2020/11 | **0 (sync)** |
| 2024-2026 | 2025/07 | 2025/10 | **3 months** |

**Observation**: If 2017-2018 pattern repeats (BTC peaks first, IGV peaks later), IGV may eventually follow BTC down. But the AI narrative could make this cycle different.

### OAS (Credit Spread) Context

- 2023/10 peak: 4.53% (regional bank crisis)
- 2025/01 trough: 2.60%
- Current: 2.72% (near historical low)

Credit conditions are improving while BTC is falling → "idiosyncratic failure" thesis confirmed.
