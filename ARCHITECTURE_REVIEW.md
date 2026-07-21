# Apex ↔ Eureka — Architecture Review

**Status:** In progress. Read-only, evidence-only review. Every substantive claim
is backed by repository evidence with inline citations `[path]` or
`[path:line-range]`.
**Clones analyzed:** Apex `e17e525` (930 `.py`, ~243,493 LOC; 259 test files) ·
Eureka `d63c200` (122 `.py`, ~19,146 LOC incl. 6,722 test LOC; 47 test files).
**Decision under review:** keep Apex and Eureka independent, or unify into one
platform.
**Priority order (given):** correctness > trading safety > fail-closed >
auditability > single source of truth > research velocity > maintenance >
low operational complexity > minimal duplication > scalability.

---

## Executive summary (Part 1)

```text
APEX ↔ EUREKA ARCHITECTURE REVIEW — PART 1 (Phases 1–2) — SUMMARY

✅ DONE
- Phase 1 repo maps: Apex = multi-tenant, live-capable trading SaaS;
  Eureka(fable5) = single-user, paper-only system. Both traced.
- Phase 2 duplication matrix: 14 subsystems compared (winner + evidence + rec).
- Overall duplication severity: CRITICAL.

🔴 CRITICAL
- Eureka is a from-scratch, safety-hardened REWRITE of Apex's core — 9 subsystems
  share identical names in both trees (live_gate, risk, execution_engine,
  parameter_store, data_validator, reconciler, liveness_monitor,
  execution_quality, cost_model). One system rebuilt, not two complementary ones.
- Honesty machinery (pre-reg / trials ledger / PSR-DSR / gate): Eureka collapsed
  to ONE external source of truth = gauntlet, version-pinned. Apex still holds >=3
  divergent forks: fable8/ + quant_system/research/ + backtesting/.
- Trading safety: Eureka broker is limit-only + paper-only STRUCTURALLY. Apex
  trades LIVE behind a single env flag LIVE_TRADING_CONFIRMED — the system that
  already lost real money.
- Risk: Eureka = 1 audited manager; Apex = 3 layered managers of unproven
  interaction.
- core/system_fortress.py = single 16,735-LOC god-file owning the run loop.

🟡 IMPORTANT
- In EVERY safety/audit-critical subsystem, Eureka wins on top-4 priorities ->
  merge direction is Eureka-as-base, NOT Apex.
- Apex's only non-duplicated runtime asset = IBKR connector; Eureka has no IBKR.
- Apex's risk/, models/, execution/ (TWAP+options) = research candidates to pass
  through gauntlet, not runtime peers.
- Apex duplicates ITSELF before it duplicates Eureka (two reconcilers, two loggers).

⚠️ CAVEATS
- Did NOT trace end-to-end reporting through Apex's 22k-LOC monitoring/.
- Winner/severity calls are architectural (cited structure), not runtime benchmarks.
```

---

## PHASE 1 — Repository maps

### A. Apex (`apex-trading-system`)

- **Purpose.** Live-capable, **multi-tenant** trading platform (trading SaaS). The
  orchestrator "scales `ApexTradingSystem` execution loops dynamically based on
  active broker connections" and provisions per-tenant sessions
  [core/orchestrator.py:35-39, core/orchestrator.py:82-194].
- **Core architecture.** Per-tenant async loop `ApexTradingSystem` assembled by
  **multiple inheritance from four mixins** — `PositionReconcilerMixin`,
  `ExecutionEngineMixin`, `SignalDispatcherMixin`, `SystemFortressMixin`
  [core/execution_loop.py:5-17]. The dominant mixin is a **single 16,735-LOC
  file** [core/system_fortress.py] owning `run()` [core/system_fortress.py:15023].
- **Primary execution flow.** `python main.py` → `run_startup_guards()`
  [main.py:52-58] → singleton file lock [main.py:29-46] →
  `execution_manager.start()` [main.py:72-73] → 10s monitor spawns/kills/restarts
  per-tenant loops [core/orchestrator.py:82-194] → `run()`
  [core/system_fortress.py:15023].
- **Package boundaries (LOC).** core 31,636 · scripts 29,808 · monitoring 22,314 ·
  risk 21,849 · models 19,525 · quant_system 16,946 · execution 8,870 · services
  7,506 · backtesting 7,238 · api 5,762 · data 5,747 · fable8 1,754 · signals
  1,455 · reconciliation 992. Tests 47,712.
