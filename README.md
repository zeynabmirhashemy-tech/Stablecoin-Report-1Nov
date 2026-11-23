# Stablecoins and the Swiss franc: data and code

Data and code for the market report *Stablecoins and the Swiss franc* (data cut-off 1 November 2026). The report compares the stablecoin market on 1 May and 1 November 2026, with a focus on Swiss franc stablecoins.

## Contents

| Path | Content |
|---|---|
| `1_download.py` | Downloads the raw data into `data/` |
| `2_results.py` | Computes every figure, table and number in the report from `data/` |
| `data/` | Raw data as downloaded (19–21 Nov 2026) |
| `figures/` | Figures of the report (PNG) |
| `Fig_*.csv`, `Table_*.csv` | Numbers behind each figure and table, named by their number in the report |
| `Numbers_in_text.csv` | All other numbers in the text, with how each is computed |
| `index.csv` | List of all outputs, with full captions and the data used |

## Data sources

- **DefiLlama**: stablecoin supply by coin, chain and currency; collateral; DeFi yield pools
- **CoinGecko**: prices, market values and trading volumes
- **Federal Reserve (FRED), ECB, SNB, World Bank**: money stocks, interest and exchange rates, GDP
- **Public blockchain nodes**: on-chain supply of CHFAU (Ethereum, Base, Polygon) and CHF24 (Arbitrum)

## How to run

```bash
pip install pandas requests matplotlib

# 1. Download the data (optional: the downloaded data are already in data/)
export COINGECKO_API_KEY=YOUR_KEY   # free CoinGecko Demo key
python3 1_download.py

# 2. Compute figures, tables and numbers (no internet or API key needed)
python3 2_results.py
```

`1_download.py` can also run single steps, e.g. `python3 1_download.py defillama coingecko`. A re-download gives today's data, so results can differ from the report.

## Note

The CHF24 supply held by clients on Mantle (about CHF 0.05 m) was read separately from a public Mantle node and is not yet computed by `1_download.py`.
