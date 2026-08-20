# V6 — Can ex-ante risk scaling and selective participation make SPY variance carry investable?

Frozen specification SHA-256: `3c7299467e18392968ed7b20775da99a7caa014c487b6d38d5ba1103283df1e0`
OOS unlocked once, after the hash and the pre-OOS memo existed. Nothing was changed afterwards.

---

## Scope and discipline

Twelve strategy specifications against a budget of 25. Zero combined candidates, because
section 20 admits combinations only from branch survivors and every branch closed. Every
adaptive rule ran beside a mandatory flat control at the rule's own average exposure, so
"held less" could never be mistaken for "timed well". The V5 engine was frozen: the
identity hedge, full CBOE strip, `dK/K²` weighting, ~30D maturity, first-trading-day
entry, expiry settlement, self-financing cash account and cost model are untouched, and
the V6 baseline reproduces the V5 ledger with a maximum per-trade difference of exactly
zero on all five cash quantities.

---

## Answers

**A. Can unconditional SPY variance carry be materially improved by ex-ante risk scaling?**

No. Risk scaling reliably changes the *shape* of the payoff and reliably costs return.
Inverse-variance scaling compresses the P&L dispersion ratio across entry-variance
quartiles from 10.2 to 2.4, and the compression survives removing the crisis (2.59 → 1.31
for the square-root version). But the return edge over a same-average-exposure control is
negative at every bound tested, in three of four development blocks, and for every rule
once Feb–Mar 2020 is removed. Branch A is the only ROBUST PLATEAU in the study, and what
it robustly identifies is a persistent give-up of carry of −0.15 to −0.20 of average
notional.

**B. Does implied variance contain useful information for position size, beyond simple
deleveraging?**

No. Once the flat control is imposed, the level of implied variance adds nothing that
holding a smaller constant position does not already provide — and it subtracts, because
the premium is concentrated in exactly the states it de-weights.

**C. Can causal expected realised variance forecast the sign or magnitude of the
subsequent variance-swap payoff?**

Not usefully, and the reason is structural. Implied variance is the best available
forecast of subsequent realised variance (QLIKE 0.380 vs HAR 0.441 and EWMA 0.570;
out-of-sample R² 0.118 vs 0.101 and −0.163). Since implied variance *is* the fair strike,
expected VRP measured against any weaker forecast is dominated by that forecast's error.
The market's own quote is the sharpest forecast on offer, which leaves no residual for a
sizing signal to exploit.

**D. Is expected VRP useful for abstaining from unattractive trades?**

No — it is worse than useless. Against 2,000 random draws of the same number of months,
C3 lands at the **0th percentile**: the rule selects months materially worse than chance.
The mechanism is visible at both catastrophes. On 2020-03-02 the fair strike stood at the
95th development percentile while the causal HAR forecast sat near 0.03, so measured
expected premium was the most attractive of the decade; C3, F1 and F2 all held their 1.50
cap into that entry and took the worst trade from −$732,061 to −$1,098,090.

**E. Does term-structure inversion identify dangerous short-variance states?**

It identifies them and cannot be shown to pay for it. Branch D produced the highest
development net P&L of any rule (+$528,699) and an edge over its flat control of exactly
**−0.001 Sharpe** once Feb–Mar 2020 is removed. The entire result is one episode. The
parameter is WEAKLY IDENTIFIED: the edge rises monotonically in the sensitivity, so the
apparent optimum sits outside the tested range.

The signal was genuinely informative in April 2025 — the ~20D/~45D ratio was at the
**92.5th development percentile** entering the worst OOS month. Informative is not the
same as profitable: acting on it across the whole sample still did not pay.

**F. Do option-surface tail measures add information beyond variance level?**

No, and part of what they measure is not a market state at all. `deep_down_share`
correlates −0.885 with how far the put wing extends and +0.61 with the number of strikes
in the strip. The wing widens when deep puts hold a non-zero bid, which happens when
volatility is high — so the signal partly measures OptionMetrics quote coverage. `E4`
had to be redefined mid-study for the same reason: on a 5% moneyness split its
denominator collapsed on quiet days and the ratio reached 1.1 × 10⁸, measuring strip
width rather than skew.

**G. Does a carry-to-tail-risk ratio improve allocation?**

No. Both ratios inherit branch C's inversion and amplify it. Randomisation percentiles of
0.49 and 0.47 are indistinguishable from noise.

**H. Which branches failed, and why?**

All six. A: robust return cost, no return edge. B: no strategy variant — the best forecast
is the strike itself. C: signal inverted at the moment it matters. D and E: single-episode
dependence, no robust plateau. F: C's defect, levered.

