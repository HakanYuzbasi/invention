# Which Project Earns First — Portfolio Ranking & Go-To-Market Memo

**Date:** 2026-07-21
**Status:** Advisory decision record. Companion to `STRATEGY.md`.
**Author's frame:** Darwin philosophy applied to the *business* question —
evidence over ambition, ranked by time-to-first-dollar for a solo dev.

---

## 0. The premise you have to accept first

Your own research already settled the most important business question, and the
answer is uncomfortable: **the money is not in running the strategies.**
`STRATEGY.md` records it plainly — apex tested 25+ pre-registered strategy
families over ~10 years of real data with walk-forward + deflated-Sharpe
discipline and found **zero deployable edge in liquid, retail-accessible
markets**; it traded real money and lost (−23.8%, Sharpe −3.21, maxDD −25.6%).
The best honest finding was that plain SPY beat every overlay.

So this memo does **not** rank "which system will make trading profits." None
reliably will, and betting a business on undiscovered alpha is exactly the
mistake apex already paid for. It ranks **which asset you can turn into revenue
in 2–3 months by selling the discipline and the infrastructure you built while
learning that lesson.** That reframing is the single most valuable output here.

The good news: the by-products of a rigorous, failed alpha hunt — a
broker-agnostic verification layer and audit-grade trading infra — are
*genuinely* scarce, and other people building trading systems keep making the
mistakes you already instrumented against.

## 1. Scope & method

Reviewed all repos on the connected account. Trading/quant candidates:
`gauntlet`, `eureka` (FABLE5), `apex-trading-system`, `quant`. Evidence came
from each repo's own code/README and the consolidation record in `STRATEGY.md`.

**Excluded, with reason:** `NavIO` and `navio-floor-plan-analysis`
(indoor-navigation / floor-plan computer vision — a different domain from the
trading/quant skillset this request is about); `Applied-DS-Capstone-CS` and
`dojo-ds-case` (2021–22 data-science coursework). `invention` is the
decision-record repo and holds this memo.

## 2. The ranking

Scored on your three axes. "Time-to-$" assumes full-time focus.

| # | Asset (as a *business*, not a repo) | Revenue potential (solo) | Skill / codebase fit | Time-to-first-$ | Why |
|---|---|---|---|---|---|
| **1** | **gauntlet** — a "prove-your-backtest" / anti-overfitting tool (open-core + hosted attestations + audits) | Medium, but real and near | **Excellent** — it's already extracted, packaged, tested | **Fastest (days–weeks)** | Already a standalone Apache-2.0 pip-installable library solving a *recognized, universal* pain; strategy/broker-agnostic, so its market is independent of your own (unprofitable) edge, and it needs **no alpha** to be worth money. |
| **2** | **eureka / FABLE5** — audit-grade trading infrastructure / done-for-you paper→live framework, or a niche compliance-SaaS | Medium-high *upside*, low *near-term* | **Excellent** — this is your core craft | Slow (2–4+ months) | Rare, production-grade infra (order FSM, broker reconciliation, live gate) — but it competes with mature *free* frameworks and has **no proven edge** to anchor a price. It's a platform without a product yet. |
| **3** | **apex research → "honest quant" content & consulting** | Low-medium, compounding | Good (writing + audits) | Medium (weeks to audience, longer to real $) | The 10-year "we tested everything and almost nothing survives" corpus is credible, differentiated *content* — but it's audience-first (slow) and the "your alpha isn't real" message is hard to sell to people who came shopping for alpha. |

`quant` (276-LOC "QUANTUM v5.0 enterprise" skeleton) is not a candidate —
archive it.

**Cross-cutting, and honestly your fastest invoice:** productized **consulting**
— "I build and audit backtesting / live-trading infrastructure" — using eureka
and gauntlet as portfolio proof. It isn't a "project," so it isn't ranked, but
it is the quickest path to real cash and it *funds* everything below. Treat it
as the cash engine, not a distraction.

---

## 3. #1 — gauntlet, in depth

### Product thesis (who pays, why, for what)

Every systematic trader, quant educator, and small fund quietly knows their
backtest is probably overfit, and has no credible, standard way to *prove
otherwise* — **gauntlet sells that proof**: a mechanical, tamper-evident
"your strategy survived pre-registered, multiple-testing-deflated,
cost-realistic out-of-sample scrutiny" attestation. People pay for **credibility
they can show someone else** (a subscriber, an allocator, a future self), not
for another backtest engine.

### The MVP to ship in 4–6 weeks

You are not building from zero — gauntlet already has `prereg`, `ledger`,
`stats` (PSR/Deflated-Sharpe), `attestation`, `gate`, and `data_contract` as
importable modules with a CLI and tests. The MVP just *packages and hosts* that:

