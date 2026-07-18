# Broker Copilot v1 — Architecture Decision Record & Implementation Spec

**Date:** 2026-07-18
**Status:** Decided. This document is the decision record and the implementation
spec; the code lands in `eureka` (package `fable5/copilot/`) in a follow-up
implementation session.
**Companion:** `STRATEGY.md` (consolidation decision, 2026-07-17).

---

## 1. What this is

A read-only broker/portfolio copilot for Claude Code: a local MCP stdio server
that gives Claude real paper-account context (account status, positions, fills,
connection health) for debugging, journaling, and operator support. It is a
control-tower layer, not a strategy project. It can never place, modify, cancel,
or preview an order — structurally, not by policy.

An optional local-Gemma helper layer is specified here as a frozen contract and
ships in v1 as a **disabled stub only**.

## 2. Placement decision: inside `eureka`

The three candidate homes were: inside apex, inside eureka, or a new adjacent
repo reusing both. The decision is **`fable5/copilot/` inside eureka**, and it
was not close:

- STRATEGY.md already decided "all new work happens in eureka." A new adjacent
  repo would re-create a second place where broker credentials and account
  state live, quietly undoing the consolidation.
- Apex is retired as a code source. Its own audit found live order paths that
  bypassed validation; wrapping its connectors would import exactly the risk
  this project exists to reduce. Apex remains a read-only research archive.
- Eureka already has the safety spine the copilot needs (see §3). Building the
  copilot anywhere else means re-implementing paper enforcement, the Alpaca
  client, structured logging, and the audit DB — four chances to drift.

**IBKR:** no IBKR integration exists in eureka (STRATEGY.md and the codebase
are Alpaca-only). v1 is Alpaca-paper only. The `ReadOnlyBroker` facade is the
seam where an IBKR adapter would plug in later; no speculative abstraction
beyond that seam is built now.

## 3. What eureka already provides (verified 2026-07-18, `main` @ `0a1161b`)

| Need | Existing code | Reuse |
|---|---|---|
| Paper-only fail-closed | `fable5/config.py::load_config` — raises `ConfigError` on `FABLE5_MODE != "paper"` or non-paper `ALPACA_BASE_URL`; `AppConfig.mode: Literal["paper"]` | Call as-is with `require_broker_keys=True`. Do **not** build a second mode system. |
| Broker reads | `fable5/alpaca_client.py::AlpacaClient` — `get_account`, `list_positions`, `list_open_orders`, `get_order`, `get_clock` | Wrap in read-only facade. Add one method: `list_account_activities` (GET, fills). |
| Structured logging | `fable5/logging_setup.py` — JSON-line logs, `ComponentLoggerAdapter` | Use with `component="copilot"`; add redaction filter. |
| Local audit truth | `fable5/db.py` — `orders`, `order_events`, `trades`, `reconciliation_log`, `risk_audit` tables | Optional read-only enrichment (strategy/signal attribution on fills). |
| Offline-testable HTTP | `fable5/http_client.py` + injectable `request_json` | All copilot tests run offline against fakes, matching `tests/fakes.py` conventions. |

The only change to existing files: one ~10-line read-only method on
`AlpacaClient` and an optional-dependency block in `pyproject.toml`. No
strategy, risk, or execution code is touched.

## 4. Protocol decision: real MCP stdio server, official SDK as an extra

"MCP-style" is resolved to: an actual Model Context Protocol stdio server built
on the official `mcp` Python SDK, so Claude Code consumes it with zero glue via
`.mcp.json`. Eureka's core stays dependency-light by making it an extra:

```toml
[project.optional-dependencies]
copilot = ["mcp>=1.0"]
```

Entry point: `python -m fable5.copilot`. Registration (project `.mcp.json` in
eureka, or user-level Claude Code config):

```json
{
  "mcpServers": {
    "fable5-copilot": {
      "command": "python",
      "args": ["-m", "fable5.copilot"],
      "env": { "FABLE5_MODE": "paper" }
    }
  }
}
```

