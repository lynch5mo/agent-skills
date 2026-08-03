# yfinance Universe Whitelist Pitfall

## Problem (2026-06-03)

The Alpha-FICC terminal's yfinance data provider uses a curated whitelist (`/app/services/data/yfinance_universe.py`) of ~204 tickers. When a ticker is NOT in the universe:

1. **Server silently accepts** the `add_series_to_chart` action — `skippedSeriesIds: []`, `unresolvedTerms: []`, HTTP 200, `ok: true`
2. **Frontend cannot fetch data** — the line doesn't render on the comparison chart
3. **No error in server logs** — the data provider never attempts to fetch the unknown ticker
4. **`/api/health` still shows** `dataProviderAvailable: true` — this only means the provider module is loaded, not that all tickers work

## Diagnosis

```bash
# Check if a ticker is in the universe
ssh lynch5mo@192.168.10.33 'docker exec alpha-ficc-api python3 -c "
import sys; sys.path.insert(0, \"/app\")
from services.data.yfinance_universe import YFINANCE_UNIVERSE
symbols = [item.symbol for item in YFINANCE_UNIVERSE]
print(\"IGV\" in symbols)  # False = not supported
"'

# List all available yfinance tickers
ssh lynch5mo@192.168.10.33 'docker exec alpha-ficc-api python3 -c "
import sys; sys.path.insert(0, \"/app\")
from services.data.yfinance_universe import YFINANCE_UNIVERSE
for item in sorted(YFINANCE_UNIVERSE, key=lambda x: x.symbol):
    print(f\"{item.symbol} | {item.label_en} | {item.instrument_type} | {item.validation_status}\")
"'
```

## Current Universe (204 tickers)

### Equity ETFs
SPY, QQQ, DIA, IWM, VTI, RSP, EFA, EEM, EWJ, EWG, EWU, INDA, EWZ, FXI, KWEB, ASHR

### Sector ETFs
XLK, XLF, XLE, XLV, XLI, XLP, XLY, XLU, XLB, XLC, XLRE, SMH, SOXX, ARKK, ITA, ICLN

### Fixed Income ETFs
TLT, IEF, SHY, TIP, BND, AGG, LQD, HYG, JNK, EMB

### Commodity/Currency ETFs
GLD, SLV, CPER, USO, UNG, DBA, UUP, FXE, FXY, VXX

### Equity Indices
BTC-USD, ^MOVE (plus standard indices via other providers)

### FRED Series
BAMLH0A0HYM2 (HY OAS), DGS10, DFII10, T10YIE, T5YIE, OVXCLS, GVZCLS, etc.

## Workaround Options

1. **Use a proxy ticker** from the whitelist (e.g., XLK instead of IGV for software exposure)
2. **Add the ticker to the universe** — requires modifying `yfinance_universe.py` in the Docker container and restarting the API
3. **Use a different data provider** — if the ticker is available via FRED, akshare, or another provider already in the system

## The IGV Case

Author's article (Tigris, 2026-02-06) argues BTC and IGV (iShares Expanded Tech-Software Sector ETF) are highly correlated due to carry trade unwind. IGV is the purest software ETF proxy. Available alternatives:
- **XLK** — broad tech sector (includes hardware, semis, software) — least pure but available
- **QQQ** — Nasdaq 100 (includes non-tech) — even less pure
- Neither captures the specific "software beta" correlation the author describes

Adding IGV to the whitelist would require:
```python
# In yfinance_universe.py, add a YFinanceInstrument entry:
YFinanceInstrument(
    symbol="IGV",
    label_zh="iShares 扩展软件板块ETF",
    label_en="iShares Expanded Tech-Software Sector ETF",
    asset_class="equity",
    category="sector_etf",
    group="technology_software",
    group_zh="软件",
    group_en="Software",
    region="us",
    currency="USD",
    exchange="NASDAQ",
    timezone="America/New_York",
    instrument_type="etf",
    quote_type="etf",
    unit="price",
    default_resolution="D",
    supported_resolutions=("D", "W", "M"),
    data_shapes=("close_series", "ohlcv_bars"),
    validation_status="candidate",
)
```
Then restart the API container: `docker restart alpha-ficc-api`
