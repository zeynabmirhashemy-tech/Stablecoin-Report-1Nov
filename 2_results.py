"""
Stablecoins and the Swiss franc - step 2 of 2: figures, tables and numbers
==========================================================================

Reads only the CSV files in the folder "data" (made by 1_download.py) and makes
every figure and table of the report, plus the numbers quoted in the text.
No internet connection and no API key are needed, so anyone can re-run it.

Run in a terminal, from any folder:

    pip install pandas matplotlib
    python3 2_results.py

Output, next to this script:
    <Fig/Table number>_<short title>.csv   the numbers behind each figure and table
    Numbers_in_text.csv                    every other number in the text, with how it is computed
    index.csv                              list of all outputs with the full caption and the data used
    figures/<Fig number>_<short title>.png  the figures (plain style; the report draws the
                                            same numbers in Word)

Each figure and table has its own function below (fig_1_1, table_2_1, ...), so
the code behind any number in the report can be found by its number.
Conventions: "value on a date" = last value on or before that date; Swiss franc
amounts are converted at the SNB end-of-month rate (end-October 2026 for 1 Nov).
"""

import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates   # noqa: E402
import matplotlib.pyplot as plt     # noqa: E402
import numpy as np                  # noqa: E402
import pandas as pd                 # noqa: E402

D0, D1 = "2026-05-01", "2026-11-01"           # comparison date and cut-off date
MONEY_MONTH = "2026-09"                       # latest money stocks published before 1 Nov 2026
FX_MONTH = {D0: "2026-04", D1: "2026-10"}     # SNB end-of-month rates used for each report date
AFTER_CUTOFF = "2026-11-19"                   # last day of data used for statements after the cut-off

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
OUT = HERE
FIGS = HERE / "figures"

INDEX, TEXT = [], []

# ------------------------------------------------------------------- style --
INK, INK2, GRID, BAND = "#1a1a1a", "#555555", "#e3e2de", "#efeeea"
COLORS = {"Bitcoin": "#1baf7a", "Ether": "#eda100", "Stablecoins": "#2a78d6",
          "Other cryptocurrencies": "#9a9a9a", "Tokenised funds and loans": "#6250d6",
          "Gold-backed tokens": "#c9a227",
          "USDT": "#2a78d6", "USDC": "#eb6834", "All stablecoins": "#1a1a1a",
          "CHFAU": "#2a78d6", "ZCHF": "#eb6834", "VCHF": "#1baf7a", "CHF24": "#7b5fc4",
          "CHFm": "#e5a50a", "HCHF": "#a9a9a9", "CHFm and HCHF": "#a9a9a9",
          "date0": "#9cc3f0", "date1": "#2a78d6"}
plt.rcParams.update({"font.family": "sans-serif", "font.size": 10, "axes.edgecolor": GRID,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left",
                     "savefig.bbox": "tight", "savefig.pad_inches": 0.2, "savefig.dpi": 200})
SNB_CURRENCY = {"peggedEUR": ("EUR1", 1), "peggedGBP": ("GBP1", 1), "peggedJPY": ("JPY100", 100),
                "peggedRUB": ("RUB1", 1), "peggedCAD": ("CAD1", 1), "peggedAUD": ("AUD1", 1), "peggedSGD": ("SGD1", 1),
                "peggedREAL": ("BRL100", 100), "peggedMXN": ("MXN100", 100), "peggedTRY": ("TRY100", 100),
                "peggedCNY": ("CNY100", 100), "peggedZAR": ("ZAR1", 1), "peggedARS": ("ARS1", 1),
                "peggedKRW": ("KRW100", 100), "peggedHKD": ("HKD100", 100), "peggedMYR": ("MYR100", 100)}
CATEGORIES = ["Bitcoin", "Ether", "Stablecoins", "Other cryptocurrencies",
              "Tokenised funds and loans", "Gold-backed tokens"]


