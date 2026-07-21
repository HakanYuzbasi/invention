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

## PHASE 3 — Safety review (comparative; severity rated for Apex)

| Risk | Apex — evidence | Eureka — evidence | Severity |
|---|---|---|---|
| Accidental live trading | live gated only by two env vars; `assert_live_trading_confirmation` raises only `if LIVE_TRADING and not LIVE_TRADING_CONFIRMED` [config.py:3101-3104]; no structural block | live structurally impossible: `mode: Literal["paper"]`, non-paper mode/URL raises at load [fable5/config.py:3-5,55-66]; non-paper broker built only after signed attestation, "no override, no env backdoor, no silent fallback" [fable5/main.py:410-433] | **Critical** |
| Market-order execution | router escalates to MARKET on high/critical urgency [execution/smart_order_router.py:34,37,53,100,143]; "falls back to market sweep" [config.py:74] | only `submit_limit_order` exists; no market code path [fable5/alpaca_client.py:5-6,51] | **Critical** |
| Fail-open config | `ConfigMetaclass.__getattribute__` wraps parameter-store lookup in `except Exception: pass` → silently returns static default [config.py:57-62] | typed + validated at load; invalid raises [fable5/config.py:55-88] | **High** |
| Double submission / idempotency | `OrderIdempotencyGuard` keyed on `(symbol,side,qty)`, per-process, **`TTL=0` disables it** [execution/order_idempotency.py:1-40]; TTL range admits 0.0 [config.py:3239] | single attempt `retries=0`; recovery via `client_order_id` in reconcile [fable5/alpaca_client.py:75-77; fable5/execution_engine.py:160-182] | **High** |
| Silent failures | 77 broad `except Exception`→pass/continue in the god-file alone [core/system_fortress.py]; 94 except clauses across core/execution/risk | 0 broad `except…pass/continue` in `fable5/*.py`; 52 total | **High** |
| Global mutable state / races | module singletons shared across concurrent per-tenant loops: `execution_manager` [core/orchestrator.py:208], `_parameter_store` [core/parameter_store.py:113], `broker_service` [services/broker/service.py:1080] (specific race not proven; pattern is the finding) | no module-level component singletons in `fable5/*.py`; built once in composition root [fable5/main.py:84-95] | **High** |
| Paper/live confusion | one code+config object serves both; strict live rules default off [config.py:131-168] | paper is the only representable mode; live is a separate attestation-gated branch [fable5/main.py:423-433] | **High** |
| Credential leakage | mitigated: no committed `.env`/keys; active `scripts/check_secrets.py` rejects weak secrets [scripts/check_secrets.py:1-40] | keys from env only [README.md] | **Low (both)** |

**Verdict:** Apex safety is policy-based and defeatable (env flags, config booleans, silent fallbacks, market escalation); Eureka's is structural/fail-closed. On priorities #2–#3, Eureka is the correct inheritance base.

## PHASE 4 — Dead code review

| Item | Evidence | Recommendation |
|---|---|---|
| Root round-artifacts | `r16_best_config.json`, `r17_artifacts/`, `r18_artifacts/`, `r17_train.py`, `r18_train.py` | Archive |
| `scratch/` throwaways | `scratch/{test_orders,liquidate_orphans_true,analyze_fortress,split_code}.py` etc. | Delete (some destructive) |
| `scripts/` 120 files / 29,808 LOC | `alpha_lab.py` + `alpha_lab_v2.py`, ~15 overlapping one-off backtests [scripts/] | Archive + Merge to one entrypoint |
| Honesty machinery triplicated | `fable8/{preregistration,walk_forward,metrics}.py` + `quant_system/research/{trials_ledger,stats}.py` + `backtesting/*` | Delete/Merge → adopt `gauntlet` |
| `fable8/` embedded subsystem | newer sibling of `fable5` inside Apex | Merge into Eureka research |
| Intra-Apex duplicate reconciler/logger | `core/position_reconciler.py`+`reconciliation/position_reconciler.py`; `core/logging_config.py`+`utils/structured_logger.py` | Delete redundant copy |
| Legacy paths | "Unified (legacy) mode" [core/orchestrator.py:173]; [config.py:1922,1967,1995,2597] | Rewrite/Delete |

