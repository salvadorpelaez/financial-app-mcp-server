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
mcp = FastMCP("financial-data")

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


# ── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run(transport="stdio")
