# Pre-2023 Development Memo — written before the final test was unlocked

Config SHA-256: `ef9bb0eb6c81c625594d1236c388423d8d3af8828271249dab5efc6a357aea0f`

## Selected candidate

**Central 80% variance-weight strip · ~30D maturity · monthly first-trading-day entry ·
fixed $1,000,000 variance notional · daily delta hedge · hold to DTE ≤ 2.**

## Why

The documented selection rule ranks candidates on an equal-weight average of six ranks:
median block Sharpe, minimum block Sharpe, number of positive blocks, pooled Sharpe,
maximum drawdown and ES95. On that rule `c80 + risk-targeted` placed first
(avg rank 1.667) and `c80 + fixed` second (2.333).

`c80 + risk-targeted` was **rejected** under the pre-specified requirement that an
improvement survive the paired comparison: its paired difference against the previous
c90 baseline is **−$1,374 per trade (t = −0.76)**. It lowers drawdown by giving up
carry, the same trade-off found in the earlier structural phase. `c80 + fixed` is the
highest-ranked candidate whose paired difference is not negative (+$288, t = 0.31).

Coverage was chosen over the previously post-selected 85–115 corridor because the
central-80% strip is the only candidate with **four positive blocks and a positive
minimum block Sharpe (0.222)**.

## Pre-2023 performance

Pooled 2013-06 → 2022-12 (115 trades): net **$420,589**, Sharpe **0.801**,
max DD 0.121, worst trade −$108,431, ES95 −$39,513, skew −2.79, costs $99,182,
median 37 legs at 4.11 contracts per leg.

| Block | Sharpe | Net P&L |
|---|---|---|
| 2013–2016 | 1.462 | $111,348 |
| 2017–2018 | 0.222 | $19,260 |
| 2019–2020 | 0.462 | $91,083 |
| 2021–2022 | 2.972 | $198,898 |

**All four blocks positive.**

## Stitched walk-forward 2017–2022 (72 trades)

Net **$309,241** · Sharpe **0.770** · max DD 0.134 · worst −$108,431 ·
ES95 −$51,771 · t = 1.858 · Newey–West t = 1.723 · **5 of 6 years positive**.

By year: 2017 +$29,705 · 2018 −$10,445 · 2019 +$28,691 · 2020 +$62,393 ·
2021 +$138,884 · 2022 +$60,014.

Against the previous c90 baseline over the same window: Sharpe 0.770 vs 0.428,
max DD 0.134 vs 0.238, worst trade −$108,431 vs −$211,142.

## Parameter stability

| Parameter | Classification |
|---|---|
| Coverage = central 80% | robust gradient, **boundary-limited** (0.801 / 0.591 / 0.487 / 0.320 monotone in coverage; nothing below 80% was tested) |
| Maturity = ~30D | **weakly identified** (21D −0.097, 30D 0.487, 45D 0.075, 55D 0.582 — non-monotone; 55D is an isolated peak, so the incumbent is retained) |
| Sizing = fixed | plateau exists but rejected on the paired test |
| Hedge = daily | robust — no alternative passed eligibility on ≥3 of 4 blocks |
| Entry = first trading day | robust — biweekly halves contracts/leg and doubles fair-strike error |

## Does the improvement survive paired comparison?

**No, not in a significance sense.** +$288 per trade with t = 0.31 and a 95% interval
of [−$913, +$2,468]. The improvement over the previous baseline is directionally
positive and not statistically demonstrable.

## Does the selection appear robust?

**Only partially, and one result argues against it.** Fifty specifications were
evaluated in this phase. With N = 50 and a Sharpe standard error of 0.416 over 72
observations, the expected maximum Sharpe under a no-skill null is **0.947** — above
the selected walk-forward Sharpe of **0.770**. The deflated-Sharpe probability is
**0.335**.

**The selected strategy does not clear its own multiple-testing bar.** Whatever the
locked period shows, that fact stands and is recorded here before the unlock.

## Expectation stated in advance

On the evidence above I expect the locked 2023–2025 window to show, at best, weakly
positive expectancy with materially lower Sharpe than 0.770, and I would not be
surprised by a negative result. Recording this here so the final test is not
rationalised after the fact.