1. **Week 1 — distribute the core.** Publish `gauntlet-verify` to PyPI (the
   name is already reserved), tag a real release, tighten the README's
   quick-start into a 5-minute "register → verify → gate" demo, add one
   worked example notebook (a deliberately overfit strategy that the gate
   *rejects* — the demo *is* the pitch). Free, Apache-2.0. This is your funnel.
2. **Weeks 2–4 — the hosted attestation report.** A thin web app: user uploads
   an OOS returns series + config (+ trial count / ledger), and gets back a
   **signed, shareable PDF/HTML report** — Deflated Sharpe against the honest
   denominator, PSR, drawdown, a plain-English "this clears / does not clear the
   0.95 bar," and an HMAC-signed attestation record. This is the paid object.
   All the math already exists; you're wrapping it in an upload form + a
   report template + a signature.
3. **Weeks 4–6 — one adapter that removes friction.** Importers for the two
   places returns actually live: a CSV/JSON returns file and a `vectorbt` /
   generic-equity-curve import. Ship a "Verified with gauntlet" badge + a public
   attestation-verify page (paste a signed record → confirm it's authentic).
   The badge is the growth loop.

Explicitly **out of MVP scope:** running backtests, fetching data, broker
integrations. gauntlet's whole credibility is that it *refuses* to do those —
keep it a referee, never a player.

### Monetization

Open-core:

- **Free:** the Apache-2.0 library + CLI (adoption, trust, top of funnel).
- **Prosumer, ~$19–39/mo (or per-report credits):** hosted attestations,
  history of your ledger/registrations, the shareable badge + PDF reports.
  Target: retail systematic traders, aspiring quants, fintwit strategy sellers.
- **Pro/Team, ~$99–299/mo:** private hosted ledger, multiple strategies,
  team/reviewer roles, signed attestation registry. Target: quant newsletters,
  course creators, small CTAs/prop shops who *sell trust* to their own audience.
- **B2B licensing / white-label:** the biggest realistic checks — a quant
  course or signals platform embeds "every strategy we teach/sell ships with a
  gauntlet attestation." One such deal beats 100 individual subs.

**Sales channel:** content-led, where this audience already argues about
overfitting — r/algotrading, quant Discords/Slacks, fintwit, the
López-de-Prado-literate crowd. Lead magnet: a blog post + the "reject an overfit
strategy" demo ("Your backtest is lying to you — here's a 5-minute proof").
Then DM educators/newsletter authors for the white-label conversation.

### Top 3 risks and mitigations

1. **The market is small and *resists the message*.** Most retail traders don't
   want a tool whose main output is "your edge is probably noise."
   → *Mitigation:* sell **credibility, not judgment.** Position it as a badge
   that *sellers of trust* (educators, newsletter authors, signal services) use
   to look rigorous to *their* customers — a marketing asset for them, not a
   killjoy for individuals. Lead with "prove your edge," not "disprove it."
2. **It's a feature, not a company — trivially cloneable** (stdlib, Apache-2.0,
   the math is public Bailey & López de Prado).
   → *Mitigation:* the moat is not the algorithm; it's the **hosted ledger +
   signed attestation registry + being *the* named standard.** Own the verb
   ("gauntlet-verified"), accumulate a public registry of attestations, and make
   the badge socially recognizable. Ship fast enough to be first.
3. **Willingness-to-pay is unproven and could be near zero.**
   → *Mitigation:* validate with **dollars before code.** Before building the
   SaaS, sell a manual **"strategy overfitting audit"** (you run gauntlet on
   their returns/config and deliver the signed report + a written critique) for
   a flat fee to 5–10 people from the communities above. Real invoices in weeks
   tell you whether the hosted product is worth building — and if nobody buys the
   $300 audit, nobody was going to buy the $29/mo app.

---

## 4. #2 — eureka / FABLE5: why not #1, and when it becomes the best bet

**Why it's not #1.** It is your best *engineering* but your weakest *near-term
business*. Three reasons: (a) **no proven edge** — the README itself says "do
not deploy real capital until a survivorship-free, cost-realistic walk-forward
shows positive expectancy," so you cannot sell returns; (b) **it competes with
free** — nautilus_trader, Lean/QuantConnect, vectorbt, and freqtrade are mature,
adopted, and cost nothing, so "another Python trading framework" has no wedge;
(c) **a platform is not a product** — it's ~16.6k LOC of excellent plumbing with
no single buyer or job-to-be-done attached yet. Selling it in 3 months means
selling *hours* (consulting), which is really the cash-engine play, not a
product.

**What would make it #1.** Two paths:

- **You validate a real, cost-realistic edge** (even a modest structural one —
  the VRP put-spread sleeve is the only near-candidate, and it currently
  *fails* its own 0.95 DSR bar on modeled prices). Then the asset isn't the
  code — it's *your own track record*, and the business is a small fund / SMA /
  a paid signal with a gauntlet attestation attached. High bar, slow, but the
  only path with large upside.
- **You find the niche where "audit-grade" is the product, not a nice-to-have.**
  The one genuinely differentiated thing here is the immutable audit trail +
  reconciliation + mechanical live-gate. That's compliance language. A small
  CTA/prop shop or a family office that needs *provable* controls and an
  audit-ready order history might pay for that specifically — a
  "compliance/audit layer for small systematic managers." If you find 2–3 such
  buyers, eureka leapfrogs gauntlet.

## 5. #3 — apex research → "honest quant" content/consulting: why not #1, and when

**Why it's not #1.** It's not software revenue; it's audience-building, which is
slow and non-deterministic. The content is strong and rare (a documented,
pre-registered, 10-year "almost nothing survives" study is more honest than 95%
of quant content), but monetizing an audience takes months of consistent
publishing before it pays, and the core message fights the buyer's motivation:
people search for alpha, not for proof that alpha is scarce.

**When it becomes the best bet.** If you *enjoy* writing and want inbound rather
than outbound sales. A serialized, evidence-driven "honest quant" newsletter or
a course ("How to know if your backtest is lying — and what actually survives")
built from apex's findings would (a) build the exact audience gauntlet sells to,
and (b) generate inbound **consulting/audit** leads that compound. In other
words, #3 is the *distribution layer* for #1 — run as a marketing function, it
raises #1's ceiling rather than competing with it. If your comparative advantage
turns out to be credibility/writing more than shipping SaaS, promote it.

---

## 6. Critical verdict (the part you asked me not to soften)

As standalone, <3-month software businesses, **none of these is a slam-dunk, and
you should not quit anything on the expectation that one becomes a real
venture.** The trading itself is not a business — your own evidence proves it.
gauntlet is a good *tool* but plausibly a small market that resists its own
pitch. eureka is superb engineering with no buyer attached. apex-as-content is
slow.

The realistic, non-delusional plan is a **barbell**: 

- **Cash now:** productized quant-infra + strategy-audit **consulting**, priced
  in real dollars, using eureka + gauntlet as proof. This can invoice within
  2–4 weeks and is the most certain money on this list.
- **Equity/optionality:** **gauntlet open-core**, funded by that consulting, as
  the one asset with a shot at leverage beyond your hours.

**What would need to change for any of these to become a genuine company, not a
side income:**

1. **Distribution, which you currently don't have.** Every path here dies
   without an audience of systematic traders/educators. The cheapest fix is to
   start publishing the apex findings *now* — content is the input to all three.
2. **A validated edge** (would upgrade eureka from "infra" to "fund/track
   record") — high bar, and your own gate says it isn't there yet. Don't wait
   for it; treat it as a lottery ticket you keep buying cheaply via the research
   lab, not as the plan.
3. **Proof that someone pays.** Until 5–10 strangers pay for a gauntlet audit,
   treat "quant SaaS founder" as a hypothesis, not a job. The audit test settles
   it in weeks, for almost no build cost.

If, after 30 days of the barbell, the consulting has clients but the gauntlet
audits get zero takers, the honest read is that the market isn't there — and the
right move is to lean fully into consulting (or a different domain) rather than
polish a product nobody buys. Pre-registering that disconfirmation now is the
same discipline `STRATEGY.md` applied to the strategies; apply it to the
business too.

## 7. Recommended 90-day sequence

- **Weeks 0–2 — cash engine + funnel.** Publish `gauntlet-verify` to PyPI; write
  the "your backtest is lying to you" post with the reject-an-overfit-strategy
  demo; put up a one-page consulting/audit offer; DM 15–20 people in the target
  communities offering a paid strategy-overfitting audit.
- **Weeks 2–6 — validate willingness-to-pay.** Deliver 5–10 paid audits by hand
  (using gauntlet). In parallel, build the hosted attestation-report MVP only if
  the audits sell. Ship the "gauntlet-verified" badge + public verify page.
- **Weeks 6–12 — decide with evidence.** If audits + early SaaS interest are
  real: build the open-core funnel and test prosumer pricing, and open the
  white-label conversation with one educator/newsletter. If not: pivot budget to
  consulting and shelve the SaaS. Either way, keep publishing apex's findings —
  it's the distribution that every option depends on.

**Bottom line:** Rank #1 is **gauntlet**, but the winning *strategy* is
gauntlet-as-open-core **funded by strategy-audit / infra consulting**, with
eureka as portfolio proof and the apex research as the content that markets all
of it. Sell the discipline, not the dream of alpha.