The MCP SDK is imported only inside `fable5/copilot/__main__.py`; `tools.py`,
`models.py`, `normalize.py`, `redact.py` are plain Python so the whole tool
layer is testable without the SDK installed.

## 5. Module layout

```
fable5/copilot/
  __init__.py
  __main__.py          # MCP stdio entry; runs the fail-closed startup sequence,
                       # then registers and serves the 4 tools
  readonly_broker.py   # ReadOnlyBroker facade (composition, not inheritance)
  models.py            # frozen dataclasses + ToolEnvelope
  normalize.py         # Alpaca dicts -> domain models; broker data stays at this edge
  redact.py            # alias mapping + credential scrubbing (logs AND tool output)
  tools.py             # the 4 tool implementations + per-call audit logging
  gemma/
    __init__.py
    contract.py        # request/response schemas + validators (frozen in v1)
    adapter.py         # LocalModelAdapter protocol + DisabledAdapter (default)

tests/
  test_copilot_config.py     # startup fail-closed matrix
  test_copilot_readonly.py   # read-only invariant (see §7)
  test_copilot_tools.py      # tool outputs vs FakeBroker; redaction; envelope
  test_copilot_gemma.py      # disabled / timeout / invalid-output behavior

RUNBOOK-COPILOT.md           # operator runbook (see §12)
```

## 6. Startup fail-closed sequence

Order matters; each step refuses startup (non-zero exit, clear stderr message,
nothing served) on failure:

1. `load_config(require_broker_keys=True)` — rejects live/mixed/unknown mode,
   non-paper base URL, missing keys. This is eureka's single enforcement point.
2. Construct `ReadOnlyBroker` and probe `GET /v2/account`.
   - Unreachable / 401 / timeout → refuse startup (broker unavailability is
     fail-closed, not degraded).
3. **Paper self-check:** assert the probed account is a paper account (Alpaca
   paper account numbers are only reachable via the paper host already enforced
   in step 1; additionally assert `account.status == "ACTIVE"` and log the
   aliased account id). Any ambiguity → refuse startup.
4. Initialize redaction map (raw account id → stable alias, default
   `alpaca-paper-1`, overridable via `FABLE5_COPILOT_ACCOUNT_ALIAS`).
5. Attach `RedactionFilter` to the copilot logger, then serve tools.

DB is intentionally **not** in the startup chain: the local DB enriches fills
but its absence must not block read-only account visibility (it degrades with
an explicit `"local-db": "unavailable"` note in affected tool output).

## 7. Read-only as an invariant, not a policy

- `ReadOnlyBroker` **composes** `AlpacaClient` and exposes exactly:
  `get_account`, `list_positions`, `list_open_orders`, `get_order`,
  `get_clock`, `list_account_activities`. No passthrough, no `__getattr__`
  delegation, no inheritance.
