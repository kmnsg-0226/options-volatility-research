# Archived research phases

These are **superseded exploratory phases**, retained for provenance and
reproducibility. They are not the project's conclusions.

The current results live in five directories one level up:

| Phase | Directory |
|---|---|
| Methodology audit | [`../variance_hedge_identity_audit/`](../variance_hedge_identity_audit/) |
| V5 canonical engine | [`../correct_variance_engine_v5/`](../correct_variance_engine_v5/) |
| V6 risk & timing | [`../canonical_risk_timing_v6/`](../canonical_risk_timing_v6/) |
| V7 capped variance & Greeks | [`../capped_variance_greeks_v7/`](../capped_variance_greeks_v7/) |
| V8 listed options | [`../greek_managed_listed_strategy_v8/`](../greek_managed_listed_strategy_v8/) |

## Why these are kept

Several conclusions in the current phases are corrections of results produced
here. The audit that rebuilt the replication engine, for example, is only
meaningful against the earlier engine it replaced, and the anti-overfitting work
in V6 is a direct response to the strategy searches recorded in these
directories. Deleting them would remove the evidence that the corrections were
corrections.

**Read these as a lab notebook, not as findings.** Where an archived result
disagrees with a current phase, the current phase supersedes it.

## What was removed

Row-level intermediate dumps have been deleted to keep the repository a
reasonable size — 34 files, roughly 34 MB:

- `chain_positions*.csv` — per-trade, per-strike position rows
- `model_free_variance_diagnostics.csv` — per-strike variance contributions
- `signals.csv`, `daily_ledger.csv` — per-day intermediate ledgers

These are machine-generated inputs to the analysis, not results. Nothing cites
them, and they can be regenerated from the cached option panel by re-running the
relevant phase script. **Every memo, summary, frozen specification, figure and
result table has been preserved unchanged.**

## Note on three directories

`diagnostics/`, `local_eod/` and `diagnostic_eod/` are also the *default output
paths* of `scripts/run_backtest_audit.py` and the `local-eod` CLI command. The
historical outputs are archived here; re-running those commands will recreate
empty directories at `reports/` top level. Those regenerated paths are
gitignored.
