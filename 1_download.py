"""
Stablecoins and the Swiss franc - step 1 of 2: download the data
=================================================================

Downloads every dataset the report uses and saves each one, unchanged, as a CSV
file in the folder "data" next to this script. No figures or tables are made
here; that is done by 2_results.py, which reads only these files.

Run in a terminal, from any folder:

    pip install requests pandas
    python3 1_download.py --api-key YOUR_COINGECKO_KEY

    The key is a free CoinGecko "Demo" key. Without one, the script still runs,
    but more slowly (stricter rate limits). You can also set it once per session:
        export COINGECKO_API_KEY=YOUR_COINGECKO_KEY      (macOS / Linux)

Run only some steps (names in STEPS below), e.g. after a failure:

    python3 1_download.py coingecko chf24 --api-key YOUR_COINGECKO_KEY

Runtime: about 30-60 minutes in total (the DefiLlama coin and pool histories
and the 100 CoinGecko coin histories take most of it).

Report dates: DATE_START (1 May 2026) and DATE_END (1 Nov 2026). "Value on a
date" always means the last value on or before that date.

Things to know before re-running:
  * CoinGecko's free API returns at most 365 days of daily history. The values
    for 1 May 2026 can therefore only be downloaded until about late April 2027.
  * Files ending in "_now" or "_latest" hold the values on the day of the
    download, not on 1 Nov 2026.
  * APIs revise their history, so a new download can differ slightly from the
    data the report was written with (downloaded 19-21 Nov 2026).
  * manual_inputs.csv holds the few numbers that have no API (from reports and
    web pages). They are written below in manual_inputs(), each with its source.

Output (folder "data"):
  manual_inputs.csv               hand-entered figures with source and link
  fred_series.csv                 US M1 and M2 (FRED)
  ecb_euro_money.csv              euro-area M1 and M2 (ECB)
  snb_snbmonagg.csv               Swiss M1, M2, sight deposits, banknotes (SNB)
  snb_zimoma.csv                  money market rates incl. SARON (SNB)
  snb_devkum.csv                  exchange rates, monthly (SNB)
  wb_gdp_emu_che.csv              GDP of the euro area and Switzerland (World Bank)
  dl_coins_list.csv               every stablecoin on DefiLlama, with currency and backing
  dl_total_supply_history.csv     daily total stablecoin supply, by currency, in USD
  dl_chain_history.csv            daily stablecoin supply of the 10 largest blockchains
  dl_all_coins_on_dates.csv       supply of every stablecoin on both report dates
  dl_coin_history.csv             daily supply of the 20 largest coins and all CHF coins
  dl_chf_chain_split_on_dates.csv supply of each CHF coin by blockchain on both dates
  dl_yield_pools_all_now.csv      every DeFi yield pool on the download day
  dl_yield_pools_tvl_on_dates.csv value in each pool (>= USD 1 m) on both dates
  dl_protocol_collateral_history.csv daily collateral (TVL) of Frankencoin (ZCHF) and HLiquity (HCHF)
  cg_comparators_history.csv      daily price, market value, volume: BTC, ETH, USDT, USDC
  cg_top_crypto_on_dates.csv      market value of the 100 largest crypto-assets on both dates
  cg_top_crypto_volume_on_dates.csv  30-day average daily trading volume of the same 100
  cg_top_crypto_latest.csv        market value of the same 100 on the download day
  cg_chf_coins_history.csv        daily price (CHF), market value, volume of the CHF coins
  cg_chf_contracts.csv            blockchains and contract addresses of the CHF coins
  chf_extra_supply_daily.csv      on-chain supply of CHFAU (not on DefiLlama)
  chf_extra_supply_check.csv      which public node answered, and today's CHFAU supply
  chf24_supply.csv                CHF24 (Fiat24): total supply, Fiat24's own accounts, clients
  chf24_internal_accounts.csv     CHF24 balance of each Fiat24 internal account (9000-9999)
  _download_log.csv               what was downloaded when, and what failed
"""

import argparse
import getpass
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

# ------------------------------------------------------------------ settings --
DATE_START = "2026-05-01"          # comparison date
DATE_END = "2026-11-01"            # cut-off date
DATES = (DATE_START, DATE_END)
TOP_N_COINS_HISTORY = 20           # largest stablecoins whose full daily history is saved
TOP_N_CHAINS = 10                  # largest blockchains whose stablecoin history is saved
TOP_N_CRYPTO = 100                 # crypto market approximated by the 100 largest crypto-assets
MIN_POOL_TVL_USD = 1e6             # yield pools smaller than this today are skipped

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 stablecoin-report/2.0"})
LOG = []
CG_HEADERS, CG_PAUSE = None, 15.0  # set in main() once the API key is known


