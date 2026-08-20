# V8 — A delta-hedged, Greek-managed listed SPY option strategy

Frozen specification SHA-256: `7155b37835e9e421965c305627f19928753fd1f74ad8ef1fb0e6c6e6a26c6841`
Six variants against a budget of six. OOS unlocked once, after the hash and the
pre-OOS memo existed. Nothing changed afterwards.

Black–Scholes is not a diagnostic in this phase. Implied volatility picks the
strikes, Greeks size the book and cap its risk, and a daily Black–Scholes delta
hedge keeps it flat. That is the correct hedge for *this* product, and it is
deliberately not the model-free identity hedge that belongs to the variance-swap
engine.

---

## Answers

**A. Does a 10–15 delta winged straddle preserve meaningful theta carry?**

Yes — 90.4% of the naked structure's entry theta, at both 10 and 15 delta. Theta
retention was never the problem.

**B. How much gamma-dollar and tail risk do the wings remove?**

A great deal, and this is the part that works. Because the dollar-gamma cap binds
on 95–97% of entries, all three structures run at the same −$44M of entry dollar
gamma, so the comparison is already gamma-matched. At that matched exposure:

| Development | naked | 10-delta | 15-delta |
|---|---|---|---|
| Worst trade | −$302,734 | **−$106,305** | −$133,223 |
| Worst 5 trades | −$541,501 | −$398,917 | −$464,626 |
| ES95 | −$96,473 | −$75,322 | −$87,017 |
| Skew | −4.57 | **−0.16** | −0.39 |
| Kurtosis | 37.9 | **2.8** | 3.9 |

The worst trade improves 65% and the return distribution stops being
pathological. The wings do exactly what wings are supposed to do.

**C. What is the transaction-cost price of adding the wings?**

Decisive. Matching the same dollar gamma with four legs rather than two requires
**3.6× the contracts** — 656 versus 184 per trade at 10 delta, 889 at 15 delta.
Development costs rise from $188,989 to $444,853 and $612,817.

Set against a gross edge that barely moves:

| Development | gross edge | total costs | costs / gross | net |
|---|---|---|---|---|
| naked | $246,122 | $188,989 | **77%** | **+$45,412** |
| 10-delta | $241,032 | $444,853 | **185%** | −$215,135 |
| 15-delta | $288,807 | $612,817 | **212%** | −$335,866 |

The wings do not weaken the edge. They multiply the bill.

**D. Does vega targeting plus gamma capping create stable exposure through time?**

Very stable, but not in the way intended. The gamma cap binds on 96.7% of naked
entries and 100% out of sample, so **the cap, not the vega target, is the
operative sizing rule**: entry dollar gamma sits at −$44M almost every month
while realised vega averages $5,400 against a $10,000 target.

One caveat is material and I flagged it before OOS. The cap is applied **at entry
only**, and an at-the-money book's gamma grows as expiry approaches: against a
−$44M entry cap, the largest intra-trade reading is **−$126M** for the naked
structure. The DTE ≤ 7 exit is the only control on that drift, and it is a loose
one. A production version would re-cap intra-trade.

**E. Does daily Black–Scholes delta hedging work as intended?**

Exactly as intended, and this is measurable rather than asserted. Residual delta
after hedging is **0.00 shares on every non-closing day** across all 2,085
option-days. In the Greek attribution the hedge P&L is exactly equal and opposite
to the attributed delta term — −$511,454 against +$511,454 — because the book
holds precisely minus the option delta. There is no hidden directional exposure.

One bug had to be fixed to get there, and it was worth the trouble. When a leg's
implied volatility failed to invert on a violent day, an earlier version treated
portfolio delta as zero and **liquidated the entire share hedge**, re-establishing
it the next day at gap prices. That fabricated P&L: it turned the COVID trade from
−$302,734 into +$191,791. The engine now carries each leg's last solved
volatility forward, and holds the hedge if nothing solves. Eight of 2,085
option-days used the fallback.

**F. Does theta/gamma efficiency predict subsequent net P&L?**

No. Spearman 0.178 (p = 0.052) for the naked structure and 0.05–0.08 for the
winged ones, and the quartile means are **non-monotonic in every case** — Q3 is
the worst quartile twice. Section 16 requires "a clear, broad, monotonic
relationship". There is none, so that branch was closed without spending a
variant.

**G. Does the causal expected-gamma-loss calculation contain useful information?**

It contains a diagnosis rather than a signal, and the diagnosis is the finding of
this phase. Using the causal HAR forecast:

| naked, development | per trade |
|---|---|
| Expected theta over the holding period | $35,904 |
| Expected gamma loss at HAR variance | $38,863 |
| Expected transaction cost | $1,575 |
| **Expected carry efficiency** | **−$4,535** |
| Share of entries with positive expected efficiency | **23%** |

The strategy is diagnosed as unattractive **before it is traded**, on 77% of
entries. The calculation is internally sound: expected theta equals
`0.5·|Γ·S²|·IV²·T` to a ratio of 0.997, exactly as Black–Scholes requires.