def clean(ax, grid="y"):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_visible(grid != "y")
    ax.grid(axis=grid, color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


# ----------------------------------------------------------------- helpers --
def read(name, **kw):
    return pd.read_csv(DATA / f"{name}.csv", **kw)


def slug(text, n=70):
    """File-name version of a caption, cut at a word boundary."""
    s = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return s if len(s) <= n else s[:n].rsplit("_", 1)[0]


def save_table(item, caption, df, data_used, note="", part=""):
    """Write the numbers of one figure or table to <item>_<title>.csv and list it in index.csv."""
    name = f"{item.replace('. ', '_').replace(' ', '_')}_{slug(caption)}{'_' + part if part else ''}.csv"
    df.to_csv(OUT / name, index=False)
    INDEX.append({"item": item, "caption": caption, "file": name, "kind": "numbers",
                  "data_used": data_used, "note": note})
    return name


def save_figure(item, caption, fig):
    name = f"{item.replace('. ', '_').replace(' ', '_')}_{slug(caption)}.png"
    fig.savefig(FIGS / name)
    plt.close(fig)
    INDEX.append({"item": item, "caption": caption, "file": f"figures/{name}", "kind": "figure",
                  "data_used": "", "note": ""})


def text_number(where, report_text, value, unit, how, data_used):
    """A number quoted in the text of the report, with the calculation behind it."""
    TEXT.append({"where": where, "report_text": report_text,
                 "value": round(float(value), 6) if value is not None and not isinstance(value, str) else value,
                 "unit": unit, "how_computed": how, "data_used": data_used})


def on_or_before(series, day):
    """Last value of a date-indexed series on or before `day`."""
    s = series.dropna()
    s = s[s.index <= pd.Timestamp(day)]
    return s.iloc[-1] if len(s) else np.nan


def pct(a, b):
    return (b / a - 1) * 100


def manual(key):
    m = read("manual_inputs").set_index("key")
    return float(m.loc[key, "value"])


# ============================================================================
# Common inputs
# ============================================================================
def load_common():
    c = {}
    fx = read("snb_devkum")
    fx = fx[fx["D0"] == "M1"]                                   # M1 = end of month, CHF per unit
    c["chf_per_usd"] = {d: float(fx[(fx.D1 == "USD1") & (fx.Date == m)]["Value"].iloc[0])
                        for d, m in FX_MONTH.items()}
    c["chf_per_eur"] = {d: float(fx[(fx.D1 == "EUR1") & (fx.Date == m)]["Value"].iloc[0])
                        for d, m in FX_MONTH.items()}
    # US dollars per unit of each stablecoin currency the SNB publishes (for the ranking in section 2.2)
    c["usd_per_unit"] = {}
    for d, m in FX_MONTH.items():
        rates = {"peggedCHF": 1 / c["chf_per_usd"][d]}
        for peg, (code, per) in SNB_CURRENCY.items():
            v = fx[(fx.D1 == code) & (fx.Date == m)]["Value"]
            if len(v):
                rates[peg] = float(v.iloc[0]) / per / c["chf_per_usd"][d]
        c["usd_per_unit"][d] = rates

    # 100 largest crypto-assets, classified
    top = read("cg_top_crypto_on_dates")[["id", "symbol", f"mcap_{D0}", f"mcap_{D1}"]]
    coins = read("dl_coins_list")
    stable_syms = set(coins["symbol"].astype(str).str.lower())
    gold, funds = {"xaut", "paxg"}, {"usdy", "usyc", "buidl", "ustb", "eursafo", "jaaa", "benji", "figr_heloc"}
    not_stable = {"memecore"}                     # its symbol clashes with a stablecoin symbol on DefiLlama

    def category(r):
        s, i = str(r["symbol"]).lower(), r["id"]
        if i == "bitcoin":
            return "Bitcoin"
        if i == "ethereum":
            return "Ether"
        if s in gold:
            return "Gold-backed tokens"
        if s in funds:
            return "Tokenised funds and loans"
        if s in stable_syms and i not in not_stable:
            return "Stablecoins"
        return "Other cryptocurrencies"

    top["category"] = top.apply(category, axis=1)
    c["top"] = top
    c["coins"] = coins

    # DefiLlama totals and coin values on the two dates
    tot = read("dl_total_supply_history", parse_dates=["date"]).set_index("date").sort_index()
    c["total_hist"] = tot
    c["total"] = {d: on_or_before(tot["total_usd"], d) for d in (D0, D1)}
    on = read("dl_all_coins_on_dates").merge(coins[["id", "pegMechanism", "price_usd"]], on="id", how="left")
    on["pegMechanism"] = on["pegMechanism"].replace({"crytpo-backed": "crypto-backed"})
    c["on"] = on

    # Swiss franc coins: daily supply in CHF
    hist = read("dl_coin_history", parse_dates=["date"])
    chf = (hist[hist.pegType == "peggedCHF"]
           .pivot_table(index="date", columns="symbol", values="circulating_native_units", aggfunc="last"))
    cg = read("cg_chf_coins_history", parse_dates=["date"])
    c["cg_chf"] = cg
    chfau_cg = cg[(cg.coin_id == "allunity-chf") & (cg.market_cap > 0)].set_index("date")["market_cap"]
    extra = read("chf_extra_supply_daily", parse_dates=["date"])
    chfau_chain = extra[(extra.coin == "CHFAU") & (extra.chain == "total")].set_index("date")["supply"]
    # on-chain supply until CoinGecko's history starts (4 Aug 2026), CoinGecko market value afterwards
    chf["CHFAU"] = pd.concat([chfau_chain[chfau_chain.index < chfau_cg.index.min()], chfau_cg]).sort_index()
    c["chf_supply"] = chf.sort_index()
    c["chf24"] = read("chf24_supply").set_index("date")
    return c


def chf_on(c, coin, day, max_gap_days=7):
    """Supply of a CHF coin on a date; empty if the last observation is more than a week old."""
    s = c["chf_supply"][coin].dropna()
    s = s[s.index <= pd.Timestamp(day)]
    if s.empty or (pd.Timestamp(day) - s.index[-1]).days > max_gap_days:
        return np.nan
    return s.iloc[-1]


CHF_COINS = ["CHFAU", "ZCHF", "VCHF", "CHFm", "HCHF"]    # coins with market data (CHF24 shown separately)


def chf_market(c):
    rows = []
    for coin in CHF_COINS:
        a, b = chf_on(c, coin, D0), chf_on(c, coin, D1)
        rows.append({"coin": coin, "chf_m_1_may": a / 1e6, "chf_m_1_nov": b / 1e6})
    t = pd.DataFrame(rows)
    return t


# ============================================================================
# Chapter 1
# ============================================================================
def table_1_1(c, ch3_total):
    """Stablecoins by currency compared with the money stock of their currency area."""
    tot = c["total_hist"]
    fred = read("fred_series")
    fred["month"] = fred["date"].str[:7]
    us = {s: float(fred[(fred.series == s) & (fred.month == MONEY_MONTH)]["value"].iloc[0]) for s in ("M1SL", "M2SL")}
    ecb = read("ecb_euro_money")
    ea = {k: float(ecb[ecb.series.str.contains(k) & (ecb.date == MONEY_MONTH)]["value"].iloc[0]) for k in ("M10", "M20")}
    snb = read("snb_snbmonagg")
    snb = snb[(snb.D0 == "B") & (snb.Date == MONEY_MONTH)].set_index("D1")["Value"]
    usd_per_eur = c["chf_per_eur"][D1] / c["chf_per_usd"][D1]
    fx = c["chf_per_usd"][D1]
    rows = [
        ["US dollar", on_or_before(tot["peggedUSD_usd"], D1) / 1e9,
         pct(on_or_before(tot["peggedUSD_usd"], D0), on_or_before(tot["peggedUSD_usd"], D1)),
         us["M1SL"], us["M2SL"]],
        ["Euro", on_or_before(tot["peggedEUR_usd"], D1) / 1e9,
         pct(on_or_before(tot["peggedEUR_usd"], D0), on_or_before(tot["peggedEUR_usd"], D1)),
         ea["M10"] * usd_per_eur / 1e3, ea["M20"] * usd_per_eur / 1e3],
        ["Swiss franc", ch3_total[D1] / fx / 1e3, pct(ch3_total[D0], ch3_total[D1]),
         snb["GM1"] / fx / 1e3, snb["GM2"] / fx / 1e3],
    ]
    t = pd.DataFrame(rows, columns=["currency", "stablecoins_usd_bn", "change_since_1_may_%", "m1_usd_bn", "m2_usd_bn"])
    t["stablecoins_%_of_m1"] = t["stablecoins_usd_bn"] / t["m1_usd_bn"] * 100
    t["stablecoins_%_of_m2"] = t["stablecoins_usd_bn"] / t["m2_usd_bn"] * 100
    save_table("Table 1.1", "Stablecoins by currency compared with the money stock of their currency area, 1 Nov 2026",
               t.round(6), "dl_total_supply_history, Table 3.1 (franc coins), fred_series, ecb_euro_money, "
               "snb_snbmonagg, snb_devkum",
               f"Money stocks for {MONEY_MONTH}; converted at SNB end-October 2026 rates "
               f"(CHF {fx:.5f} per USD, USD {usd_per_eur:.5f} per EUR). Franc coins change measured in CHF.")


def crypto_split(c, col_prefix="mcap_"):
    top = c["top"]
    s = top.groupby("category")[[f"{col_prefix}{D0}", f"{col_prefix}{D1}"]].sum() / 1e9
    return s.reindex(CATEGORIES)


def fig_1_1_and_1_2(c):
    s = crypto_split(c)
    t = pd.DataFrame({"category": s.index, "usd_bn_1_may": s.iloc[:, 0].values, "usd_bn_1_nov": s.iloc[:, 1].values})
    t["share_%_1_may"] = t.usd_bn_1_may / t.usd_bn_1_may.sum() * 100
    t["share_%_1_nov"] = t.usd_bn_1_nov / t.usd_bn_1_nov.sum() * 100
    t["growth_%"] = pct(t.usd_bn_1_may, t.usd_bn_1_nov)
    total = pd.DataFrame([{"category": "Whole market (100 largest)", "usd_bn_1_may": t.usd_bn_1_may.sum(),
                           "usd_bn_1_nov": t.usd_bn_1_nov.sum(), "share_%_1_may": 100, "share_%_1_nov": 100,
                           "growth_%": pct(t.usd_bn_1_may.sum(), t.usd_bn_1_nov.sum())}])
    t = pd.concat([t, total], ignore_index=True)
    used = "cg_top_crypto_on_dates, dl_coins_list (to classify stablecoins)"

    cap = "Shares of the crypto market on 1 May and 1 Nov 2026"
    save_table("Fig. 1.1", cap, t[["category", "usd_bn_1_may", "usd_bn_1_nov", "share_%_1_may", "share_%_1_nov"]].round(4),
               used, "Crypto market approximated by the 100 largest crypto-assets by market value on CoinGecko.")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.8))
    for ax, col, lab in zip(axes, ("usd_bn_1_may", "usd_bn_1_nov"), ("1 May 2026", "1 Nov 2026")):
        v = t.iloc[:-1]
        w, _ = ax.pie(v[col], colors=[COLORS[k] for k in v.category], startangle=90, counterclock=False,
                      wedgeprops={"edgecolor": "white", "linewidth": 1.5})
        for wedge, val in zip(w, v[col] / v[col].sum() * 100):
            if val >= 6:
                ang = np.deg2rad((wedge.theta1 + wedge.theta2) / 2)
                ax.text(0.65 * np.cos(ang), 0.65 * np.sin(ang), f"{val:.0f}%", ha="center", va="center",
                        color="white", fontweight="bold")
        ax.set_title(f"{lab}: total USD {v[col].sum():,.0f} bn", loc="center")
    fig.legend(w, [f"{k}: {a:.2g}% -> {b:.2g}%" for k, a, b in zip(t.category[:-1], t["share_%_1_may"], t["share_%_1_nov"])],
               loc="lower center", ncol=3, frameon=False)
    fig.suptitle(f"Fig. 1.1. {cap}", x=0.02, ha="left", fontweight="bold")
    fig.tight_layout(rect=(0, 0.1, 1, 0.95))
    save_figure("Fig. 1.1", cap, fig)

    cap = "Value of each part of the crypto market on 1 May and 1 Nov 2026, with its growth"
    save_table("Fig. 1.2", cap, t[["category", "usd_bn_1_may", "usd_bn_1_nov", "growth_%"]].round(4), used)
    v = t.iloc[:-1].iloc[::-1]
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    y = np.arange(len(v))
    ax.barh(y + 0.19, v.usd_bn_1_may, 0.38, color=COLORS["date0"], label="1 May 2026")
    ax.barh(y - 0.19, v.usd_bn_1_nov, 0.38, color=COLORS["date1"], label="1 Nov 2026")
    for yi, (_, r) in zip(y, v.iterrows()):
        ax.text(max(r.usd_bn_1_may, r.usd_bn_1_nov) + 20, yi, f"USD {r.usd_bn_1_nov:,.0f} bn ({r['growth_%']:+.1f}%)",
                va="center", fontsize=9)
    ax.set_yticks(y, v.category)
    ax.set_xlim(0, v[["usd_bn_1_may", "usd_bn_1_nov"]].max().max() * 1.45)
    ax.set_xlabel("Market value, USD bn")
    clean(ax, "x")
    ax.legend(frameon=False, loc="lower right")
    tw = t.iloc[-1]
    ax.set_title(f"Fig. 1.2. {cap}\nWhole market (100 largest): USD {tw.usd_bn_1_may:,.0f} bn -> "
                 f"{tw.usd_bn_1_nov:,.0f} bn ({tw['growth_%']:+.1f}%)")
    save_figure("Fig. 1.2", cap, fig)

    # numbers in the text, section 1.2
    st = t.set_index("category")
    w = "1.2 Stablecoins within the crypto market"
    text_number(w, "Bitcoin 59%, stablecoins 11%, Ether 10% of the market on 1 Nov 2026",
                f"{st.loc['Bitcoin', 'share_%_1_nov']:.2f} / {st.loc['Stablecoins', 'share_%_1_nov']:.2f} / "
                f"{st.loc['Ether', 'share_%_1_nov']:.2f}", "%", "Fig. 1.1 shares", used)
    text_number(w, "100 largest crypto-assets worth USD 2,637 bn on 1 Nov 2026, 2.9% more than on 1 May",
                f"{tw.usd_bn_1_nov:.1f} / {tw['growth_%']:.2f}", "USD bn / %", "Sum of the 100 market values", used)
    text_number(w, "Stablecoins fell by 4.1% to USD 291 bn",
                f"{st.loc['Stablecoins', 'usd_bn_1_nov']:.1f} / {st.loc['Stablecoins', 'growth_%']:.2f}",
                "USD bn / %", "Stablecoins among the 100 largest", used)
    text_number(w, "Share of stablecoins declined from 11.9% to 11.0%",
                f"{st.loc['Stablecoins', 'share_%_1_may']:.2f} -> {st.loc['Stablecoins', 'share_%_1_nov']:.2f}", "%",
                "Fig. 1.1 shares", used)
    text_number(w, "Other cryptocurrencies +10.4%, tokenised funds and loans +43.6%",
                f"{st.loc['Other cryptocurrencies', 'growth_%']:.2f} / {st.loc['Tokenised funds and loans', 'growth_%']:.2f}",
                "%", "Fig. 1.2 growth", used)
    smallest = c["top"][f"mcap_{D1}"].min() / 1e6
    text_number("3.1 Market size", "Smallest of the 100 largest crypto-assets worth about USD 285 m on 1 Nov",
                smallest, "USD m", "Minimum market value among the 100 on 1 Nov 2026", "cg_top_crypto_on_dates")

    # after the cut-off: the same 100 coins on the download day
    latest = read("cg_top_crypto_latest").merge(c["top"][["id", "category", f"mcap_{D1}"]], on="id", how="left")
    day = latest["date_pulled"].iloc[0]
    tot_now, tot_d1 = latest.market_cap_usd.sum() / 1e9, latest[f"mcap_{D1}"].sum() / 1e9
    by = latest.groupby("category")[["market_cap_usd", f"mcap_{D1}"]].sum() / 1e9
    text_number(w, f"On {day} the same 100 crypto-assets were worth about USD 2,095 bn, roughly 21% less than on 1 Nov",
                f"{tot_now:.1f} / {pct(tot_d1, tot_now):.2f}", "USD bn / %",
                "Sum of today's market values of the same 100 coins (coins without a value today count as 0)",
                "cg_top_crypto_latest, cg_top_crypto_on_dates")
    text_number(w, "Bitcoin lost about 22%; stablecoins fell by about 5%, to USD 278 bn",
                f"BTC {pct(by.loc['Bitcoin', f'mcap_{D1}'], by.loc['Bitcoin', 'market_cap_usd']):.2f}; stablecoins "
                f"{pct(by.loc['Stablecoins', f'mcap_{D1}'], by.loc['Stablecoins', 'market_cap_usd']):.2f}, "
                f"{by.loc['Stablecoins', 'market_cap_usd']:.1f}", "% / USD bn", "As above, by category",
                "cg_top_crypto_latest, cg_top_crypto_on_dates")
    return st


