# Project Gauntlet — The Next Project Decision

**Date:** 2026-07-19
**Status:** Decided. This document is the decision record; `STRATEGY.md` is its
predecessor and remains in force for the trading system itself.

---

## 1. What this document is

`STRATEGY.md` answered "which trading system survives." This document answers
the next question: **given everything in this GitHub account, what is the next
best project to start?** It applies the same method as before — inventory the
evidence, consider the options adversarially, decide once, pre-register the
criteria under which the decision is wrong.

The clarified goal: a **hybrid** — the trading stack keeps compounding evidence
in the background (it is designed to run itself), while the new project builds
something public. Capacity: near full-time.

## 2. Asset inventory (the whole account, honestly appraised)

| Repo | What it actually is | Strategic value |
|---|---|---|
| `eureka` (fable5) | The surviving trading system: ERP core validated, VRP mechanically gated, 377 tests green | High — but its *expected outcome is market-like returns*, by its own research |
| `apex-trading-system` | Read-only research archive: 25+ pre-registered strategy families tested on ~10y of data, **zero deployable retail edge found**; a real-money audit of a −23.8% loss | **Unique** — see §3 |
| `invention` | Decision records (this repo) | The method itself |
| `quant` | Archived skeleton | None |
| `NavIO`, `navio-floor-plan-analysis` | Indoor navigation + floor-plan CV, dormant since early 2026 | Optionality only; crowded space, orthogonal to current momentum |
| `Applied-DS-Capstone-CS`, `dojo-ds-case` | Coursework | Background skills |

## 3. The insight the evidence forces

Read §2 with apex's own conclusion in mind: *for a retail account trading
liquid US markets on public data, no deployable alpha was found.* That
conclusion cuts two ways:

1. It caps the expected value of pouring more full-time effort into
   alpha-hunting: the next unit of research effort has, by our own measured
   base rate (0 for 25+), near-zero expected alpha.
2. It reveals what the *actual* rare asset in this account is. It is not a
   trading signal. It is the combination of:
   - **battle-tested honesty machinery** — ante-hoc pre-registration
     (config-hash freeze), a cumulative fail-closed trials ledger,
     walk-forward with PSR/Deflated-Sharpe, admissible-data contracts,
     derived-not-tuned risk budgets — already written, already under test;
   - **an evidence base nobody publishes**: 25+ *pre-registered negative
     results* and an audited real-money post-mortem.

Everyone in retail quant publishes beautiful backtests. Essentially nobody
publishes disciplined negative results or their own audited losses, because
the incentive structure punishes it. That is precisely why doing it is a moat:
the differentiator is radical, verifiable honesty, and the cost of copying it
is having spent years and real money generating the evidence.

## 4. Options considered

- **A. Finish the VRP path and keep researching (trading only).** Necessary
  but not sufficient — `STRATEGY.md` already prescribes it, it is roughly a
  week of setup plus waiting for paper evidence to accumulate, and its honest
  expected outcome (market-like returns, better drawdowns) does not consume
  full-time capacity or produce anything public. **Kept, as background Track A
  — not the project.**
- **B. Revive NavIO with modern multimodal models.** A real market, but a
  crowded one (every mapping and CV team is pointing multimodal models at
  floor plans), it abandons all accumulated momentum, and we hold no unique
  evidence or infrastructure there. **Rejected; revisit only per §8.**
- **C. Hunt a data edge (build proprietary datasets).** The honest implication
  of "no alpha in public data" is that real edge lives in non-commodity data —
  but building that solo against funds with satellite budgets fails the
  feasibility test. **Rejected.**
- **D. Project Gauntlet (chosen).** Turn the honesty machinery + negative
  evidence into a public standard. Detailed below.

**The Darwin test.** Project Darwin was killed for being ideation machinery
with commodity inputs and an untestable success criterion. Gauntlet is the
opposite on all three axes: it is *verification* machinery, its inputs
(battle-tested code + unpublishable-by-others evidence) are proprietary, and
its success criterion is externally measurable adoption, pre-registered in §8.

## 5. The decision: Project Gauntlet

**Extract fable5's validation stack into an open-source, broker-agnostic
strategy-validation standard, launch it on the strength of the Edge Graveyard,
and grow it into a public attested pre-registration ledger — the
clinicaltrials.gov of trading strategies.**

