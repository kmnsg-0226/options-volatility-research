# Pre-OOS memo — V6 canonical risk and timing

**Written before `allow_oos` was set to `True`. No out-of-sample data appears below.**

Frozen specification SHA-256: `3c7299467e18392968ed7b20775da99a7caa014c487b6d38d5ba1103283df1e0`

---

## 1. What was tested

**12 strategy specifications**, against a budget of 25. Zero combined candidates were
built, because section 20 admits combinations only from branch survivors and every
branch closed. Branch B produced no strategy variants at all: the choice of expected-
realised-variance estimator was made on forecast loss (QLIKE), never on P&L, so it
consumed no variant budget.

| Branch | Question | Variants | Outcome |
|---|---|---|---|
| A | implied-variance risk targeting | 2 | **CLOSED** |
| B | causal expected realised variance | 0 | informative, not a strategy |
| C | expected-VRP participation | 3 | **CLOSED** |
| D | term structure | 1 | **CLOSED** |
| E | surface tail state | 4 | **CLOSED** |
| F | carry-to-tail-risk | 2 | **CLOSED** |

Every adaptive rule was run beside a mandatory flat control holding constant exposure
at the rule's own average, so that "held less" could never be mistaken for "timed well".

## 2. The canonical baseline reproduced exactly

The V6 engine reproduces V5 to the last cent on every trade: theoretical variance-swap
P&L +$639,144, replicated gross +$536,727, financing −$17,481, costs $138,578, net
+$380,668, tracking correlation 0.9993, RMSE $3,736, maximum cash reconciliation error
1.16 × 10⁻⁹. Maximum per-trade difference against the stored V5 ledger is exactly zero
across all five cash quantities.

## 3. Selected final rule

**The canonical unconditional baseline — section 25 option B.** Constant $1M variance
notional, no signal, no participation rule, no scaling normalisation.

### Economic rationale

Not "nothing worked, so give up". Three specific findings force it.

**The variance premium is compensation for exactly the risk that risk-targeting
removes.** Sorting development trades by entry fair strike, mean P&L rises monotonically
across quartiles ($76 → $3,432 → $3,697 → $5,083) while dispersion rises nine-fold
($15,850 → $143,938). Reducing exposure when variance is high de-weights the only
quartile that pays. Inverse-variance scaling cuts top-quartile mean P&L roughly in half.
This is why every branch-A bound tested returns a *negative* edge against its flat
control — the effect is robust, and robustly the wrong direction for return.

**Expected VRP is widest immediately before the loss.** On 2020-03-02 the fair strike
stood at the 95th development percentile (K = 0.1002) while the causal HAR forecast sat
near 0.03, so measured expected premium was at its most attractive of the decade. C3,
F1 and F2 all held their 1.50 cap into that entry and took the worst trade from
−$732,061 to −$1,098,090. Against 2,000 random draws of the same number of months, C3
lands at the **0th percentile** — materially worse than choosing months at random. The
carry signal is not weak; it is inverted at the moment it matters.

**Branch B explains why.** Implied variance beats both HAR and EWMA at forecasting
subsequent realised variance (QLIKE 0.380 vs 0.441 and 0.570; out-of-sample R² 0.118 vs
0.101 and −0.163). Because implied variance *is* the fair strike, any expected VRP
computed against a weaker forecast is mostly that forecast's error. Branches C and F
were sizing on noise, and the noise happened to peak before the crash.

## 4. Development results for the selected rule

120 trades, 2013-01-01 to 2022-12-31.

| | |
|---|---|
| Net P&L | **+$368,604** |
| Return on average notional | 36.9% over ten years |
| Sharpe (annualised, 12 trades/yr) | **0.146** |
| Newey–West t (3 lags) | 0.508 |
| Max drawdown | $813,014 (0.813 × notional) |
| Worst trade | **−$732,061** (2020-03-02) |
| ES95 | −$171,332 |
| Skew / excess kurtosis | −8.72 / 89.3 |
| Win rate | 74.2% |
| Costs / financing | $117,783 / −$789 |
| **Stitched walk-forward Sharpe (2017–2022, 72 trades)** | **0.051** |
| Walk-forward net P&L | +$97,864 |

Carry retained is 100% by construction — no exposure was given up.

Concentration is the defining feature: the worst single trade is −$732,061 against a
ten-year total of +$368,604. Excluding it, development net is +$1,100,665. The bottom
five trades account for 82% of all losses; 2021 alone contributes 84% of the total.

## 5. Flat-deleveraging comparison

This is the control that closed the study. For every adaptive rule, the flat control at
the same average exposure earns a Sharpe of 0.146 — unchanged from the baseline, as a
constant rescale should. The adaptive rules post development Sharpes up to 0.386. But
removing the two Feb–Mar 2020 entries:

| Rule | Sharpe edge over flat, full development | Sharpe edge, crisis removed |
|---|---|---|
| A1 inverse variance | +0.181 | **−0.394** |
| A2 inverse vol | +0.091 | **−0.114** |
| D term structure | +0.183 | **−0.001** |
| E2 deep downside | +0.240 | **−0.096** |
| E3 skew wedge | +0.193 | **−0.091** |

Not one rule retains a positive edge. Two trades out of 120 carry the entire result.

The honest counter-argument is that deleting the two loss events deletes precisely what
a risk rule exists for. It has weight, and one piece of evidence supports it: the
dispersion normalisation is real outside the crisis too — the quartile SD ratio falls
from 2.59 to 1.31 (A2) and 1.11 (E2) with the crisis removed. Risk scaling genuinely
transforms the payoff distribution. What it does not do is improve risk-adjusted carry
on any evidence broader than a single episode, and it costs 50–70% of top-quartile
premium to achieve. A risk transformation with a known price is not the same thing as
an edge, and n = 1 crisis cannot support selecting one.

## 6. Parameter stability

Classified on immediate economic neighbours per section 19.

| Variant | Classification | Why |
|---|---|---|
| A1 inverse variance | ROBUST PLATEAU | flat and same-signed — but the stable quantity is a **negative** return edge of −0.15 to −0.20 at every bound |
| A2 inverse vol | WEAKLY IDENTIFIED | monotone; optimum outside the tested range |
| D term structure | WEAKLY IDENTIFIED | edge climbs monotonically in sensitivity to the grid boundary |
| E1 / E3 / E4 | WEAKLY IDENTIFIED | same monotone pattern |
| E2 deep downside | WEAKLY IDENTIFIED | same-signed but varies by more than half its mean |

Section 19 permits only a ROBUST PLATEAU into the final model. The single rule that
qualifies robustly identifies a persistent give-up of carry, so admitting it would mean
knowingly selecting a rule whose stable property is losing money.

## 7. Multiple-testing assessment

Across the 12 specifications, the expected maximum Sharpe under the null is **0.263**
annualised. The best observed is E2 at 0.386, then E3 0.339, D 0.329, A1 0.327 — all
within one lucky draw of what 12 attempts produce from noise. Deflated Sharpe
probabilities are 0.61, 0.57, 0.56 and 0.56 respectively, against the 0.95 that would be
required. Bootstrap 95% intervals for mean trade P&L (2,000 resamples) contain zero for
every specification including the baseline. Newey–West t never exceeds 1.23.

No specification in this study is statistically distinguishable from luck.

## 8. Data-quality caveat carried forward

Branch E's tail-state measures are contaminated by strip geometry. `deep_down_share`
correlates −0.885 with how far the put wing extends and +0.61 with the number of strikes
in the strip. The wing widens when deep puts hold a non-zero bid, which happens when
volatility is high — so part of what E2 measures is OptionMetrics quote coverage rather
than a market state. `E4` had to be redefined mid-study for the same reason: on a 5%
moneyness split its denominator collapsed on quiet days and the ratio reached 1.1 × 10⁸,
measuring strip width rather than skew. It was moved to a 2% split, where both legs are
populated on all 152 dates.

## 9. Explicit expectations for OOS

Stated in advance, and the frozen specification is hashed above.

1. **The baseline should be weakly positive at best.** Development Sharpe is 0.146 with
   t = 0.51 and a bootstrap interval spanning zero. Over 32 OOS trades the standard error
   on mean trade P&L is roughly $13,000 against a development mean of $3,072, so the
   period cannot resolve the premium either way. I expect a small positive net P&L with
   no statistical significance, and I would not treat a negative outcome as a refutation.

2. **A single bad month can erase the period.** The development record says one entry can
   cost more than twenty months of accumulated carry. If the OOS window contains a
   comparable variance shock, expect the period total to be negative.

3. **The three pre-registered diagnostic rules — A1, D, E2 — should show an edge over a
   same-average-exposure control of approximately zero, except in any month containing a
   comparable variance shock.** This is the falsifiable claim. If their OOS edge is
   materially positive in calm months as well, my single-crisis diagnosis is wrong and
   the branches were closed in error. These rules are frozen as diagnostics, not as
   candidates: the selection is already fixed as the baseline and section 30 forbids a
   V6.1 regardless of what the OOS shows.

4. **Costs and financing should matter more than in development.** Development financing
   was −$789 on a period that was mostly at the zero bound; the OOS window sits at 4–5%
   policy rates, so the financing drag on the same strategy should be materially larger.