def fig_1_3(c):
    """Turnover: daily volume / market value, 30-day average up to each date."""
    h = read("cg_comparators_history", parse_dates=["date"])
    h["turnover_%"] = h["volume_24h"] / h["market_cap"] * 100
    avg = (h.pivot_table(index="date", columns="coin_id", values="turnover_%").sort_index()
           .rolling(30, min_periods=30).mean())
    names = {"tether": "USDT (Tether)", "usd-coin": "USDC", "ethereum": "Ether", "bitcoin": "Bitcoin"}
    t = pd.DataFrame({"coin": list(names.values()),
                      "turnover_%_30d_to_1_may": [on_or_before(avg[k], D0) for k in names],
                      "turnover_%_30d_to_1_nov": [on_or_before(avg[k], D1) for k in names]})
    cap = "Daily trading volume as a share of market value, 30-day average up to 1 May and 1 Nov 2026"
    save_table("Fig. 1.3", cap, t.round(4), "cg_comparators_history",
               "Average over the 30 days up to and including each date of (24h volume / market value). "
               "The report caption says 'Dec 2025 to 1 Nov 2026'; the figure shows the two dates.")
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    x = np.arange(len(t))
    ax.bar(x - 0.19, t.iloc[:, 1], 0.38, color=COLORS["date0"], label="30 days to 1 May 2026")
    ax.bar(x + 0.19, t.iloc[:, 2], 0.38, color=COLORS["date1"], label="30 days to 1 Nov 2026")
    for xi, (a, b) in enumerate(zip(t.iloc[:, 1], t.iloc[:, 2])):
        ax.text(xi - 0.19, a + 0.5, f"{a:.1f}%", ha="center", fontsize=8.5)
        ax.text(xi + 0.19, b + 0.5, f"{b:.1f}%", ha="center", fontsize=8.5)
    ax.set_xticks(x, t.coin)
    ax.set_ylabel("Traded per day, % of market value")
    clean(ax)
    ax.legend(frameon=False)
    ax.set_title(f"Fig. 1.3. {cap}")
    save_figure("Fig. 1.3", cap, fig)
    r = t.set_index("coin")
    text_number("1.2 Stablecoins within the crypto market",
                "USDT volume = 28% of its market value (34% to 1 May); Bitcoin 1.7% (2.6%); "
                "a dollar in USDT changed hands 13 to 16 times as often as a dollar in Bitcoin",
                f"USDT {r.iloc[0, 1]:.2f} ({r.iloc[0, 0]:.2f}); BTC {r.iloc[3, 1]:.2f} ({r.iloc[3, 0]:.2f}); "
                f"ratio {r.iloc[0, 0] / r.iloc[3, 0]:.1f} (1 May) and {r.iloc[0, 1] / r.iloc[3, 1]:.1f} (1 Nov)",
                "%", "Fig. 1.3", "cg_comparators_history")


def fig_1_4(c, st):
    vol = read("cg_top_crypto_volume_on_dates").drop(columns=["category"], errors="ignore")
    vol = vol.merge(c["top"][["id", "category"]], on="id", how="left")
    traded = {d: vol.loc[vol.category == "Stablecoins", f"vol30_{d}"].sum() / vol[f"vol30_{d}"].sum() * 100
              for d in (D0, D1)}
    t = pd.DataFrame({"measure": ["Share of market value (held)", "Share of trading volume (traded)"],
                      "share_%_1_may": [st.loc["Stablecoins", "share_%_1_may"], traded[D0]],
                      "share_%_1_nov": [st.loc["Stablecoins", "share_%_1_nov"], traded[D1]]})
    cap = "Stablecoins' share of the crypto market by value held and by trading volume, 1 May and 1 Nov 2026"
    save_table("Fig. 1.4", cap, t.round(4), "cg_top_crypto_on_dates, cg_top_crypto_volume_on_dates, dl_coins_list",
               "Trading volume: 30-day average up to each date (1 Nov 2026 was a Sunday). "
               f"Coins with volume data: {vol[f'vol30_{D1}'].notna().sum()} of {len(c['top'])}.")
    fig, ax = plt.subplots(figsize=(8.5, 3.2))
    y = np.array([1, 0])
    ax.barh(y + 0.19, t["share_%_1_may"], 0.38, color=COLORS["date0"], label="1 May 2026")
    ax.barh(y - 0.19, t["share_%_1_nov"], 0.38, color=COLORS["date1"], label="1 Nov 2026")
    for yi, a, b in zip(y, t["share_%_1_may"], t["share_%_1_nov"]):
        ax.text(a + 0.8, yi + 0.19, f"{a:.1f}%", va="center", fontsize=9)
        ax.text(b + 0.8, yi - 0.19, f"{b:.1f}%", va="center", fontsize=9)
    ax.set_yticks(y, t.measure)
    ax.set_xlim(0, 70)
    ax.set_xlabel("% of the 100 largest crypto-assets")
    clean(ax, "x")
    ax.legend(frameon=False, loc="upper right")
    ax.set_title(f"Fig. 1.4. {cap}")
    save_figure("Fig. 1.4", cap, fig)
    text_number("1.2 Stablecoins within the crypto market", "Stablecoins: about 55% of trading (52% on 1 May)",
                f"{traded[D1]:.2f} ({traded[D0]:.2f})", "%", "Fig. 1.4", "cg_top_crypto_volume_on_dates")


def fig_1_5():
    keys = [("Business-to-business (B2B)", "B2B"), ("Consumer-to-consumer (C2C)", "C2C"),
            ("Consumer-to-business (C2B)", "C2B"), ("Business-to-consumer (B2C)", "B2C")]
    t = pd.DataFrame({"type": [k[0] for k in keys],
                      "usd_bn_per_year": [manual(f"payments_{k[1]}") for k in keys],
                      "stablecoin_share_of_all_payments_of_this_type_%": [manual(f"penetration_{k[1]}") for k in keys]})
    t["share_%"] = t.usd_bn_per_year / t.usd_bn_per_year.sum() * 100
    cap = "Real stablecoin payments by type, annualised, based on December 2025, USD bn"
    save_table("Fig. 1.5", cap, t.round(4), "manual_inputs (McKinsey & Company 2026a, 2026b)")
    fig, ax = plt.subplots(figsize=(8, 4.2))
    cols = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
    w, _ = ax.pie(t.usd_bn_per_year, colors=cols, startangle=90, counterclock=False,
                  wedgeprops={"edgecolor": "white", "linewidth": 1.5})
    ax.legend(w, [f"{a}: {s:.2g}% (USD {v:.0f} bn)" for a, s, v in zip(t.type, t["share_%"], t.usd_bn_per_year)],
              loc="center left", bbox_to_anchor=(1, 0.5), frameon=False)
    ax.set_title(f"Fig. 1.5. {cap}\n(total USD {t.usd_bn_per_year.sum():.0f} bn per year)")
    save_figure("Fig. 1.5", cap, fig)
    text_number("1.3 Stablecoins in payments", "Real stablecoin payments about USD 390 bn a year, roughly 0.02% of "
                "global payments", manual("payments_real_total") / manual("payments_global_total") * 100, "%",
                "payments_real_total / payments_global_total", "manual_inputs")


