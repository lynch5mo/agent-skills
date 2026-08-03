# BTC Correlation Framework — TIPS, OAS, and Fiscal Liquidity (2026-06-04)

## User's Core Framework

The user treats BTC as a **risk asset**, not a safe haven or currency. Their original primary correlation indicator was the **5-year TIPS yield** (real yield = real cost of money).

### Original Logic Chain (2020-2022 era)

```
5Y TIPS Yield ↓ (real rates low/negative) → USD opportunity cost low → liquidity overflow → BTC ↑
5Y TIPS Yield ↑ (real rates rising) → USD attractive → capital回流 → BTC ↓
```

This was validated during 2020-2022 when Fed QE/QT was the dominant liquidity source.

## KEY FINDING: TIPS-BTC Correlation Broke Down (2023+)

### Measured Correlation (55 trading days, Feb-Jun 2026)

| Metric Pair | Correlation | Verdict |
|---|---|---|
| **BTC vs 5Y TIPS** | **-0.006** | ❌ Zero correlation |
| **BTC vs 10Y TIPS** | -0.164 | Very weak negative |
| **BTC vs OAS** | **-0.716** | ✅ Strong negative |

**TIPS is no longer the right anchor for BTC.** OAS (credit spread) is the correct medium-term driver.

## Why TIPS Broke: The Fiscal vs Monetary Shift

### Phase 1 (2020-2022): Fed QE/QT Dominant
```
Fed 扩表/缩表 → TIPS↓/↑ → BTC↑/↓
TIPS and BTC correlated because SAME source (Fed balance sheet)
```

### Phase 2 (2023+): Treasury Fiscal Expansion Takes Over
```
Fed maintains high rates → TIPS stays elevated
BUT Treasury runs $1.5-2T+ annual deficits → spending injects liquidity
TIPS and BTC DECOUPLE because DIFFERENT sources
```

**The mechanism**: Treasury issues bonds → buyers pay → Treasury spends on fiscal programs → money enters economy/financial markets. This creates liquidity WITHOUT Fed balance sheet expansion. So TIPS stays high (Fed policy) but risk assets benefit from fiscal spending.

### Supporting Data (Annual)

| FY | Deficit | YoY Change | BTC Year-End | Same Direction? |
|---|---|---|---|---|
| FY2020 | $3.1T | +218% | $10.8K | ✅ |
| FY2021 | $2.8T | -11% | $43.8K | ❌ (lagged) |
| FY2022 | $1.4T | -50% | $19.4K | ✅ |
| FY2023 | $1.7T | +23% | $27K | ✅ |
| FY2024 | $1.8T | +8% | $63.3K | ✅ |
| FY2025E | $1.9T | +4% | $82K | ❌ (narrative) |

Annual direction matches 4/6 years. Quarter-level correlation: +0.20 (weak positive) — fiscal deficits provide a floor, not a driver.

## 3-Layer Liquidity Model (Updated Framework)

```
┌─────────────────────────────────────────────┐
│  Layer 1: Treasury Fiscal Deficit (slow)     │
│  → Provides liquidity "floor"               │
│  → Determines BTC long-term valuation       │
│  → Annual correlation: +0.20 (weak)         │
├─────────────────────────────────────────────┤
│  Layer 2: OAS Credit Spread (fast)           │
│  → Reflects liquidity "tightness"           │
│  → Determines BTC medium-term trend         │
│  → Monthly correlation: -0.72 (strong)      │
├─────────────────────────────────────────────┤
│  Layer 3: Narrative/Leverage (instant)       │
│  → Determines BTC short-term volatility     │
│  → Current drop = AI narrative + carry unwind│
└─────────────────────────────────────────────┘
```

### Practical Use

| Indicator | BTC Signal | Confidence |
|---|---|---|
| OAS > 3.5% | Strong bearish | High |
| OAS 3.0-3.5% | Bearish | Medium-High |
| OAS 2.5-3.0% | Neutral | Medium |
| OAS < 2.5% | Bullish | Medium-High |
| 5Y TIPS > 2.0% | Minor headwind | Low |
| 5Y TIPS < 1.5% | Minor tailwind | Low |
| Fiscal deficit expanding | Long-term support | Low-Medium |

### 2026-06 Anomaly: OAS Stable but BTC Crashed

OAS at 2.71% (stable) but BTC dropped from $82K to $64K (-22%). This is Layer 3 (narrative/leverage) dominating:
- AI captured offense narrative
- Gold captured defense narrative
- Yen carry trade unwind
- Leverage washout

## Comparison with Other Frameworks

| Author | View | Alignment with User |
|---|---|---|
| 智堡 | BTC "priced in dollars", captured by fiat system | ✅ Consistent — TIPS IS the price of dollars (pre-2023) |
| Tigris | BTC = "high-beta derivative of global liquidity" | ✅ Consistent — OAS is the liquidity measure |
| User | BTC = shadow of total liquidity (Fed + Treasury) | ✅ Most complete — includes fiscal channel |

## Cross-Asset Overflow Framework (2026-06-04)

### Liquidity Transmission Chain

```
Treasury TGA↓ (fiscal spending) → injects liquidity
    ↓
Priority 1: US Equities (S&P/NASDAQ/QQQ)
    → Valuations rise → Risk appetite increases → OAS narrows
    ↓ Overflow
Priority 2: BTC/Crypto (high-beta, lags equities)
    → Narrative amplifies volatility
    ↓ Diversification
Priority 3: Gold (safe haven, competes with BTC for "supranational" narrative)
```

### Terminal Data Validation

| Quarter | TGA Change | OAS Change | BTC Return | Same Direction? |
|---------|-----------|-----------|-----------|----------------|
| 2025-Q1 | -$79B (spend) | -0.24 | +10% | ✅ |
| 2025-Q3 | +$20B | -0.10 | +8% | ✅ (lagged) |
| 2025-Q4 | **+$150B (absorb)** | +0.14 | **-4%** | ✅ |
| 2026-Q1 | -$19B | +0.07 | **-10%** | ❌ (narrative) |

**Key finding**: When TGA rises >$100B in a quarter (Treasury absorbing liquidity), BTC tends to drop in the next 1-2 months. 2025-Q3's $374B TGA spike was the true trigger for BTC's top.

### 2026 Feb Case Study: Gold vs BTC Divergence

- BTC: **-14.8%**
- Gold: **+11.0%**
- OAS: +0.24 (widening)
- TGA: +$64B (absorbing)

→ Liquidity contraction → capital flows OUT of BTC → some flows INTO gold (safe haven) → gold and BTC diverge

### Practical Signal Hierarchy

| Priority | Indicator | BTC Signal | Timeframe |
|----------|----------|-----------|-----------|
| 1 | OAS (credit spread) | Strongest correlation (-0.72) | Weekly-Monthly |
| 2 | TGA (Treasury balance) | Leading indicator (1-2 month lag) | Monthly-Quarterly |
| 3 | Fed rate | Background noise (2023+失效) | Quarterly |
| 4 | Gold vs BTC | Narrative competition indicator | Monthly |
| 5 | QQQ vs BTC | Overflow/lag relationship | Weekly |

## Data Sources

- FRED: `DFII05` (5Y TIPS yield), `BAMLH0A0HYM2` (OAS) — note FRED truncated OAS to 3 years from Apr 2026
- Alpha-FICC terminal: `tips5y`, `tips10y` series (user-added)
- Treasury fiscal data: CBO reports, Treasury Monthly Statement
- BTC data: `yfinance:BTC-USD` via Alpha-FICC
