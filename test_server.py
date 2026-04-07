#!/usr/bin/env python3
"""
Quick local test — calls each MCP tool directly as Python functions.
No MCP client/server transport needed. Just run: python test_server.py
"""

import json
from server import get_market_data, get_fundamentals, get_technicals

SEP = "-" * 60

def pretty(label: str, raw: str):
    print(f"\n{SEP}")
    print(f"  {label}")
    print(SEP)
    try:
        data = json.loads(raw)
        print(json.dumps(data, indent=2))
    except Exception:
        print(raw)

if __name__ == "__main__":
    print("\n=== Financial Data MCP Server — Local Tool Test ===\n")

    # 1. Market data — last 3 months for Apple
    pretty(
        "get_market_data('AAPL', period='3mo')",
        get_market_data("AAPL", period="3mo")
    )

    # 2. Fundamentals — Microsoft
    pretty(
        "get_fundamentals('MSFT')",
        get_fundamentals("MSFT")
    )

    # 3. Technicals — NVIDIA
    pretty(
        "get_technicals('NVDA', period='6mo')",
        get_technicals("NVDA", period="6mo")
    )

    print(f"\n{SEP}")
    print("  All tests complete.")
    print(SEP + "\n")