Three components, in dependency order:

1. **The `gauntlet` library** (open source, broker-agnostic). Extracted from
   fable5: pre-registration with ante-hoc config-hash freeze, the cumulative
   trials ledger with fail-closed deflation counts, walk-forward evaluation
   with PSR/Deflated-Sharpe, admissible-data contracts (point-in-time,
   provenance-hashed, stale-data fail-closed), and risk budgets derived from a
   pre-registered allocation rather than tuned to a backtest. `eureka` becomes
   its first consumer — the extraction is only done when eureka's full suite
   is green against the library as a dependency.
2. **The Edge Graveyard** (launch content). A public, methodology-complete
   write-up of the 25+ pre-registered negative results from the apex archive,
   plus the post-mortem of the audited −23.8% real-money loss. This is the
   marketing no competitor can run: verifiable receipts for "here is what does
   *not* work, and here is what fooling yourself costs."
3. **The attestation ledger** (the endgame). A public, append-only,
   hash-timestamped registry: a strategy's config hash is registered *before*
   out-of-sample evaluation; the pass/fail outcome is attested against that
   hash. This makes third-party track records verifiable for the first time —
   and every registered trial raises the honest multiple-testing (deflation)
   bar for everyone, so the ledger's value compounds with use and cannot be
   bootstrapped by a copycat starting from zero.

**Why this serves "being the best."** If Gauntlet works, it makes this account
the reference point for honest strategy validation — reputation, users, and
allocator-grade credibility. If the trading research ever *does* clear its
bar, a Gauntlet attestation is what makes that claim believable to outsiders.
The two tracks reinforce each other; neither depends on being lucky.

## 6. What stays in force

Nothing here weakens `STRATEGY.md`. In particular:

- **VRP stays hard-gated** on an admissible real option-chain dataset; the
  Black-Scholes-from-VIX screen remains locked to `clears_gate=False`.
- **No crypto** on venues where fees exceed measured gross edge; **no market
  orders, no naked short options, no unvalidated live paths** — code-level
  invariants, unchanged.
- **Paper first, mechanically gated.** Going live remains a consequence of the
  pre-registered live gate, never a mood.

## 7. 90-day roadmap (near full-time)

| Weeks | Track | Deliverable |
|---|---|---|
| 1 | A (trading) | Execute `RUNBOOK.md` on a networked machine: real SPY + VIX/VIX9D backfill, paper campaign started. From here Track A is monitoring, not building. |
| 2–5 | B (Gauntlet) | Extract the `gauntlet` library into its own repo; eureka green as its first dependent; docs + examples runnable by a stranger. |
| 4–7 | B | Write the Edge Graveyard + apex post-mortem (drafted from `docs/ALPHA_EDGE_HUNT_2026-06.md`, `docs/AUDIT_2026_06_10.md`, `docs/C1_CRYPTO_ALPHA_FINDINGS.md`). |
| 6–10 | B | Attestation ledger v1: append-only, hash-timestamped, repo-backed (no service to operate yet); registration + verification CLI in the library. |
| 8–12 | B | Public launch: library + Graveyard published together; distribution to quant communities; collect external registrations. |
| ~13 (day 90) | — | Checkpoint against §8. Hard review at day 120. |

## 8. Pre-registered success / kill criteria (so future-us can't cheat)

Recorded now, before launch, in the same spirit as the live gate:

- **Day 120 adoption bar** — at least one of: (a) ≥ 10 external strategies
  registered in the public ledger by people we did not recruit personally,
  (b) ≥ 3 substantive external contributors to the library, or
  (c) ≥ 500 GitHub stars *plus* evidence of real third-party use (issues/PRs
  from usage, not drive-by).
- **If the bar fails:** Gauntlet is not deleted — the library remains eureka's
  validation dependency (the extraction pays for itself regardless) — but
  public/adoption work stops, and the next-project question is reopened with
  NavIO-×-multimodal as the first candidate to re-examine.
- **Track A disconfirmation** (unchanged from `STRATEGY.md`): if the ERP core
  underperforms raw SPY by more than its modeled cost budget over a rolling
  paper year, the implementation is reviewed.
- The roadmap changes only when evidence changes.
