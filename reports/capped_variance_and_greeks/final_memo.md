# V7 — Capped variance pricing and Greek P&L attribution

Two questions, neither of them about alpha: can the catastrophic variance tail be
**priced** rather than heuristically hedged, and can realised option P&L be
**explained** through Black–Scholes Greeks. No signals were searched, no V6
branch reopened, nothing optimised for Sharpe.

---

## PART I — CAPPED VARIANCE

### A. Can Heston reproduce the observed SPY surface adequately?

Adequately, with a known and visible weakness. All 152 calibrations converged;
none was flagged unstable. Median implied-volatility RMSE is **0.92 vol points**
(p95 2.07, max 2.41), median price RMSE $0.105. The fit is worst exactly where a
tail model most needs to be right:

| Moneyness bucket | IV RMSE | | Maturity bucket | IV RMSE |
|---|---|---|---|---|
| deep put (< 0.90) | **0.0144** | | 7–14 DTE | **0.0133** |
| OTM put | 0.0077 | | 15–30 DTE | 0.0084 |
| at the money | 0.0068 | | 31–45 DTE | 0.0049 |
| OTM call | 0.0053 | | 46–60 DTE | 0.0051 |
| deep call | 0.0070 | | | |

The downside wing and the shortest maturities fit least well. That is the
textbook Heston limitation — a diffusion cannot generate enough short-dated skew
without jumps — and it lands directly on the part of the distribution that prices
the cap.

### B. Are the parameters economically stable enough for tail pricing?

**No, not in the textbook sense**, and this is the most serious qualification in
Part I.

- The **Feller condition is violated on all 152 dates** (median 2κθ/ξ² = 0.258).
  The QE scheme keeps variance non-negative so nothing breaks numerically, but the
  fitted process is one that regularly visits zero variance.
- **κ sits on its upper bound of 20 on 96 of 152 dates.** With no options beyond
  60 DTE, mean reversion and long-run variance are weakly identified: θ correlates
  **+0.887** with the current variance level, so it is tracking the spot level
  rather than anchoring a long-run mean.
- Month on month, ξ moves a median **17.4%** and κ has a 95th-percentile relative
  jump of 104%.

The defensible reading: what the surface pins down is the **distribution of
30-day realised variance**, not a unique parameter vector. Since the 7–60 DTE
universe brackets the ~30-day contract, that distribution is the identified
object, and it is the only thing the capped price depends on. But parameter
instability is not cosmetic here — see J.

### C. Does the Monte Carlo engine recover benchmark prices?

Yes; it passed the gate before pricing any tail. Across ten dates spanning
regimes, at 200,000 paths: vanilla prices match the semi-analytic Lewis integral
to a maximum |z| of **4.25** (largest absolute error $0.06 on a ~$100 forward),
the forward is reproduced to **2.1 × 10⁻⁴**, and simulated daily-monitored
realised variance matches the closed-form integrated variance. Two conventions
were measured rather than assumed:

- daily vs continuous monitoring: median **+0.04%**
- calibrated model vs market model-free strike: median **−0.12%**

The second is the meaningful one. The model reproduces the market's own variance
strike to about a tenth of a percent, so the calibration is not distorting the
variance level it is asked to cap.

### D. What is the fair cost of capping realised variance at 2.5× the fair strike?

**A concession of 22.0% of the fair strike in development and 19.2% out of
sample** — the risk-neutral value of the tail being given away, computed as
`K_var − E^Q[(RV − C)⁺]` with `K_var` taken model-free from the listed strip so
the model prices only the tail. In dollars: **$766,834** of carry surrendered
across 120 development trades and **$168,133** across 32 OOS trades.

The cap bound on 7 of 152 trades. The model expected it to bind on 9.4% of
trades against an actual 4.6% — consistent with a positive variance risk premium,
since the risk-neutral measure prices variance above its realised average.

### E. How different is this from the naive "same strike, capped payoff" arithmetic?

**Enough to reverse the interpretation.** Keeping the uncapped strike while
capping the loss gives +$1,315,563 in development against +$564,513 uncapped — an
apparent free doubling. The fairly priced contract gives **+$548,729**. The
entire $766,834 difference is the strike concession that the naive calculation
forgets to pay. Any analysis that caps losses without repricing the strike is
describing a contract nobody would write.

### F. Does the cap materially reduce catastrophic tail risk?

