# FRED Data Truncation Issue (2026-06-03)

## Problem

The ICE BofA US High Yield Index OAS series (`BAMLH0A0HYM2`) on FRED was truncated to only 3 years of data starting April 2026. This is a **FRED policy change**, not a data provider bug.

## Evidence

FRED page meta tag states:
> "Starting in April 2026, this series will only include 3 years of observations. For more data, go to the source."

## Impact

- `BAMLH0A0HYM2` only returns data from ~2023-05 onwards
- Cannot access historical OAS data (e.g., 2008 crisis, 2020 COVID spike to 10%+)
- Affects any long-term credit spread analysis

## Workarounds

1. **ICE original source**: The data originates from ICE (Intercontinental Exchange), which acquired BofA's index business in 2020. Check `https://www.theice.com/` for historical data.
2. **BofA research portal**: `https://research.bankofamerica.com/` may have historical data.
3. **Alternative FRED series**: Check if older series codes exist (e.g., `BAMLH0A0HYM2EY` for yield instead of spread).
4. **Bloomberg terminal**: If available, Bloomberg has full historical OAS data.

## Alternative Series Available on FRED

| Series | Description | History |
|--------|-------------|---------|
| `BAMLH0A0HYM2` | ICE BofA US HY OAS (spread) | 2023-05+ only |
| `BAMLH0A0HYM2EY` | ICE BofA US HY yield | 2023-05+ only |
| `BAMLH0A0HYM3` | ICE BofA US HY 3Y OAS | May have longer history |

## Recommendation

For long-term OAS analysis (10+ years), the Alpha-FICC terminal's FRED data provider will not have sufficient history. Plan to either:
1. Fetch from ICE/BofA original source and import as custom data
2. Use a different proxy for credit stress (e.g., VIX, MOVE index)
3. Accept the 3-year limitation and focus on recent cycle analysis
