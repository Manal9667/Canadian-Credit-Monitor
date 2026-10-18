"""Dependence-aware extensions for the Canadian consumer-credit analysis."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .household_credit_research import POLICY, REGIME_THRESHOLD_PP, classify_regime

SEED = 20261018
BOOTSTRAP_REPS = 2000
BLOCK_LENGTH = 12


def prepare_credit_panel(df: pd.DataFrame, threshold_pp: float = REGIME_THRESHOLD_PP) -> pd.DataFrame:
    """Monthly credit-growth/policy panel. lag1 regime means prior month label."""
    policy = df.loc[df.series_id == POLICY, ["observation_date", "value"]].copy()
    policy["month"] = policy.observation_date.dt.to_period("M")
    policy = policy.groupby("month").value.mean().rename("policy_rate").to_frame()
    if len(policy):
        policy = policy.reindex(pd.period_range(policy.index.min(), policy.index.max(), freq="M"))
        policy.index.name = "month"
    policy["policy_change_12m_pp"] = policy.policy_rate - policy.policy_rate.shift(12)
    policy["regime_baseline"] = policy.policy_change_12m_pp.map(
        lambda x: classify_regime(x) if pd.notna(x) else None
    )
    policy["regime_prior_month"] = policy.regime_baseline.shift(1)
    if threshold_pp != REGIME_THRESHOLD_PP:
        policy["regime_baseline"] = policy.policy_change_12m_pp.map(
            lambda x: None if pd.isna(x) else ("hiking" if x >= threshold_pp else "easing" if x <= -threshold_pp else "stable")
        )
        policy["regime_prior_month"] = policy.regime_baseline.shift(1)
    credit = df.loc[df.series_id == "V122667758", ["observation_date", "value"]].copy()
    credit["month"] = credit.observation_date.dt.to_period("M")
    credit = credit.set_index("month").sort_index()
    if len(credit):
        credit = credit[~credit.index.duplicated(keep="last")].reindex(
            pd.period_range(credit.index.min(), credit.index.max(), freq="M")
        )
    credit["growth_yoy_pct"] = 100 * (credit.value - credit.value.shift(12)) / credit.value.shift(12).abs()
    credit["observation_date"] = credit.index.to_timestamp()
    credit["month"] = credit.index
    credit = credit.reset_index(drop=True)
    credit["month"] = pd.PeriodIndex(credit.month, freq="M")
    panel = credit.merge(policy.reset_index(), on="month", how="left")
    return panel.sort_values("month").reset_index(drop=True)


def _nw_regime_ci(panel: pd.DataFrame, regime_col: str, regime: str, lag: int = 12) -> tuple[float, float]:
    """HAC CI for regime mean with zero scores retained in other calendar months."""
    valid = panel.growth_yoy_pct.notna() & panel[regime_col].notna()
    n = int((valid & (panel[regime_col] == regime)).sum())
    total = int(valid.sum())
    if n < 2 or total < 2:
        return np.nan, np.nan
    mean = panel.loc[valid & (panel[regime_col] == regime), "growth_yoy_pct"].mean()
    score = np.where(valid & (panel[regime_col] == regime), panel.growth_yoy_pct - mean, 0.0)
    # Ratio-estimator influence is scaled by the regime share.
    score = score / (n / total)
    variance = np.dot(score, score) / total
    for k in range(1, min(lag, total - 1) + 1):
        weight = 1 - k / (lag + 1)
        variance += 2 * weight * np.dot(score[k:], score[:-k]) / total
    se = np.sqrt(max(variance, 0) / total)
    return float(mean - 1.96 * se), float(mean + 1.96 * se)


def summarize_regimes(panel: pd.DataFrame, regime_col: str = "regime_baseline", reps: int = BOOTSTRAP_REPS) -> pd.DataFrame:
    """Summary stats plus conventional, HAC, and circular moving-block CIs."""
    rng = np.random.default_rng(SEED)
    p = panel.dropna(subset=["growth_yoy_pct", regime_col]).copy()
    output = []
    # Resample contiguous 12-month blocks of the complete panel; recompute means
    # within each regime to retain serial structure and changing regime shares.
    n_all = len(panel)
    boot: dict[str, list[float]] = {r: [] for r in ("hiking", "stable", "easing")}
    for _ in range(reps):
        starts = rng.integers(0, n_all, size=int(np.ceil(n_all / BLOCK_LENGTH)))
        idx = np.concatenate([(np.arange(s, s + BLOCK_LENGTH) % n_all) for s in starts])[:n_all]
        sample = panel.iloc[idx].dropna(subset=["growth_yoy_pct", regime_col])
        for regime in boot:
            vals = sample.loc[sample[regime_col] == regime, "growth_yoy_pct"]
            if len(vals):
                boot[regime].append(float(vals.mean()))
    for regime in ("hiking", "stable", "easing"):
        sub = p.loc[p[regime_col] == regime]
        vals = sub.growth_yoy_pct.to_numpy(dtype=float)
        n = len(vals)
        zcrit = 1.96
        se_iid = vals.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
        hac_lo, hac_hi = _nw_regime_ci(panel, regime_col, regime)
        b = boot[regime]
        output.append({"regime": regime, "definition": regime_col, "n": n,
            "date_min": sub.observation_date.min().date().isoformat() if n else "",
            "date_max": sub.observation_date.max().date().isoformat() if n else "",
            "mean_pct": vals.mean() if n else np.nan, "median_pct": np.median(vals) if n else np.nan,
            "sd_pct": vals.std(ddof=1) if n > 1 else np.nan,
            "iid_ci95_low": vals.mean()-zcrit*se_iid if n > 1 else np.nan,
            "iid_ci95_high": vals.mean()+zcrit*se_iid if n > 1 else np.nan,
            "hac12_ci95_low": hac_lo, "hac12_ci95_high": hac_hi,
            "block12_ci95_low": np.quantile(b, .025) if b else np.nan,
            "block12_ci95_high": np.quantile(b, .975) if b else np.nan,
            "lag1_autocorrelation": pd.Series(vals).autocorr(1) if n > 2 else np.nan,
            "bootstrap_reps": len(b), "seed": SEED})
    return pd.DataFrame(output)


def lagged_correlations(panel: pd.DataFrame, max_lag: int = 12) -> pd.DataFrame:
    """lag k pairs policy change in month t with growth observed at t+k."""
    rows = []
    indexed = panel.set_index("month")
    for k in range(max_lag + 1):
        x = indexed[["policy_change_12m_pp"]].rename(columns={"policy_change_12m_pp": "policy_t"})
        y = indexed[["growth_yoy_pct"]].copy()
        y.index = y.index - k
        y = y.rename(columns={"growth_yoy_pct": "growth_t_plus_k"})
        aligned = x.join(y, how="inner").dropna()
        rows.append({"lag_months": k, "convention": "policy change at t; credit growth at t+k",
                     "n": len(aligned), "date_min": str(aligned.index.min()) if len(aligned) else "",
                     "date_max": str(aligned.index.max()) if len(aligned) else "",
                     "correlation": aligned.corr().iloc[0, 1] if len(aligned) > 2 else np.nan})
    return pd.DataFrame(rows)


def sensitivity_table(panel: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    for name, threshold, start, end, regime_col in [
        ("baseline_25bp", .25, None, None, "regime_baseline"),
        ("threshold_50bp", .50, None, None, "regime_baseline"),
        ("threshold_10bp", .10, None, None, "regime_baseline"),
        ("prior_month_label", .25, None, None, "regime_prior_month"),
        ("post_2020", .25, "2020-01", None, "regime_baseline"),
        ("pre_pandemic", .25, None, "2020-02", "regime_baseline")]:
        q=panel.copy()
        if threshold != .25:
            ch=q.policy_change_12m_pp
            q["sensitivity_regime"] = np.where(ch >= threshold,"hiking",np.where(ch <= -threshold,"easing","stable"))
            q.loc[ch.isna(),"sensitivity_regime"] = None
            col="sensitivity_regime"
        else:
            col = regime_col
        if start:
            q = q[q.month.astype(str) >= start]
        if end:
            q = q[q.month.astype(str) <= end]
        for row in summarize_regimes(q, col, reps=500).to_dict("records"):
            rows.append({"specification":name, **row})
    return pd.DataFrame(rows)


def hac_regression(panel: pd.DataFrame, max_lag: int = 3) -> pd.DataFrame:
    """OLS association of growth with current/lagged policy change and lagged growth; HAC(12)."""
    p=panel.copy().set_index("month")
    p["growth_lag1"]=p.growth_yoy_pct.shift(1)
    for k in range(max_lag + 1):
        p[f"policy_lag{k}"] = p.policy_change_12m_pp.shift(k)
    p["trend"]=np.arange(len(p),dtype=float)
    cols=["policy_lag0","policy_lag1","policy_lag2","policy_lag3","growth_lag1","trend"]
    d = p[["growth_yoy_pct"] + cols].dropna()
    X = np.column_stack([np.ones(len(d)), d[cols].to_numpy()])
    y = d.growth_yoy_pct.to_numpy()
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    resid = y - X @ beta
    scores = X * resid[:, None]
    meat = scores.T @ scores
    L=12
    for lag in range(1,min(L,len(d)-1)+1):
        w = 1 - lag / (L + 1)
        gamma = scores[lag:].T @ scores[:-lag]
        meat += w*(gamma+gamma.T)
    inv = np.linalg.pinv(X.T @ X)
    cov = inv @ meat @ inv
    return pd.DataFrame({"term":["intercept"]+cols,"estimate":beta,"hac12_se":np.sqrt(np.maximum(np.diag(cov),0)),
        "ci95_low":beta-1.96*np.sqrt(np.maximum(np.diag(cov),0)),"ci95_high":beta+1.96*np.sqrt(np.maximum(np.diag(cov),0)),
        "n":len(d),"date_min":d.index.min().strftime("%Y-%m"),"date_max":d.index.max().strftime("%Y-%m"),
        "specification":"YoY growth ~ policy 12m change lags 0-3 + lagged YoY growth + linear trend; OLS HAC(12)"})
