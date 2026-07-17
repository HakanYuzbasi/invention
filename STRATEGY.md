# One System, Honest Edge — Consolidated Trading Strategy

**Date:** 2026-07-17
**Status:** Decided. This document is the decision record; the code lives in `eureka`.

---

## 1. What this document is

Hakan has built three automated trading systems. This is the consolidation
decision: which one survives, what it trades, and what "making money" honestly
means given the evidence the systems themselves produced. It is the Darwin
philosophy (evidence over intuition, adversarial review before decisions)
applied to our own portfolio of projects.

## 2. Evidence review of the three systems

### apex-trading-system (~243k LOC, Alpaca)

- Traded real money and **lost**: −$3,962 realized in crypto (equities +$71);
  full window Apr 13 → Jun 10 2026: **−23.8%, Sharpe −3.21, maxDD −25.6%**;
  post-fix era May 1 → Jun 10: −4.2% in six weeks — a consistent bleed from
  costs plus thin, unvalidated edges (`docs/AUDIT_2026_06_10.md`).
- Its research layer is its real asset. Across 25+ pre-registered strategy
  families tested on ~10 years of real data with deflated-Sharpe and
  walk-forward discipline (`docs/ALPHA_EDGE_HUNT_2026-06.md`):
  **zero deployable edge was found in liquid, retail-accessible markets.**
  Plain SPY buy-and-hold (Sharpe 0.81 full / 1.38 OOS) beat every overlay.
- Crypto mean-reversion had real gross edge but is structurally unprofitable
  at Alpaca's 10–25 bps fees (`docs/C1_CRYPTO_ALPHA_FINDINGS.md`).
- Best single finding: **tail-hedged VRP put-spread** (sell ~ATM 1-month SPY
  put, buy −15% put): Sharpe 0.93 vs SPY 0.81, half SPY's drawdown, DSR 0.77
  — mostly equity beta with a modest real premium (+0.12 Sharpe), loss-capped
  by construction (`docs/VRP_PHASE1_FINDINGS.md`).
- Operationally: the audit found live order paths that bypassed validation,
  a tail hedger with fabricated fallback prices, and containment graded D.

**Verdict: retire the runtime; keep as a read-only research archive.**

### eureka / fable5 (~16.6k LOC, Alpaca)

- Clean rebuild with the right priorities: paper-only enforced at config load,
  limit-orders-only by construction, order FSM with immutable audit trail,
  broker-truth reconciliation, risk circuit breakers, walk-forward validation
  with PSR/Deflated-Sharpe, and a hard statistical **live gate** — real-money
  trading is structurally impossible until pre-registered out-of-sample
  criteria are met.
- 330 tests passing; real paper-trading logs from June 2026 (orders submitted,
  filled, reconciled cleanly).

**Verdict: the foundation. All new work happens here.**

### quant (276 LOC)

Skeleton with aspirational branding. **Verdict: archive.**

## 3. The honest thesis

The systems' own research says it plainly: for a retail account trading liquid
US markets through public data, **no deployable alpha was found**, and the
single highest risk-adjusted return available is the equity risk premium
itself. Therefore the goal is not a money-printer. The goal is:

1. **Capture the equity risk premium efficiently** — don't pay turnover,
   costs, and churn to underperform SPY (which is what both prior systems
   effectively did).
2. **Improve its shape** with the one near-validated structural premium:
   a small, defined-risk, tail-hedged VRP put-spread sleeve.
3. **Keep hunting alpha honestly** — every candidate strategy passes through
   pre-registration, a cumulative trials ledger, walk-forward, and a
   deflated-Sharpe bar before it may touch capital. Deploying sub-bar signals
   is precisely how apex lost money.
4. **Paper first, mechanically gated.** Going live is a consequence of the
   live gate passing, never a mood.

Expected realistic outcome: market-like returns with materially better
drawdown control and audited, statistically honest decision-making. Anything
better than that must earn its place through the gauntlet.

## 4. The system (three layers, all in `eureka`)