Dead code is **structural** (whole abandoned packages/scripts), not TODO-annotated.

## PHASE 5 — Dependency review

- `config.py` god-hub: imported by **151 files**; 3,447 LOC.
- Real circular dep: `config.py` lazily imports `core.parameter_store` [config.py:57] while `core/parameter_store.py` imports `from config import ApexConfig` [core/parameter_store.py:31].
- `system_fortress.py` coupling sink: 16,735 LOC, 103 imports, owns run/broker/risk [core/system_fortress.py:15023,385-451,486-794].
- Hidden dep swallowed on failure [config.py:57-62] vs Eureka's explicit pinned `gauntlet` [pyproject.toml].
- Eureka graph: flat, `config` imported by 4 files, largest file 603 LOC [fable5/main.py].

**Debt hotspots & untangling cost:** `system_fortress.py` **XL**; `config.py`+circular **L**; `risk/` (3 managers) **L/XL**; honesty→gauntlet **M**; scripts/scratch **S**. Reuse Apex as base = **XL**; re-home Apex's unique pieces onto Eureka = **M–L**.

## Executive summary (Part 2)

```text
APEX ↔ EUREKA — PART 2 (Phases 3–5) — SUMMARY

CRITICAL (safety): Apex live is 2 env vars away, no structural block
[config.py:3101-3104]; router escalates to MARKET [execution/smart_order_router.py:37,53,100,143;
config.py:74]; fail-open config swallows errors [config.py:57-62]; 77 silent
except->pass in system_fortress.py (Eureka: 0 in all of fable5/); 3 shared global
singletons across tenant loops [orchestrator.py:208; parameter_store.py:113;
service.py:1080]; idempotency defeatable at TTL=0 [execution/order_idempotency.py].
Eureka is structurally fail-closed [fable5/config.py:3-5,55-66; fable5/main.py:410-433].

DEAD CODE: scripts/ 120 files/29,808 LOC, scratch/ throwaways, r16/r17/r18
artifacts, fable8+quant_system+backtesting honesty triplication, intra-Apex
duplicate reconciler/logger. Structural, not TODO-annotated.

DEPS: config.py imported by 151 files + circular with core.parameter_store
[config.py:57; core/parameter_store.py:31]; system_fortress.py 16,735 LOC/103
imports. Untangle Apex-as-base = XL; re-home unique pieces onto Eureka = M–L.

CREDENTIALS: low risk both (no committed secrets; check_secrets.py guard).
```

---

# PART 3 — Synthesis & Final Recommendation (Phases 6–10)

## Executive Summary

**UNIFY** — merge Apex **into** Eureka, with Eureka as the base, single source of
truth, and go-forward runtime; retire Apex to a read-only research archive; and
re-home only Apex's genuinely-unique, safety-neutral assets (the IBKR connector,
TWAP/options execution, specific risk/signal research) by passing each through
the `gauntlet` gate before it can touch capital.

The decision is forced by the mission's own priority order (correctness >
trading safety > fail-closed > auditability > single source of truth). On every
one of those top-five axes the Eureka implementation wins on cited evidence, and
the two systems are not complementary — Eureka is already a from-scratch,
safety-hardened re-implementation of Apex's core (9 subsystems name-mirrored
across both trees) plus one further extraction (`gauntlet`) that Apex never
adopted. "Keep separate" is the status quo that the CRITICAL duplication
severity condemns; "merge into Apex" inherits a 16,735-LOC god-module
[core/system_fortress.py], a fail-open config imported by 151 files
[config.py:57-62], and a live/market-order pathway
[execution/smart_order_router.py:37,53,100,143]; "new repo" throws away Eureka's
19k tested LOC to rebuild what Eureka already is.

## Repository Inventory

| Repo | Purpose | Size | State | Role going forward |
|---|---|---|---|---|
| Apex | Multi-tenant, live-capable trading SaaS [core/orchestrator.py:35-39] | 930 `.py`, ~243,493 LOC; 259 test files | Runtime retired per `STRATEGY.md`; lost real money | Read-only research archive; donor of unique modules |
| Eureka (`fable5`) | Single-user, paper-only, auditable Alpaca system [README.md:1-6] | 122 `.py`, ~19,146 LOC; 47 test files | Actively developed; 330–377 tests green | Base / SSOT / go-forward runtime |
| `gauntlet` | Extracted honesty machinery [gauntlet/README.md] | stdlib-only, Apache-2.0 | Consumed by Eureka, pinned [pyproject.toml] | Shared library for both |