def saving_numbers():
    p = read("dl_yield_pools_tvl_on_dates")
    allnow = read("dl_yield_pools_all_now")
    p["stablecoin"] = p["stablecoin"].astype(str).str.lower() == "true"
    res = {}
    for d in (D0, D1):
        res[d] = (p.loc[p.stablecoin, f"tvl_{d}"].sum() / 1e9, p[f"tvl_{d}"].sum() / 1e9)
    coverage = allnow.loc[allnow.tvlUsd >= 1e6, "tvlUsd"].sum() / allnow.tvlUsd.sum() * 100
    w = "1.1 Stablecoins compared with money"
    used = "dl_yield_pools_tvl_on_dates, dl_yield_pools_all_now, manual_inputs (ICI)"
    text_number(w, "Stablecoins in DeFi yield pools at most USD 34 bn, about 0.4% of US money market fund assets",
                f"{res[D1][0]:.2f} / {res[D1][0] / manual('mmf_us_assets') * 100:.2f}", "USD bn / %",
                "Sum of 1 Nov value of pools flagged 'stablecoin' by DefiLlama; MMF assets week ended 28 Oct 2026. "
                f"Pools >= USD 1 m on the download day ({coverage:.1f}% of that day's total value).", used)
    text_number("1.2 Stablecoins within the crypto market",
                "About a quarter of the value in yield pools was in stablecoin pools on 1 Nov 2026",
                f"{res[D1][0] / res[D1][1] * 100:.2f} (1 May: {res[D0][0] / res[D0][1] * 100:.2f})", "%",
                "Stablecoin pools / all pools", used)


# ============================================================================
# Chapter 2
# ============================================================================
def fig_2_1(c):
    tot = c["total_hist"]["total_usd"]
    hist = read("dl_coin_history", parse_dates=["date"])
    series = {"All stablecoins": tot}
    for sym in ("USDT", "USDC"):
        series[sym] = hist[hist.symbol == sym].set_index("date")["circulating_native_units"].sort_index()
    df = pd.DataFrame(series)
    df = df[(df.index >= "2025-01-01") & (df.index <= D1)] / 1e9
    cap = "Stablecoin supply, January 2025 to 1 November 2026: all stablecoins, USDT and USDC"
    save_table("Fig. 2.1", cap, df.round(4).reset_index().rename(columns={"index": "date"}),
               "dl_total_supply_history, dl_coin_history", "USD bn; USDT and USDC in their own units (= USD).")
    fig, ax = plt.subplots(figsize=(9.5, 4.3))
    for k, s in df.items():
        ax.plot(s.index, s, color=COLORS[k], lw=2)
        ax.text(s.index[-1], s.iloc[-1], f"  {k} {s.iloc[-1]:.0f}", va="center", fontsize=9)
    peak_day = df["All stablecoins"]["2026-01-01":].idxmax()
    ax.annotate(f"peak USD {df['All stablecoins'][peak_day]:.0f} bn\n{peak_day:%d %b %Y}",
                (peak_day, df["All stablecoins"][peak_day]), xytext=(-60, -45), textcoords="offset points",
                ha="center", fontsize=8.5, arrowprops={"arrowstyle": "-", "color": INK2})
    ax.axvline(pd.Timestamp(D0), color=INK2, ls=":", lw=1)
    ax.set_ylabel("Supply, USD bn")
    ax.set_ylim(0, df.max().max() * 1.1)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    clean(ax)
    ax.set_title(f"Fig. 2.1. {cap}")
    save_figure("Fig. 2.1", cap, fig)

    # numbers in the text, section 2.1
    w = "2.1 Market size"
    used = "dl_total_supply_history"
    t_all = c["total_hist"]["total_usd"]
    text_number(w, "Total supply fell by 4.4%, from USD 312 bn to USD 298 bn",
                f"{c['total'][D0] / 1e9:.2f} -> {c['total'][D1] / 1e9:.2f} ({pct(c['total'][D0], c['total'][D1]):.2f})",
                "USD bn / %", "Value on each date", used)
    text_number(w, "Total supply peaked at USD 314 bn on 17 May 2026",
                f"{t_all[:D1]['2026-01-01':].max() / 1e9:.2f} on {t_all[:D1]['2026-01-01':].idxmax():%Y-%m-%d}",
                "USD bn", "Maximum in 2026 up to the cut-off", used)
    text_number(w, "By 19 Nov, after the cut-off, it was USD 287 bn", on_or_before(t_all, AFTER_CUTOFF) / 1e9,
                "USD bn", f"Value on {AFTER_CUTOFF}", used)
    m = t_all.groupby(t_all.index.to_period("M")).last()
    ch = m.diff()
    june = pd.Period("2026-06", "M")
    earlier = ch[(ch.index >= pd.Period("2022-06", "M")) & (ch.index < june)]
    text_number(w, "Largest monthly fall came in June: about USD 8 bn, the most in dollar terms since May 2022, "
                "but only 2.6%",
                f"{ch[june] / 1e9:.2f} ({ch[june] / m[june - 1] * 100:.2f}%); largest fall Jun 2022-May 2026: "
                f"{earlier.min() / 1e9:.2f} in {earlier.idxmin()}", "USD bn / %",
                "Month-end to month-end change of total supply", used)
    on = c["on"]
    n = {d: int((on[f"supply_{d}"].fillna(0) > 0).sum()) for d in (D0, D1)}
    text_number(w, "Number of stablecoins rose by a fifth, from 352 to 425", f"{n[D0]} -> {n[D1]}", "coins",
                "Coins on DefiLlama with supply above 0 on each date", "dl_all_coins_on_dates")


def coin_values(c):
    """USD value of every stablecoin on both dates, with CHFAU added from Table 3.1 (it is not on DefiLlama).
    US-dollar coins at par; other currencies at the SNB end-of-month rate for each date where the SNB publishes
    one, otherwise at DefiLlama's price on the download day; coins with neither are left without a value."""
    on = c["on"].copy()
    for d in (D0, D1):
        rate = on.pegType.map(c["usd_per_unit"][d])
        rate = np.where(on.pegType == "peggedUSD", 1.0, rate.fillna(on["price_usd"]))
        on[f"usd_{d}"] = on[f"supply_{d}"] * rate
    chfau = {d: chf_on(c, "CHFAU", d) / c["chf_per_usd"][d] for d in (D0, D1)}
    on = pd.concat([on, pd.DataFrame([{"id": "not on DefiLlama", "symbol": "CHFAU", "pegType": "peggedCHF",
                                       f"usd_{D0}": chfau[D0], f"usd_{D1}": chfau[D1]}])], ignore_index=True)
    for d in (D0, D1):
        live = on[f"usd_{d}"].fillna(0) > 0
        on.loc[live, f"rank_{d}"] = on.loc[live, f"usd_{d}"].rank(ascending=False, method="min")
    on["share_of_all_%_1_nov"] = on[f"usd_{D1}"] / c["total"][D1] * 100
    on["growth_%"] = pct(on[f"supply_{D0}"], on[f"supply_{D1}"])
    return on.sort_values(f"usd_{D1}", ascending=False)


def section_2_2(c):
    v = coin_values(c)
    cols = ["symbol", "pegType", "pegMechanism", f"usd_{D0}", f"usd_{D1}", "growth_%", f"rank_{D0}", f"rank_{D1}",
            "share_of_all_%_1_nov"]
    save_table("Section 2.2", "All stablecoins ranked by supply on 1 Nov 2026", v[cols].round(4),
               "dl_all_coins_on_dates, dl_coins_list, Table 3.1 (CHFAU)",
               "US-dollar coins at par; other currencies at SNB end-of-month rates (end-April for 1 May, end-October "
               "for 1 Nov) or, where the SNB has no rate, at DefiLlama's price on the download day. "
               "Growth in each coin's own units.")
    s = v.set_index("symbol")
    w = "2.2 Issuers and market structure"
    used = "dl_all_coins_on_dates, dl_total_supply_history"
    for sym in ("USDT", "USDC"):
        text_number(w, f"{sym} supply, share of all stablecoins, growth",
                    f"{s.loc[sym, f'usd_{D1}'] / 1e9:.2f} bn, {s.loc[sym, 'share_of_all_%_1_nov']:.2f}%, "
                    f"{s.loc[sym, 'growth_%']:.2f}%", "USD bn / % / %", "Coin supply / total supply", used)
    two = {d: (s.loc["USDT", f"usd_{d}"] + s.loc["USDC", f"usd_{d}"]) / c["total"][d] * 100 for d in (D0, D1)}
    text_number(w, "USDT and USDC together hold 84% of the market, down from 85.5% on 1 May",
                f"{two[D1]:.2f} ({two[D0]:.2f})", "%", "(USDT + USDC) / total supply", used)
    usd = c["on"][c["on"].pegType == "peggedUSD"]
    hhi = {}
    for d in (D0, D1):
        sh = usd[f"supply_{d}"].fillna(0) / usd[f"supply_{d}"].fillna(0).sum() * 100
        hhi[d] = (sh ** 2).sum()
    text_number(w, "HHI of the dollar coins about 4,230 on 1 Nov 2026 (4,320 on 1 May)",
                f"{hhi[D1]:.0f} ({hhi[D0]:.0f})", "index", "Sum of squared % shares of all US-dollar coins",
                "dl_all_coins_on_dates")
    third = v[~v.symbol.isin(["USDT", "USDC"])].iloc[0]
    text_number(w, "Below the two leaders, no coin exceeds 2.1% of supply",
                f"{third.symbol}: {third['share_of_all_%_1_nov']:.2f}", "%", "Third-largest coin's share", used)
    for sym in ("USD1", "USDG", "PYUSD", "RLUSD", "USDGO", "OUSD", "USDS", "DAI", "USDe", "A7A5", "EURC", "JPYSC"):
        if sym in s.index:
            r = s.loc[sym]
            r = r.iloc[0] if isinstance(r, pd.DataFrame) else r
            text_number(w, f"{sym}: supply, growth, share and rank on 1 Nov 2026",
                        f"USD {r[f'usd_{D1}'] / 1e9:.3f} bn (1 May {r[f'usd_{D0}'] / 1e9:.3f}), {r['growth_%']:+.1f}%, "
                        f"{r['share_of_all_%_1_nov']:.3f}%, rank {r[f'rank_{D1}']:.0f}", "", "Ranking table", used)
    return v


