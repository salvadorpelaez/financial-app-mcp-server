#!/usr/bin/env python3
"""
Financial Data MCP Server
Exposes yfinance data as standardized MCP tools for use across financial apps.

Tools:
  - get_market_data   : OHLCV price history for a ticker
  - get_fundamentals  : Key fundamental metrics (P/E, market cap, EPS, etc.)
  - get_technicals    : RSI, MACD, Bollinger Bands for a ticker
"""

import json
import time
from datetime import datetime, timedelta

import yfinance as yf
import pandas as pd
from mcp.server.fastmcp import FastMCP

# ── Server instance ──────────────────────────────────────────────────────────
# Port 8002 for HTTP/SSE mode (stdio is default for Claude Desktop / agents)
MCP_HOST = "127.0.0.1"
MCP_PORT = 8002
mcp = FastMCP("financial-data", host=MCP_HOST, port=MCP_PORT)

# ── Simple in-memory cache ───────────────────────────────────────────────────
_cache: dict = {}
CACHE_TTL = 3600  # seconds (1 hour)


def _get_cache(key: str):
    entry = _cache.get(key)
    if entry and (time.time() - entry["ts"]) < CACHE_TTL:
        return entry["data"]
    return None


def _set_cache(key: str, data):
    _cache[key] = {"data": data, "ts": time.time()}


# ── Tool: get_market_data ────────────────────────────────────────────────────
@mcp.tool()
def get_market_data(
    symbol: str,
    start_date: str = "",
    end_date: str = "",
    period: str = "1y",
) -> str:
    """
    Fetch OHLCV price history for a ticker.

    Args:
        symbol:     Ticker symbol (e.g. 'AAPL', 'SPY')
        start_date: Start date as YYYY-MM-DD (optional — use period instead)
        end_date:   End date as YYYY-MM-DD (optional)
        period:     yfinance period string: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y
                    Ignored if start_date is provided.

    Returns:
        JSON string with date-indexed OHLCV records.
    """
    cache_key = f"market:{symbol}:{start_date}:{end_date}:{period}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    try:
        ticker = yf.Ticker(symbol.upper())
        if start_date:
            end = end_date or datetime.today().strftime("%Y-%m-%d")
            df = ticker.history(start=start_date, end=end)
        else:
            df = ticker.history(period=period)

        if df.empty:
            return json.dumps({"error": f"No data found for symbol '{symbol}'"})

        df.index = df.index.strftime("%Y-%m-%d")
        result = json.dumps({
            "symbol": symbol.upper(),
            "rows": len(df),
            "data": df[["Open", "High", "Low", "Close", "Volume"]].round(4).to_dict(orient="index")
        })
        _set_cache(cache_key, result)
        return result

    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Tool: get_bulk_prices ────────────────────────────────────────────────────
@mcp.tool()
def get_bulk_prices(symbols: list[str]) -> str:
    """
    Fetch the latest price and daily change for many tickers in one call.

    Runs the yfinance bulk download server-side so callers on rate-limited
    IPs (e.g. Vercel serverless) don't get blocked by Yahoo.

    Args:
        symbols: list of ticker symbols in yfinance notation (e.g. ['AAPL','BRK-B'])

    Returns:
        JSON string: {"SYMBOL": {"price": float|"N/A", "change": float,
        "change_percent": float}, ...} keyed by upper-cased symbol.
    """
    syms = [s.upper().strip() for s in (symbols or []) if s and s.strip()]
    if not syms:
        return json.dumps({})

    try:
        # 5d (not 2d): today's daily bar is often NaN until the close is
        # finalized, so we drop NaNs and use the last two *valid* closes.
        data = yf.download(syms, period="5d", interval="1d",
                           progress=False, timeout=30)
        close = data["Close"]
        multi = hasattr(close, "columns")  # DataFrame => multiple tickers

        out = {}
        for s in syms:
            try:
                if multi and s not in close.columns:
                    out[s] = {"price": "N/A", "change": 0, "change_percent": 0}
                    continue
                series = (close[s] if multi else close).dropna()
                if series.empty:
                    out[s] = {"price": "N/A", "change": 0, "change_percent": 0}
                    continue
                cur = series.iloc[-1]
                prev = series.iloc[-2] if len(series) > 1 else cur
                chg = cur - prev
                chg_pct = (chg / prev * 100) if prev else 0
                if pd.isna(chg):
                    chg = 0.0
                if pd.isna(chg_pct):
                    chg_pct = 0.0
                out[s] = {"price": float(cur), "change": float(chg),
                          "change_percent": float(chg_pct)}
            except Exception:
                out[s] = {"price": "N/A", "change": 0, "change_percent": 0}
        return json.dumps(out)

    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Tool: get_fundamentals ───────────────────────────────────────────────────