## Architecture Maps

- **Apex** — per-tenant async `ApexTradingSystem` via 4-mixin multiple inheritance
  [core/execution_loop.py:5-17], dominated by the 16,735-LOC `SystemFortressMixin`
  owning `run()` [core/system_fortress.py:15023]; orchestrator spawns/kills/restarts
  tenant loops [core/orchestrator.py:82-194]; dual broker
  [core/system_fortress.py:385-451]; three layered risk managers
  [core/system_fortress.py:486,774,786-794]; SaaS deps incl. Postgres/Redis/Stripe/torch
  [requirements.txt]; class-config with parameter-store metaclass and env-gated live
  [config.py:50-60,97-103].
- **Eureka** — flat `fable5/` wired by one composition root
  [fable5/main.py:23-95]; cycle `engine → signal → strategy → execution`
  [fable5/scheduler.py:4,254]; single limit-only broker [fable5/alpaca_client.py:5-6,51];
  single risk manager [fable5/risk_manager.py]; minimal CPU-only deps + pinned
  `gauntlet` [pyproject.toml]; paper-only enforced at load [fable5/config.py:3-5,55-66].

## Duplicate Systems

Fourteen subsystems overlap; 9 share identical module names across both trees
(`live_gate`, `liveness_monitor`, `execution_quality`, `execution_engine`,
`universe_manager`, `parameter_store`, `data_validator`, `signal_aggregator`,
`cost_model`). Full matrix in Part 2 above. Decisive case: honesty machinery is a
single pinned SSOT in Eureka via `gauntlet` re-exports
[fable5/preregistration.py:14-27, fable5/trials_ledger.py:14, fable5/metrics.py:33]
but triplicated in Apex across `fable8/`, `quant_system/research/`, `backtesting/`.
Only non-duplicated Apex runtime asset: the IBKR connector
[execution/ibkr_connector.py]. Overall duplication severity: **CRITICAL**.

## Safety Review

Apex safety is policy-based/defeatable; Eureka's is structural/fail-closed.
Criticals: accidental live two env vars away, no structural block
[config.py:3101-3104] vs attestation-only live "no override, no env backdoor"
[fable5/main.py:410-433]; router escalates to MARKET
[execution/smart_order_router.py:37,53,100,143] vs structurally limit-only
[fable5/alpaca_client.py:5-6]. Highs: fail-open config [config.py:57-62]; 77
silent `except…pass/continue` in the god-file vs 0 in all of `fable5/`; 3 shared
global singletons across tenant loops [core/orchestrator.py:208,
core/parameter_store.py:113, services/broker/service.py:1080]; idempotency
defeatable at `TTL=0` [execution/order_idempotency.py:1-40]. Credential leakage
low for both (`scripts/check_secrets.py`).

## Dead Code

Structural, not annotated: `scripts/` (120 files/29,808 LOC incl.
`alpha_lab.py`+`alpha_lab_v2.py`); `scratch/` throwaways (some destructive);
root round-artifacts (`r16_best_config.json`, `r17_artifacts/`, `r18_artifacts/`,
`r17_train.py`, `r18_train.py`); honesty triplication; intra-Apex duplicate
reconciler and logger; legacy modes [core/orchestrator.py:173, config.py:1922-2597].
Delete `scratch/`; Archive artifacts; Merge `scripts/` to one entrypoint;
Delete/Merge honesty forks → `gauntlet`.

## Dependency Review

Two god-nodes: `config.py` (151 importers; real `config ↔ core.parameter_store`
cycle [config.py:57; core/parameter_store.py:31]) and `system_fortress.py`
(16,735 LOC, 103 imports). Eureka flat (config imported by 4 files; largest file
603 LOC [fable5/main.py]) with one explicit pinned shared abstraction. Untangle
Apex-as-base = XL; re-home Apex's unique pieces onto Eureka = M–L.

## Evidence Gaps

