# China Macro Cost-Analysis Workflow

Date: 2026-06-01
Source: User conversation — analyzing A-share direction via import category data

## Purpose

User pushes a chart from `/comparison` and asks for forward-looking A-share analysis. This reference captures the analytical methodology and data sources used.

## Step 1: Receive Chart Context

```
GET /api/comparison/current/context
Authorization: Bearer ${ALPH...act: series IDs, latest values, time window, workspace/panel IDs.

## Step 2: Identify the Transmission Chain

User's chart design typically follows a transmission chain pattern. Infer the chain from the series composition. Example (2026-06-01):

```
贸易基本面（出口/进口/顺差）→ 汇率（USDCNH）→ 股市（CSI 300）
```

## Step 3: Data Analysis — Separate Data from Inference

Hard rule: only state data facts first (dates, values, magnitudes). Label inferences explicitly. User expects disciplined data-driven analysis, not causal storytelling.

## Step 4: Dig Deeper — Import Category Breakdown

When user asks about cost impact from imports, need category-level data:

### Data Sources (by reliability)

1. **Trading Economics** (best for category breakdown):
   ```
   curl "https://tradingeconomics.com/china/imports-by-category" -H "User-Agent: Mozilla/5.0 ..."
   ```
   Returns annual category data (HS-2 level). Parse HTML table rows.

2. **akshare** — does NOT have import category breakdown. Only has:
   - `macro_china_imports_yoy()` — total import YoY
   - `macro_china_trade_balance()` — trade balance
   - No per-category import data

3. **China Customs (customs.gov.cn)** — blocked by WAF from overseas. Not accessible.

4. **World Bank WITS** — has annual data but requires session handling.

### Key Categories to Track

| Category | Share (2024) | Cost Impact |
|----------|-------------|-------------|
| Electronics (chips/semiconductors) | 22.6% | Low price volatility |
| Mineral fuels/oil | 19.5% | High — affects transport, chemicals, power |
| Iron ore | 9.7% | High — affects steel, construction |
| Machinery | 8.9% | Medium |
| Copper | 2.8% | High — affects electronics, construction |
| Plastics | 2.4% | Medium — petrochemical downstream |
| Agricultural (oilseeds/grain) | 2.4% | Medium — affects food/feed |

### Cost-Relevant Grouping

- **Raw materials** (oil + metals): ~33% of imports — directly affect manufacturing costs
- **Intermediate goods** (electronics + machinery): ~34% — core manufacturing inputs
- **Agricultural**: ~5% — food/feed cost pressure

## Step 5: Cross-Reference with Price Signals

Use akshare for proxy data:
- **PPI** (`macro_china_ppi_yearly()`): factory gate prices — if negative while import costs rise, margins are squeezed
- **CPI** (`macro_china_cpi_monthly()`): consumer prices — if flat, companies can't pass costs
- **Commodity price index** (`macro_china_commodity_price_index()`): input cost direction
- **BDI** (`macro_shipping_bdi()`): shipping/transport cost proxy

## Step 6: Present the Cost-Price Scissors

Core analytical output:

```
进口成本（上升）  vs  出厂价（下跌/flat）
     = 利润被挤压
```

Quantify: `actual cost increase ≈ import_price_change - RMB_appreciation`

## Output Format

1. Chart data summary (bullet points)
2. Transmission chain diagram (text art)
3. Import category breakdown (table)
4. Price signal comparison (PPI/CPI/commodity/BDI)
5. Cost-price scissors conclusion
6. Sector risk ranking (high/medium/low)
7. Clear judgment with caveat about data limitations

## Pitfalls

- akshare does NOT have import category data — don't waste time trying
- China Customs website blocks overseas requests — use Trading Economics
- PPI data on akshare (`macro_china_ppi_yearly()`) may lag by several months
- Cloudflare blocks Python urllib for alpha-ficc endpoints — use curl
- Always separate "data" from "inference" in analysis output — user is strict about this
