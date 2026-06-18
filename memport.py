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

import time
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf

# ── Portfolio Configuration ───────────────────────────────────────────────────

HOLDINGS = [
    # ticker  company                          tier                shares  entry
    ("MU",   "Micron Technology",            "DRAM / NAND",        96,  1086.00),
    ("WDC",  "Western Digital",              "Storage",            96,   739.00),
    ("LRCX", "Lam Research",                 "Memory Equipment",  203,   386.00),
    ("ONTO", "Onto Innovation",              "Memory Equipment",  112,   332.00),
    ("SOXX", "iShares Semiconductor ETF",    "ETFs",               72,   619.00),
    ("EWY",  "iShares MSCI South Korea ETF", "ETFs",              171,   212.00),
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

@st.cache_data(ttl=60)
def fetch_live(tickers: tuple) -> dict:
    """Fetch current price + previous close for each ticker. Cached 60 s."""
    result = {}
    try:
        raw = yf.download(
            list(tickers), period="5d", interval="1d",
            progress=False, auto_adjust=True, group_by="ticker"
        )
        # group_by="ticker" gives a MultiIndex (ticker, field); handle both layouts
        if isinstance(raw.columns, pd.MultiIndex):
            for t in tickers:
                try:
                    s = raw[t]["Close"].dropna()
                except KeyError:
                    continue
                if len(s) >= 2:
                    result[t] = {"price": float(s.iloc[-1]), "prev": float(s.iloc[-2])}
                elif len(s) == 1:
                    result[t] = {"price": float(s.iloc[0]), "prev": float(s.iloc[0])}
        else:
            # Single-ticker fallback
            s = raw["Close"].dropna()
            t = tickers[0]
            if len(s) >= 2:
                result[t] = {"price": float(s.iloc[-1]), "prev": float(s.iloc[-2])}
            elif len(s) == 1:
                result[t] = {"price": float(s.iloc[0]), "prev": float(s.iloc[0])}
    except Exception as e:
        st.warning(f"Price fetch error: {e}")
    return result


@st.cache_data(ttl=3_600)
def fetch_historical(tickers: tuple, start: date) -> dict:
    """Fetch first available close on or after `start` (7-day window). Cached 1 h."""
    result = {}
    try:
        end = start + timedelta(days=8)
        raw = yf.download(list(tickers), start=start.isoformat(), end=end.isoformat(),
                          interval="1d", progress=False, auto_adjust=True)
        closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
        for t in tickers:
            if t in closes.columns:
                s = closes[t].dropna()
                if len(s) > 0:
                    result[t] = float(s.iloc[0])
    except Exception as e:
        st.warning(f"Historical fetch error: {e}")
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

    auto_refresh = st.toggle("Auto-refresh every 60 s", value=True)
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
        "**Prices:** Yahoo Finance via yfinance (~15 min delay)\n\n"
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
    "Prices via Yahoo Finance (~15 min delay on free tier). "
    "Not investment advice."
)

# ── Auto-refresh Countdown ────────────────────────────────────────────────────

if auto_refresh:
    placeholder = st.empty()
    for i in range(60, 0, -1):
        placeholder.caption(f"⏱ Auto-refreshing in {i}s…")
        time.sleep(1)
    placeholder.empty()
    st.cache_data.clear()
    st.rerun()