Yes, and — importantly — this part is almost model-free. The cap level is
`2.5 × K_var` with `K_var` observable, and realised variance is observable, so
the *shape* of the capped payoff involves no model. Only its level shifts by the
concession.

| 2.5× cap | Development | | OOS | |
|---|---|---|---|---|
| | uncapped | capped | uncapped | capped |
| Worst trade | −$748,599 | **−$172,598** | −$209,691 | **−$76,400** |
| Max drawdown / notional | 0.830 | **0.227** | 0.270 | **0.141** |
| ES95 | −$175,890 | **−$59,714** | −$134,733 | **−$70,689** |
| Skew | −8.53 | **−0.80** | −4.52 | −2.70 |
| Sharpe | 0.217 | **0.561** | 0.193 | **0.249** |

Worst trade down **76.9% in development** and **63.6% out of sample**; drawdown
down 72.7% and 47.5%; and development skew moves from −8.5, which is barely a
distribution, to −0.8.

### G. How much normal-period carry is surrendered?

Strikingly little. **97.2% of development net payoff is retained** (+$548,729 vs
+$564,513) and **64.7% out of sample** (+$48,253 vs +$74,632); 93.4% over the full
sample. The reason is arithmetic, not luck: over 2013–2025 the model charged
$934,967 for the tail and the tail actually cost $892,805 — a **loss ratio of
0.955**. Priced insurance that pays out roughly what it charges leaves the mean
almost unchanged while removing the variance.

By cap level the loss ratio was 0.84 (2.0×), 0.96 (2.5×) and 1.05 (3.0×) — tight
caps were slightly rich, wide caps slightly cheap. **With only 7–8 binding events
these ratios carry enormous sampling error** and should not be read as evidence
that Heston prices variance tails correctly in general.

### H. Does the capped product improve return-on-capital economics?

Substantially, on the drawdown proxy. **This is a historical peak-drawdown
capital proxy, not a margin requirement. Broker or clearing margin is not
modelled**; a real desk would post SPAN-style initial margin that is larger,
path-dependent and revised daily.

| Window | Structure | Capital | Return p.a. | vs cash |
|---|---|---|---|---|
| Development | uncapped | $830,373 | 6.86% | +6.22% |
| Development | **2.5× capped** | **$227,134** | **24.38%** | **+23.74%** |
| OOS | uncapped | $269,466 | 10.75% | +6.13% |
| OOS | **2.5× capped** | **$141,377** | **13.25%** | **+8.63%** |
| Full sample | uncapped | $830,373 | 6.12% | +4.64% |
| Full sample | 2.5× capped | $227,134 | 20.90% | +19.42% |

Stated per window, because the payoff-to-capital relationship is much weaker out
of sample and a blended figure hides that:

| | Payoff retained | Drawdown capital used |
|---|---|---|
| Development 2013–2022 | 97.2% | 27.4% |
| OOS 2023–2025 | **64.7%** | **52.5%** |
| Full sample | 93.4% | 27.4% |

The full-sample capital ratio equals the development one only because the peak
drawdown of both structures falls inside the development window; it is not a
stable property. The development pairing — 97% of the payoff on 27% of the
capital — is the strong version of this result, and it does not repeat out of
sample, where the cap keeps 65% of the payoff while still needing 53% of the
capital.

### I. Does the improvement survive OOS?

Yes, in the same direction and smaller in size. Out of sample the cap cost
$168,133 and returned $141,755, a net insurance cost of $26,378 — the seller paid
slightly more than the tail was worth, which is what buying insurance normally
looks like. Against that, the worst trade fell 64% and drawdown 48%, and return
on drawdown capital rose from 10.75% to 13.25% (from 13.81% to 24.52% on a
worst-trade capital basis). April 2025 alone: the uncapped swap lost $209,691;
the 2.5× cap bound and limited the loss to $76,400.

### J. How sensitive is the capped strike to model risk?

**This is the binding constraint on Part I.** Parameters were perturbed by fixed
amounts and never re-optimised.

| Perturbation | Tail value change | Development net | OOS net |
|---|---|---|---|
| baseline | — | +$550,427 | +$47,941 |
| **ξ +20%** | **+31.6%** | +$308,607 | **−$4,757** |
| **ξ −20%** | **−32.4%** | +$798,327 | +$102,591 |
| θ ±20% | ∓14% | $438k / $655k | $24k / $70k |
| κ ±20% | ∓9% | $615k / $479k | $63k / $30k |
| v₀ ±10% | ∓7.5% | $491k / $608k | $35k / $60k |
| ρ ±0.05 | ∓1.2% | $559k / $541k | $50k / $46k |