**I. How many total strategy variants were tested?**

Twelve, plus the unsearched baseline. Branch B consumed no budget because the forecast
estimator was chosen on QLIKE, never on P&L. Parameter scans are sensitivity diagnostics
of already-counted variants, used to reject rather than to pick a grid maximum.

**J. Is the final parameterisation a robust plateau or an isolated optimum?**

Neither applies: the selected strategy has no free parameter. Of the twelve tested, one
(A1) is a ROBUST PLATEAU — of a negative edge — and the rest are WEAKLY IDENTIFIED.
Section 19 admits only a robust plateau into the final model, and the sole qualifier
robustly identifies losing money.

**K. How much unconditional carry is retained?**

100%. No exposure was given up, because no signal earned the right to move it.

**L. How much are max DD, ES95 and worst trade reduced?**

For the selected strategy, not at all — that is the cost of the verdict. The rejected
rules did reduce them: A1 takes the development worst trade from −$732,061 to −$183,023
and max drawdown from 0.813 to 0.297 of notional. The reduction is real and mechanical.
It is also not free, and not selectable on this evidence.

**M. How much of that improvement survives a same-average-exposure control?**

Almost none in development. Sharpe edge over flat, before and after removing Feb–Mar 2020:
A1 +0.181 → **−0.394**; A2 +0.091 → −0.114; D +0.183 → **−0.001**; E2 +0.240 → −0.096;
E3 +0.193 → −0.091. Two trades out of 120 carry the entire result.

**N. What is the stitched pre-2023 walk-forward Sharpe?**

**0.051** for the selected strategy over 2017–2022 (72 trades, +$97,864), calibrating
through year Y−1 and trading year Y with a causal flat control.

**O. What happens in OOS 2023–2025?**

32 trades, one run, exactly as frozen.

| | |
|---|---|
| Gross P&L | +$49,551 |
| Financing | −$16,692 |
| Costs | $20,795 |
| **Net P&L** | **+$12,064** |
| Annualised return on notional | 0.47% |
| Sharpe | 0.032 |
| Newey–West t | 0.050 |
| Max drawdown | 0.263 × notional |
| Worst trade | −$209,153 |
| ES95 | −$131,506 |
| Skew / kurtosis | −4.69 / 24.1 |
| Win rate | 78.1% |
| Mean exposure / carry retained | 1.00 / 100% |

Both of the memo's headline predictions held. The strategy is weakly positive and
statistically empty; and financing rose from −$789 across a decade at the zero bound to
−$16,692 across 32 months at 4–5% policy rates, more than the entire net result.

Comparators A and B collapse into the strategy: the frozen rule *is* the canonical
baseline and its mean exposure is exactly 1.00, so both comparators are identical to it by
construction. They are reported for completeness and carry no information.

**P. What happens specifically in April 2025?**

It repeats March 2020 in miniature and destroys the period.

| | |
|---|---|
| Fair variance strike | 0.0453 — 77.5th development percentile, 1.87× the expanding median |
| Term structure ~20D/~45D | 1.153 — **92.5th percentile** |
| Deep-downside share | 0.197 — 76.7th percentile |
| Expected VRP (K − HAR) | +0.0165 — **80.8th percentile** |
| Selected exposure | 1.00 |
| Realised variance | **0.2550 — 5.63× the strike** |
| Theoretical VS loss | −$209,691 |
| Replicated V6 loss | −$209,153 (tracking error $538) |

The other 31 OOS trades made +$221,217 between them. One month removed 95% of it.

**Did the V6 rule have any ex-ante reason to reduce this exposure?** The frozen rule had
none — it holds constant exposure by construction, so the answer for the selected strategy
is **no**. But the information was on the screen: the term structure was at its 92.5th
percentile of inversion, the strike at 1.87× its median, the tail share at the 77th
percentile. Every risk signal was elevated — and the carry signal was elevated too, at the
80.8th percentile, pointing the opposite way. That contradiction is this project's whole
finding in a single month.

**Q. Does the OOS improvement, if any, arise from genuine state-dependent sizing rather
than lower average exposure?**

There is no improvement to attribute, because no adaptive rule was selected. The
pre-registered diagnostics — frozen in the hashed specification before the unlock, and not
candidates — give a partial answer, and it went partly against my written prediction. I
predicted their OOS edge over a same-average-exposure control would be roughly zero except
in a shock month. Outcome:

| Rule | OOS edge (Sharpe) | Edge excluding Mar–Apr 2025 | April 2025 scale | April 2025 loss |
|---|---|---|---|---|
| A1 inverse variance | +0.276 | **+0.123** | 0.535 | −$111,923 |
| D term structure | +0.123 | −0.039 | 0.697 | −$145,848 |
| E2 deep downside | +0.005 | +0.274 | 0.830 | −$173,556 |

D behaved as predicted. A1 kept a positive edge outside the shock, and E2's edge was
entirely outside it — both inconsistent with a pure shock story. I record that my
prediction was not fully borne out. It does not change the verdict, for two reasons.
Thirty-two trades cannot establish an edge that 120 development trades failed to
establish: the standard error on an OOS Sharpe over 32 monthly trades is roughly 0.6, so
+0.28 is well inside noise, and the three rules disagree with each other about where their
edge comes from. And section 30 forbids revisiting the specification regardless. A1's
+$63,964 over 2.7 years on ~$938k average notional is ~2.5% annualised on a position that
lost $112k in a single month — better than the baseline, still not investable.

**R. After realistic costs and financing, is there evidence of an investable variance-carry
strategy?**

No. The premium is real — that was V5's finding and it survives here, with development net
+$368,604 and OOS +$12,064, both positive. But it is not harvestable at this frequency and
structure. Ten years of development produced a Sharpe of 0.146 with t = 0.51; 2.7 years
out of sample produced 0.032 with t = 0.05. Costs of $117,783 and $20,795 and financing of
−$789 and −$16,692 consume most of what is earned. A single month has now twice erased the
majority of accumulated carry — 2/3 of the development total, 95% of the OOS total. No
sizing or timing rule tested repairs this, and the one class that reliably changes the
distribution does so by discarding the premium along with the risk.

---

## Section 31 diagnostic — the cost of explicit catastrophe insurance

Not a strategy and not an improvement claim. Two conventional structures, priced against
the same schedule with a sizing convention fixed in advance (puts on the spot-equivalent
of the variance notional), no optimisation.

| 2013–2025 | Net P&L | Worst trade | Premium paid | Payoff received |
|---|---|---|---|---|
| Unhedged | +$380,668 | −$732,061 | — | — |
| Long 0.90 put | +$123,995 | −$647,965 | $383,791 | $127,119 |
| 0.90/0.80 put spread | +$249,160 | −$645,527 | $258,627 | $127,119 |

The insurance costs 67% of lifetime net P&L and improves the worst trade by 11.5%. The
reason is instructive and general: **variance is a path functional and a put pays on the
terminal level.** March 2020 produced enormous realised variance along a path that had
substantially recovered by the contract's expiry, so the put barely paid while the
variance swap lost everything. Options on the terminal price are a structurally poor
hedge for short-variance risk.

---

## What this phase is worth as research

The negative result is the contribution, and it is specific rather than vague. Three
findings are reusable outside this project:

1. **The variance premium is compensation for exactly the risk that risk-targeting
   removes.** Mean P&L rises monotonically across entry-variance quartiles while dispersion
   rises nine-fold. This is why vol-targeting a short-variance book reduces return roughly
   in proportion to the risk it removes, and it predicts the same outcome for any strategy
   whose premium is concentrated in its high-volatility states.

2. **Carry signals built on a forecast that is worse than the market's own quote are
   inverted at the moment they matter.** Because implied variance beats HAR and EWMA,
   expected VRP is mostly HAR's error — and that error is largest precisely when implied
   variance spikes ahead of a shock. A rule that sizes on it will lever into the crash. The
   0th-percentile randomisation result is the clean statement of this.

3. **Terminal-payoff options do not hedge path functionals.** Worth remembering before
   anyone proposes put protection for a short-variance book.

The methodological record is also the point: 12 specifications against a 25 budget, every
rule paired with a same-average-exposure control, a hashed pre-OOS specification with
written falsifiable predictions, one OOS run, and a prediction that partly failed reported
as such rather than quietly dropped.

---

# RESULT C — ex-ante scaling/timing does not make unconditional variance carry investable

The premium exists and is positive in both windows. Risk scaling genuinely stabilises the
payoff distribution, and out of sample the pre-registered A1 diagnostic did cut the April
2025 loss by 46%. But no rule tested improves risk-adjusted carry on evidence broader than
a single crisis, none survives a same-average-exposure control, none is statistically
distinguishable from the best of twelve lucky draws, and the strategy remains one month
away from losing a decade of accumulated premium. The disciplined outcome was to freeze
the unconditional baseline rather than manufacture an adaptive rule from one crash, and
the out-of-sample window did not overturn that judgement.