1. Apex `monitoring/` (22,314 LOC) reporting flow not traced end-to-end.
2. Neither system executed; test-pass claims from counts/`STRATEGY.md`, not a run.
3. No runtime benchmarking — winner/severity/cost calls are architectural.
4. Shallow clones (depth 1) — no blame/churn; "legacy" inferred from structure.
5. `services/broker/service.py` internals and much of `risk/` sampled, not fully read.
6. Business value of Apex's SaaS/multi-tenant/IBKR/options stack is out of scope.

## Strongest Case Against My Recommendation

*The opposite: keep Apex as base (or keep both), because Eureka is too small.*

Strongest evidence for it: Apex has ~243k LOC and 259 test files of capabilities
Eureka lacks — IBKR [execution/ibkr_connector.py], options/TWAP
[execution/options_trader.py, execution/adaptive_twap.py], multi-tenant
orchestration [core/orchestrator.py:82-194], a SaaS spine (auth, Stripe, Postgres,
Redis, FastAPI) [requirements.txt], and ML/RL research. Eureka is paper-only,
single-broker, single-user, no live path. If the goal is a commercial live
platform, "merge into Eureka" looks like discarding the only assets that could
become a product and mistaking Eureka's safety (partly from doing less) for
superiority.

Why it loses: (1) mission priorities rank correctness/safety/fail-closed/audit
above velocity/scalability — and Apex fails exactly those on cited evidence
[config.py:57-62; execution/smart_order_router.py:37,53; config.py:3101-3104];
an option can't win on the lowest-weighted criteria. (2) Apex's capabilities are
largely unproven/unsafe — `STRATEGY.md` records it traded real money and lost with
zero validated edge; the SaaS scaffolding served a product with no product-market
fit, so it is sunk cost, not banked value. (3) UNIFY does not discard those assets
— it cherry-picks IBKR/TWAP/options/risk research through the gauntlet gate and
keeps Apex as a readable archive, so the objection's valid content is satisfied by
the recommendation. (4) "New repo" is dominated because Eureka *is* the clean
rewrite a greenfield would produce. The counter-case wins only if the objective
were "maximize feature surface regardless of safety," which inverts the priorities.

## Final Recommendation

**UNIFY — merge Apex into Eureka (Eureka as base/SSOT); archive Apex; port unique
modules through the gate.**

### Decision scorecard (Phase 9)
Weights derive from the mission priority order. Weighted total = Σ(weight × score);
normalized = total ÷ 60.

| Criterion (weight) | Keep Separate | Apex→Eureka | Eureka→Apex | New repo |
|---|---|---|---|---|
| Correctness (10) | 6 | 9 | 3 | 7 |
| Trading safety (9) | 5 | 9 | 3 | 8 |
| Fail-closed (8) | 5 | 9 | 3 | 8 |
| Auditability (7) | 5 | 9 | 4 | 8 |
| Single source of truth (6) | 3 | 9 | 3 | 8 |
| Maintainability (5) | 3 | 8 | 2 | 7 |
| Research velocity (4) | 5 | 7 | 6 | 4 |
| Operational simplicity (3) | 5 | 8 | 2 | 7 |
| Developer productivity (3) | 4 | 7 | 3 | 4 |
| Testing (5) | 5 | 7 | 5 | 5 |
| **Weighted total** | 285 | **508** | 201 | 419 |
| **Normalized (/10)** | 4.75 | **8.47** | 3.35 | 6.98 |

Ranking: **Apex→Eureka (8.47)** > New repo (6.98) > Keep Separate (4.75) >
Eureka→Apex (3.35).

### Migration plan (Phase 8) — no code
- **Principles:** Eureka is base and SSOT; `gauntlet` is the sole honesty library;
  nothing from Apex enters runtime until it passes the gauntlet gate and conforms
  to Eureka's structural safety (limit-only, paper-default, attestation-gated
  live); one capability at a time; Apex stays an untouched read-only archive so
  rollback is always "use Eureka as-is."
- **Order:** (1) Freeze Apex runtime → archive. (2) Ratify `gauntlet` as the only
  honesty SSOT. (3) Port unique, safety-neutral modules behind Eureka interfaces:
  IBKR connector *as a second adapter conforming to the limit-only contract* →
  TWAP/options opt-in → Apex risk/signal ideas as candidate strategies that must
  clear pre-registration + walk-forward + DSR. (4) Carry only still-relevant
  parameters via Eureka's audited `ParameterStore`.
