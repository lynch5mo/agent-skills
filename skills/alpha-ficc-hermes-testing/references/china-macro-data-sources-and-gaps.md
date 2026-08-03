# China Macro Data Sources & Gaps

*Last verified: 2026-06-08*

## Working Data Sources

### FX & Dollar
| Series | Source | Status |
|--------|--------|--------|
| USDCNH | `usdcnh` (terminal built-in) | ✅ Daily, reliable |
| DXY (Trade Weighted) | `fred:DTWEXBGS` | ✅ Monthly, works |
| DXY (spot) | `yfinance:DX-Y.NYB` | ❌ Not in yfinance whitelist — returns N/A |

**Pitfall**: `yfinance:DX-Y.NYB` is silently accepted by the API (no error, no skippedSeriesIds) but returns no data points. Always use `fred:DTWEXBGS` for dollar strength analysis.

### China Equity
| Series | Source | Status |
|--------|--------|--------|
| CSI 300 | `akshare:index_csi300_close` | ✅ Daily, reliable |

### China Bond Yields
| Series | Source | Status |
|--------|--------|--------|
| CGB 10Y | `akshare:bond_china_cgb_10y` | ✅ Daily, reliable |

### Trade Data
| Series | Source | Status |
|--------|--------|--------|
| Exports YoY | `akshare:macro_china_exports_yoy` | ✅ Monthly |
| Imports YoY | `akshare:macro_china_imports_yoy` | ✅ Monthly |
| Trade balance (USD) | `akshare:macro_china_trade_balance_usd` | ✅ Monthly |
| Current account | `fred:CHNBCABP6USD` | ⚠️ Annual only, 3 data points |

### PMI
| Series | Source | Status |
|--------|--------|--------|
| Manufacturing PMI | `nbs:publicrelease:pmi_cn_mfg` | ✅ Monthly |
| New orders | `nbs:publicrelease:pmi_cn_mfg_new_orders` | ✅ Monthly |
| New export orders | `nbs:publicrelease:pmi_cn_mfg_export_orders` | ✅ Monthly |
| Imports | `nbs:publicrelease:pmi_cn_mfg_imports` | ✅ Monthly |
| Employment | `nbs:publicrelease:pmi_cn_mfg_employment` | ✅ Monthly |
| Production | `nbs:publicrelease:pmi_cn_mfg_production` | ✅ Monthly |

### FX Reserves / PBOC
| Series | Source | Status |
|--------|--------|--------|
| FX reserves | `akshare:macro_china_fx_reserves` | ✅ Monthly |
| PBOC foreign assets | `akshare:macro_china_pboc_foreign_assets` | ✅ Monthly |

## Known Data Gaps

### ❌ PMI Price Sub-Indices (Critical Gap)

The NBS publishes detailed PMI sub-indices including:
- 主要原材料购进价格 (Raw Material Purchase Price)
- 出厂价格 (Ex-Factory Price)

**Neither Alpha-FICC terminal nor akshare has these.** This is a systematic gap that prevents:
- Verifying margin compression claims (PMI price scissors analysis)
- Calculating the gap between input costs and output prices

**Workaround**: These sub-indices are available from:
- Wind (万德) terminal
- East Money (东方财富) — may be accessible via custom API scraping
- NBS official releases (manual lookup)

When an article cites PMI price sub-indices (e.g., "原材料购进价格 63.9, 出厂价格 55.4"), flag these as **unverifiable from terminal** and note the data gap explicitly.

### ⚠️ Export Structure Data

Terminal has top-line export/import YoY and trade balance, but lacks:
- Volume vs. price decomposition
- Product category breakdown
- Destination country breakdown

This makes it impossible to distinguish "genuine demand recovery" from "front-loading ahead of tariffs" using terminal data alone.

### ⚠️ USDCNH Granularity

USDCNH daily data can lag by 1-2 trading days. For real-time event analysis (e.g., Section 301 announcement on June 2), expect a delay before the FX reaction appears in the terminal.

## Verification Workflow for China Macro Research

When verifying a research article that makes claims about China macro:

1. **Pull all cited series** from terminal and align by date
2. **Check for missing variables**: If the article's causal chain depends on a variable not available in terminal (e.g., DXY, PMI sub-indices), flag this as a verification gap
3. **Time-window audit**: Recalculate the article's claimed changes using the article's own stated dates, not the absolute low-to-high
4. **Check intermediate extremes**: If the article uses start→end dates, check if the variable went significantly beyond those endpoints in between
5. **DXY overlay**: For any RMB strength claim, always pull `fred:DTWEXBGS` to decompose passive (USD-driven) vs. active (CNY-driven) components
6. **Mark unverifiable claims explicitly**: Separate "confirmed from terminal" from "cannot verify" in output