@mcp.tool()
def get_fundamentals(symbol: str) -> str:
    """
    Fetch key fundamental metrics for a ticker.

    Args:
        symbol: Ticker symbol (e.g. 'MSFT', 'TSLA')

    Returns:
        JSON string with P/E, market cap, EPS, revenue, dividend yield, etc.
    """
    cache_key = f"fundamentals:{symbol}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    try:
        info = yf.Ticker(symbol.upper()).info

        result = json.dumps({
            "symbol":            symbol.upper(),
            "name":              info.get("longName"),
            "sector":            info.get("sector"),
            "industry":          info.get("industry"),
            "market_cap":        info.get("marketCap"),
            "pe_ratio":          info.get("trailingPE"),
            "forward_pe":        info.get("forwardPE"),
            "eps":               info.get("trailingEps"),
            "revenue":           info.get("totalRevenue"),
            "profit_margin":     info.get("profitMargins"),
            "dividend_yield":    info.get("dividendYield"),
            "52w_high":          info.get("fiftyTwoWeekHigh"),
            "52w_low":           info.get("fiftyTwoWeekLow"),
            "analyst_target":    info.get("targetMeanPrice"),
            "beta":              info.get("beta"),
            "shares_outstanding": info.get("sharesOutstanding"),
        })
        _set_cache(cache_key, result)
        return result

    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Tool: get_technicals ─────────────────────────────────────────────────────
@mcp.tool()
def get_technicals(symbol: str, period: str = "6mo") -> str:
    """
    Compute technical indicators for a ticker: RSI, MACD, Bollinger Bands.

    Args:
        symbol: Ticker symbol (e.g. 'NVDA')
        period: History window for calculation — 3mo, 6mo, 1y, 2y

    Returns:
        JSON string with latest RSI, MACD line, signal line, and Bollinger Bands.
    """
    cache_key = f"technicals:{symbol}:{period}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    try:
        df = yf.Ticker(symbol.upper()).history(period=period)
        if df.empty or len(df) < 26:
            return json.dumps({"error": f"Not enough data for '{symbol}' technicals"})

        close = df["Close"]

        # RSI (14-period)
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rs    = gain / loss
        rsi   = (100 - (100 / (1 + rs))).iloc[-1]

        # MACD (12/26 EMA, 9 signal)
        ema12  = close.ewm(span=12, adjust=False).mean()
        ema26  = close.ewm(span=26, adjust=False).mean()
        macd   = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()

        # Bollinger Bands (20-period, 2 std)
        sma20  = close.rolling(20).mean()
        std20  = close.rolling(20).std()
        bb_upper = (sma20 + 2 * std20).iloc[-1]
        bb_lower = (sma20 - 2 * std20).iloc[-1]
        bb_mid   = sma20.iloc[-1]

        result = json.dumps({
            "symbol":        symbol.upper(),
            "period":        period,
            "as_of":         df.index[-1].strftime("%Y-%m-%d"),
            "rsi_14":        round(float(rsi), 2),
            "macd":          round(float(macd.iloc[-1]), 4),
            "macd_signal":   round(float(signal.iloc[-1]), 4),
            "macd_hist":     round(float(macd.iloc[-1] - signal.iloc[-1]), 4),
            "bb_upper":      round(float(bb_upper), 4),
            "bb_mid":        round(float(bb_mid), 4),
            "bb_lower":      round(float(bb_lower), 4),
            "current_price": round(float(close.iloc[-1]), 4),
        })
        _set_cache(cache_key, result)
        return result

    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Tool: get_pro_brief_data ─────────────────────────────────────────────────