def table_2_1(c):
    tot = c["total_hist"]
    on = c["on"]
    usd = on[on.pegType == "peggedUSD"]
    rows = []
    for mech, g in usd.groupby("pegMechanism"):
        rows.append(["Type of backing (US-dollar coins, USD bn)", mech.capitalize(),
                     g[f"supply_{D0}"].sum() / 1e9, g[f"supply_{D1}"].sum() / 1e9])
    back_total = usd[f"supply_{D1}"].sum() / 1e9
    ch = read("dl_chain_history", parse_dates=["date"]).pivot_table(index="date", columns="chain", values="total_usd")
    chv = pd.DataFrame({d: ch.apply(lambda s: on_or_before(s, d)) for d in (D0, D1)}).sort_values(D1, ascending=False)
    top6 = chv.head(6)
    for name, r in top6.iterrows():
        rows.append(["Blockchain (all coins, USD bn)", name, r[D0] / 1e9, r[D1] / 1e9])
    rows.append(["Blockchain (all coins, USD bn)", "All other blockchains",
                 (c["total"][D0] - top6[D0].sum()) / 1e9, (c["total"][D1] - top6[D1].sum()) / 1e9])
    named = {"US dollar": "peggedUSD_usd", "Euro": "peggedEUR_usd", "Russian rouble": "peggedRUB_usd",
             "Japanese yen": "peggedJPY_usd", "Swiss franc": "peggedCHF_usd"}
    for name, col in named.items():
        rows.append(["Currency (USD m)", name, on_or_before(tot[col], D0) / 1e6, on_or_before(tot[col], D1) / 1e6])
    other = {d: c["total"][d] - sum(on_or_before(tot[col], d) for col in named.values()) for d in (D0, D1)}
    rows.append(["Currency (USD m)", "Other currencies", other[D0] / 1e6, other[D1] / 1e6])
    rows.append(["All stablecoins (USD bn)", "All stablecoins", c["total"][D0] / 1e9, c["total"][D1] / 1e9])
    t = pd.DataFrame(rows, columns=["group", "part", "1_may", "1_nov"])
    t["change_%"] = pct(t["1_may"], t["1_nov"])
    denom = {"Type of backing (US-dollar coins, USD bn)": back_total,
             "Blockchain (all coins, USD bn)": c["total"][D1] / 1e9,
             "Currency (USD m)": c["total"][D1] / 1e6, "All stablecoins (USD bn)": c["total"][D1] / 1e9}
    t["share_%_1_nov"] = t["1_nov"] / t["group"].map(denom) * 100
    save_table("Table 2.1", "Stablecoin supply by type of backing, blockchain and currency, 1 May and 1 Nov 2026",
               t.round(4), "dl_all_coins_on_dates, dl_coins_list, dl_chain_history, dl_total_supply_history",
               "Backing from coin-level data (its dollar total differs slightly from the aggregate series); shares of "
               "backing are of US-dollar coins, other shares of all stablecoins. Swiss franc as listed on DefiLlama, "
               "without CHFAU.")


def fig_2_2():
    h = read("cg_comparators_history", parse_dates=["date"])
    h = h[h.coin_id.isin(["tether", "usd-coin"])].copy()
    h["deviation_bp"] = (h.price - 1) * 1e4
    wide = h.pivot_table(index="date", columns="coin_id", values="deviation_bp").rename(
        columns={"tether": "USDT", "usd-coin": "USDC"})[["USDT", "USDC"]]
    wide = wide[wide.index <= D1]
    cap = "Daily deviation of USDT and USDC from USD 1, November 2025 to 1 November 2026"
    save_table("Fig. 2.2", cap, wide.round(3).reset_index(), "cg_comparators_history",
               "Deviation in basis points = (daily closing price in USD - 1) x 10,000.")
    fig, ax = plt.subplots(figsize=(9.5, 3.8))
    ax.axhspan(-50, 50, color=BAND, zorder=0)
    for k in ("USDT", "USDC"):
        ax.plot(wide.index, wide[k], color=COLORS[k], lw=1.3, label=k)
    ax.set_ylim(-60, 60)
    ax.set_ylabel("Deviation from USD 1, basis points")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    clean(ax)
    ax.legend(frameon=False, ncol=2)
    ax.set_title(f"Fig. 2.2. {cap} (grey band = ±50 bp)")
    save_figure("Fig. 2.2", cap, fig)
    win = wide[wide.index >= D0]
    for k in ("USDT", "USDC"):
        text_number("2.3 Peg stability and reserves of USDT and USDC",
                    f"{k}: average daily deviation, largest deviation, days outside ±50 bp (1 May-1 Nov); "
                    "average since Nov 2025",
                    f"{win[k].abs().mean():.2f} bp, max {win[k].abs().max():.1f} bp, "
                    f"{int((win[k].abs() > 50).sum())} of {win[k].notna().sum()} days; since Nov 2025 "
                    f"{wide[k].abs().mean():.2f} bp", "bp", "Mean and maximum of |deviation|", "cg_comparators_history")


def reserves_numbers():
    w = "2.3 Peg stability and reserves of USDT and USDC"
    a, l_ = manual("tether_assets"), manual("tether_liabilities")
    text_number(w, "Tether assets USD 191.45 bn exceeded liabilities of USD 183.50 bn by USD 7.95 bn",
                a - l_, "USD bn", "tether_assets - tether_liabilities", "manual_inputs")
    sar = read("snb_zimoma")
    text_number(w, "SARON averaged -0.06% in October 2026",
                float(sar[(sar.D0 == "SARON") & (sar.Date == "2026-10")]["Value"].iloc[0]), "%",
                "SNB monthly SARON, October 2026", "snb_zimoma")


EURO_ISSUERS = {   # issuer and place of authorisation: from FXC Intelligence (2026), Decta (2026), eco.com (2026)
    "EURC": ("Circle", "France"), "EURCV": ("Société Générale-FORGE", "France"),
    "EURI": ("Banking Circle", "Luxembourg"), "EURe": ("Monerium", "Iceland (EEA)"),
    "REUR": ("The RIB Digital Holdings Ltd", "Hong Kong (not MiCA)"), "EUROP": ("Schuman Financial", "France"),
    "EURR": ("StablR", "Malta"), "EURQ": ("Quantoz", "Netherlands")}


def table_2_2(c):
    on = c["on"]
    eur = on[on.pegType == "peggedEUR"][["symbol", f"supply_{D0}", f"supply_{D1}"]].copy()
    eur = eur.groupby("symbol", as_index=False).sum().sort_values(f"supply_{D1}", ascending=False)
    eur["eur_m_1_may"], eur["eur_m_1_nov"] = eur[f"supply_{D0}"] / 1e6, eur[f"supply_{D1}"] / 1e6
    eur["growth_%"] = pct(eur.eur_m_1_may.replace(0, np.nan), eur.eur_m_1_nov)
    info = {k.upper(): v for k, v in EURO_ISSUERS.items()}
    eur["issuer"] = eur.symbol.str.upper().map(lambda s: info.get(s, ("", ""))[0])
    eur["authorised_in"] = eur.symbol.str.upper().map(lambda s: info.get(s, ("", ""))[1])
    eur["in_report_table"] = eur.symbol.str.upper().isin(list(info))
    total = pd.DataFrame([{"symbol": "All euro coins", "eur_m_1_may": eur.eur_m_1_may.sum(),
                           "eur_m_1_nov": eur.eur_m_1_nov.sum(),
                           "growth_%": pct(eur.eur_m_1_may.sum(), eur.eur_m_1_nov.sum())}])
    t = pd.concat([eur, total], ignore_index=True)[["symbol", "issuer", "authorised_in", "eur_m_1_may",
                                                    "eur_m_1_nov", "growth_%", "in_report_table"]]
    save_table("Table 2.2", "Euro stablecoins, supply in EUR m", t.round(4), "dl_all_coins_on_dates",
               "All euro coins on DefiLlama; the report shows the eight largest. Issuer and authorisation from "
               "FXC Intelligence (2026), Decta (2026) and eco.com (2026), not from the data.")
    w = "2.4 Euro stablecoins"
    tot = c["total_hist"]["peggedEUR_usd"]
    text_number(w, "Euro stablecoins grew by 29% in euro terms, from EUR 586 m to EUR 755 m; 23% in US dollars",
                f"{total.eur_m_1_may[0]:.1f} -> {total.eur_m_1_nov[0]:.1f} ({total['growth_%'][0]:.2f}%); USD "
                f"{pct(on_or_before(tot, D0), on_or_before(tot, D1)):.2f}%", "EUR m / %",
                "Sum of euro coins in EUR; USD from the aggregate series", "dl_all_coins_on_dates, dl_total_supply_history")
    text_number(w, "Euro coins make up only 0.3% of all stablecoins", on_or_before(tot, D1) / c["total"][D1] * 100,
                "%", "Euro coins (USD) / all stablecoins", "dl_total_supply_history")
    e = eur.set_index("symbol")
    text_number(w, "EURC and EURCV together hold 83% of the euro market",
                (e.loc["EURC", "eur_m_1_nov"] + e.loc["EURCV", "eur_m_1_nov"]) / total.eur_m_1_nov[0] * 100, "%",
                "(EURC + EURCV) / all euro coins", "dl_all_coins_on_dates")
    return total.eur_m_1_nov[0]


