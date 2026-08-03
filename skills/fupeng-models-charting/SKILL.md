---
name: fupeng-models-charting
description: Pull financial data from OpenBB FRED + akshare and chart Fupeng's (付鹏) core research models — real rate vs gold, CN-US spread vs FX, yield curve vs equities. Supports both PNG and terminal (plotext) output.
license: MIT
metadata:
  version: "1.0.0"
  author: lynch5mo
  category: knowledge-management
  triggers: [付鹏模型图表, 实际利率 vs 黄金, FICC数据图表, 从终端拉数据做付鹏图表, 中美利差图表]
---

# Fupeng Core Models — Financial Charting Pipeline

## Data Sources

| Region | Source | Method |
|--------|--------|--------|
| US (TIPS, Treasuries) | OpenBB → FRED | `dp.fetch("tips10y")`, `dp.fetch_dynamic_fred("DGS10")` |
| China (bonds, gold, FX) | akshare | `ak.bond_zh_us_rate()`, `ak.spot_golden_benchmark_sge()` |

**Critical**: OpenBB registry only has 47 series. Chinese bond/gold/FX data MUST come from akshare. DO NOT try to get CN data from OpenBB/FRED — it's not there.

## OpenBB DataProvider Usage

```python
import sys
sys.path.insert(0, '/Users/lynch5mo/Documents/OpenBB')
from services.data.series_registry import SeriesRegistry
from services.data.provider import DataProvider

reg = SeriesRegistry()
dp = DataProvider(registry=reg)

# Registry-managed series (47 total — check registry.yaml)
tips = dp.fetch("tips10y", start="2018-01-01", use_cache=True)
# tips10y → FRED DFII10 → 美国10年期TIPS实际收益率

# Dynamic FRED fetch (for series NOT in registry)
dgs = dp.fetch_dynamic_fred("DGS10", start="2018-01-01", use_cache=True)
# NOTE: use_cache=True helps when FRED SSL is flaky (intermittent SSLEOFError)

# Also available: T10YIE (breakeven inflation)
t10yie = dp.fetch_dynamic_fred("T10YIE", start="2018-01-01", use_cache=True)
```

### FRED SSL Issues
FRED API has intermittent `SSLEOFError: EOF occurred in violation of protocol`. When fetching fails:
1. Retry with `use_cache=True` — cached data from previous successful fetches works
2. Cache is at `runtime/cache/*.parquet` (needs pyarrow to read)
3. Registry `tips10y` is more reliable than `fetch_dynamic_fred` — prefer registry entries

### Data Verification
```python
# Verify: real_yield ≈ nominal - breakeven
df['implied_real'] = df['nominal'] - df['breakeven']
corr = df[['real_yield','implied_real']].corr().iloc[0,1]  # Should be ~1.0000
```

## akshare Data Sources

```python
import akshare as ak

# CN-US bond yields (9246 rows, 1990-2026)
bond = ak.bond_zh_us_rate()
bond = bond.set_index('日期')[['中国国债收益率10年','美国国债收益率10年','美国国债收益率10年-2年']]
bond['中美利差'] = bond['中国国债收益率10年'] - bond['美国国债收益率10年']

# SGE Gold benchmark (2438 rows, 2016-2026)
gold = ak.spot_golden_benchmark_sge()
gold = gold.set_index('交易时间')
gold['price'] = (gold['晚盘价'] + gold['早盘价']) / 2

# S&P 500 via Sina (5624 rows, 2004-2026)
spx = ak.index_us_stock_sina(symbol=".INX")
spx = spx.set_index('date')

# BOC CNY middle rate (7957 rows, 1994-2026)
cny = ak.currency_boc_safe()
cny = cny.set_index('日期')
cny['USDCNY'] = cny['美元'] / 100  # Convert from 人民币/100外币
cny['JPYCNY'] = cny['日元'] / 100
```

### akshare Pitfalls
- `bond_china_yield()` returns empty DataFrame — use `bond_zh_us_rate()` instead
- `futures_foreign_hist(symbol="黄金")` and `futures_foreign_hist(symbol="伦敦金")` fail with "Expected object or value" — use `spot_golden_benchmark_sge()` instead
- `currency_boc_sina()` only returns 180 rows — use `currency_boc_safe()` for 7957 rows
- `bond_us_yield()` and `bond_global_yield()` don't exist

