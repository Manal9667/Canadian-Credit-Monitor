# Canadian Household Credit and Interest-Rate Analysis

## Question and Thesis

This note asks how Bank of Canada policy-rate changes were associated with
posted and effective lending rates, and how those rate regimes coincided with
Canadian household-credit growth and debt indicators. The headline finding is
that prime-rate pass-through was mechanically close to the policy rate, while
effective consumer and card rates stayed meaningfully above policy rates and
credit-growth relationships were noisier across lags and regimes.

All figures use aggregate public indicators only. Bank of Canada data are as of
2026-10-13T22:43:11.139739+00:00 from snapshot `20261013T224303Z`. Statistics Canada data
are as of 2026-10-13T22:43:12.617130+00:00 from snapshot `20261013T224311Z`. A
Statistics Canada refresh attempt on 2026-10-12 returned HTTP 403; that failure
was not reproduced on 2026-10-13, when the public WDS and official CSV download
both succeeded and all four configured series passed preflight validation.
Current validation passed for both sources with no warnings or failures.

## Evidence

**Mechanical pass-through.** Prime and policy rates are aligned on exact weekly
observation dates from 2009-04-22 to 2026-10-07 (N=912).
The latest prime-policy spread was 2.20 percentage
points, compared with an average spread of 2.13
percentage points over the aligned sample. This is the cleanest pass-through
measure because prime is a posted administered lending rate.

**Informative pass-through.** Effective lending rates are monthly series and are
compared with the average daily policy rate in the same calendar month. The
latest consumer-credit effective spread was 5.67
percentage points (N=121, 2016-07-01 to
2026-07-01); the credit-card effective spread was
19.03 percentage points. Posted mortgage rates are also
shown, but they are informative rather than mechanical because they depend on
funding costs and bond yields as well as the overnight policy rate. The latest
5-year posted mortgage-policy spread was 3.94
percentage points.

**Credit growth by regime.** Regimes are defined before computation using the
trailing 12-month change in the monthly average policy rate: hiking is at least
+0.25 percentage points, easing is at most
-0.25 percentage points, and stable is between those
thresholds. For total consumer credit, the computed regime averages were:
hiking: 5.81% average YoY growth (N=52, 2017-08-01 to 2024-05-01); stable: 3.23% average YoY growth (N=20, 2017-07-01 to 2024-07-01); easing: 3.53% average YoY growth (N=37, 2020-03-01 to 2026-07-01). These are associations, not causal estimates.

**Lag profile.** The lead/lag table reports correlations between the trailing
12-month policy-rate change and later YoY balance growth for lags from 0 to 12
months. The profile is intentionally shown in full rather than optimized around
the strongest lag. Mixed signs and moderate sample sizes mean this evidence
should be read as timing context, not a predictive model.

**Debt and composition.** Statistics Canada debt-to-income is quarterly and can
only be joined to policy regimes after policy data begin in 2009. The Bank of
Canada tracked component shares are not total household-debt composition. As of
2026-07-01, the largest tracked
component was Uninsured mortgages at
54.49% of tracked components.

## Illustrative Sensitivity

This is a mechanical sensitivity, not a forecast. It applies +100 bp or +200 bp
directly to latest observed balances and ignores repricing schedules, defaults,
credit mix, balances paid in full, and borrower behaviour. Mortgages are
excluded because this dataset does not include an effective mortgage lending
rate. For consumer credit, a +100 bp move equals
7045.8 million CAD of
incremental annual interest, or 1.0% of
the balance, using V122667758 and V122667809
as of 2026-07-01.

## Implications for Banks and Lenders

The analysis separates rates that are administratively linked to policy from
rates that embed product mix, credit risk, funding costs, and customer behavior.
That distinction matters for bank revenue sensitivity: balances can still grow
or shift composition even when policy rates stabilize, and effective rates can
remain elevated relative to policy. For lenders, the useful interview takeaway
is not that rate hikes caused credit outcomes, but that public aggregate data
can quantify the timing, spreads, and balance exposure that an analyst would
then investigate with richer portfolio data.

## Limitations and Risks

The data are aggregate and public. They contain no individual borrowers, credit
bureau records, delinquencies, defaults, bank-level portfolios, or loan-level
repricing schedules. The analysis does not interpolate across mismatched
frequencies. Posted-rate comparisons start when policy-rate data begin in
2009-04. Effective-rate comparisons use monthly average policy rates. Results
are descriptive and may change when the public sources revise or refresh.
