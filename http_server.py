#!/usr/bin/env python3
"""
Financial Data MCP Server — HTTP wrapper
Exposes the MCP tools as plain REST endpoints so Flask apps can call
them via requests without async complexity.

Run with: python http_server.py
Listens on: http://127.0.0.1:8001
"""

from flask import Flask, request, jsonify
from server import get_market_data, get_fundamentals, get_technicals
import json

app = Flask(__name__)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "financial-data-mcp"})


@app.route("/tools/get_market_data", methods=["POST"])
def route_market_data():
    body = request.get_json(force=True) or {}
    result = get_market_data(
        symbol=body.get("symbol", ""),
        start_date=body.get("start_date", ""),
        end_date=body.get("end_date", ""),
        period=body.get("period", "1y"),
    )
    return app.response_class(result, mimetype="application/json")


@app.route("/tools/get_fundamentals", methods=["POST"])
def route_fundamentals():
    body = request.get_json(force=True) or {}
    result = get_fundamentals(symbol=body.get("symbol", ""))
    return app.response_class(result, mimetype="application/json")


@app.route("/tools/get_technicals", methods=["POST"])
def route_technicals():
    body = request.get_json(force=True) or {}
    result = get_technicals(
        symbol=body.get("symbol", ""),
        period=body.get("period", "6mo"),
    )
    return app.response_class(result, mimetype="application/json")


if __name__ == "__main__":
    print("\n  Financial Data MCP Server (HTTP mode)")
    print("  Listening on http://127.0.0.1:8001\n")
    app.run(host="127.0.0.1", port=8001, debug=False)
