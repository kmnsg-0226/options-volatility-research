# Pre-OOS memo — V8 Greek-managed listed SPY option strategy

**Written before `allow_oos` was set to `True`. No out-of-sample data appears below.**

Frozen specification SHA-256: `7155b37835e9e421965c305627f19928753fd1f74ad8ef1fb0e6c6e6a26c6841`

---

## 1. What was tested

Six strategy variants against a budget of six, plus one branch closed on its own
evidence before it consumed a variant.

| ID | Variant | Dev net P&L | Blocks positive | Decision |
|---|---|---|---|---|
| V8-01 | naked ATM straddle | **+$45,412** | 2 / 4 | rejected |
| V8-02 | naked + carry filter | +$143,079 | 2 / 4 | rejected |
| V8-03 | 10-delta wings | −$215,135 | 1 / 4 | rejected |
| V8-04 | 10-delta wings + filter | +$130,712 | 2 / 4 | rejected |
| V8-05 | 15-delta wings | −$335,866 | 1 / 4 | rejected |
| V8-06 | 15-delta wings + filter | +$72,016 | 2 / 4 | rejected |
| V8-07 | theta/gamma efficiency rule (§16) | — | — | branch closed |

Section 16's branch was closed on its stated test rather than run: the Spearman
correlation between entry theta-per-dollar-gamma and subsequent net P&L is 0.178
(p = 0.052) for the naked structure and 0.05–0.08 for the winged ones, and the
quartile means are non-monotonic in every case (Q3 is the worst quartile twice).
Section 16 requires a "clear, broad, monotonic relationship"; there is none.

## 2. Selected strategy

**The naked delta-hedged ATM straddle — the section 28 fallback, not a winner.**

No variant clears criterion 3 of the hierarchy, a positive majority of
chronological blocks. Every candidate is positive in exactly 2 of 4. Section 28
provides for this outcome explicitly ("retain the naked strategy or conclude no
listed strategy qualifies; do not force a winner"), and a frozen specification is
needed for the out-of-sample test, so the naked structure is retained: it is the
only variant that is profitable after realistic costs without an added rule, and
it is the simplest.

The honest development verdict is that **no listed variant qualified.**

## 3. Why the wings fail, structurally

This is the finding that makes the phase worth reporting, and it is not
statistical.

Measuring the implied variance actually being traded, against the realised
variance that followed, across 120 development entries:

| | Implied variance | Premium vs realised | t |
|---|---|---|---|
| ATM straddle (what the strategy sells) | 0.02723 | **−0.00423** | −0.62 |
| 10-delta wings (what it buys) | 0.03362 | **+0.00216** | +0.32 |
| Strike-integrated IVAR30 | 0.03617 | +0.00470 | +0.69 |
| Causal HAR forecast | 0.02659 | — | — |
| Subsequent realised | 0.03147 | — | — |

The at-the-money premium is **negative**. The wings carry a positive one. A
winged straddle is therefore short the cheapest part of the surface and long the
richest — exactly inverted relative to where this project has repeatedly located
the premium. Wing implied volatility exceeds ATM implied volatility on 99% of
entries, by 1.95 volatility points on average.

The Greek attribution says the same thing from the other direction. Because the
hedge holds exactly minus the option delta, its P&L cancels the delta term to the
cent, and the strategy reduces to:

| naked, development | |
|---|---|
| Theta collected | **+$4,240,747** |
| Gamma paid | **−$4,097,255** |
| **Theta − gamma** | **+$143,492** |
| Vega | −$307,057 |
| Second-order residual | +$409,688 |
| Financing | −$11,721 |
| Transaction costs | **−$188,989** |
| **Net** | **+$45,412** |

Theta and gamma very nearly cancel over ten years — which is precisely what an
ATM premium of −0.004 with t = −0.62 predicts. What remains is smaller than the
transaction costs.

## 4. What the wings do buy, and what it costs

At matched dollar gamma (the cap binds on 95–97% of entries in every structure,
so all three run at the same −$44M of dollar gamma):

| | naked | 10-delta | 15-delta |
|---|---|---|---|
| Worst trade | −$302,734 | **−$106,305** | −$133,223 |
| Skew | −4.57 | **−0.16** | −0.39 |
| Kurtosis | 37.9 | **2.8** | 3.9 |
| Theta retained | 100% | 90.4% | 90.4% |
| Contracts per trade | 184 | 656 | 889 |
| Costs (development) | $188,989 | $444,853 | $612,817 |

The wings do what wings are supposed to do: the worst trade improves 65% and the
distribution stops being pathological. In the COVID entry the naked structure
loses $302,734 and the 10-delta structure only $36,323 — gamma P&L falls from
−$377,690 to −$90,154.

They cost $255,864 more in transaction costs over the same 120 trades, because
matching the same gamma with four legs instead of two requires 3.6× the
contracts. The COVID saving is $266,411; the cumulative extra cost plus the lost
edge everywhere else is larger. **Wings are not too weak here — they are correctly
priced insurance sold through an expensive channel, bought on the wrong side of
the surface.**

## 5. Risk controls behaved as designed

- **Delta**: residual delta after hedging is exactly 0 shares on every
  non-closing day across all 2,085 option-days.
- **Gamma cap**: binds on 96.7% of naked entries. It is therefore the operative
  sizing rule, not the vega target — realised vega averages $5,400 against a
  $10,000 target.
- **A caveat that matters**: the cap is applied at entry only, and dollar gamma
  grows as expiry approaches. Entry gamma averages −$44M, but the largest
  intra-trade reading is −$126M for the naked structure. The DTE ≤ 7 exit is the
  only control on this drift, and it is not a tight one.
- **Stale quotes**: 8 of 2,085 option-days needed a carried-forward implied
  volatility, all on extreme days when an end-of-day quote sat below intrinsic.

## 6. Explicit expectations for OOS

1. **Near zero, most likely slightly negative.** Development net is +$45,412 over
   ten years, a Sharpe of 0.035 and a Newey–West t of 0.12 — indistinguishable
   from zero. Over 32 OOS trades I expect a result within roughly ±$150,000 and
   would not read either sign as evidence.

2. **Costs should again exceed the edge.** Costs were 77% of gross P&L in
   development. Nothing about the OOS window makes execution cheaper.

3. **Financing should be a larger drag.** Development financing was −$11,721
   across a decade largely at the zero bound; the OOS window sits at 4–5% policy
   rates.

4. **One bad month can define the period.** The worst development trade is
   −$302,734 against a ten-year total of +$45,412.

5. **The pre-registered 10-delta comparator should lose more than the naked
   structure**, unless the window contains a COVID-scale event. This is the
   falsifiable claim: if the winged structure wins out of sample in calm months
   too, my structural diagnosis about which side of the surface carries the
   premium is wrong.

6. **April 2025 is the interesting test.** V7 established it was a round trip —
   large path volatility, flat terminal price. Long wings pay on terminal
   distance from the strike, so I expect them to provide little protection there,
   in contrast to COVID where the terminal move was −20%. If the wings do protect
   April 2025, my reading of that event is wrong.
