# Eudora

A **rule-based, risk-managed trading bot** for Robinhood's
[Agentic Trading](https://robinhood.com/us/en/agentic-trading/) (the
`agent.robinhood.com/mcp/trading` MCP server).

The strategy math decides what to trade; Eudora executes deterministically by
calling the Robinhood MCP trading tools directly. **No LLM sits in the order
path** — so given the same data, the bot always does the same thing, and every
decision is journaled and auditable.

> ⚠️ **Real money.** Live mode places real orders against a funded Robinhood
> Agentic Trading account. Trading is risky and you can lose money. Start in
> dry-run, keep the daily caps low, and read the safety section below.

---

## How it works

```
 price history ──▶ strategy (SMA crossover + RSI filter) ──▶ signal
                                                              │
   position ───────────────────────────────────────────────▶│
                                                              ▼
                                              risk manager (caps, kill switch)
                                                              │
                                          dry-run? ──▶ journal "would place"
                                          live?    ──▶ Robinhood MCP ──▶ order
```

| Piece | File | Notes |
|---|---|---|
| Indicators | `src/eudora/indicators.py` | SMA, EMA, RSI — pure Python, no deps |
| Strategy | `src/eudora/strategy/sma_crossover.py` | fast/slow SMA crossover, optional RSI filter |
| Risk | `src/eudora/risk.py` | per-order + daily caps, circuit breaker, kill switch |
| Execution | `src/eudora/broker/` | `PaperBroker` (dry run) and `RobinhoodMCPBroker` (live) |
| Data | `src/eudora/feed/` | `CsvPriceFeed`; plug in any provider |
| Loop | `src/eudora/engine.py` | data → strategy → risk → execute |
| Journal | `src/eudora/journal.py` | append-only JSONL of every decision |

The core (everything except live trading) has **zero third-party dependencies**.

---

## Quick start (dry run — safe)

```bash
cp config.example.toml config.toml         # edit symbols/strategy/risk to taste
PYTHONPATH=src python3 -m eudora.cli run --config config.toml
cat trades.jsonl                           # see what it would have done
```

Synthetic sample data for `ACME`/`GLOB` is included under `data/` so this works
immediately. Add your own as `data/<SYMBOL>.csv` with a `close` column.

Run the tests:

```bash
python3 -m unittest discover -s tests
```

---

## Evaluate before risking capital (backtest)

Replay the strategy over historical closes and see how it would have done —
**no auth, no real money.** This is the step to do *before* funding anything.

```bash
PYTHONPATH=src python3 -m eudora.cli backtest --config config.toml
# also enforce the live [risk] caps during the replay:
PYTHONPATH=src python3 -m eudora.cli backtest --config config.toml --apply-risk
```

Example output (on the bundled **synthetic** sample data):

```
  Starting capital : $500.00
  Final equity     : $604.01
  Total return     : +20.80%
  Buy & hold (eq-wt): +10.41%
  Max drawdown     : 4.45%
  Orders placed    : 23
  Closed round-trips: 11
  Win rate         : 90.9%
```

> ⚠️ **Those numbers are meaningless as a forecast.** The bundled `ACME`/`GLOB`
> data is synthetic oscillating series that a crossover strategy trivially
> profits from. **Before trusting this strategy with real money, drop real
> historical daily closes into `data/<TICKER>.csv` (a `close` column) and
> backtest those.** Compare against the buy & hold benchmark — if the strategy
> doesn't beat it after costs, don't run it live. The backtest is walk-forward
> (no look-ahead) and reuses the exact strategy/sizing/risk code the live engine
> uses, so it's a faithful dry simulation — but it's only as good as the data.

The risk manager's daily window is anchored to the data's timeline (one bar =
one day), so `--apply-risk` reflects how the $500 caps would actually behave
live rather than collapsing into the replay instant.

## Going live (real money)

Live trading needs three things the dry run doesn't: **authentication**, the
**real MCP tool names**, and an **explicit acknowledgement**.

### 1. Authenticate the Robinhood MCP — on your LOCAL machine

The OAuth flow needs a browser, so it **cannot** be done in a remote/headless
session. On your own computer with the Claude CLI:

```bash
claude mcp add robinhood-trading --transport http https://agent.robinhood.com/mcp/trading
# then, in Claude Code:
/mcp        # select robinhood-trading -> authenticate (browser opens)
```

Open a dedicated **Agentic Trading account**, fund it with only what you're
willing to risk, and set its daily cap ($500 is the smallest) in the Robinhood
app. Eudora can only touch that account.

Export the session's bearer token so Eudora can call the MCP directly:

```bash
cp .env.example .env       # then set ROBINHOOD_MCP_TOKEN
export ROBINHOOD_MCP_TOKEN=...
```

### 2. Discover and pin the real MCP tool names

The exact tool names/schemas are confirmed against the live server (Eudora ships
with `TODO_` placeholders and **refuses to trade live** until you replace them):

```bash
pip install "mcp[cli]"                      # only needed for live trading
python scripts/discover_mcp_tools.py        # prints real tool names + schemas
```

Put the names in `config.toml` under `[broker.tools]` and set `confirmed = true`.

### 3. Run live (deliberately awkward)

```bash
# still dry-run unless BOTH flags are present:
PYTHONPATH=src python3 -m eudora.cli run --live --i-understand-the-risk --config config.toml

# repeat on a schedule (e.g. once per hour during market hours):
PYTHONPATH=src python3 -m eudora.cli loop --interval 3600 --live --i-understand-the-risk --config config.toml
```

---

## Safety model (defence in depth)

1. **Dry run is the default.** Live mode requires `--live` **and**
   `--i-understand-the-risk`.
2. **Kill switch.** `touch KILL_SWITCH` halts all order placement instantly.
   Delete the file to resume.
3. **Independent risk caps** (`[risk]` in config) on top of Robinhood's own
   account cap: per-order notional, rolling 24h notional, daily order count, and
   a short-window **circuit breaker** that trips on a runaway loop.
4. **Long-only by default** (`allow_short = false`) — the bot can't open shorts
   or sell more than it holds.
5. **Full audit trail.** Every placed / skipped / rejected decision is written
   to `trades.jsonl` with its reason.

Recommended first live config (and the bundled default): **$500 initial
capital**, one or two lower-priced symbols, `max_daily_notional = 500`,
`order_notional` small, RSI filter on, and watch the journal for a few sessions
before loosening anything. Fund the Robinhood Agentic Trading account with only
that $500 — it's the hard ceiling on what the bot can ever touch.

---

## Known limitations

- **Whole shares only.** The sizer floors to whole shares; if `order_notional`
  is below one share's price it places nothing (logged as "sized to 0 shares").
  Fractional-share support is a future addition.
- **Equities only, US only** — matches Robinhood Agentic Trading's beta scope.
- **`CsvPriceFeed` is for backtests/dry runs.** For live scheduling, wire a
  real intraday/daily data provider into the `PriceFeed` interface.
- **Not financial advice.** This is software, not a recommendation to trade.