- **External deps (SaaS-grade)** [requirements.txt]: torch, scikit-learn, xgboost,
  lightgbm, stable-baselines3, gymnasium, statsmodels, Cython; ib_insync,
  alpaca-py, ccxt; fastapi, uvicorn, streamlit, sqlalchemy/alembic/asyncpg/psycopg2
  (Postgres), redis, **stripe**, authlib/PyJWT/bcrypt/pyotp/qrcode, reportlab,
  google-generativeai.
- **Config model.** Class `ApexConfig` with a `ConfigMetaclass` that reads live
  values from `core.parameter_store` on attribute access [config.py:50-60]; live
  trading is real and env-gated via `LIVE_TRADING` / `LIVE_TRADING_CONFIRMED`
  [config.py:97-103] + `assert_live_trading_confirmation()` [main.py:56].
- **Lifecycles.** Execution [core/execution_loop.py:5-17; core/system_fortress.py:15023];
  Signal — many generators combined in `SignalDispatcherMixin`
  [core/signal_dispatcher.py:45-154]; Order — `broker_dispatch.place_order`
  [core/system_fortress.py:15810]; Risk — **three** managers `RiskManager` /
  `InstitutionalRiskManager` / `GodLevelRiskManager`
  [core/system_fortress.py:46,486,774,786-794]; Reporting — monitoring/dashboard/
  api/analytics + reportlab + prometheus (surface only; internal path not traced).

### B. Eureka (`fable5`)

- **Purpose.** Single-user, **paper-only**, auditable Alpaca system; "live trading
  is structurally impossible until explicit live-gate criteria are met"
  [README.md:1-6].
- **Core architecture.** One flat package `fable5/`, wired by an explicit
  **composition root**, one instance per component [fable5/main.py:23-95]. No
  god-module.
- **Primary execution flow.** `python -m fable5.main` → composition root
  [fable5/main.py:84-95] → `TradingScheduler.run_trading_cycle()`
  [fable5/scheduler.py:254] runs `engine → signal → strategy → execution`
  [fable5/scheduler.py:4]; maintenance reconciles orders/positions
  [fable5/scheduler.py:360-367].
- **External deps (minimal, CPU-only)** [pyproject.toml]: polars, yfinance, numpy,
  python-dotenv, and `gauntlet-verify` pinned to an immutable commit.
- **Config model.** Env `AppConfig` with **paper-only enforced at load**
  [fable5/config.py; README.md]; paper base URL constant [fable5/main.py:25];
  values live as data in the audited regime-keyed `ParameterStore`
  [fable5/parameter_store.py].
- **Lifecycles.** Execution [fable5/scheduler.py:254,340]; Signal — engines behind
  an `EngineRunner` latency budget → `SignalAggregator` [fable5/signal_aggregator.py];
  Order — `OrderManager` FSM [fable5/order_fsm.py] → `submit_limit_order` as the
  **only** submission method [fable5/alpaca_client.py:5-6,51]; Risk — a **single**
  `RiskManager` [fable5/risk_manager.py] with derived limits [fable5/risk_budget.py];
  Reporting — `export_jobs.py` [fable5/export_jobs.py], `metrics.py` (re-exports
  gauntlet.stats) [fable5/metrics.py:33], Prometheus [fable5/observability.py].

---

## PHASE 2 — Duplication analysis

Naming is not coincidental: **9 subsystems exist in both trees under identical
names** (`live_gate`, `liveness_monitor`, `execution_quality`, `execution_engine`,
`universe_manager`, `parameter_store`, `data_validator`, `signal_aggregator`,
`cost_model`). Eureka reads as a clean re-implementation of Apex's core, plus a
further extraction (`gauntlet`) Apex has not adopted.

