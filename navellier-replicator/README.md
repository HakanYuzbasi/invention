# navellier-replicator

A **private, single-subscriber** automation pipeline that logs into your own
InvestorPlace premium account, captures the Louis Navellier *Platinum Growth*
portfolio/recommendation state, normalizes it into auditable events, and (in
later versions) prepares **paper-only** Interactive Brokers trades.

This is a deterministic *signal-replication* tool for one paid research source —
not a quant strategy engine. It is built for reliability, traceability, and
forensic auditability over cleverness.

> **Paper only. Dry-run by default. Live trading is never enabled.**
> The broker layer refuses to construct in anything other than paper mode, and
> no code path submits real-money orders.

## Release stages

| Stage | Scope |
|-------|-------|
| **v0.1 (this release)** | Authenticated Playwright collection → raw artifact persistence → first hybrid parser with confidence scoring → extracted-item persistence → daily markdown diff report. **No broker integration.** |
| v0.2 | Event builder, materialized active-state engine, `mirror_published_if_explicit` + `fifo_cap5` policies, target-portfolio reporting. |
| v0.3 | IBKR **paper** adapter, order planning, reconciliation, guarded paper-submission toggle. |

The full directory tree exists now; v0.2/v0.3 modules are present as real classes
that **fail closed** (raise a controlled "not enabled" error) until their stage.

## What it does in v0.1

1. **Authenticated collection** (Playwright): logs in with credentials from the
   environment, navigates to the portfolio page and any configured update pages,
   and captures **HTML + visible text + full-page screenshot + SHA256 + final
   (post-redirect) URL** for every page. Bounded retries; failure screenshots.
2. **Raw persistence** (SQLite via SQLAlchemy): every page is stored verbatim so
   a human can later answer *exactly what page was seen*.
3. **Hybrid parsing**: structured table extraction with a text fallback, a
   transparent additive **confidence score** on every item, and explicit
   `UNKNOWN` classification when uncertain. Every item keeps its source snippet.
4. **Fail-closed safety guards**: block on login-but-empty content, zero
   actionable items, all-low-confidence, and large unexplained set changes —
   each recorded as an `audit_flag`.
5. **Daily report**: a markdown summary of the run (status, pages, parse counts,
   new-vs-previous diff, current active set, audit flags).

## Install

```bash
cd navellier-replicator
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium
```

## Configure

Secrets live in a **gitignored** `.env`. Behavior lives in YAML.

```bash
cp .env.example .env                              # fill in credentials + URLs
cp config/settings.example.yaml config/settings.yaml
cp config/selectors.example.yaml config/selectors.yaml
```

Required in `.env`:

```
INVESTORPLACE_USERNAME=you@example.com
INVESTORPLACE_PASSWORD=••••••••
INVESTORPLACE_LOGIN_URL=https://investorplace.com/login/
INVESTORPLACE_PORTFOLIO_URL=https://investorplace.com/…/platinum-growth-portfolio/
```

Add any additional update/subpage URLs under `sources.update_urls` in
`config/settings.yaml` — Platinum Growth may span multiple signal surfaces.

### Supplying credentials safely

- Credentials are read **only** from environment variables / `.env`; they are
  never hardcoded and `.env` is gitignored. Do not commit it.
- The login **selectors** live in `config/selectors.yaml` (also gitignored), so
  you can adapt to site changes without touching code.
- Prefer a machine-local `.env` with restrictive permissions
  (`chmod 600 .env`). Rotate the password if it is ever exposed.

## Initialize the database

```bash
alembic upgrade head          # creates data/navellier.db with all tables
```

## Run

```bash
# health check — no network, verifies config is ready
python -m navellier_replicator.main check

# one authenticated scrape (requires .env credentials + a real portfolio URL)
python -m navellier_replicator.cli.scrape

# parse a run's captured pages into items + write the daily report
python -m navellier_replicator.cli.parse --run-id <id>

# full daily pipeline (scrape -> parse -> report); paper/dry-run only
python -m navellier_replicator.main run-daily --paper --dry-run

# later-stage commands exist but fail closed in v0.1:
python -m navellier_replicator.cli.plan --policy fifo_cap5 --as-of today   # v0.2
python -m navellier_replicator.cli.rebalance --paper --dry-run             # v0.3
python -m navellier_replicator.cli.reconcile                               # v0.3
```

Artifacts land under `data/`:

- `data/raw/<timestamp>_scrape/` — HTML, text, screenshots, `run.log`
- `data/navellier.db` — all persisted evidence and extracted items
- `data/exports/daily_report_run<id>_<date>.md` — the report

## Test

```bash
pytest -q                     # all tests, fully offline (fixtures only)
pytest tests/unit -q          # unit tests
pytest tests/integration -q   # replay saved artifacts -> parsed items -> report
```

The test suite requires **no network and no browser** — Playwright is imported
lazily, and integration tests replay the HTML fixtures in `tests/fixtures/`.

## Data model (evidence-preserving)

Nine tables: `scrape_runs`, `raw_pages`, `extracted_items`,
`recommendation_events`, `portfolio_targets`, `orders_sent`, `fills`,
`broker_positions`, `audit_flags`.

Parser upgrades never erase evidence: `raw_pages` keeps the full page forever,
and `extracted_items` are **append-only**, stamped with the `parser_version`
that produced them. Re-parsing with a new parser version *adds* rows; it never
overwrites older evidence.

## Safety posture

The system fails **closed**. If login succeeds but no real content is found, if
the parser returns zero actionable items, if confidence is too low, or if the
recommendation set changes drastically without corroboration, the run is blocked
and an `audit_flag` is recorded. Live trading is not implemented and cannot be
enabled by configuration.