## Fupeng's Core Chartable Models

### Model 1: Real Rate → Gold (Fupeng's pricing anchor)
```
公式: 实际利率 = 名义利率 - 通胀预期
逻辑: 实际利率↓ → 黄金↑
数据: TIPS 10Y (DFII10) vs SGE Gold
关键: 2020 年名义利率≈0 但通胀预期从 0.5%→2.5%，实际利率从 0→-1%，驱动黄金暴涨
      → 用名义利率代理完全丢失此信号
```

### Model 2: CN-US Spread → RMB
```
逻辑: 中美利差 = 资本流向方向标
数据: CN 10Y - US 10Y vs USDCNY
```

### Model 3: Yield Curve → Risk Assets (FICC anchor)
```
逻辑: 曲线倒挂 → 衰退预警 → FICC框架核心信号
数据: US 2s10s spread vs S&P 500
```

### Model 4: US-JP Spread → Carry Trade
```
逻辑: 利差扩大 → 借低息(JPY)投高息(USD) → 日元贬值趋势
数据: US 10Y vs JPYCNY (BOC proxy for USDJPY)
```

## Terminal Charting with plotext

### Critical plotext API Gotchas

```python
import plotext as plt

# 1. Date format: NO % prefix! plotext strips %
plt.date_form('Y-m')     # NOT '%Y-%m'
plt.date_form('d/m/Y')   # default, NOT '%d/%m/%Y'

# 2. date_form() MUST be called AFTER subplots()
plt.subplots(2, 2)
plt.date_form('Y-m')     # ← here, NOT before subplots!

# 3. hline/vline take ONLY 2 args
plt.hline(0, color='white')    # coordinate, color
plt.vline(date_str, color='red')  # coordinate, color

# 4. Use string dates matching date_form format
dates = [d.strftime('%Y-%m') for d in df.index]  # matches 'Y-m'
```

### Terminal Chart Template
```python
plt.clf(); plt.theme('dark')
plt.subplots(2, 2)
plt.date_form('Y-m')  # ← after subplots
W = min(plt.tw(), 110); H = 15

plt.subplot(1, 1)
plt.title("Title")
plt.plot_size(W-4, H)
plt.plot(dates, data_series, color='cyan')
plt.hline(0, color='white')
plt.ylabel('unit')

# ... repeat for other subplots ...
plt.show()
```

## Why Nominal Rate is NOT a Proxy for Real Rate

Fupeng's core formula demands the REAL rate. Using nominal as proxy:
- ❌ 2020 Q3-Q4: nominal stuck at 0.6%, but breakeven went 0.5%→2.3%
- ❌ Real rate went from 0 to -1% — this drove gold from 400→450
- ❌ Nominal proxy showed flat → completely missed the signal
- ✅ TIPS real yield captures both nominal AND inflation expectations

## Fupeng Knowledge Base Source Structure

```
raw/inbox/付鹏系列/
├── 付鹏日记2013-14/     # 27 files, early period
├── 公众号/              # 572 files, mid-period (付鹏的财经世界)
├── 付鹏说/              # 174 files, video transcripts
├── transcripts_md/      # 131 files
├── transcripts_video/   # 102 files
├── 付鹏：FICC金融知识架构/  # 70 files, FICC framework
├── 付鹏微信日志/         # 29 files, mature period
└── 付鹏大师课/           # 5 files

Wiki compiled: ~1100 summaries in wiki/summaries/finance/
Concept frequency (top 5): 经济学(432), 交易(383), 利率(325), 投资(319), 供给(261)
```

## Pitfalls

- Never use US 10Y nominal yield as proxy for real rate — Fupeng's formula requires TIPS
- OpenBB registry only covers US/FRED data — Chinese data requires akshare
- FRED SSL errors are intermittent — retry with cache, or use previously cached data
- plotext `date_form` has non-standard format (no `%`) and must go AFTER `subplots()`
- yfinance SSL failures are known (memory note) — use akshare for CN data, OpenBB/FRED for US
