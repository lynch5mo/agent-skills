# BTC Analysis Annotations Session (2026-06-03)

## Session Summary
Analyzed a tweet by Tigris (@tig88411109) about BTC's narrative squeeze, credit spread divergence, and carry trade unwind. Pushed analysis annotations to Alpha-FICC terminal chart.

## Annotation API Findings

### Flat Format Works (post-Codex-fix)
After Codex fixed the annotation rendering bug, the `terminal-chart-actions` endpoint started rejecting the nested `target.annotations` format with `INVALID_TARGET`. A simplified flat format works:

```python
payload = {
    "action": "add_chart_annotations",
    "workspaceId": ws_id,  # from GET /api/comparison/current/context
    "annotations": [
        {
            "type": "vertical-line",
            "panelId": "panel-btc-gold",
            "points": [{"x": "2026-05-10", "y": 0}],
            "color": "#8B0000",
            "text": "BTC peak",
            "visible": True,
            "locked": True,
            "axisSide": "left",
            "id": f"my_vline_{ts}"
        }
    ]
}
resp = requests.post(
    "https://alpha-ficc.lynch5mo.xyz/api/terminal-chart-actions",
    json=payload,
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    timeout=15
)
```

### trend-line Requires text Field
`trend-line` type returns `INVALID_ANNOTATION_TEXT_0` without `text`. Other types (`vertical-line`, `horizontal-line`) don't require it.

### Sequential Probe Pattern
When batch push fails with indexed error (e.g., `INVALID_ANNOTATION_TEXT_1`), test each annotation type individually to isolate the problematic one.

## Data Sources Used

### CoinGecko API (no key needed)
```python
resp = requests.get(
    "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
    params={"vs_currency": "usd", "days": "90", "interval": "daily"},
    timeout=10
)
data = resp.json()
volumes = data.get('total_volumes', [])  # [[timestamp_ms, volume_usd], ...]
```
Useful for BTC trading volume when yfinance is blocked.

### Alpha-FICC Chart Data for ETF Prices
```python
resp = requests.get(
    "https://alpha-ficc.lynch5mo.xyz/api/comparison/current/chart-data",
    headers=headers,
    params={"series": "yfinance:IBIT", "window": "6M", "granularity": "D"},
    timeout=10
)
```
Works for ETF tickers: IBIT, FBTC, GBTC, ARKB, BITB.

## Analysis Conclusions

1. **Credit spread thesis**: ✅ Fully valid. OAS -19.7% vs BTC -19% = idiosyncratic failure in risk-on environment.
2. **Narrative squeeze thesis**: ⚠️ Partially valid. IGV +40% proves capital rotation, but gold -15% contradicts pure safe-haven replacement.
3. **Carry trade unwind thesis**: ❌ Refuted. IGV +40% vs BTC -19% = complete divergence, not systemic deleveraging.

## User Preferences Expressed
- User expects visual analysis (trend lines, vertical lines) when asked to "划线", not just text boxes
- User confused test annotations with real analysis — always explicitly label annotation intent