- `tests/test_copilot_readonly.py` enforces it two ways:
  1. Attribute assertion: `ReadOnlyBroker` has no attribute named
     `submit_limit_order` or `cancel_order`.
  2. Source scan: no file under `fable5/copilot/` contains the tokens
     `submit_limit_order`, `cancel_order`, or `"POST"`/`"DELETE"` HTTP verbs
     (mirroring eureka's `test_no_naked_datetime.py` lint-test pattern).
- The new `AlpacaClient.list_account_activities` method is GET-only:

```python
async def list_account_activities(
    self, activity_type: str = "FILL", page_size: int = 100
) -> list[dict]:
    return await self._call(
        "GET",
        "/v2/account/activities",
        params={"activity_types": activity_type, "page_size": page_size},
    ) or []
```

## 8. Domain models and the tool envelope

Frozen dataclasses in `models.py` (matching `trading_types.py` conventions:
`@dataclass(frozen=True, slots=True)`, validation in `__post_init__`):

- `AccountStatus`: `account_alias, status, currency, equity, cash,
  buying_power, portfolio_value, pattern_day_trader, as_of_utc`
- `Position`: `symbol, asset_class, side, qty, avg_entry_price, current_price,
  market_value, unrealized_pl, unrealized_pl_pct`
- `Fill`: `symbol, side, qty, price, transaction_time_utc, order_alias,
  strategy (nullable), signal_id (nullable)` — order ids are aliased
  (`ord-<first8ofsha256>`), never raw broker ids
- `ConnectionHealth`: `broker_reachable, broker_latency_ms, market_open,
  next_open_utc, next_close_utc, local_db_available, last_success_utc`

Every tool response is wrapped:

```json
{
  "envelope": {
    "mode": "paper",
    "source": "alpaca-paper",
    "as_of_utc": "2026-07-18T14:02:11+00:00",
    "freshness_seconds": 0,
    "truncated": false
  },
  "data": { ... },
  "error": null
}
```

Rules:
- `mode` is always `"paper"` (it cannot be anything else past startup).
- `source` ∈ `"alpaca-paper" | "alpaca-paper+local-db"`.
- Broker error mid-serve → `data: null` and a structured
  `error: {"kind": "broker_unavailable" | "broker_auth" | "timeout", "detail": "<redacted message>"}`.
  Never fabricated or stale-silently-served data.
- Payload caps: positions ≤ 200 rows, fills ≤ 100 rows; overflow sets
  `truncated: true` with a count of omitted rows. Tool outputs land in
  Claude's context window; caps are a feature.

## 9. The four v1 tools

All tools are read-only, take minimal inputs, log one audit line per call
(tool name, redacted params, duration, outcome — never payload contents).

### `get_account_status` — no inputs
`data`: an `AccountStatus`. Raw account number never appears; `account_alias`
does.

### `get_positions` — inputs: `{ "symbols": ["SPY", ...]? }` (optional filter)
`data`: `{ "positions": [Position, ...], "count": n, "total_market_value": x,
"total_unrealized_pl": x }`. Empty account → empty list with `count: 0` (not an
error).

### `get_recent_fills` — inputs: `{ "limit": 25?, "since_utc": "..."? }`
`data`: `{ "fills": [Fill, ...], "count": n }`.
Source of truth: broker `GET /v2/account/activities?activity_types=FILL`.
Enrichment: when the local DB is present, join on `client_order_id` against the
`orders` table to attach `strategy` and `signal_id`; on any DB error the tool
still returns broker fills with `source: "alpaca-paper"` and a
`local_db_available: false` note. Broker truth is never replaced by DB data.

### `get_connection_health` — no inputs
`data`: a `ConnectionHealth`. Measures a live `get_clock` round-trip for
latency and market open/close, checks DB file presence/readability, and reports
the last successful broker call timestamp kept in-process.

**Slice 2+ (explicitly not in v1):** `get_open_orders`, `get_pnl_summary`,
`get_exposure_summary`, `explain_no_trade_today` — see §11.

## 10. Gemma layer: frozen contract, disabled stub

**v1 ships the boundary, not the model.** For every listed Gemma task
(summaries, narratives, journal drafts) Claude Code is already in the loop and
strictly better today; a local Gemma runtime adds serving, timeout, and
validation work for no v1 capability. What must not drift later is the
*contract*, so it is frozen now and enforced by tests.

### Interface

```python
class LocalModelAdapter(Protocol):
    async def generate(self, request: GemmaRequest) -> GemmaResponse: ...

class DisabledAdapter:
    """Default. Always raises GemmaUnavailable — deterministic fallback path."""
```

Selection: `FABLE5_COPILOT_GEMMA` env var, default `"disabled"`. v1 accepts
only `"disabled"`; any other value is a startup `ConfigError` (fail closed —
no half-configured model states).

### Request (what Gemma receives)

```json
{
  "schema_version": "1.0",
  "task": "summarize_portfolio" | "narrate_fills" | "draft_journal",
  "data": { "<normalized, redacted domain models only>": "..." },
  "max_output_chars": 2000
}
```

Gemma never receives: raw broker payloads, credentials, raw account/order ids,
env values, or anything outside the normalized models. `contract.py` validates
this at construction, not by convention.

### Response (what Gemma may return)

```json
{ "schema_version": "1.0", "task": "<echo>", "text": "<free text>" }
```

Free text only. Prohibited and rejected by the validator:
- any additional structured fields (numbers-as-fields, decisions, scores);
- text containing order-action imperatives (regex class over
  buy/sell/place/cancel/modify + order/position context) — narratives describe,
  they never instruct;
- symbols or quantities not present in the input `data` (anti-fabrication
  check: extract tickers and numeric quantities from `text`, require each to
  appear in the input);
- output over `max_output_chars`;
- wrong `schema_version` or `task` echo.

### Failure behavior

Adapter unavailable, timeout (hard cap 10s), or invalid output → the calling
feature returns its deterministic non-Gemma rendering (e.g. a plain formatted
fills table) with `"gemma": "unavailable"` in the envelope. Gemma can never
block a tool, degrade account truth, or fabricate content that reaches the
operator unvalidated.

### Authority rules (restated as tests to write)

- Gemma output is always labeled a draft; it is never the source of any number.
- Gemma may **annotate** alerts; it may never filter, suppress, or rank them
  out of the operator's view.
- No code path passes Gemma output back into any broker or DB write. (Trivially
  true in v1 — the copilot has no writes — and kept true by the §7 lint test.)

## 11. Slice map

| Slice | Contents | Gate to build it |
|---|---|---|
| **1 (v1, next session)** | Everything in §5–§10 | This document approved |
| 2 | `get_open_orders`, `get_pnl_summary`, `get_exposure_summary` | Asset-class + cost-basis normalization decisions written down first |
| 3 | `explain_no_trade_today` | Only if implementable as a **pure reader** of `risk_audit` / `order_events` / `reconciliation_log`; if it would require hooks inside strategy or risk code, it is dropped, not forced |
| 4 | Working Gemma adapter (Ollama-served, behind §10 contract); first feature: daily operator journal draft | Slices 1–2 in daily use; contract unchanged |

**Permanently out of scope for this project:** order routes of any kind, live
mode, changes to strategy/risk/execution logic, paper execution loops,
auto-trading, IBKR (until an IBKR integration exists in eureka on its own
merits).

## 12. Runbook sketch (becomes `RUNBOOK-COPILOT.md` in eureka)

```
Install:   pip install -e ".[copilot,dev]"
Configure: ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY (paper keys), FABLE5_MODE=paper
Register:  add .mcp.json block (see §4) to the project Claude Code runs in
Verify:    python -m fable5.copilot   # must print "serving 4 tools (paper)" to stderr
Fail-closed check: FABLE5_MODE=live python -m fable5.copilot  -> non-zero exit
Logs:      JSON lines, component=copilot; one audit line per tool call
Troubleshooting: broker_auth -> rotate paper keys; broker_unavailable ->
           check Alpaca paper status page; local_db_available=false is
           informational, not an error
```

## 13. Verification (for the implementation session)

1. `pytest tests/test_copilot_*.py` green, and the **full** eureka suite stays
   green (no regressions from the `AlpacaClient` addition).
2. Fail-closed matrix (`test_copilot_config.py`): `FABLE5_MODE=live`, mixed
   base URL, missing keys, unreachable broker, 401 → each refuses startup.
3. Read-only invariant (`test_copilot_readonly.py`): attribute + source-scan
   assertions of §7.
4. Canary-secret test: set fake key `CANARY_SECRET_XYZ` in env, run every tool
   against the fake broker, assert the canary appears in no log line and no
   tool output.
5. Gemma tests: `DisabledAdapter` path, timeout path, each §10 validator
   rejection, deterministic fallback rendering.
6. Manual: register in `.mcp.json`, run `tools/list` and all four tools from
   Claude Code against a real Alpaca paper account.

## 14. Exact next step

Open a Claude Code session **on the `eureka` repo** and implement Slice 1 per
this document: create `fable5/copilot/` and tests as specified in §5–§10, add
`list_account_activities` to `AlpacaClient`, add the `copilot` extra to
`pyproject.toml`, write `RUNBOOK-COPILOT.md`, run the §13 verification, and
commit on a feature branch.