# ============================================================================
# Chapter 3
# ============================================================================
CHF_INFO = {   # issuer and launch date: from issuer websites and the sources in the report, not from the data
    "CHFAU": ("AllUnity GmbH (Frankfurt)", "26 Feb 2026"),
    "ZCHF": ("None; Frankencoin Association stewards it (Zug)", "2023"),
    "VCHF": ("VNX Global Ltd. (Bermuda; before: Liechtenstein)", "15 Dec 2022"),
    "CHFm": ("None; Mento protocol (Celo)", "6 Jun 2025"),
    "HCHF": ("None; HLiquity protocol by Swisscoast AG", "5 Jun 2024"),
    "CHF24": ("SR Saphirstein AG (Fiat24, Zurich)", "Unknown"),
    "CHF-S": ("Safirum AG (Rotkreuz, Zug)", "3 Nov 2026")}


def table_3_1(c):
    t = chf_market(c)
    fx = c["chf_per_usd"][D1]
    t["growth_%"] = pct(t.chf_m_1_may, t.chf_m_1_nov)
    tot0, tot1 = t.chf_m_1_may.sum(), t.chf_m_1_nov.sum()
    t["share_of_chf_coins_%"] = t.chf_m_1_nov / tot1 * 100
    t["share_of_all_stablecoins_%"] = t.chf_m_1_nov * 1e6 / fx / c["total"][D1] * 100
    c24 = c["chf24"]
    extra = pd.DataFrame([
        {"coin": "CHF24", "chf_m_1_may": c24.loc[D0, "arbitrum_client_supply"] / 1e6,
         "chf_m_1_nov": c24.loc[D1, "arbitrum_client_supply"] / 1e6},
        {"coin": "CHF-S"},
        {"coin": "All CHF coins", "chf_m_1_may": tot0, "chf_m_1_nov": tot1, "share_of_chf_coins_%": 100,
         "share_of_all_stablecoins_%": tot1 * 1e6 / fx / c["total"][D1] * 100},
        {"coin": "All CHF coins without CHFAU", "chf_m_1_may": tot0 - t.chf_m_1_may[0],
         "chf_m_1_nov": tot1 - t.chf_m_1_nov[0]}])
    extra["growth_%"] = pct(extra.chf_m_1_may, extra.chf_m_1_nov)
    t = pd.concat([t, extra], ignore_index=True)
    t.insert(1, "issuer", t.coin.map(lambda k: CHF_INFO.get(k, ("", ""))[0]))
    t.insert(2, "launched", t.coin.map(lambda k: CHF_INFO.get(k, ("", ""))[1]))
    save_table("Table 3.1", "Swiss franc stablecoins: issuer, launch and supply, 1 May and 1 Nov 2026", t.round(4),
               "dl_coin_history (ZCHF, VCHF, CHFm, HCHF), chf_extra_supply_daily (CHFAU, 1 May), "
               "cg_chf_coins_history (CHFAU, 1 Nov), chf24_supply, dl_total_supply_history, snb_devkum",
               f"Totals exclude CHF24 (clients only, no market data) and CHF-S (launched after the cut-off). Share of "
               f"all stablecoins at CHF {fx:.4f} per USD. Issuer and launch dates from issuer websites, not the data.")
    return {D0: tot0, D1: tot1}, t


def fig_3_1(c):
    t = chf_market(c)
    cap = "Share of each coin in the Swiss franc stablecoin market, 1 May and 1 Nov 2026"
    t["share_%_1_may"] = t.chf_m_1_may / t.chf_m_1_may.sum() * 100
    t["share_%_1_nov"] = t.chf_m_1_nov / t.chf_m_1_nov.sum() * 100
    save_table("Fig. 3.1", cap, t.round(4), "as Table 3.1")
    fig, ax = plt.subplots(figsize=(9.5, 2.6))
    for yi, col, lab in [(1, "share_%_1_may", "1 May 2026"), (0, "share_%_1_nov", "1 Nov 2026")]:
        left = 0
        for _, r in t.iterrows():
            ax.barh(yi, r[col], left=left, color=COLORS[r.coin], height=0.55, edgecolor="white")
            if r[col] >= 6:
                ax.text(left + r[col] / 2, yi, f"{r.coin}\n{r[col]:.0f}%", ha="center", va="center",
                        color="white", fontsize=9)
            left += r[col]
        small = ", ".join(f"{r.coin} {r[col]:.1f}%" for _, r in t.iterrows() if r[col] < 6)
        total = t[col.replace("share_%", "chf_m")].sum()
        ax.text(0, yi + 0.36, f"{lab}: CHF {total:.1f} m; smaller: {small}", fontsize=8.5, color=INK2)
    ax.set_yticks([])
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.45, 1.75)
    clean(ax, "x")
    ax.set_title(f"Fig. 3.1. {cap}")
    save_figure("Fig. 3.1", cap, fig)


def section_3_1(c, tot, ch1_total_crypto, ranks, euro_eur_m):
    w = "3.1 Market size"
    fx = c["chf_per_usd"][D1]
    usd_m = tot[D1] / fx
    text_number(w, "CHF 72.7 m (USD 88.5 m) on 1 Nov 2026; 0.03% of all stablecoins; about 0.003% of the crypto market",
                f"CHF {tot[D1]:.2f} m = USD {usd_m:.2f} m; {usd_m * 1e6 / c['total'][D1] * 100:.4f}% of stablecoins; "
                f"{usd_m / 1e3 / ch1_total_crypto * 100:.5f}% of the 100 largest crypto-assets", "",
                "Table 3.1 total at the SNB end-October rate", "Table 3.1, dl_total_supply_history, cg_top_crypto_on_dates")
    r = ranks.set_index("symbol")
    for sym in ("CHFAU", "ZCHF", "VCHF"):
        rr = r.loc[sym]
        text_number(w, f"{sym}: USD value and rank among all stablecoins on 1 Nov 2026 (rank on 1 May)",
                    f"USD {rr[f'usd_{D1}'] / 1e6:.2f} m, rank {rr[f'rank_{D1}']:.0f} (1 May: {rr[f'rank_{D0}']:.0f})",
                    "", "Ranking table, Section 2.2", "Section 2.2 ranking")
    live = ranks[ranks.id != "not on DefiLlama"][f"supply_{D1}"].fillna(0) > 0
    text_number(w, "Some 430 stablecoins tracked by DefiLlama",
                f"{int(live.sum())} with supply on 1 Nov; {int(ranks[f'rank_{D1}'].notna().sum())} of them (incl. CHFAU) "
                "with a US-dollar value for the ranking", "coins", "Count of coins with supply above 0 on 1 Nov 2026",
                "dl_all_coins_on_dates")
    snb = read("snb_snbmonagg")
    snb = snb[(snb.D0 == "B") & (snb.Date == MONEY_MONTH)].set_index("D1")["Value"]
    text_number(w, "0.01% of sight deposits at banks (CHF 689 bn) and 0.1% of banknotes in circulation (CHF 71 bn)",
                f"{tot[D1] / snb['S0'] * 100:.4f}% of {snb['S0'] / 1e3:.1f} bn; {tot[D1] / snb['B'] * 100:.3f}% of "
                f"{snb['B'] / 1e3:.1f} bn", "", f"SNB monetary aggregates, {MONEY_MONTH} (S0 sight deposits, B banknotes)",
                "snb_snbmonagg")
    eur_chf = euro_eur_m * c["chf_per_eur"][D1]
    text_number(w, "The euro stablecoin market is about ten times larger", eur_chf / tot[D1], "times",
                "Euro coins (EUR m, converted to CHF at the SNB end-October rate) / franc coins (CHF m)",
                "Table 2.2, Table 3.1, snb_devkum")
    gdp = read("wb_gdp_emu_che").pivot(index="year", columns="iso3", values="gdp_usd_bn")
    eur_usd = on_or_before(c["total_hist"]["peggedEUR_usd"], D1)
    text_number(w, "In 2025 the euro area economy was about 17 times the Swiss economy (USD 18.0 tn against 1.04 tn); "
                "franc coins about 0.0085% of Swiss GDP, euro coins about 0.0046% of euro-area GDP",
                f"{gdp.loc[2025, 'EMU'] / gdp.loc[2025, 'CHE']:.1f}x ({gdp.loc[2025, 'EMU']:.0f} / "
                f"{gdp.loc[2025, 'CHE']:.0f} bn); CHF coins {usd_m / 1e3 / gdp.loc[2025, 'CHE'] * 100:.4f}%; euro coins "
                f"{eur_usd / 1e9 / gdp.loc[2025, 'EMU'] * 100:.4f}%", "", "Coin values on 1 Nov 2026 / 2025 GDP",
                "wb_gdp_emu_che, Table 3.1, dl_total_supply_history")


