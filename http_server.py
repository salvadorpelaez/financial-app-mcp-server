#!/usr/bin/env python3
"""
Financial Data MCP Server — HTTP wrapper
Exposes the MCP tools as plain REST endpoints so Flask apps can call
them via requests without async complexity.

Run with: python http_server.py
Listens on: http://127.0.0.1:8001
"""

import os
import time
from flask import Flask, request, jsonify
from server import get_market_data, get_fundamentals, get_technicals, get_pro_brief_data, get_bulk_prices, get_dividend_screen
import json

app = Flask(__name__)

MCP_API_KEY = os.environ.get("MCP_API_KEY")


def _commit_sha():
    """The commit this process is actually running.

    /health already proved the process is up; it said nothing about which code
    it is up on. Every other route needs an API key, so without this there is no
    way for a deploy script to tell a finished deploy from a stale one — which is
    exactly what was missing on 2026-08-16, when a dependency resolution took the
    service down and a rebuild could not be distinguished from a boot failure.

    Railway injects RAILWAY_GIT_COMMIT_SHA when the service builds from the
    connected repo. `railway up` from a laptop does not set it and neither does
    running locally, so fall back to reading .git directly. Read the ref files
    rather than shelling out: the runtime image has no git binary, and spawning a
    subprocess inside the endpoint Railway health-checks on a timer is a poor
    trade even where it would work.

    Resolved once at import — the answer cannot change without a new process.
    """
    for var in ("RAILWAY_GIT_COMMIT_SHA", "GIT_COMMIT_SHA", "SOURCE_COMMIT"):
        sha = (os.environ.get(var) or "").strip()
        if sha:
            return sha

    git = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".git")
    try:
        with open(os.path.join(git, "HEAD")) as fh:
            head = fh.read().strip()
        if not head.startswith("ref:"):
            return head or None          # detached HEAD holds the sha itself
        ref = head.split(" ", 1)[1].strip()

        loose = os.path.join(git, *ref.split("/"))
        if os.path.exists(loose):
            with open(loose) as fh:
                return fh.read().strip() or None

        # A freshly cloned repo has no loose ref file — the branch tip lives in
        # packed-refs until something writes to it.
        with open(os.path.join(git, "packed-refs")) as fh:
            for line in fh:
                parts = line.split()
                if len(parts) == 2 and parts[1] == ref:
                    return parts[0]
    except (OSError, IndexError):
        pass
    return None


COMMIT_SHA = _commit_sha()


@app.before_request
def require_api_key():
    if request.path == "/health":
        return
    if not MCP_API_KEY or request.headers.get("X-API-Key") != MCP_API_KEY:
        return jsonify({"error": "unauthorized"}), 401


@app.route("/health")
def health():
    # Unauthenticated by the before_request exemption above, on purpose: a deploy
    # check that needed the API key could not be run by a deploy script. Returns
    # nothing about configuration — no env values, no key material. `sha` is null
    # rather than absent when it cannot be resolved, so a caller comparing against
    # a known commit fails loudly instead of matching nothing. `status` and
    # `service` are unchanged for anything already reading them.
    return jsonify({
        "status": "ok",
        "service": "financial-data-mcp",
        "sha": COMMIT_SHA,
        "ts": int(time.time()),
    })


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


@app.route("/tools/get_pro_brief_data", methods=["POST"])
def route_pro_brief_data():
    body = request.get_json(force=True) or {}
    result = get_pro_brief_data(symbol=body.get("symbol", ""))
    return app.response_class(result, mimetype="application/json")


@app.route("/tools/get_bulk_prices", methods=["POST"])
def route_bulk_prices():
    body = request.get_json(force=True) or {}
    result = get_bulk_prices(symbols=body.get("symbols", []))
    return app.response_class(result, mimetype="application/json")


@app.route("/tools/get_dividend_screen", methods=["POST"])
def route_dividend_screen():
    body = request.get_json(force=True) or {}
    result = get_dividend_screen(symbols=body.get("symbols", []))
    return app.response_class(result, mimetype="application/json")


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8001))
    host = "0.0.0.0"
    print(f"\n  Financial Data MCP Server (HTTP mode)")
    print(f"  Listening on http://{host}:{port}\n")
    app.run(host=host, port=port, debug=False)