**H. Does any Greek-based participation rule survive robustness testing?**

No. The one permitted section 17 rule — skip the bottom quintile of expected
carry efficiency, on an expanding causal percentile — lifts development net P&L
from +$45,412 to +$143,079 for the naked structure. But it improves only **2 of 4
chronological blocks**, so it is not robust and was rejected.

A note on how that number was obtained. My first version of the filter used each
trade's *realised* total cost, which includes hedge slippage incurred over the
trade's life — lookahead. Replaced with a genuinely ex-ante estimate (round-trip
quoted option spread plus commissions, hedge slippage excluded as unknowable),
the improvement fell from +$150,795 to +$97,668.

**I. How does the strategy behave in COVID?**

The naked structure loses **−$302,734** on the 2020-03-02 entry — its worst trade
of the decade, and 6.7× the entire ten-year net result. Gamma P&L is −$377,690
against theta of +$62,350. Realised variance over the holding window was 0.7575
against an entry implied of 0.0736.

The wings work: 10-delta loses $36,323 and 15-delta actually **makes** $15,817,
with gamma P&L falling from −$377,690 to −$90,154 and −$20,890. Vega sizing helps
too — high entry volatility means high vega per structure, so the position going
into the crisis was already small (141 structures against a typical 90–250).

**J. Does it survive across all pre-2023 blocks?**

No, and neither does anything else. **No variant is positive in more than 2 of 4
blocks.**

| Development block | naked | 10-delta | 15-delta |
|---|---|---|---|
| 2013–2016 | +$108,406 | −$79,301 | −$147,807 |
| 2017–2018 | −$59,133 | −$116,736 | −$145,722 |
| 2019–2020 | −$104,540 | **+$81,649** | **+$112,596** |
| 2021–2022 | +$100,678 | −$100,747 | −$154,932 |

The winged structures are positive only in the COVID block — precisely the
inverse of the naked structure's pattern, and exactly what correctly-functioning
but expensive insurance looks like.

**K. Which specification was frozen?**

The **naked delta-hedged ATM straddle**, as the section 28 fallback rather than
as a winner. No variant cleared criterion 3 of the hierarchy (a positive majority
of blocks), and section 28 provides for that outcome explicitly. The naked
structure is the only variant profitable after realistic costs without an added
rule, and the simplest. **The honest development verdict is that no listed
variant qualified.**

**L. What happens OOS 2023–2025?**

32 trades, one run, exactly as frozen.

| | naked (frozen) | 10-delta | 15-delta |
|---|---|---|---|
| Net P&L | **−$101,775** | −$153,551 | −$169,229 |
| Sharpe | −0.418 | −1.116 | −1.222 |
| Newey–West t | −0.809 | −1.695 | −1.780 |
| Max drawdown | $196,276 | $240,825 | $255,301 |
| Worst trade | −$135,024 | **−$45,427** | **−$28,872** |
| ES95 | −$78,645 | −$35,872 | −$28,785 |
| Skew | −4.20 | −0.23 | **+0.31** |
| Costs | $27,358 | $55,280 | $73,350 |
| Financing | −$30,238 | −$26,219 | −$24,451 |

Four of the memo's five predictions held: the result was inside the stated
±$150,000 band, costs again exceeded the edge, financing was a much larger drag
(−$30,238 over 32 months against −$11,721 over 120), and the winged comparators
lost more than the naked structure while cutting the tail. The Greek bridge tells
the same story as development — theta +$1,026,127 against gamma −$1,047,587, a
shortfall of $21,461 before vega, costs and financing.

**M. How does April 2025 differ from COVID?**

COVID was a −20.2% terminal move with a 29.1% path range. April 2025 was a
12.1% path range that ended −4.6% from entry at the DTE ≤ 7 exit. Both destroyed
the naked book, for the same reason: short gamma, hedged daily, against realised
volatility far above implied.

| | naked | 10-delta | 15-delta |
|---|---|---|---|
| COVID net | −$302,734 | −$36,323 | +$15,817 |
| April 2025 net | −$135,024 | −$45,427 | −$28,698 |
| April 2025 gamma P&L | −$205,933 | −$106,841 | −$94,761 |

**N. Do listed wings protect path volatility, or only large terminal moves?**

**Both — and my pre-registered prediction here was wrong.** I predicted before
unlocking OOS that the wings would provide little protection in April 2025,
because long options pay on terminal distance from the strike and V7 established
April 2025 as a round-trip event. The wings cut the April 2025 loss by 66% and
79%.

Two reasons, and the first is the one I should have seen. In a **continuously
delta-hedged** book, long wings do not function as terminal-payoff insurance —
they function as *gamma* insurance every single day, reducing the portfolio's
convexity and therefore the daily hedging losses, wherever the price finally
lands. That is structurally different from V7, where outright puts were held
against a variance swap to expiry and paid only on terminal level. Second, the
DTE ≤ 7 exit closed this trade on 2025-04-24 at 535.42, before the recovery to
566.76 that made V7's contract a round trip; over the V8 window the move was
−4.6%, not +1.0%.