# ------------------------------------------------------------------- helpers --
def log(msg):
    print(msg, flush=True)
    LOG.append({"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "message": msg})


def get_json(url, params=None, headers=None, pause=0.0, tries=4):
    """GET a JSON answer; waits and retries when the API says 'too many requests'."""
    for attempt in range(tries):
        try:
            r = SESSION.get(url, params=params, headers=headers, timeout=90)
        except requests.RequestException as e:
            if attempt == tries - 1:
                raise
            log(f"  connection problem ({e.__class__.__name__}), retrying")
            time.sleep(10 * (attempt + 1))
            continue
        if r.status_code == 429:
            wait = 60 * (attempt + 1)
            log(f"  rate limited, waiting {wait} s")
            time.sleep(wait)
            continue
        r.raise_for_status()
        time.sleep(pause)
        return r.json()
    r.raise_for_status()


def save(name, df):
    df.to_csv(DATA / f"{name}.csv", index=False)
    log(f"  saved data/{name}.csv ({len(df)} rows)")


def ts_to_date(ts):
    return datetime.fromtimestamp(int(ts), tz=timezone.utc).date()


def native_sum(d):
    """Sum of a DefiLlama 'circulating' dict, e.g. {'peggedCHF': 123.0}."""
    return sum(v for v in (d or {}).values() if isinstance(v, (int, float)))


def value_on(df, day, col="value"):
    """Last value on or before `day` from a frame with a 'date' column."""
    sub = df[pd.to_datetime(df["date"]) <= pd.Timestamp(day)]
    return sub[col].iloc[-1] if len(sub) else None


# =============================================================================
# 1. Figures without an API (entered by hand, each with its source)
# =============================================================================
def manual_inputs():
    log("Manual inputs: figures from reports and web pages")
    mck_art = ("https://www.mckinsey.com/industries/financial-services/our-insights/"
               "stablecoins-in-payments-what-the-raw-transaction-numbers-miss")
    mck_chart = "https://www.mckinsey.com/featured-insights/charts/stablecoins-find-their-niche"
    ici = "https://www.ici.org/research/stats/mmf"
    rows = [
        # key, value, unit, as_of, source, link, note
        ["mmf_us_assets", 7901, "USD bn", "2026-10-28", "ICI, Money Market Fund Assets, weekly release 29 Oct 2026",
         ici, "Week ended 28 Oct 2026"],
        ["mmf_us_assets_may", 7626, "USD bn", "2026-04-29", "ICI, Money Market Fund Assets, weekly release",
         ici, "Week ended 29 Apr 2026 (comparison only, not used in a figure)"],
        ["payments_real_total", 390, "USD bn per year", "2025-12", "McKinsey & Company (2026a), with Artemis",
         mck_art, "Real stablecoin payments, annualised from December 2025"],
        ["payments_global_total", 2_000_000, "USD bn per year", "2025", "McKinsey & Company (2026a)",
         mck_art, "About USD 2 quadrillion; used only for the 'about 0.02%' figure"],
        ["payments_B2B", 226, "USD bn per year", "2025-12", "McKinsey & Company (2026b)", mck_chart, ""],
        ["payments_C2C", 77, "USD bn per year", "2025-12", "McKinsey & Company (2026b)", mck_chart, ""],
        ["payments_C2B", 76, "USD bn per year", "2025-12", "McKinsey & Company (2026b)", mck_chart, ""],
        ["payments_B2C", 11, "USD bn per year", "2025-12", "McKinsey & Company (2026b)", mck_chart,
         "Remainder 390 - 226 - 77 - 76; McKinsey labels it business-to-consumer"],
        ["penetration_B2B", 0.01, "% of all B2B payments", "2025", "McKinsey & Company (2026b)", mck_chart, ""],
        ["penetration_C2C", 0.37, "% of all C2C payments", "2025", "McKinsey & Company (2026b)", mck_chart, ""],
        ["penetration_C2B", 0.11, "% of all C2B payments", "2025", "McKinsey & Company (2026b)", mck_chart, ""],
        ["penetration_B2C", 0.01, "% of all B2C payments", "2025", "McKinsey & Company (2026b)", mck_chart, ""],
        ["tether_assets", 191.45, "USD bn", "2026-09-30", "Tether Q3 2026 attestation (BDO Italia)",
         "https://tether.io/transparency/", "Total reserve assets"],
        ["tether_liabilities", 183.50, "USD bn", "2026-09-30", "Tether Q3 2026 attestation (BDO Italia)",
         "https://tether.io/transparency/", ""],
        ["circle_reserves", 74.0, "USD bn", "2026-09-30", "Crypto Briefing (2026), Circle Q3 2026 reserves",
         "https://cryptobriefing.com", "About USD 74 bn"],
        ["usdc_outstanding", 73.9, "USD bn", "2026-09-30", "Crypto Briefing (2026), Circle Q3 2026 reserves",
         "https://cryptobriefing.com", ""],
        ["hchf_min_ratio", 1.10, "x", "", "HLiquity documentation", "https://hliquity.org", "Minimum collateral ratio"],
        ["chfm_collateral", 119_575, "USD (USDm)", "2026-11-20", "Mento reserve dashboard, CHFm CDP",
         "https://reserve.mento.org", "Collateral in Mento dollars"],
        ["chfm_debt_value", 61_991, "USD", "2026-11-20", "Mento reserve dashboard, CHFm CDP",
         "https://reserve.mento.org", "USD value of the 52,176 CHFm outstanding, at the dashboard's rate"],
        ["chfm_outstanding", 52_176, "CHFm", "2026-11-20", "Mento reserve dashboard, CHFm CDP",
         "https://reserve.mento.org", ""],
        ["chfm_min_ratio", 1.50, "x", "", "Mento documentation", "https://docs.mento.org", "Minimum collateral ratio"],
    ]
    cols = ["key", "value", "unit", "as_of", "source", "link", "note"]
    save("manual_inputs", pd.DataFrame(rows, columns=cols))


# =============================================================================
# 2. Money and GDP: FRED, ECB, SNB, World Bank (no key)
# =============================================================================
FRED_SERIES = {"M1SL": "US M1 (USD bn, monthly, seasonally adjusted)",
               "M2SL": "US M2 (USD bn, monthly, seasonally adjusted)"}


def fred():
    log("FRED: US M1 and M2")
    frames = []
    for sid, label in FRED_SERIES.items():
        df = pd.read_csv(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}")
        df.columns = ["date", "value"]
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df["series"], df["description"] = sid, label
        frames.append(df[df["date"] >= "2019-01-01"])
        time.sleep(0.5)
    save("fred_series", pd.concat(frames))


ECB_SERIES = {"BSI/M.U2.Y.V.M10.X.1.U2.2300.Z01.E": "Euro area M1 (EUR mn, monthly)",
              "BSI/M.U2.Y.V.M20.X.1.U2.2300.Z01.E": "Euro area M2 (EUR mn, monthly)"}


def ecb():
    log("ECB: euro-area M1 and M2")
    frames = []
    for key, label in ECB_SERIES.items():
        url = f"https://data-api.ecb.europa.eu/service/data/{key}?format=csvdata&startPeriod=2019-01"
        df = pd.read_csv(url)[["TIME_PERIOD", "OBS_VALUE"]]
        df.columns = ["date", "value"]
        df["series"], df["description"] = key, label
        frames.append(df)
    save("ecb_euro_money", pd.concat(frames))


SNB_CUBES = {"snbmonagg": "Swiss monetary aggregates (M1, M2, M3, sight deposits, banknotes)",
             "zimoma": "Money market rates incl. SARON",
             "devkum": "Exchange rates, monthly"}


def snb():
    log("SNB data portal: Swiss money, SARON and exchange rates")
    for cube, label in SNB_CUBES.items():
        df = pd.read_csv(f"https://data.snb.ch/api/cube/{cube}/data/csv/en", sep=";", skiprows=2)
        df["cube"], df["description"] = cube, label
        save(f"snb_{cube}", df)
        time.sleep(0.5)


def worldbank():
    log("World Bank: GDP of the euro area and Switzerland")
    d = get_json("https://api.worldbank.org/v2/country/EMU;CHE/indicator/NY.GDP.MKTP.CD",
                 params={"format": "json", "date": "2022:2025", "per_page": 100})
    rows = [{"country": x["country"]["value"], "iso3": x["countryiso3code"], "year": int(x["date"]),
             "gdp_usd_bn": x["value"] / 1e9 if x["value"] else None} for x in d[1]]
    save("wb_gdp_emu_che", pd.DataFrame(rows).sort_values(["iso3", "year"]))


# =============================================================================
# 3. DefiLlama stablecoins (no key)
# =============================================================================
DL = "https://stablecoins.llama.fi"


def defillama():
    log("DefiLlama: list of all stablecoins")
    raw = get_json(f"{DL}/stablecoins", params={"includePrices": "true"})["peggedAssets"]
    coins = pd.DataFrame([{
        "id": a.get("id"), "name": a.get("name"), "symbol": a.get("symbol"),
        "pegType": a.get("pegType"), "pegMechanism": a.get("pegMechanism"),
        "circulating_native_units": native_sum(a.get("circulating")),
        "price_usd": a.get("price"),
        "chains": ", ".join(a.get("chains") or []),
        "n_chains": len(a.get("chains") or []),
    } for a in raw])
    coins["circulating_usd_approx"] = coins["circulating_native_units"] * coins["price_usd"].fillna(1)
    coins = coins.sort_values("circulating_usd_approx", ascending=False).reset_index(drop=True)
    save("dl_coins_list", coins)

    log("DefiLlama: total stablecoin supply history, by currency (USD)")
    h = []
    for p in get_json(f"{DL}/stablecoincharts/all"):
        row = {"date": ts_to_date(p["date"])}
        row.update({f"{k}_usd": v for k, v in (p.get("totalCirculatingUSD") or {}).items()})
        h.append(row)
    h = pd.DataFrame(h).fillna(0)
    h["total_usd"] = h[[c for c in h.columns if c != "date"]].sum(axis=1)
    save("dl_total_supply_history", h)

    log(f"DefiLlama: supply history of the {TOP_N_CHAINS} largest blockchains")
    chains = pd.DataFrame(get_json(f"{DL}/stablecoinchains"))
    chains["total_usd"] = chains["totalCirculatingUSD"].apply(
        lambda d: sum(d.values()) if isinstance(d, dict) else 0)
    chain_hist = []
    for ch in chains.sort_values("total_usd", ascending=False)["name"].head(TOP_N_CHAINS):
        try:
            for p in get_json(f"{DL}/stablecoincharts/{ch}", pause=0.5):
                chain_hist.append({"chain": ch, "date": ts_to_date(p["date"]),
                                   "total_usd": sum((p.get("totalCirculatingUSD") or {}).values())})
        except Exception as e:
            log(f"  FAILED chain {ch}: {e}")
    save("dl_chain_history", pd.DataFrame(chain_hist))

    log(f"DefiLlama: history of each of the {len(coins)} stablecoins (takes several minutes)")
    chf_ids = set(coins.loc[coins["pegType"] == "peggedCHF", "id"])
    keep_ids = set(coins["id"].head(TOP_N_COINS_HISTORY)) | chf_ids
    on_dates, history, chf_chains = [], [], []
    for i, c in coins.iterrows():
        try:
            d = get_json(f"{DL}/stablecoin/{c['id']}", pause=0.3)
        except Exception as e:
            log(f"  FAILED {c['symbol']}: {e}")
            continue
        s = pd.DataFrame([{"date": ts_to_date(t["date"]), "value": native_sum(t.get("circulating"))}
                          for t in (d.get("tokens") or [])])
        if len(s):
            on_dates.append({"id": c["id"], "symbol": c["symbol"], "pegType": c["pegType"],
                             "first_date": s["date"].min(),
                             f"supply_{DATE_START}": value_on(s, DATE_START),
                             f"supply_{DATE_END}": value_on(s, DATE_END)})
        if c["id"] in keep_ids and len(s):
            history.append(s.rename(columns={"value": "circulating_native_units"})
                           .assign(id=c["id"], symbol=c["symbol"], pegType=c["pegType"]))
        if c["id"] in chf_ids:
            for ch, cb in (d.get("chainBalances") or {}).items():
                cs = pd.DataFrame([{"date": ts_to_date(t["date"]), "value": native_sum(t.get("circulating"))}
                                   for t in (cb.get("tokens") or [])])
                if len(cs):
                    chf_chains.append({"symbol": c["symbol"], "chain": ch,
                                       f"supply_{DATE_START}": value_on(cs, DATE_START),
                                       f"supply_{DATE_END}": value_on(cs, DATE_END)})
        if i and i % 50 == 0:
            log(f"  ... {i} coins done")
    save("dl_all_coins_on_dates", pd.DataFrame(on_dates))
    save("dl_coin_history", pd.concat(history))
    save("dl_chf_chain_split_on_dates", pd.DataFrame(chf_chains))
    log("  NOTE: per-coin supplies are in each coin's own currency (CHF coins in CHF, euro coins in EUR).")


def yields():
    """Value (TVL) in every DeFi yield pool of at least USD 1 m, on both report dates."""
    y = "https://yields.llama.fi"
    log("DefiLlama Yields: all pools today")
    pools = pd.DataFrame(get_json(f"{y}/pools")["data"])
    keep = ["pool", "chain", "project", "symbol", "tvlUsd", "stablecoin", "exposure"]
    pools = pools[[c for c in keep if c in pools.columns]]
    save("dl_yield_pools_all_now", pools)
    sel = pools[pools["tvlUsd"] >= MIN_POOL_TVL_USD]
    log(f"  history of {len(sel)} pools with at least USD {MIN_POOL_TVL_USD / 1e6:g} m (10-30 minutes)")
    rows = []
    for n, p in enumerate(sel.itertuples(index=False), 1):
        try:
            h = pd.DataFrame(get_json(f"{y}/chart/{p.pool}", pause=0.3)["data"])
            h["date"] = pd.to_datetime(h["timestamp"], utc=True).dt.tz_convert(None).dt.normalize()
            h = h.sort_values("date")
            tvl = {}
            for day in DATES:
                before = h[h["date"] <= pd.Timestamp(day)]
                tvl[day] = before["tvlUsd"].iloc[-1] if len(before) else 0.0   # not yet launched = 0
            rows.append({"pool": p.pool, "project": p.project, "chain": p.chain, "symbol": p.symbol,
                         "stablecoin": bool(p.stablecoin),
                         f"tvl_{DATE_START}": tvl[DATE_START], f"tvl_{DATE_END}": tvl[DATE_END]})
        except Exception as e:
            log(f"  FAILED pool {p.pool} ({p.project} {p.symbol}): {e}")
        if n % 200 == 0:
            log(f"  ... {n} of {len(sel)} pools done")
    save("dl_yield_pools_tvl_on_dates", pd.DataFrame(rows))


PROTOCOLS = {"frankencoin": "ZCHF", "hliquity": "HCHF"}     # DefiLlama protocol name -> CHF coin it backs
NOT_CHAINS = {"staking", "pool2", "borrowed", "vesting", "treasury", "offers", "doublecounted",
              "liquidstaking", "govtokens", "dcAndLsOverlap"}


def protocols():
    """Collateral behind the crypto-backed CHF coins = the protocol's TVL on DefiLlama (default definition:
    the value locked on each blockchain, without staking, pool2 or borrowed amounts).
    Frankencoin: collateral in minting positions; HLiquity: HBAR deposited for borrowed HCHF."""
    log("DefiLlama: collateral (TVL) history of Frankencoin and HLiquity")
    rows = []
    for slug, coin in PROTOCOLS.items():
        d = get_json(f"https://api.llama.fi/protocol/{slug}", pause=0.5)
        chains = [k for k in (d.get("chainTvls") or {}) if "-" not in k and k not in NOT_CHAINS]
        for ch in chains:
            for p in d["chainTvls"][ch].get("tvl") or []:
                rows.append({"protocol": slug, "coin": coin, "chain": ch, "date": ts_to_date(p["date"]),
                             "tvl_usd": p["totalLiquidityUSD"]})
        log(f"  {slug}: chains used {', '.join(chains)}")
    save("dl_protocol_collateral_history", pd.DataFrame(rows))


# =============================================================================
# 4. CoinGecko (Demo API key optional)
# =============================================================================
CG = "https://api.coingecko.com/api/v3"
COMPARATORS = ["bitcoin", "ethereum", "tether", "usd-coin"]
CHF_COINS = {"allunity-chf": "CHFAU", "frankencoin": "ZCHF", "vnx-swiss-franc": "VCHF",
             "hedera-swiss-franc": "HCHF"}          # CHFm (Mento) is not listed on CoinGecko


def cg_market_chart(coin_id, vs="usd", days=365):
    d = get_json(f"{CG}/coins/{coin_id}/market_chart",
                 params={"vs_currency": vs, "days": days, "interval": "daily"},
                 headers=CG_HEADERS, pause=CG_PAUSE)
    df = pd.DataFrame({
        "date": [ts_to_date(p[0] / 1000) for p in d["prices"]],
        "price": [p[1] for p in d["prices"]],
        "market_cap": [p[1] for p in d["market_caps"]],
        "volume_24h": [p[1] for p in d["total_volumes"]],
    })
    df["coin_id"], df["vs_currency"] = coin_id, vs
    return df.drop_duplicates("date", keep="last")


def coingecko():
    log("CoinGecko: Bitcoin, Ether, USDT and USDC, daily history in USD")
    save("cg_comparators_history", pd.concat([cg_market_chart(c) for c in COMPARATORS]))

    log(f"CoinGecko: the {TOP_N_CRYPTO} largest crypto-assets (one history call each, several minutes)")
    top = get_json(f"{CG}/coins/markets", params={"vs_currency": "usd", "order": "market_cap_desc",
                                                   "per_page": TOP_N_CRYPTO, "page": 1},
                   headers=CG_HEADERS, pause=CG_PAUSE)
    today = datetime.now(timezone.utc).date()
    save("cg_top_crypto_latest", pd.DataFrame(
        [{"id": c["id"], "market_cap_usd": c["market_cap"], "date_pulled": today} for c in top]))
    mcap, vol = [], []
    for n, c in enumerate(top, 1):
        try:
            h = cg_market_chart(c["id"])
        except Exception as e:
            log(f"  FAILED {c['id']}: {e}")
            continue
        h["value"] = h["market_cap"]
        mcap.append({"id": c["id"], "symbol": c["symbol"],
                     f"mcap_{DATE_START}": value_on(h, DATE_START), f"mcap_{DATE_END}": value_on(h, DATE_END)})
        v = h.set_index(pd.to_datetime(h["date"]))["volume_24h"]
        vol.append({"id": c["id"], "symbol": c["symbol"],     # 30-day average up to and including each date
                    f"vol30_{DATE_START}": v.loc[:DATE_START].tail(30).mean(),
                    f"vol30_{DATE_END}": v.loc[:DATE_END].tail(30).mean()})
        if n % 10 == 0:
            log(f"  ... {n} of {len(top)} coins done")
    save("cg_top_crypto_on_dates", pd.DataFrame(mcap))
    save("cg_top_crypto_volume_on_dates", pd.DataFrame(vol))

    log("CoinGecko: Swiss franc coins, daily history in CHF, and their blockchains")
    chf = pd.concat([cg_market_chart(cid, "chf") for cid in CHF_COINS])
    chf["peg_deviation_bp"] = (chf["price"] - 1) * 10_000
    save("cg_chf_coins_history", chf)
    rows = []
    for cid, sym in CHF_COINS.items():
        d = get_json(f"{CG}/coins/{cid}", params={"localization": "false", "tickers": "false",
                                                  "market_data": "false", "community_data": "false",
                                                  "developer_data": "false"},
                     headers=CG_HEADERS, pause=CG_PAUSE)
        for plat, info in (d.get("detail_platforms") or {}).items():
            if info and info.get("contract_address"):
                rows.append({"symbol": sym, "coin_id": cid, "platform": plat,
                             "contract_address": info["contract_address"],
                             "decimals": info.get("decimal_place"), "source": "CoinGecko"})
    save("cg_chf_contracts", pd.DataFrame(rows))
    log("  NOTE: the free API returns at most 365 days of daily history.")


# =============================================================================
# 5. On-chain data from public blockchain nodes (no key)
# =============================================================================
RPC = {
    "Ethereum": ["https://ethereum-rpc.publicnode.com", "https://eth.drpc.org", "https://eth.llamarpc.com",
                 "https://cloudflare-eth.com"],
    "Base": ["https://base-rpc.publicnode.com", "https://base.drpc.org", "https://mainnet.base.org"],
    "Polygon": ["https://polygon-bor-rpc.publicnode.com", "https://polygon.drpc.org", "https://polygon-rpc.com"],
    "Arbitrum": ["https://arbitrum-one.public.blastapi.io", "https://arbitrum.drpc.org",
                 "https://arbitrum-one-rpc.publicnode.com", "https://arb1.arbitrum.io/rpc", "https://1rpc.io/arb",
                 "https://arbitrum.meowrpc.com"],
    "Mantle": ["https://rpc.mantle.xyz", "https://mantle-rpc.publicnode.com", "https://mantle.drpc.org",
               "https://1rpc.io/mantle"],
}
TOTAL_SUPPLY, BALANCE_OF, OWNER_OF = "0x18160ddd", "0x70a08231", "0x6352211e"   # ERC-20 / ERC-721 functions


class Node:
    """A public JSON-RPC endpoint of one blockchain."""

    def __init__(self, url):
        self.url, self.n = url, 0

    def post(self, payload):
        for i in range(4):
            try:
                r = requests.post(self.url, json=payload, timeout=60,
                                  headers={"Content-Type": "application/json",
                                           "User-Agent": "Mozilla/5.0 stablecoin-report/2.0"})
                if r.status_code == 200:
                    return r.json()
                if r.status_code in (429, 502, 503, 504):
                    time.sleep(3 * (i + 1))
                    continue
                raise RuntimeError(f"HTTP {r.status_code}")
            except requests.RequestException:
                time.sleep(3 * (i + 1))
        raise RuntimeError("no answer")

    def call(self, method, params):
        self.n += 1
        js = self.post({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params})
        if "error" in js:
            raise RuntimeError(str(js["error"])[:150])
        return js["result"]

    def calls(self, items, size=50):
        """Many eth_calls; batched if the node allows it, one by one otherwise. Failed calls give None."""
        out = []
        for k in range(0, len(items), size):
            chunk = items[k:k + size]
            batch = [{"jsonrpc": "2.0", "id": j, "method": "eth_call", "params": p} for j, p in enumerate(chunk)]
            try:
                res = self.post(batch)
                if not isinstance(res, list):
                    raise RuntimeError("no batch")
                res = {x["id"]: x.get("result") for x in res}
                out += [res.get(j) for j in range(len(chunk))]
            except Exception:
                for p in chunk:
                    try:
                        out.append(self.call("eth_call", p))
                    except Exception:
                        out.append(None)
                    time.sleep(0.1)
            time.sleep(0.3)
        return out

    def block(self, number):
        b = self.call("eth_getBlockByNumber", [hex(number) if isinstance(number, int) else number, False])
        return int(b["number"], 16), int(b["timestamp"], 16)

    def block_before(self, day, latest):
        """Highest block with a timestamp before 00:00 UTC on `day` (interpolation, then bisection)."""
        ts = pd.Timestamp(day, tz="UTC").timestamp()
        lo, lo_t = 1, self.block(1)[1]
        hi, hi_t = latest
        if ts > hi_t:
            return hi
        for _ in range(60):
            if hi - lo <= 1:
                break
            guess = lo + int((ts - lo_t) / max(hi_t - lo_t, 1) * (hi - lo))
            guess = min(max(guess, lo + 1), hi - 1)
            if hi - lo > 64:
                guess = (guess * 3 + (lo + hi) // 2) // 4
            _, t = self.block(guess)
            if t < ts:
                lo, lo_t = guess, t
            else:
                hi, hi_t = guess, t
        return lo

    def total_supply(self, contract, decimals, blk):
        res = self.call("eth_call", [{"to": contract, "data": TOTAL_SUPPLY}, hex(blk)])
        return 0.0 if res in ("0x", None) else int(res, 16) / 10 ** decimals   # "0x" = not yet deployed


def first_node(chain, contract, decimals, test_day):
    """First endpoint that can read the token at an old block (needs an archive node)."""
    for url in RPC[chain]:
        node = Node(url)
        try:
            latest = node.block("latest")
            node.total_supply(contract, decimals, node.block_before(test_day, latest))
            log(f"  {chain}: using {url}")
            return node, latest
        except Exception as e:
            log(f"  {chain}: {url} did not work ({str(e)[:100]})")
    return None, None


CHFAU = "0xbd4dfc058eb95b8de5ceaf39966a1a70f5556f78"     # same address on Ethereum, Base and Polygon, 6 decimals


def chf_onchain():
    """CHFAU supply on its EVM chains. Not on DefiLlama, and CoinGecko's history starts only on 4 Aug 2026.
    Dates: every Monday from 23 Feb 2026, plus launch day (26 Feb), 1 May, 4 Aug and 1 Nov 2026.
    Not covered: Solana (from 5 Aug 2026, after CoinGecko's history starts), Tempo and Arc."""
    log("On-chain: CHFAU total supply (Ethereum, Base, Polygon)")
    days = sorted(set(pd.date_range("2026-02-23", "2026-11-16", freq="W-MON").strftime("%Y-%m-%d"))
                  | {"2026-02-26", DATE_START, "2026-08-04", DATE_END})
    rows, checks = [], []
    for chain in ("Ethereum", "Base", "Polygon"):
        node, latest = first_node(chain, CHFAU, 6, "2026-03-01")
        if node is None:
            log(f"  FAILED: no {chain} endpoint answered")
            continue
        for day in days:
            try:
                rows.append({"date": day, "coin": "CHFAU", "chain": chain,
                             "supply": round(node.total_supply(CHFAU, 6, node.block_before(day, latest)), 2)})
            except Exception as e:
                log(f"  {chain} {day}: {str(e)[:120]}")
            time.sleep(0.2)
        checks.append({"coin": "CHFAU", "chain": chain, "endpoint": node.url,
                       "supply_today": round(node.total_supply(CHFAU, 6, latest[0]), 2)})
    out = pd.DataFrame(rows)
    tot = out.groupby(["date", "coin"], as_index=False)["supply"].sum().assign(chain="total")
    out = pd.concat([out, tot])[["date", "coin", "chain", "supply"]].sort_values(["coin", "chain", "date"])
    save("chf_extra_supply_daily", out)
    save("chf_extra_supply_check", pd.DataFrame(checks))


CHF24 = {"Arbitrum": "0xd41f1f0cf89fd239ca4c1f8e8ada46345c86b0a4",
         "Mantle": "0x53587a05ccddce555c2cd7ce4c9c5bc3d912e2f3"}
FIAT24_ACCOUNT_NFT = "0x133caeeca096ca54889db71956c7f75862ead7a0"    # Fiat24Account contract on Arbitrum
CHF24_DAYS = [DATE_START, "2026-08-04", DATE_END]


def chf24():
    """CHF24 (Fiat24) held by clients = totalSupply on Arbitrum minus the balances of Fiat24's own accounts.
    Fiat24 accounts are NFTs of the Fiat24Account contract; the NFT number is the account number. Accounts
    9000-9999 are Fiat24's internal accounts (developer documentation), e.g. 9101 'Cash In Desk'.
    On Mantle only totalSupply is read: Fiat24's own holdings there cannot be identified."""
    log("On-chain: CHF24 (Fiat24) supply on Arbitrum and Mantle")
    rows = {d: {"date": d} for d in CHF24_DAYS}
    node, latest = first_node("Arbitrum", CHF24["Arbitrum"], 2, DATE_START)
    if node is None:
        raise RuntimeError("no Arbitrum endpoint answered")
    blocks = {d: node.block_before(d, latest) for d in CHF24_DAYS}
    internal = range(9000, 10000)
    owners = node.calls([[{"to": FIAT24_ACCOUNT_NFT, "data": OWNER_OF + hex(i)[2:].rjust(64, "0")}, "latest"]
                         for i in internal])
    accounts = [(i, "0x" + r[-40:]) for i, r in zip(internal, owners) if r not in (None, "0x") and int(r, 16) != 0]
    log(f"  {len(accounts)} internal accounts found")
    acc = pd.DataFrame(accounts, columns=["account", "wallet"])
    for d in CHF24_DAYS:
        tot = node.total_supply(CHF24["Arbitrum"], 2, blocks[d])
        bal = node.calls([[{"to": CHF24["Arbitrum"], "data": BALANCE_OF + w[2:].rjust(64, "0")}, hex(blocks[d])]
                          for _, w in accounts])
        acc[f"chf24_{d}"] = [0.0 if b in ("0x", None) else int(b, 16) / 100 for b in bal]
        own = acc[f"chf24_{d}"].sum()
        rows[d].update({"arbitrum_total_supply": round(tot, 2), "fiat24_internal_accounts": round(own, 2),
                        "arbitrum_client_supply": round(tot - own, 2),
                        "failed_balance_calls": sum(b is None for b in bal)})
    mnode, mlatest = first_node("Mantle", CHF24["Mantle"], 2, DATE_START)
    for d in CHF24_DAYS:
        try:
            rows[d]["mantle_total_supply"] = round(
                mnode.total_supply(CHF24["Mantle"], 2, mnode.block_before(d, mlatest)), 2)
        except Exception as e:
            rows[d]["mantle_total_supply"] = None
            log(f"  Mantle {d}: {str(e)[:100]}")
    save("chf24_supply", pd.DataFrame(rows.values()))
    save("chf24_internal_accounts", acc.sort_values(f"chf24_{DATE_END}", ascending=False))


# =============================================================================
STEPS = {"manual": manual_inputs, "fred": fred, "ecb": ecb, "snb": snb, "worldbank": worldbank,
         "defillama": defillama, "yields": yields, "protocols": protocols, "coingecko": coingecko,
         "chf_onchain": chf_onchain, "chf24": chf24}


def main():
    global CG_HEADERS, CG_PAUSE
    ap = argparse.ArgumentParser(description="Download the data for the stablecoin report into ./data/")
    ap.add_argument("steps", nargs="*", metavar="step",
                    help=f"steps to run (default: all): {', '.join(STEPS)}")
    ap.add_argument("--api-key", help="CoinGecko Demo API key (or set COINGECKO_API_KEY)")
    args = ap.parse_args()
    unknown = [s for s in args.steps if s not in STEPS]
    if unknown:
        ap.error(f"unknown step(s): {', '.join(unknown)}. Choose from: {', '.join(STEPS)}")
    chosen = args.steps or list(STEPS)

    key = args.api_key or os.environ.get("COINGECKO_API_KEY")
    if not key and "coingecko" in chosen and sys.stdin.isatty():
        key = getpass.getpass("CoinGecko API key (hidden; press Enter to continue without one): ").strip()
    if key:
        CG_HEADERS, CG_PAUSE = {"x-cg-demo-api-key": key}, 2.5
    DATA.mkdir(exist_ok=True)

    log(f"Download started; steps: {', '.join(chosen)}; CoinGecko key: {'yes' if key else 'no'}")
    failed = []
    for name in chosen:
        try:
            STEPS[name]()
        except Exception as e:
            failed.append(name)
            log(f"STEP FAILED {name}: {e}")
    log("Finished. " + (f"Failed steps (run them again): {', '.join(failed)}" if failed else "All steps worked."))

    logfile = DATA / "_download_log.csv"
    pd.DataFrame(LOG).to_csv(logfile, mode="a", index=False, header=not logfile.exists())
    print(f"\nData folder: {DATA}")


if __name__ == "__main__":
    main()
