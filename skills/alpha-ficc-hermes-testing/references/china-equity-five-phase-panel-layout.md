# China Equity Five-Phase Analysis — Terminal Panel Layout

Date: 2026-06-08
Source: Hermes Agent session analyzing CSI300 rally from July 2024 to June 2026

## Purpose

Reusable panel layout for analyzing China A-share multi-phase rallies on the Alpha-FICC terminal. Pushes a single unified workspace with 5 panels covering price, FX, rates, PMI, and trade data — then annotates phase boundaries, extremes, and attribution analysis.

## When to Use

User asks to analyze an A-share/CSI300 rally with supporting data. Always use the terminal — **never generate matplotlib charts locally** (user corrected this: "你要用终端配图，不要自己生成图").

## Panel Layout

| Panel | Title | Series | Color | Notes |
|-------|-------|--------|-------|-------|
| panel-a-csi300 | CSI300 | `akshare:index_csi300_close` | `#1a237e` | equity kind, heightWeight 1.2 |
| panel-a-fx | USDCNH + DXY | `usdcnh` (left, `#c62828`, inverted), `fred:DTWEXBGS` (right, `#e65100`) | macro, 1.0 | USDCNH inverted so up=RMB stronger |
| panel-a-spread | CN-US 10Y Spread | `us10y` (`#e65100`), `akshare:bond_china_cgb_10y` (`#1565c0`) | policy, 1.0, zeroLine:true | Both on left axis; spread is visual gap |
| panel-a-pmi | PMI Sub-indices | `nbs:publicrelease:pmi_cn_mfg_export_orders` (`#1565c0`), `nbs:publicrelease:pmi_cn_mfg_imports` (`#e65100`) | macro, 1.0 | Add hline at 50 |
| panel-a-trade | Trade Balance + FX | `akshare:macro_china_trade_balance_usd` (left, `#2e7d32`), `akshare:macro_china_fx_reserves` (right, `#6a1b9a`) | macro, 1.0 | Dual axis |

## Series IDs Reference

```
Core daily:
  akshare:index_csi300_close     — CSI300 close
  usdcnh                         — USDCNH spot
  fred:DTWEXBGS                  — Trade Weighted USD Broad
  us10y                          — US 10Y Treasury yield
  akshare:bond_china_cgb_10y     — China 10Y CGB yield

PMI monthly:
  nbs:publicrelease:pmi_cn_mfg_export_orders  — New export orders
  nbs:publicrelease:pmi_cn_mfg_imports        — Imports PMI
  nbs:publicrelease:pmi_cn_mfg_new_orders     — New orders
  nbs:publicrelease:pmi_cn_mfg               — Headline manufacturing PMI

Trade monthly:
  akshare:macro_china_exports_yoy       — Exports YoY (%)
  akshare:macro_china_imports_yoy       — Imports YoY (%)
  akshare:macro_china_trade_balance_usd — Trade balance (USD 100M)

FX/Reserves monthly:
  akshare:macro_china_fx_reserves        — FX reserves (USD 100M)
  akshare:macro_china_pboc_foreign_assets — PBOC foreign assets (CNY 100M)
```

## Annotation Template

Push after chart is `applied`. Use the workspace ID from the chart action response.

### Phase Boundary Vertical Lines (on CSI300 panel)

Color-code by phase meaning:
- `#2e7d32` (green) — positive catalysts (policy bazooka, main rally)
- `#c62828` (red) — negative shocks (tariffs, Trump)
- `#1565c0` (blue) — recovery phases
- `#6a1b9a` (purple) — anomalous phases
- `#e65100` (orange) — transition periods

Key dates for 2024-2026 cycle:
- `2024-07-01` — analysis start
- `2024-09-24` — policy bazooka (solid line, width 2)
- `2024-10-01` — Phase I→II: tariff shock begins
- `2024-11-06` — Trump elected (dotted)
- `2025-02-01` — Phase II→III: tariffs implemented
- `2025-05-01` — Phase III→IV: main rally (solid, width 2)
- `2026-01-01` — Phase IV→V: anomalous final leg (solid, width 2)