- **Safety checkpoints:** each port preserves paper-only default, introduces no
  market-order path unless explicitly gated, keeps the Eureka suite green, and
  clears the live-gate/attestation before any capital.
- **Rollback checkpoints:** every capability on a branch behind a flag; failed
  validation → revert the module; base stays green because Apex is never mutated.
- **Testing milestones:** (i) Eureka suite green post-ratification; (ii) IBKR
  adapter conformance (limit-only + reconciliation) green in paper; (iii) each
  ported idea passes walk-forward + DSR in the trials ledger; (iv) end-to-end
  paper run reconciles cleanly.
- **Repository retirement:** tag a final Apex commit, mark README "retired —
  research archive; runtime superseded by Eureka," keep read-only, never delete.
  Eureka becomes the single maintained runtime; `gauntlet` stays its own library.

### Required attributes
- **Confidence:** 85%. Architectural evidence is strong and consistent; the 15%
  reflects un-executed/un-benchmarked gaps and the out-of-scope business question.
- **Major risks:** (a) porting IBKR/options re-introduces a market-order or live
  path if the limit-only/attestation contracts are not enforced on the adapter;
  (b) scope creep recreating the monolith inside Eureka; (c) losing knowledge
  buried in Apex `risk/`/`scripts/` if archived carelessly.
- **Major benefits:** collapses CRITICAL duplication to one SSOT; inherits
  fail-closed safety by construction; ~19k maintainable LOC replaces ~243k for a
  solo dev; one audit trail + attestation-gated live; `gauntlet` already shared.
- **Non-negotiable requirements:** paper-only default preserved; no market-order
  path except behind an explicit pre-registered gate; `gauntlet` is the only
  honesty machinery (delete Apex forks from the go-forward path); every ported
  capability clears pre-registration + walk-forward + DSR before capital; Apex
  archived read-only, not deleted.
- **Expected engineering effort:** Medium. Most of Apex is archived, not migrated;
  the expensive clean-rewrite already exists as Eureka. Effort is selective,
  on-demand porting (IBKR M–L; TWAP/options M; risk/signal research L, mostly
  validation). Rises to High only if the full multi-tenant/SaaS surface is ported
  — not recommended.
- **Biggest unknowns:** (1) whether Apex's IBKR/options/multi-tenant surface has
  real business value (business call); (2) whether any Apex `risk/` module encodes
  a validated edge that survives the gauntlet gate (`STRATEGY.md`: none found so
  far); (3) Apex `monitoring/` internals never traced.

---

## Executive summary (Part 3)

```text
APEX ↔ EUREKA ARCHITECTURE REVIEW — PART 3 (Phases 6–10) — SUMMARY

DECISION: UNIFY — merge Apex INTO Eureka (Eureka = base/SSOT); archive Apex
read-only; port only unique pieces (IBKR, TWAP/options, risk research) through the
gauntlet gate.

SCORECARD (weighted /10): Apex→Eureka 8.47 > New repo 6.98 > Keep Separate 4.75 >
Eureka→Apex 3.35. Weights from mission priorities.

WHY: on the top-5 priorities (correctness, safety, fail-closed, audit, SSOT)
Eureka wins on cited evidence; Apex = fail-open config [config.py:57-62],
market-order escalation [smart_order_router.py:37,53], live-behind-a-flag
[config.py:3101-3104], 16,735-LOC god-module, 151-importer config + circular dep.
Eureka is already the clean rewrite a greenfield would produce.

COUNTER-CASE (argued + defeated): Apex has IBKR/options/multi-tenant/SaaS Eureka
lacks — but unproven/unsafe sunk cost, ranked below safety; UNIFY preserves them
via cherry-pick + archive.

CONFIDENCE 85%. EFFORT Medium (most of Apex archived, not migrated; Eureka exists).
NON-NEGOTIABLES: paper-only default; no market path except behind a pre-registered
gate; gauntlet as sole honesty SSOT; every port clears prereg+walk-forward+DSR;
Apex archived not deleted.

EVIDENCE GAPS: monitoring/ not traced; nothing executed/benchmarked; depth-1
clones (no churn history).
```

*End of review.*