Vol-of-vol dominates everything else. A 20% error in ξ moves development P&L by
±45% and is enough to turn the OOS result negative — and ξ itself moves 17.4%
month-on-month in the fits. Correlation ρ, by contrast, barely matters.

Two benchmark models make the point sharper:

- **Constant variance (Black–Scholes)**: tail value falls **99.99%** to
  essentially zero. Under constant volatility, realised variance simply cannot
  reach 2.5× its mean, so the cap would appear free.
- **IID bootstrap of historical daily returns**: tail value falls **75%**.

So it is not fat tails in daily returns that make the cap expensive — an IID
bootstrap of the actual historical returns still underprices it fourfold. It is
**volatility clustering**. Any model without stochastic volatility will conclude
the cap is nearly free and produce a spectacular, false result (the BS benchmark
"earns" +$1,315,468 in development, matching the naive arithmetic almost exactly).

Note what model risk does *not* touch: the worst trade, drawdown, ES95 and skew
are set by the cap level and realised variance, both observable. Model error
moves the price of the protection, not the protection.

---

## PART II — GREEK ATTRIBUTION

### K. What share of daily option P&L do Delta/Gamma/Theta/Vega explain?

Across **3,078 non-expiry option-days**: correlation **0.9951**, explained
variance **0.9902**, MAE $862 against a mean absolute daily P&L of about $40,000.
It holds up where it matters — 0.9912 on high-implied-volatility days, 0.9933 on
days with spot moves above 2%, 0.9920 through the COVID trade and 0.9931 through
April 2025.

It is weakest on quiet days: explained variance 0.798 when |return| < 0.5%, where
the actual P&L is small and quote noise dominates.

### L. Which Greek dominates ordinary carry periods?

**Theta, and it is the only source of profit.** Cumulatively across all 152
trades, the short strip's option leg earned **+$1,064,660**, decomposed as:

| | Cumulative | Share of gross Greek flow |
|---|---|---|
| Theta | **+$7,350,242** | 47.6% |
| Gamma | **−$5,071,501** | 32.9% |
| Vega | −$2,235,737 | 14.5% |
| Delta | +$777,002 | 5.0% (removed by the hedge) |
| Residual | +$244,654 | — |

Theta collects, gamma pays back 69% of it, vega another 30%. The textbook line
"theta is the profit" is literally true here, but only after gamma and vega have
taken four fifths of it away.

### M. Which Greek dominates COVID and April 2025?

**Gamma, in both — but the two episodes are structurally different, and that is
the most interesting finding in Part II.**

| | COVID (entry 2020-03-02) | April 2025 (entry 2025-04-01) |
|---|---|---|
| SPY entry → expiry | 309.09 → 246.15 (**−20.4%**) | 560.97 → 566.76 (**+1.0%**) |
| Realised / implied variance | 8.47× | 5.63× |
| Gamma | −$838,722 | −$273,146 |
| Theta | +$491,464 | +$128,749 |
| Vega | −$148,222 | −$66,329 |
| **Option leg (engine)** | **−$452,681** | **+$44,628** |
| **Dynamic hedge (engine)** | **−$279,087** | **−$257,017** |
| Net | −$732,061 | −$209,153 |

COVID was a large terminal move: the static strip itself lost, and the hedge lost
alongside it. **April 2025 was a round trip.** SPY fell 12% and recovered fully
by expiry, so the static option strip finished *profitable* at +$44,628 — and the
entire $209,153 loss sat in the dynamic hedge, the leg that converts the static
log contract into realised variance.

That is the cleanest available demonstration of why variance is a path
functional. It also closes the loop on V6's tail-hedge diagnostic, which found
that long puts cost 67% of lifetime P&L while improving the worst trade only
11.5%: in April 2025 any terminal-payoff structure would have expired worthless,
because the terminal price was where it started. A capped variance swap works on
exactly the episode a put cannot touch.

### N. Is the four-Greek approximation adequate?

Adequate for risk, **not** for P&L accounting — which is why the verdict below is
GREEKS B rather than GREEKS A.

The daily residual averages just 2.18% of mean absolute daily P&L. But it is
systematic and it accumulates: **+$244,654, or 23.0% of the net option-leg
result**, because the net is a small difference between large opposing flows. The
residual is also structured — positive on moderate moves (+$284,515 on 2–5% days)
and negative on the largest (−$192,135 across the 15 days beyond 5%), which is
what a fixed local parabola does when gamma itself is changing through the move.