### Horizontal Lines

- CSI300 low: `3159.25` (2024-09-13) — `#c62828`, dotted
- CSI300 high: `4998.34` (2026-05-13) — `#2e7d32`, dotted
- PMI 50 line: `panel-a-pmi` — `#c62828`, dashed
- Spread zero line: `panel-a-spread` — `#c62828`, dashed

### Text Annotations

Phase labels on CSI300 panel, placed near the middle of each phase at ~y=4400-4700:
- "I: 政策驱动 +27%"
- "II: 关税冲击 横盘守3900"
- "III: 关税落地 DXY-4.6%但RMB未动"
- "IV: 主升浪 +22.8% 利差改善22bp 传统逻辑完美成立"
- "V: 反常末段 +6% 利差恶化41bp仍涨 动量 > 利差定价"

FX panel:
- "USDCNH(红,倒轴) 7.35→6.77 / DXY(橙,右轴) 129→119 / 美元走弱贯穿全程 贡献RMB升值59-65%"
- "阶段III反常: DXY跌4.6% 但RMB纹丝不动 关税压制升值"

Spread panel:
- "阶段IV: 利差改善22bp CSI300涨22.8% → 传统逻辑完美成立"
- "阶段V: 利差恶化41bp CSI300仍涨6% → 动量 > 利差"

PMI panel:
- "2月低点: 出口订单45.0 进口45.6"
- "4月回50+: 出口50.3 进口50.1 经常项边际支撑RMB"

Trade panel:
- "贸易差额(绿柱) 5月: $848亿 / 外储(紫线,右轴) 4月: $3.41万亿 2015年来最高"

## API Call Template

```python
# Step 1: Push unified chart
POST /api/terminal-chart-actions
{
  "actionId": "hermes_full_story_{ts}",
  "actionType": "add_series_to_chart",
  "source": "external-hermes",
  "note": "CSI300 multi-phase: full data panorama",
  "target": {
    "seriesIds": [...all series from above...],
    "window": "3Y",
    "granularity": "D",
    "replaceSelection": true,
    "panelMode": "appendPanel",
    "workspace": { "id": "ws_full_story_{ts}", "panels": [...], "objects": [...] }
  }
}

# Step 2: Poll until applied
GET /api/agent-actions/{actionId}

# Step 3: Push annotations (flat format)
POST /api/terminal-chart-actions
{
  "actionId": "hermes_full_annotations_{ts}",
  "actionType": "add_chart_annotations",
  "source": "external-hermes",
  "workspaceId": "{ws_id}",
  "annotations": [...]
}
```

## Pitfalls

1. **Always use terminal, not matplotlib.** User explicitly corrected this: "你要用终端配图，不要自己生成图." When asked to produce charts for financial analysis, push to Alpha-FICC terminal — never generate PNGs locally.

2. **Single unified workspace > multiple workspaces.** Pushing separate charts to separate workspaces causes workspace-mismatch chaos when pushing annotations. One workspace with all panels avoids this.

3. **replaceSelection: true** ensures the user sees your chart immediately after refreshing `/comparison`.

4. **Time window matters.** User corrected: don't just analyze the recent window mentioned in an article. Trace back to the actual start of the rally (e.g., July 2024 for CSI300, not March 2026).

5. **DXY is a critical control variable.** Any analysis of RMB strength MUST include DXY to decompose USD weakness vs. genuine RMB strength. The terminal has `fred:DTWEXBGS` (Trade Weighted USD Broad). `yfinance:DX-Y.NYB` is NOT in the yfinance whitelist — use the FRED series.

6. **PMI price sub-indices are NOT available.** The terminal and akshare both lack raw material purchase price and ex-factory price sub-indices. These come from NBS official releases and require external sources. Don't claim to verify price-scissors claims without acknowledging this data gap.

7. **USDCNH granularity.** Daily data for `usdcnh` may lag by several days at the current edge. The latest available date may be 5-7 days behind the current date. Acknowledge this blind spot when analyzing post-event FX movement (e.g., Section 301 announced June 2 but USDCNH data ends May 29).