| Layer | What | Capital share | Status |
|---|---|---|---|
| 1. ERP core | `core_equity_v1` — band-rebalanced, vol-targeted, regime-aware SPY core; near-zero turnover | dominant (~85%) | **built + validated** |
| 2. VRP sleeve | `research/vrp_putspread.py` — defined-risk SPY put-spread, entries conditioned on VIX term-structure contango + IV−RV richness; never naked | small (~10–15%) once it clears | **evaluation gate built; execution deliberately not built** |
| 3. Research lab | existing engines/strategies (mean-reversion, momentum) at minimal size plus new candidates — nothing scales until it clears pre-registration + trials-ledger-deflated Sharpe | residual | **honesty machinery built** |

**Why the VRP sleeve is a gate, not a live sleeve (yet).** Apex's own research
put VRP's Deflated Sharpe at ~0.77, below the 0.95 bar. The project's first rule
is that deploying sub-bar signals is how the prior account lost real money. So
Phase 3 shipped the *evaluation gate* — the defined-risk put-spread backtest
with Black-Scholes pricing, realistic skew, and VIX term-structure conditioning,
wired to pre-registration — and deliberately did **not** build options execution
into fable5's equity pipeline. That execution work is premature architecture for
a sleeve that fails its own bar; it unlocks only if/when the gate clears on real
paper data.

Supporting machinery ported from apex into fable5:

- **Cumulative trials ledger** — the deflated-Sharpe bar must use the true,
  ever-growing count of everything ever tried, across all research sessions.
- **Ante-hoc pre-registration** — a strategy's config is hashed and registered
  before it may touch out-of-sample data; the attestation records the hash.

## 5. Decision rules (pre-agreed, so future-us can't cheat)

- **No crypto** on venues where fees exceed the measured gross edge
  (Alpaca: proven structurally unprofitable).
- **No market orders, no naked short options, no unvalidated live paths** —
  these are code-level invariants, not policies.
- **Live gate criteria** (pre-registered parameters in the ParameterStore):
  minimum paper days, minimum closed trades, minimum Sharpe/Sortino/PSR, and
  minimum out-of-sample deflated Sharpe from walk-forward attestation.
- **Disconfirming evidence for the ERP core**: if the implemented core
  underperforms a raw SPY benchmark by more than its modeled cost budget over
  a rolling year of paper trading, the implementation (not the thesis) is
  reviewed.
- The roadmap changes only when evidence changes.

## 6. What happened to Project Darwin

Darwin's philosophy survives (this document is a Darwin-style investment
memo). Darwin the platform is not being built: the adversarial review
concluded it was ideation machinery with commodity inputs and an untestable
success criterion. Its three cheap artifacts — the memo template, the
decision/prediction journal, and pre-registered thresholds — are exactly what
was folded into fable5's attestation and trials-ledger machinery, where they
gate real decisions.

## 7. What was delivered (2026-07-17)

All code lives on the `eureka` repo branch `claude/consolidation-v1`; the full
test suite is green (356 passed).

- **Layer 1 — `fable5/strategies/core_equity_v1.py`**: band-rebalanced,
  vol-targeted, regime-aware SPY core. Validated end-to-end through the
  production `BacktestEngine`: near-zero turnover (≈9 orders over 500 days),
  lower drawdown than buy-and-hold in a correction, correct vol-based de-risk.
  Registered as the dominant strategy with a strategy+symbol-scoped exposure
  carve-out; the loss circuit breakers were retuned (and the core exempted from
  per-trade stops and the daily-loss breaker's unrealized view) because a
  passive equity core's risk is managed by *size*, not a loss kill-switch —
  while the 25% equity-drawdown halt still covers the whole book.
- **Layer 3 — honesty machinery**: `fable5/trials_ledger.py` (cumulative,
  idempotent, fail-closed deflation count) and `fable5/preregistration.py`
  (ante-hoc config-hash freeze, fails closed on drift), wired into
  `walk_forward.py` so every OOS evaluation raises the multiple-testing bar for
  the next candidate.
- **Layer 2 — `fable5/research/vrp_putspread.py`**: the VRP evaluation gate
  (see §6). Run it with `python -m fable5.research.vrp_putspread --register`; it
  currently reports `clears_gate=False`, which is the correct, honest outcome.

**Next step to actually deploy VRP:** feed the gate real SPY + VIX/VIX9D history
(not the offline synthetic path), and only if the Deflated Sharpe clears 0.95 on
that real, pre-registered evidence, build the limit-only options execution path.
Until then the system is the ERP core plus a disciplined research lab — paper
only, with live trading mechanically gated on the pre-registered live-gate
criteria.