Adding vanna and volga does not fix it and makes things **worse**: explained
variance falls from 0.9902 to 0.9882 overall, and from 0.9904 to 0.9635 on
low-volatility days. Higher-order Greeks evaluated at the start of a whole-day
interval add more approximation error than they remove. They are reported so this
is visible rather than omitted to protect a headline.

### O. How should Black–Scholes and model-free variance be described together?

They answer different questions and the numbers show they are not
interchangeable. The full argument is in `greeks_methodology.md`; the key figure
is that the strip's cumulative **Black–Scholes delta P&L is +$777,002** while the
**canonical identity hedge contributed −$609,783** — it offsets 78.5% of the
strip's directional exposure, not 100%. That gap is not an error. A BSM delta
hedge tries to make the option portfolio directionally neutral; the identity
hedge holds `2/T · (1/F − 1/S_t)` shares to convert the static log contract into
realised variance, with no volatility input and no reference to any option's
delta. V5's methodology audit reached the same conclusion from the other
direction: an aggregate BSM delta hedge carried only ~57% of the position the
variance payoff requires.

So: **model-free replication values and hedges the contract; Black–Scholes Greeks
measure and explain it.** Using Greeks to hedge this book would reintroduce the
V5 defect; refusing to use them for attribution would leave "the trade lost
$732,061" as the entire explanation.

### Concentrated vs distributed strike exposure (section 29)

The original ATM straddle, run unchanged and unoptimised, against the strip:

| Share of gross Greek flow | Variance strip | ATM straddle |
|---|---|---|
| Theta | 47.6% | 44.2% |
| Gamma | 32.9% | **39.8%** |
| Vega | **14.5%** | 9.3% |
| Delta | 5.0% | 6.7% |

The straddle is a more concentrated gamma bet at a single strike; the strip
spreads exposure across the surface and picks up materially more vega. That is
the structural reason the project moved from straddles to the model-free strip in
the first place — an ATM straddle cannot hold the wing exposure where the
strike-integrated premium lives.

### P. Does V7 improve the project's depth even without creating a profitable strategy?

Yes, and it is the clearest answer to the "so what" question the earlier phases
invited. V5 built a correct replication engine; V6 established, adversarially,
that no timing rule made it investable. V7 adds the two things a derivatives
desk would expect next: a **stochastic-volatility model calibrated point-in-time
and validated against arbitrage bounds, parity, the BS limit and Monte Carlo
gates**, used to price a genuinely path-dependent payoff no static portfolio
spans; and a **Greek decomposition that explains 99% of daily P&L variance** and
identifies exactly which risk factor destroyed each of the two catastrophes.

It also produces the first result in the whole project that improves the
economics — and does so by changing the **contract**, not by predicting anything.

---

## Verdicts

# CAPPED A — fairly priced cap materially improves tail-adjusted economics

In development it keeps 97.2% of the payoff on 27.4% of the drawdown capital,
cutting the worst trade 76.9%, drawdown 72.7% and skew from −8.5 to −0.8. Out of
sample the direction repeats but materially weaker: 64.7% of the payoff on 52.5%
of the capital, with the worst trade down 63.6%. It is the only structure tested
across V5–V8 that materially improves tail-adjusted economics — the uncapped
baseline is also positive in both windows, but without the tail improvement. The
tail-risk reduction is essentially model-free; only its price is model-dependent.

Three constraints bound this verdict, and none is cosmetic. **Model risk is
material**: a 20% error in vol-of-vol moves development P&L ±45% and can turn the
OOS result negative, and ξ moves 17.4% month-on-month in the fits. **The
evidence base is 7 binding events**, so the 0.955 loss ratio is not a claim about
how Heston prices variance tails generally. And this is a **model-priced OTC
contract**: no exchange replication is derived and no dealer bid–offer is
modelled, so the concession computed here is a floor on what capping would
actually cost.

# GREEKS B — Greeks are useful, but leave material nonlinear residuals

Second-order attribution explains 99.0% of daily P&L variance and correctly
identifies gamma as the destructive factor in both catastrophes. But the residual
accumulates to 23% of the net result, is structured by move size, and gets worse
rather than better when vanna and volga are added. Excellent as a risk lens,
insufficient as a P&L ledger.
