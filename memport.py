"""
MemPort — Memory Sector Portfolio Tracker
==========================================
Tracks 6 memory & storage positions (actual purchases, Jun 2026).

Quick start
-----------
    pip install -r requirements.txt
    streamlit run memport.py

Tickers: MU · WDC · LRCX · ONTO · SOXX · EWY
"""

from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st
import requests

# ── Portfolio Configuration ───────────────────────────────────────────────────

HOLDINGS = [
    # ticker  company                          tier                shares  entry
    ("MU",   "Micron Technology",            "DRAM / NAND",        96,  1081.00),
    ("WDC",  "Western Digital",              "Storage",            96,   730.00),
    ("LRCX", "Lam Research",                 "Memory Equipment",  203,   378.00),
    ("ONTO", "Onto Innovation",              "Memory Equipment",  112,   327.00),
    ("SOXX", "iShares Semiconductor ETF",    "ETFs",               72,   608.00),
    ("EWY",  "iShares MSCI South Korea ETF", "ETFs",              171,   208.00),
]

TIER_COLORS = {
    "DRAM / NAND":      "#3B82F6",
    "Storage":          "#F59E0B",
    "Memory Equipment": "#10B981",
    "ETFs":             "#8B5CF6",
}

TICKERS     = [h[0] for h in HOLDINGS]
TOTAL_ALLOC = sum(h[3] * h[4] for h in HOLDINGS)   # shares × entry  ~$371,562
CREATION_DATE = date(2026, 6, 17)

# ── Price Fetching ────────────────────────────────────────────────────────────

TD_KEY = st.secrets.get("TWELVE_DATA_API_KEY", "")   # add TWELVE_DATA_API_KEY to Streamlit secrets

@st.cache_data(ttl=60)
def fetch_live(tickers: tuple) -> dict:
    """Fetch current price + previous close via Twelve Data /quote. One call, cached 60 s."""
    result = {}
    try:
        # /quote returns price + previous_close in a single batch call
        symbols = ",".join(tickers)
        params  = {"symbol": symbols, "apikey": TD_KEY}
        r = requests.get("https://api.twelvedata.com/quote", params=params, timeout=15)
        r.raise_for_status()
        data = r.json()

        # Single ticker returns a dict directly; multiple tickers returns {ticker: dict}
        if len(tickers) == 1:
            data = {tickers[0]: data}

        for t, q in data.items():
            if isinstance(q, dict) and q.get("status") != "error":
                price = q.get("close") or q.get("price")
                prev  = q.get("previous_close")
                if price is not None and prev is not None:
                    result[t] = {"price": float(price), "prev": float(prev)}
    except Exception as e:
        st.warning(f"Price fetch error: {e}")
    return result


@st.cache_data(ttl=3_600)
def fetch_historical(tickers: tuple, start: date) -> dict:
    """Fetch closing price on or just after `start` via Twelve Data. Cached 1 h."""
    result = {}
    end = start + timedelta(days=8)
    for t in tickers:
        try:
            params = {
                "symbol":     t,
                "start_date": start.isoformat(),
                "end_date":   end.isoformat(),
                "interval":   "1day",
                "apikey":     TD_KEY,
            }
            r = requests.get("https://api.twelvedata.com/time_series", params=params, timeout=10)
            r.raise_for_status()
            values = r.json().get("values", [])
            if values:
                # Twelve Data returns newest-first; take last (closest to start date)
                result[t] = float(values[-1]["close"])
        except Exception as e:
            st.warning(f"Historical fetch error ({t}): {e}")
    return result

# ── Page Setup ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="MemPort · Memory Sector Portfolio",
    page_icon="💾",
    layout="wide",
)