@mcp.tool()
def get_pro_brief_data(symbol: str) -> str:
    """
    Fetch the full data bundle needed for a Valerius Pro Brief in a single call.

    Runs every Yahoo/yfinance request server-side so callers on IPs that Yahoo
    rate-limits (e.g. serverless platforms) don't hit HTTP 401 errors. Returns
    the same shape the webapp's data_retriever.retrieve() produces.

    Args:
        symbol: Ticker symbol (e.g. 'AAPL')

    Returns:
        JSON string with price, valuation, analyst consensus, firm ratings,
        news, upcoming events, and 52-week performance vs SPY — or {"error": ...}.
    """
    cache_key = f"pro_brief:{symbol}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    try:
        t = yf.Ticker(symbol.upper())
        fi = t.fast_info
        info = t.info or {}

        price = fi.last_price
        prev = fi.previous_close
        if price is None or prev is None:
            return json.dumps({"error": f"No price data for '{symbol.upper()}' — check the ticker symbol"})

        chg_pct = ((price - prev) / prev) * 100 if prev else 0
        hi52 = fi.year_high
        lo52 = fi.year_low
        pos = ((price - lo52) / (hi52 - lo52)) * 100 if hi52 and lo52 and hi52 != lo52 else 0

        # Cash / debt
        total_cash = info.get("totalCash")
        total_debt = info.get("totalDebt")

        def fmt_b(v):
            return f"${v/1e9:.2f}B" if abs(v) >= 1e9 else f"${v/1e6:.0f}M"

        cash_debt = None
        if total_cash is not None and total_debt is not None:
            net = total_cash - total_debt
            cash_debt = {"cash": fmt_b(total_cash), "debt": fmt_b(total_debt), "net": fmt_b(net)}

        # Valuation
        trailing_pe = info.get("trailingPE")
        forward_pe = info.get("forwardPE")
        target_mean = info.get("targetMeanPrice")
        rev_growth = info.get("revenueGrowth")
        profit_margin = info.get("profitMargins")

        # Analyst consensus
        rec_key = info.get("recommendationKey", "").upper()
        rec_mean = info.get("recommendationMean")
        num_analysts = info.get("numberOfAnalystOpinions")

        # Individual firm ratings (90-day window, top 5 priority firms)
        BIG_FIRMS = [
            "Goldman Sachs", "Morgan Stanley", "JPMorgan", "J.P. Morgan",
            "Bank of America", "BofA", "Wells Fargo", "Citigroup", "Citi",
            "Barclays", "UBS", "Deutsche Bank", "Jefferies", "Piper Sandler",
            "KeyBanc", "Raymond James", "RBC Capital", "Needham", "Truist",
        ]
        firm_ratings = []
        try:
            ud = t.upgrades_downgrades
            if ud is not None and not ud.empty:
                ud = ud.reset_index()
                date_col = next((c for c in ["GradeDate", "Date", "date"] if c in ud.columns), None)
                if date_col:
                    ud[date_col] = pd.to_datetime(ud[date_col], utc=True)
                    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=90)
                    ud = ud[ud[date_col] >= cutoff].sort_values(date_col, ascending=False)
                seen = set()
                rows = []
                for _, row in ud.iterrows():
                    firm = str(row.get("Firm", "")).strip()
                    grade = str(row.get("ToGrade", "")).strip()
                    if not firm or not grade or grade.lower() == "nan":
                        continue
                    fk = firm.lower()
                    if fk not in seen:
                        seen.add(fk)
                        rows.append((firm, grade))
                priority = [(f, g) for f, g in rows if any(b.lower() in f.lower() for b in BIG_FIRMS)]
                others = [(f, g) for f, g in rows if not any(b.lower() in f.lower() for b in BIG_FIRMS)]
                firm_ratings = (priority + others)[:5]
        except Exception:
            pass

        # News (top 3)
        news_headlines = []
        try:
            for n in (t.news or [])[:3]:
                title = n.get("content", {}).get("title", "") or n.get("title", "")
                if title:
                    news_headlines.append(title)
        except Exception:
            pass

        # Upcoming events
        earnings_str = None
        try:
            cal = t.calendar
            if cal and "Earnings Date" in cal:
                ed = cal["Earnings Date"]
                if isinstance(ed, (list, tuple)) and ed:
                    first = ed[0]
                    earnings_str = first.strftime("%b %d, %Y") if hasattr(first, "strftime") else str(first)[:10]
                elif hasattr(ed, "strftime"):
                    earnings_str = ed.strftime("%b %d, %Y")
        except Exception:
            pass

        ex_div_str = None
        ex_div_ts = info.get("exDividendDate")
        if ex_div_ts:
            try:
                ex_div_str = datetime.utcfromtimestamp(ex_div_ts).strftime("%b %d, %Y")
            except Exception:
                pass

        # Dividends — yield computed as rate/price (never info['dividendYield'],
        # which is unreliable); ETFs often lack dividendRate → trailing-12mo sum
        div_rate = info.get("dividendRate")
        last_div = None
        try:
            divs = t.dividends
            if divs is not None and len(divs):
                last_div = round(float(divs.iloc[-1]), 4)
                if ex_div_str is None:
                    # dividends series is indexed by ex-date — covers ETFs, where
                    # info['exDividendDate'] is absent
                    ex_div_str = divs.index[-1].strftime("%b %d, %Y")
                if div_rate is None:
                    cutoff = pd.Timestamp.now(tz=divs.index.tz) - pd.Timedelta(days=365)
                    ttm = divs[divs.index >= cutoff]
                    if len(ttm):
                        div_rate = round(float(ttm.sum()), 4)
        except Exception:
            pass
        div_yield = round((div_rate / price) * 100, 2) if div_rate and price else None

        # 52-week performance vs S&P 500
        spy_chg = None
        try:
            hist = t.history(period="1y")
            spy_hist = yf.Ticker("SPY").history(period="1y")
            if not hist.empty and not spy_hist.empty:
                stock_ret = (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100
                spy_ret = (spy_hist["Close"].iloc[-1] / spy_hist["Close"].iloc[0] - 1) * 100
                spy_chg = {"stock_1y": round(stock_ret, 1), "spy_1y": round(spy_ret, 1), "alpha": round(stock_ret - spy_ret, 1)}
        except Exception:
            pass

        result = json.dumps({
            "ticker": symbol.upper(),
            "name": info.get("longName", symbol.upper()),
            "price": round(price, 2),
            "chg_pct": round(chg_pct, 2),
            "hi52": round(hi52, 2) if hi52 else None,
            "lo52": round(lo52, 2) if lo52 else None,
            "pos52": round(pos, 0),
            "cash_debt": cash_debt,
            "trailing_pe": round(trailing_pe, 1) if trailing_pe else None,
            "forward_pe": round(forward_pe, 1) if forward_pe else None,
            "target_mean": round(target_mean, 2) if target_mean else None,
            "rev_growth": round(rev_growth * 100, 1) if rev_growth else None,
            "profit_margin": round(profit_margin * 100, 1) if profit_margin else None,
            "rec_key": rec_key,
            "rec_mean": round(rec_mean, 2) if rec_mean else None,
            "num_analysts": num_analysts,
            "firm_ratings": firm_ratings,
            "news_headlines": news_headlines,
            "earnings_str": earnings_str,
            "ex_div_str": ex_div_str,
            "div_rate": div_rate,
            "div_yield": div_yield,
            "last_div": last_div,
            "spy_chg": spy_chg,
        })
        _set_cache(cache_key, result)
        return result

    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Entry point ──────────────────────────────────────────────────────────────
# Usage:
#   python server.py          → stdio  (Claude Desktop / MCP agents)
#   python server.py http     → streamable-http on http://127.0.0.1:8002/mcp
if __name__ == "__main__":
    import sys
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if transport == "http":
        print(f"\n  Financial Data MCP Server (streamable-http)")
        print(f"  MCP endpoint: http://{MCP_HOST}:{MCP_PORT}/mcp\n")
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")