So V7's finding ("terminal-payoff options do not hedge path functionals") and
V8's are not in conflict — they are about different hedges. A *static* long put
does not hedge path risk. A long wing inside a *delta-hedged* book does, because
it is being used for its gamma, not its payoff.

**O. Does the strategy earn a return meaningfully above cash?**

No. On a **historical peak-drawdown capital proxy** — actual SPY portfolio margin
is **not** modelled, and would be larger and revised daily:

| | naked | cash |
|---|---|---|
| Development 2013–2022 | +0.95% p.a. | 0.64% |
| OOS 2023–2025 | **−20.13% p.a.** | 4.62% |
| Full 2013–2025 | −0.93% p.a. | 1.48% |

On $1M reference capital: +0.46% p.a. in development, −3.95% out of sample.

**P. Is it plausibly usable?**

No, on any of the three standards worth separating:

- **Statistically interesting**: no. Development Sharpe 0.035 with t = 0.12; OOS
  Sharpe −0.418 with t = −0.81. Nothing here is distinguishable from zero.
- **Economically interesting**: yes, but as an explanation rather than a strategy
  — see below.
- **Plausibly tradeable**: no. Negative net after costs in the OOS window, below
  cash in both, and a −$302,734 single-trade loss against a ten-year net of
  +$45,412. Capacity is also unestablished: end-of-day OptionMetrics quotes carry
  no depth or market impact.

**Q. Does it demonstrate practical Black–Scholes / Greeks trading and risk
management?**

Yes, and that is what the phase delivers. Implied volatility selects the strikes;
delta chooses the wings; vega budgets the size; a dollar-gamma stress cap
overrides that size and binds on 96% of entries; a daily delta hedge drives
residual delta to exactly zero on every open day; and a Greek attribution
explains the option leg with a correlation of 0.995 and reconciles to the engine's
cash P&L to 10⁻¹¹. The risk controls behave as designed and are measured, not
asserted — including where they fall short, as with the entry-only gamma cap
letting dollar gamma drift from −$44M to −$126M.

---

## Why it does not work — the structural reason

Not bad luck, and not weak wings. The strategy is trading the wrong part of the
surface.

Measuring the implied variance actually traded against the realised variance that
followed, across 120 development entries:

| | Implied variance | Premium vs realised | t |
|---|---|---|---|
| **ATM straddle** (what the strategy sells) | 0.02723 | **−0.00423** | −0.62 |
| **10-delta wings** (what it buys) | 0.03362 | **+0.00216** | +0.32 |
| Strike-integrated IVAR30 | 0.03617 | +0.00470 | +0.69 |
| Causal HAR forecast | 0.02659 | — | — |
| Realised | 0.03147 | — | — |

The at-the-money premium is **negative**. Wing implied volatility exceeds ATM
implied volatility on 99% of entries by 1.95 volatility points. A winged straddle
is therefore **short the cheapest part of the surface and long the richest** —
inverted relative to where this project has located the premium since its earliest
phases.

The Greek attribution says the same thing independently. Because the hedge holds
exactly minus the option delta, the delta term cancels, and the strategy reduces
to a race between theta and gamma:

| Development | naked | 10-delta | 15-delta |
|---|---|---|---|
| Theta collected | +$4,240,747 | +$3,607,810 | +$3,533,353 |
| Gamma paid | −$4,097,255 | −$3,622,330 | −$3,446,829 |
| **Theta − gamma** | **+$143,492** | −$14,520 | +$86,524 |
| Transaction costs | −$188,989 | −$444,853 | −$612,817 |
| **Net** | **+$45,412** | −$215,135 | −$335,866 |

Over ten years, theta exceeds gamma by $143,492 — about $1,200 a month on a book
carrying $44M of dollar gamma. That is what an ATM premium of −0.004 with t =
−0.62 looks like from the trading side. The residual is smaller than the
commissions.

This closes a loop the project opened long ago, when ATM implied volatility was
found to measure no premium while strike-integrated variance did. V8 shows the
same fact from the execution side: **an at-the-money straddle sits exactly where
there is no premium to harvest, and adding listed wings pays away the premium
that does exist.**

---

# RESULT C — listed wings and Greek controls do not produce an economically attractive strategy

The Greek machinery works. Delta hedging is exact, the gamma cap binds and holds
exposure flat across structures, vega targeting shrinks the book into crises, and
the wings genuinely remove tail risk — worst trade down 65%, skew from −4.6 to
−0.2, and a COVID loss cut from $302,734 to $36,323.

None of it produces a tradeable strategy, and the reason is structural rather
than statistical. The at-the-money variance an ATM straddle sells carries a
negative premium in this sample; the wings it buys carry a positive one. Theta and
gamma therefore nearly cancel, transaction costs are 77% of the naked structure's
gross edge and 185–212% of the winged ones, and the result is +$45,412 over ten
development years and −$101,775 out of sample — below cash in both windows.

The wings are not too weak. They are correctly-functioning insurance, bought on
the wrong side of the surface and paid for through an expensive channel.