st.markdown("""
<style>
  /* Summary cards */
  [data-testid="stMetric"] {
    background: #f8fafc;
    border-radius: 10px;
    padding: 14px 18px;
    border-left: 3px solid #1a1a2e;
  }
  /* Positive/negative delta color override handled by Streamlit */
  header[data-testid="stHeader"] { background: #1a1a2e; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 💾 MemPort")
    st.caption("Memory & Storage Sector — Virtual Portfolio")
    st.divider()

    if st.button("↻ Refresh Prices", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()

    st.divider()

    st.markdown("### 📅 P&L Start Date")
    use_custom = st.toggle("Custom start date", value=False)
    start_date: date | None = None
    if use_custom:
        start_date = st.date_input(
            "Start date",
            value=CREATION_DATE,
            min_value=date(2010, 1, 1),
            max_value=date.today(),
            help="P&L calculated from closing prices on this date.",
        )

    st.divider()
    st.caption(
        "**Holdings:** MU · WDC · LRCX · ONTO · SOXX · EWY\n\n"
        "**Prices:** Twelve Data free tier (800 calls/day)\n\n"
        "Actual purchase prices · Jun 2026"
    )

# ── Fetch Prices ──────────────────────────────────────────────────────────────

with st.spinner("Fetching live prices…"):
    live = fetch_live(tuple(TICKERS))

hist: dict = {}
if use_custom and start_date:
    with st.spinner(f"Loading historical prices for {start_date}…"):
        hist = fetch_historical(tuple(TICKERS), start_date)

live_count = sum(1 for t in TICKERS if t in live)
missing = [t for t in TICKERS if t not in live]

# ── Build DataFrame ───────────────────────────────────────────────────────────

rows = []
for ticker, name, tier, num_shares, default_entry in HOLDINGS:
    alloc   = num_shares * default_entry          # cost basis always at purchase price
    entry   = hist.get(ticker, default_entry) if (use_custom and start_date) else default_entry
    live_data = live.get(ticker)
    price   = live_data["price"] if live_data else None
    prev    = live_data["prev"]  if live_data else None
    value   = price * num_shares if price is not None else alloc  # show cost if no live price
    pnl     = value - alloc
    pnl_pct = pnl / alloc * 100
    day_pct = (price - prev) / prev * 100 if (price and prev) else 0.0

    rows.append({
        "Ticker":  ticker,
        "Company": name,
        "Tier":    tier,
        "Alloc":   alloc,
        "Weight":  alloc / TOTAL_ALLOC * 100,
        "Shares":  num_shares,
        "Entry":   default_entry,
        "Price":   price if price is not None else float("nan"),
        "Value":   value,
        "Day %":   day_pct,
        "P&L $":   pnl,
        "P&L %":   pnl_pct,
    })

df = pd.DataFrame(rows)

total_value   = df["Value"].sum()
total_pnl     = df["P&L $"].sum()
total_pnl_pct = total_pnl / TOTAL_ALLOC * 100
day_change    = (df["Value"] * df["Day %"] / 100).sum()

# ── Header ────────────────────────────────────────────────────────────────────

col_h, col_s = st.columns([3, 1])
with col_h:
    st.markdown("# 💾 MemPort — Memory Sector Portfolio")
    date_label = f"since {start_date}" if (use_custom and start_date) else f"since {CREATION_DATE}"
    st.caption(f"6 positions · ~$372K deployed · P&L {date_label}")
with col_s:
    status = f"🟢 Live ({live_count}/{len(TICKERS)})" if live_count > 0 else "🔴 No live data"
    st.markdown(f"<div style='text-align:right;padding-top:24px;font-size:13px'>{status}</div>",
                unsafe_allow_html=True)

st.divider()

if missing:
    st.warning(
        f"⚠️ Could not fetch live prices for: **{', '.join(missing)}**. "
        "Portfolio Value for these positions shows cost basis, not market value. "
        "Try clicking ↻ Refresh Prices in the sidebar."
    )

# ── Summary Metrics ───────────────────────────────────────────────────────────

c1, c2, c3, c4, c5 = st.columns(5)

best  = df.loc[df["P&L %"].idxmax()]
worst = df.loc[df["P&L %"].idxmin()]

c1.metric("Portfolio Value",  f"${total_value:,.0f}",  f"Cost: ${TOTAL_ALLOC:,}")
c2.metric("Total P&L",
          f"${total_pnl:+,.0f}",
          f"{total_pnl_pct:+.2f}%",
          delta_color="normal")
c3.metric("Day's Change",     f"${day_change:+,.0f}")
c4.metric("Best",  best["Ticker"],  f"{best['P&L %']:+.2f}%")
c5.metric("Worst", worst["Ticker"], f"{worst['P&L %']:+.2f}%",  delta_color="inverse")

st.divider()

# ── Holdings Table ────────────────────────────────────────────────────────────

pnl_label = f"P&L % (since {start_date})" if (use_custom and start_date) else "P&L %"
st.markdown(f"### Holdings  ·  P&L {date_label}")

display = df[[
    "Ticker", "Company", "Tier", "Weight", "Shares",
    "Entry", "Price", "Day %", "Value", "P&L $", "P&L %"
]].copy()

# Capture numeric P&L % BEFORE formatting to strings, keyed by Ticker
pnl_numeric = df.set_index("Ticker")["P&L %"]

display["Weight"] = display["Weight"].map("{:.1f}%".format)
display["Shares"] = display["Shares"].map("{:.3f}".format)
display["Entry"]  = display["Entry"].map("${:,.2f}".format)
display["Price"]  = display["Price"].apply(lambda x: f"${x:,.2f}" if pd.notna(x) else "—")
display["Value"]  = display["Value"].map("${:,.0f}".format)
display["Day %"]  = display["Day %"].map("{:+.2f}%".format)
display["P&L $"]  = display["P&L $"].map(lambda x: f"${x:+,.0f}")
display["P&L %"]  = display["P&L %"].map("{:+.2f}%".format)
display = display.rename(columns={"P&L %": pnl_label})

display_indexed = display.set_index("Ticker")

def _style(row):
    # Use original numeric value via the ticker index, not the formatted string
    is_positive = pnl_numeric.get(row.name, 0) >= 0
    bg = "#D1FAE5" if is_positive else "#FEE2E2"
    return ["background-color:" + bg if c in ("P&L $", pnl_label) else "" for c in row.index]

styled = display_indexed.style.apply(_style, axis=1)
st.dataframe(styled, use_container_width=True, height=368)

st.divider()

# ── Charts ────────────────────────────────────────────────────────────────────

ch1, ch2 = st.columns(2)

with ch1:
    st.markdown("#### Allocation by Tier")
    tier_df = df.groupby("Tier", as_index=False)["Value"].sum()
    fig_pie = px.pie(
        tier_df, values="Value", names="Tier",
        color="Tier", color_discrete_map=TIER_COLORS,
        hole=0.4,
    )
    fig_pie.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=280,
                          legend=dict(font_size=11))
    fig_pie.update_traces(textposition="inside", textinfo="percent+label",
                          textfont_size=11)
    st.plotly_chart(fig_pie, use_container_width=True)

with ch2:
    st.markdown(f"#### P&L by Position ({date_label})")
    bar_df = df.sort_values("P&L %", ascending=False)
    fig_bar = px.bar(
        bar_df, x="Ticker", y="P&L %",
        color="P&L %",
        color_continuous_scale=["#DC2626", "#FCA5A5", "#D1FAE5", "#16A34A"],
        color_continuous_midpoint=0,
        text=bar_df["P&L %"].map("{:+.1f}%".format),
    )
    fig_bar.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=280,
                          coloraxis_showscale=False,
                          xaxis_title=None, yaxis_title="P&L %")
    fig_bar.update_traces(textposition="outside", textfont_size=11)
    st.plotly_chart(fig_bar, use_container_width=True)

st.caption(
    "Entry prices reflect actual purchase prices (Jun 2026). "
    "Prices via Twelve Data (free tier). "
    "Not investment advice."
)


