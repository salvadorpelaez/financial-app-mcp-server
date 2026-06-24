# financial-app-mcp-server

MCP server wrapping yfinance, exposing market data, fundamentals, and technical indicators as standardized tools. Built to decouple the data layer from consuming apps (e.g. [Valerius](https://github.com/salvadorpelaez/sp500-database-webapp)).

## Tools

| Tool | Description |
|---|---|
| `get_market_data(symbol, start_date, end_date, period)` | OHLCV price history |
| `get_fundamentals(symbol)` | P/E, market cap, EPS, revenue, profit margin, dividend yield, 52w high/low, analyst target, beta, shares outstanding |
| `get_technicals(symbol, period)` | RSI (14), MACD (12/26/9), Bollinger Bands (20-period, 2 std) |

All tools cache results in-memory for 1 hour (`CACHE_TTL`).

## Transports

- **stdio** (default) — `python server.py` — used by Claude Desktop / local MCP agents
- **streamable-http** — `python server.py http` — serves MCP protocol at `http://127.0.0.1:8002/mcp`
- **Plain REST** — `python http_server.py` — Flask wrapper exposing the same three tools as `POST /tools/<name>`, for apps that want simple HTTP without MCP/async complexity. This is what's deployed to Railway (see `Procfile`).

## Deployment

Hosted on Railway: `gunicorn http_server:app`. Consuming apps set `MCP_SERVER_URL` to the Railway URL and call `/tools/get_market_data`, `/tools/get_fundamentals`, `/tools/get_technicals`.

### Authentication

`http_server.py` requires a shared-secret header on every request except `/health`:

```
X-API-Key: <MCP_API_KEY>
```

Requests missing the header or sending the wrong value get `401 {"error": "unauthorized"}`.

Set `MCP_API_KEY` as a Railway variable (shared with whichever service runs this app — Railway's Shared Variables don't auto-inject into a service until explicitly shared to it). The consuming app must send the same value as `MCP_API_KEY` and include it as the `X-API-Key` header on each call (see `mcp_client.py` in Valerius for the reference implementation).

**Why:** added Jun 24 2026 after discovering the server had no auth — anyone with the Railway URL could call its endpoints. The endpoints only serve read-only public market data, so the risk was usage/cost abuse rather than data exposure, but the gate closes it either way.