| # | Capability | Apex | Eureka | Winner | Reason | Evidence | Rec | Severity |
|---|---|---|---|---|---|---|---|---|
| 1 | Honesty machinery | internal fork, triplicated (`fable8/`, `quant_system/research/`, `backtesting/`) | thin re-exports of `gauntlet` (one SSOT) | **Eureka** | Eureka has one extracted, pinned source; Apex ≥3 divergent copies | [fable5/preregistration.py:14-27],[fable5/trials_ledger.py:14],[fable5/attestation.py:18-26],[fable5/metrics.py:33] vs [fable8/preregistration.py],[quant_system/research/trials_ledger.py] | Delete Apex forks; adopt gauntlet | **Critical** |
| 2 | Broker — Alpaca | `execution/alpaca_connector.py` (1,576), market+live capable | `alpaca_client.py` limit-only, paper-only | **Eureka** | Trading-safety + fail-closed | [fable5/alpaca_client.py:5-6,51-104] vs [execution/alpaca_connector.py] | Keep Eureka | High |
| 3 | Broker — IBKR | `execution/ibkr_connector.py` (2,575) + adapter/lease | none | **Apex (only)** | Unique capability | [execution/ibkr_connector.py] vs (no `ibkr` in fable5/) | Keep as Apex-only asset | Low |
| 4 | Execution/routing | `core/execution_engine.py` + `execution/` TWAP/router/shield (8,870) | `execution_engine.py` (policy limit → FSM) | **Split** | Eureka safer/simpler; Apex richer but coupled+unproven | [fable5/execution_engine.py] vs [core/execution_engine.py],[execution/smart_order_router.py] | Base Eureka; cherry-pick Apex as opt-in | High |
| 5 | Risk | `risk/` 30+ modules, 3 layered managers | single `risk_manager.py` + `risk_budget.py` | **Eureka** | Auditability + correctness | [fable5/risk_manager.py],[fable5/risk_budget.py] vs [core/system_fortress.py:486,774,786-794] | Keep Eureka; mine Apex as research menu | **Critical** |
| 6 | Config | `ApexConfig`+metaclass, live via env flag | env `AppConfig`, paper-only raises at load | **Eureka** | Fail-closed | [config.py:50-60,97-103] vs [fable5/config.py],[fable5/parameter_store.py] | Keep Eureka | High |
| 7 | Live gate | `core/live_gate.py` (546) bespoke | `live_gate.py` → gauntlet Gate + signed attestation | **Eureka** | Fail-closed, no override | [fable5/live_gate.py:41-42],[fable5/attestation.py] vs [core/live_gate.py] | Keep Eureka | High |
| 8 | Backtesting | `backtesting/` (7,238), ≥5 backtesters + `fable8/walk_forward.py` | `backtest.py`+`sim_broker.py`+`walk_forward_engine.py`, replays live pipeline | **Eureka** | One engine for live+backtest removes drift | [fable5/backtest.py],[fable5/sim_broker.py] vs [backtesting/advanced_backtester.py] | Keep Eureka; delete Apex | High |
| 9 | Reconciliation | **two copies inside Apex**: `core/position_reconciler.py` (38KB) + `reconciliation/position_reconciler.py` (16KB) | `position_manager.py` + `order_fsm.py` | **Eureka** | Apex duplicates its own reconciler | [core/position_reconciler.py]&[reconciliation/position_reconciler.py] vs [fable5/position_manager.py] | Keep Eureka; delete both Apex | High |
| 10 | Logging | `core/logging_config.py` (413) **and** `utils/structured_logger.py` | single `logging_setup.py` | **Eureka** | SSOT | [fable5/logging_setup.py:24-74] vs [core/logging_config.py],[utils/structured_logger.py] | Consolidate on Eureka | Medium |
| 11 | Signals | `models/` 19,525 + `signals/` + consensus/filter | `engines/` + `signal_aggregator.py` | **Context** | Eureka auditable/CPU-only; Apex more but heavier/unproven | [core/signal_dispatcher.py:45-154] vs [fable5/signal_aggregator.py] | Keep Eureka contract; Apex signals as candidates | Medium |
| 12 | Parameter store | `core/parameter_store.py` (116) | `parameter_store.py` (regime-keyed, audited, warm-up) | **Eureka** | Auditability | [fable5/parameter_store.py] vs [core/parameter_store.py] | Keep Eureka | Medium |
| 13 | data_validator/universe/cost_model/exec-quality/liveness | `core/*`, `execution/cost_model.py` | same-named `fable5/*` | **Eureka** | Newer, test-backed rewrites | name-mirror verified both trees | Keep Eureka; delete Apex equivalents | Medium |
| 14 | VRP research | `fable8/signals/vrp.py` | `fable5/research/vrp_putspread.py` (gate-locked off) | **Eureka** | Wired to gate; refuses modeled-price deploy | [fable5/research/vrp_putspread.py:8] vs [fable8/signals/vrp.py] | Consolidate into Eureka | Medium |

**Internal-to-Apex duplication:** two reconcilers (#9), two loggers (#10),
honesty machinery split across `fable8` + `quant_system` + `backtesting` (#1);
`fable8` is itself a newer embedded sibling of Eureka's `fable5`.

**Overall duplication severity: CRITICAL.** Eureka is a from-scratch,
safety-hardened re-implementation of Apex's core plus one further extraction
(`gauntlet`) Apex never adopted. In every safety/audit-critical subsystem the
Eureka version wins on the top-4 priorities. The only genuinely non-duplicated
Apex runtime asset is the IBKR connector (#3).

---

*Part 2 (Phases 3–5: Safety, Dead Code, Dependencies) and Part 3 to follow.*