def fig_3_2(c):
    cg = c["cg_chf"]
    cg = cg[(cg.date >= D0) & (cg.date <= D1)]
    cmp_ = read("cg_comparators_history", parse_dates=["date"])
    cmp_ = cmp_[(cmp_.date >= D0) & (cmp_.date <= D1)]
    cmp_ = cmp_.assign(peg_deviation_bp=(cmp_.price - 1) * 1e4)
    series = [("CHFAU", "allunity-chf", cg), ("ZCHF", "frankencoin", cg), ("VCHF", "vnx-swiss-franc", cg),
              ("USDT", "tether", cmp_), ("USDC", "usd-coin", cmp_)]
    idx = pd.date_range(D0, D1)
    daily, stats = {}, []
    for lab, cid, df in series:
        g = df[df.coin_id == cid].set_index("date")
        n_all = int(g.peg_deviation_bp.notna().sum())
        n_low = 0
        if df is cg:
            n_low = int((g.volume_24h < 1000).sum())
            g = g[g.volume_24h >= 1000]               # days with less than CHF 1,000 of trading are left out
        k = g.peg_deviation_bp.reindex(idx)
        daily[lab] = k
        v = k.dropna()
        stats.append({"coin": lab, "days_with_price": n_all, "days_left_out_volume_below_1000": n_low,
                      "days_used": len(v), "mean_abs_deviation_bp": v.abs().mean(),
                      "days_outside_50bp": int((v.abs() > 50).sum()),
                      "share_days_outside_50bp_%": (v.abs() > 50).mean() * 100,
                      "max_abs_deviation_bp": v.abs().max(), "days_above_plus_160bp": int((v > 160).sum())})
    cap = "Daily deviation from the peg in basis points, 1 May to 1 Nov 2026"
    st = pd.DataFrame(stats)
    save_table("Fig. 3.2", cap, pd.DataFrame(daily).round(3).rename_axis("date").reset_index(),
               "cg_chf_coins_history, cg_comparators_history",
               "CHF coins: price in CHF; dollar coins: price in USD. Days with less than CHF 1,000 of trading left out.",
               part="daily")
    save_table("Fig. 3.2", cap, st.round(3), "cg_chf_coins_history, cg_comparators_history", part="summary")
    fig, axes = plt.subplots(5, 1, figsize=(9, 8), sharex=True, sharey=True)
    for ax, (lab, _, _), s in zip(axes, series, stats):
        k = daily[lab]
        col = COLORS.get(lab, "#2a78d6")
        ax.axhspan(-50, 50, color=BAND, zorder=0)
        ax.axhline(0, color=INK2, lw=0.6)
        ax.plot(k.index, k.clip(-160, 160), color=col, lw=1.4, marker="o" if lab == "CHFAU" else None, ms=2.5)
        ax.set_ylim(-170, 170)
        ax.set_yticks([-150, -50, 0, 50, 150])
        clean(ax)
        note = (f"mean |dev.| {s['mean_abs_deviation_bp']:.0f} bp · {s['days_outside_50bp']} of {s['days_used']} "
                f"days outside ±50 bp")
        if s["days_above_plus_160bp"]:
            note += f" · {s['days_above_plus_160bp']} days above +160 bp (max +{k.max():.0f}, cut off)"
        ax.set_title(lab, fontsize=10, pad=2)
        ax.text(1, 1.03, note, transform=ax.transAxes, ha="right", fontsize=8.5, color=INK2)
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.supylabel("Deviation from peg, basis points", color=INK2)
    fig.suptitle(f"Fig. 3.2. {cap} (shaded band = ±50 bp)", x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    save_figure("Fig. 3.2", cap, fig)

    s = st.set_index("coin")
    w = "3.2 How the coins compare"
    text_number(w, "CHFAU is traded so rarely that 40 of its 93 days had less than CHF 1,000 of volume",
                f"{s.loc['CHFAU', 'days_left_out_volume_below_1000']} of {s.loc['CHFAU', 'days_with_price']} days",
                "days", "Days from 1 May to 1 Nov with a CoinGecko price (CHFAU history starts 4 Aug 2026)",
                "cg_chf_coins_history")
    vchf = daily["VCHF"]
    above = vchf[vchf > 160]
    sep_oct = above[(above.index >= "2026-09-01") & (above.index <= "2026-10-31")]
    text_number(w, "VCHF: more than 50 bp away on a quarter of all days; on 12 days in September and October a premium "
                "of more than 160 bp, at most 705 bp",
                f"{s.loc['VCHF', 'share_days_outside_50bp_%']:.1f}% of days; {len(above)} days above +160 bp in all, "
                f"{len(sep_oct)} of them in Sep-Oct (max {sep_oct.max():.0f} bp); overall max {vchf.max():.0f} bp on "
                f"{vchf.idxmax():%d %b %Y}", "", "Fig. 3.2", "cg_chf_coins_history")


def chf_volumes(c):
    cg = c["cg_chf"]
    w = "3.3 The coins one by one"
    for cid, lab in (("allunity-chf", "CHFAU"), ("frankencoin", "ZCHF"), ("vnx-swiss-franc", "VCHF")):
        v = cg[(cg.coin_id == cid) & (cg.date <= D1)].sort_values("date").tail(30)["volume_24h"]
        text_number(w, f"{lab}: average and median daily trading over the 30 days to 1 Nov 2026",
                    f"mean CHF {v.mean():,.0f}, median CHF {v.median():,.0f}", "CHF",
                    "CoinGecko 24h volume in CHF, last 30 days up to 1 Nov", "cg_chf_coins_history")


def collateral_usd(coin, day):
    """Collateral (DefiLlama TVL, summed over blockchains) behind a crypto-backed CHF coin on a date, in USD."""
    p = read("dl_protocol_collateral_history", parse_dates=["date"])
    p = p[p.coin == coin].groupby("date")["tvl_usd"].sum().sort_index()
    return on_or_before(p, day)


def fig_3_3(c):
    fx = c["chf_per_usd"][D1]
    zchf, hchf = chf_on(c, "ZCHF", D1), chf_on(c, "HCHF", D1)
    zcol, hcol = collateral_usd("ZCHF", D1), collateral_usd("HCHF", D1)
    rows = [
        ["ZCHF", zcol * fx / zchf, np.nan, "1 Nov 2026", "Crypto collateral",
         f"collateral USD {zcol:,.0f} x {fx} / supply CHF {zchf:,.0f}"],
        ["HCHF", hcol * fx / hchf, manual("hchf_min_ratio"), "1 Nov 2026", "Crypto collateral",
         f"collateral USD {hcol:,.2f} x {fx} / supply CHF {hchf:,.0f}"],
        ["CHFm", manual("chfm_collateral") / manual("chfm_debt_value"), manual("chfm_min_ratio"), "20 Nov 2026",
         "Crypto collateral", "collateral USDm / USD value of CHFm outstanding (Mento dashboard)"],
        ["CHFAU", 1.0, np.nan, "by design", "Reserves, 1:1 by design", "no published figure for 1 Nov"],
        ["VCHF", 1.0, np.nan, "by design", "Reserves, 1:1 by design", "no published figure for 1 Nov"],
        ["CHF24", 1.0, np.nan, "by design", "Reserves, 1:1 by design", "no published figure for 1 Nov"],
        ["USDT", manual("tether_assets") / manual("tether_liabilities"), np.nan, "30 Sep 2026", "Reserves, reported",
         "assets / liabilities (Tether attestation)"],
        ["USDC", manual("circle_reserves") / manual("usdc_outstanding"), np.nan, "30 Sep 2026", "Reserves, reported",
         "reserves / USDC outstanding (Circle)"]]
    t = pd.DataFrame(rows, columns=["coin", "ratio", "minimum_ratio", "date", "type", "calculation"])
    cap = "Backing per coin in circulation: value of collateral or reserves divided by coins outstanding"
    save_table("Fig. 3.3", cap, t.round(4), "dl_protocol_collateral_history (ZCHF, HCHF collateral), dl_coin_history "
               "(ZCHF, HCHF supply), snb_devkum, manual_inputs (CHFm, USDT, USDC, minimum ratios)")
    fig, ax = plt.subplots(figsize=(8.8, 4.2))
    o = t.iloc[::-1].reset_index(drop=True)
    colors = {"Crypto collateral": "#eb6834", "Reserves, reported": "#2a78d6", "Reserves, 1:1 by design": "#9cc3f0"}
    ax.barh(o.index, o.ratio, 0.55, color=[colors[k] for k in o.type],
            hatch=["//" if k.endswith("design") else "" for k in o.type])
    ax.axvline(1, color=INK, lw=1)
    for i, r in o.iterrows():
        ax.text(r.ratio + 0.04, i, f"{r.ratio:.2f}x ({r.date})", va="center", fontsize=9)
        if pd.notna(r.minimum_ratio):
            ax.plot([r.minimum_ratio] * 2, [i - 0.3, i + 0.3], color=INK, lw=2)
    ax.set_yticks(o.index, o.coin)
    ax.set_xlim(0, 3.4)
    clean(ax, "x")
    ax.legend([plt.Rectangle((0, 0), 1, 1, color=v) for v in colors.values()], list(colors), frameon=False,
              loc="lower right", fontsize=8.5)
    ax.set_title(f"Fig. 3.3. {cap}\n(black ticks: minimum ratio the protocol requires)")
    save_figure("Fig. 3.3", cap, fig)
    text_number("3.2 How the coins compare", "ZCHF backed 1.36 times: CHF 47.4 m of collateral for CHF 35.0 m of ZCHF",
                f"{t.ratio[0]:.3f}; CHF {zcol * fx / 1e6:.2f} m / CHF {zchf / 1e6:.2f} m", "",
                "Fig. 3.3", "dl_protocol_collateral_history, dl_coin_history, snb_devkum")


def table_3_4(c):
    sp = read("dl_chf_chain_split_on_dates")
    sp = sp[["symbol", "chain", f"supply_{D1}"]].rename(columns={f"supply_{D1}": "chf"}).dropna()
    sp["chain"] = sp["chain"].replace({"OP Mainnet": "Optimism", "xDai": "Gnosis", "ICP": "Internet Computer"})
    t = sp.pivot_table(index="chain", columns="symbol", values="chf", aggfunc="sum") / 1e3
    t = t.loc[t.sum(axis=1).sort_values(ascending=False).index]
    t["CHF24"] = np.nan
    t.loc["Arbitrum", "CHF24"] = c["chf24"].loc[D1, "arbitrum_client_supply"] / 1e3
    plat = read("cg_chf_contracts")
    chfau = ", ".join(plat[plat.symbol == "CHFAU"].platform)
    t.loc["Total"] = t.sum()
    t.loc["Total", "CHFAU"] = chf_on(c, "CHFAU", D1) / 1e3
    save_table("Table 3.4", "Supply by blockchain, CHF thousand, 1 Nov 2026", t.reset_index().round(3),
               "dl_chf_chain_split_on_dates, cg_chf_contracts (CHFAU chains), chf24_supply",
               f"CHFAU per-chain supply not available; it is live on: {chfau}. CHF24: supply held by clients on "
               "Arbitrum; Mantle not included.")


def fig_3_4(c):
    s = c["chf_supply"]
    s = s[(s.index >= "2025-01-01") & (s.index <= AFTER_CUTOFF)]
    df = pd.DataFrame({"ZCHF": s["ZCHF"], "CHFAU": s["CHFAU"], "VCHF": s["VCHF"],
                       "CHFm and HCHF": s[["CHFm", "HCHF"]].sum(axis=1, min_count=1)}) / 1e6
    cap = "Swiss franc stablecoin supply by coin, January 2025 to 19 November 2026"
    save_table("Fig. 3.4", cap, df.round(4).reset_index().rename(columns={"index": "date"}),
               "dl_coin_history, chf_extra_supply_daily, cg_chf_coins_history",
               "CHF m. CHFAU: weekly on-chain supply until 4 Aug 2026, daily CoinGecko market value in CHF afterwards.")
    fig, ax = plt.subplots(figsize=(9.5, 4.2))
    for k in df.columns:
        v = df[k].dropna()
        ax.plot(v.index, v, color=COLORS[k], lw=2 if k != "CHFm and HCHF" else 1.4, label=k)
    for d, lab in ((D0, "1 May"), (D1, "1 Nov")):
        ax.axvline(pd.Timestamp(d), color=INK2, ls=":", lw=0.8)
        ax.text(pd.Timestamp(d), df.max().max(), f" {lab}", fontsize=8.5, color=INK2, va="top")
    ax.set_ylabel("Supply, CHF m")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    clean(ax)
    ax.legend(frameon=False, ncol=4, loc="upper left", bbox_to_anchor=(0, -0.08))
    ax.set_title(f"Fig. 3.4. {cap}")
    save_figure("Fig. 3.4", cap, fig)

    w = "3.3 The coins one by one"
    used = "dl_coin_history, chf_extra_supply_daily, cg_chf_coins_history"
    a = df["CHFAU"].dropna()
    peak = a[a.index <= "2026-08-03"]
    text_number(w, "CHFAU on-chain supply CHF 2.5 m at end-March, CHF 4.4 m on 1 May, about CHF 50.7 m at its weekly "
                "peak on 20 Jul; by 19 Nov CHF 33.8 m",
                f"end-Mar {on_or_before(a, '2026-03-31'):.2f} ({a[:'2026-03-31'].index[-1]:%d %b}); 1 May "
                f"{on_or_before(a, D0):.2f}; weekly peak {peak.max():.2f} on {peak.idxmax():%d %b}; 19 Nov "
                f"{on_or_before(a, AFTER_CUTOFF):.2f}", "CHF m", "Fig. 3.4 series", used)
    z = df["ZCHF"].dropna()
    spring25 = z["2025-03-01":"2025-05-31"]
    text_number(w, "ZCHF grew from about CHF 10 m in spring 2025 to a peak near CHF 37 m in June 2026; 19 Nov CHF 32.3 m",
                f"spring 2025 {spring25.min():.1f}-{spring25.max():.1f}; peak {z[:D1].max():.2f} on "
                f"{z[:D1].idxmax():%d %b %Y}; 19 Nov {on_or_before(z, AFTER_CUTOFF):.2f}", "CHF m", "Fig. 3.4 series", used)
    v = df["VCHF"].dropna()
    text_number(w, "VCHF dropped from CHF 8 m to CHF 3 m in April 2025",
                f"31 Mar 2025 {on_or_before(v, '2025-03-31'):.2f}; 30 Apr 2025 {on_or_before(v, '2025-04-30'):.2f}",
                "CHF m", "Fig. 3.4 series", used)
    text_number(w, "CHFm: about CHF 73,000 outstanding on 1 Nov", chf_on(c, "CHFm", D1), "CHF", "DefiLlama supply",
                "dl_coin_history")
    if "XCHF" in c["chf_supply"]:
        x = c["chf_supply"]["XCHF"].dropna()
        text_number(w, "About 270,000 XCHF still outstanding in November 2026",
                    f"{x.iloc[-1]:,.0f} on {x.index[-1]:%d %b %Y}", "XCHF", "Last DefiLlama value", "dl_coin_history")


def chf24_numbers(c):
    c24 = c["chf24"]
    acc = read("chf24_internal_accounts")
    a9101 = acc.loc[acc.account == 9101, f"chf24_{D1}"]
    text_number("3.3 The coins one by one",
                "Of 185.8 m CHF24 on Arbitrum, 184.5 m sat in Fiat24's internal accounts on 1 Nov 2026, 123.9 m in "
                "account 9101; clients held CHF 1.28 m on 1 Nov, down from CHF 1.78 m (-28%); 7.1 m on Mantle",
                f"total {c24.loc[D1, 'arbitrum_total_supply'] / 1e6:.2f} m; internal "
                f"{c24.loc[D1, 'fiat24_internal_accounts'] / 1e6:.2f} m; account 9101 "
                f"{a9101.iloc[0] / 1e6 if len(a9101) else float('nan'):.2f} m; clients "
                f"{c24.loc[D1, 'arbitrum_client_supply'] / 1e6:.3f} m (1 May "
                f"{c24.loc[D0, 'arbitrum_client_supply'] / 1e6:.3f} m, "
                f"{pct(c24.loc[D0, 'arbitrum_client_supply'], c24.loc[D1, 'arbitrum_client_supply']):.1f}%); Mantle "
                f"{c24.loc[D1, 'mantle_total_supply'] / 1e6:.2f} m", "", "On-chain balances at the last block before "
                "each date", "chf24_supply, chf24_internal_accounts")


# ============================================================================
def main():
    FIGS.mkdir(exist_ok=True)
    c = load_common()
    print("Chapter 3 totals (needed for chapter 1) ...")
    ch3_total, _ = table_3_1(c)
    print("Chapter 1 ...")
    table_1_1(c, ch3_total)
    st = fig_1_1_and_1_2(c)
    fig_1_3(c)
    fig_1_4(c, st)
    fig_1_5()
    saving_numbers()
    print("Chapter 2 ...")
    fig_2_1(c)
    ranks = section_2_2(c)
    table_2_1(c)
    fig_2_2()
    reserves_numbers()
    euro_eur_m = table_2_2(c)
    print("Chapter 3 ...")
    fig_3_1(c)
    section_3_1(c, ch3_total, st.loc["Whole market (100 largest)", "usd_bn_1_nov"], ranks, euro_eur_m)
    fig_3_2(c)
    chf_volumes(c)
    fig_3_3(c)
    table_3_4(c)
    fig_3_4(c)
    chf24_numbers(c)

    pd.DataFrame(TEXT).to_csv(OUT / "Numbers_in_text.csv", index=False)
    idx = pd.DataFrame(INDEX)
    idx["order"] = idx["item"].str.extract(r"(\d+)\.(\d+)").astype(float).apply(lambda r: r[0] * 100 + r[1], axis=1)
    idx.sort_values(["order", "item", "kind"]).drop(columns="order").to_csv(OUT / "index.csv", index=False)
    print(f"\nDone: {sum(k == 'numbers' for k in idx.kind)} tables, {sum(k == 'figure' for k in idx.kind)} figures, "
          f"{len(TEXT)} numbers in the text.")
    print(f"Tables and index.csv: {OUT}\nFigures: {FIGS}")


if __name__ == "__main__":
    main()
