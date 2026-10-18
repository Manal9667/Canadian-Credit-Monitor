"""Auditable static interest-cost scenario calculations.

Balances are expressed in CAD millions, shocks in basis points, shares as
fractions, and horizons in months. This module contains no UI or data loading.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


MAX_BALANCE_MILLIONS_CAD = 1_000_000_000.0
MAX_ABS_SHOCK_BP = 10_000.0
MAX_PASS_THROUGH = 5.0
MAX_HORIZON_MONTHS = 120
TIMINGS = {"uniform", "start"}


@dataclass(frozen=True)
class ScenarioInputs:
    eligible_balance_millions_cad: float
    policy_shock_bp: float
    exposure_share: float
    pass_through: float
    repriced_share: float
    horizon_months: int
    timing: str = "uniform"


@dataclass(frozen=True)
class ScenarioResult:
    borrowing_rate_change_bp: float
    partial_balance_millions_cad: float
    partial_annualized_millions_cad: float
    partial_cumulative_millions_cad: float
    mechanical_annualized_millions_cad: float
    mechanical_cumulative_millions_cad: float
    cumulative_timing_factor: float


def validate_inputs(inputs: ScenarioInputs) -> None:
    """Reject missing, non-finite, out-of-range, and unsafe scenario inputs."""
    numeric = {
        "eligible_balance_millions_cad": inputs.eligible_balance_millions_cad,
        "policy_shock_bp": inputs.policy_shock_bp,
        "exposure_share": inputs.exposure_share,
        "pass_through": inputs.pass_through,
        "repriced_share": inputs.repriced_share,
    }
    for name, value in numeric.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number")
    if not 0 <= inputs.eligible_balance_millions_cad <= MAX_BALANCE_MILLIONS_CAD:
        raise ValueError(f"eligible_balance_millions_cad must be between 0 and {MAX_BALANCE_MILLIONS_CAD:g}")
    if abs(inputs.policy_shock_bp) > MAX_ABS_SHOCK_BP:
        raise ValueError(f"policy_shock_bp must be between {-MAX_ABS_SHOCK_BP:g} and {MAX_ABS_SHOCK_BP:g}")
    if not 0 <= inputs.exposure_share <= 1:
        raise ValueError("exposure_share must be between 0 and 1")
    if not 0 <= inputs.pass_through <= MAX_PASS_THROUGH:
        raise ValueError(f"pass_through must be between 0 and {MAX_PASS_THROUGH:g}")
    if not 0 <= inputs.repriced_share <= 1:
        raise ValueError("repriced_share must be between 0 and 1")
    if isinstance(inputs.horizon_months, bool) or not isinstance(inputs.horizon_months, int):
        raise ValueError("horizon_months must be an integer")
    if not 1 <= inputs.horizon_months <= MAX_HORIZON_MONTHS:
        raise ValueError(f"horizon_months must be between 1 and {MAX_HORIZON_MONTHS}")
    if inputs.timing not in TIMINGS:
        raise ValueError("timing must be 'uniform' or 'start'")


def calculate_interest_cost(inputs: ScenarioInputs) -> ScenarioResult:
    """Return partial-repricing scenario and full immediate-repricing comparator.

    Partial case:
      delta_rate = policy_shock_bp * pass_through / 10,000
      affected_balance = eligible_balance * exposure_share * repriced_share
      annualized run rate = affected_balance * delta_rate
      uniform cumulative cost = annualized * horizon_years / 2
      start cumulative cost = annualized * horizon_years

    The uniform convention means the repriced share becomes active evenly from
    month 0 through horizon end. The mechanical comparator assumes 100% exposure,
    100% pass-through, and repricing at the start of the horizon.
    """
    validate_inputs(inputs)
    balance = float(inputs.eligible_balance_millions_cad)
    rate_change = float(inputs.policy_shock_bp) * float(inputs.pass_through) / 10_000.0
    partial_balance = balance * inputs.exposure_share * inputs.repriced_share
    annualized = partial_balance * rate_change
    years = inputs.horizon_months / 12.0
    timing_factor = 0.5 if inputs.timing == "uniform" else 1.0
    mechanical_annualized = balance * float(inputs.policy_shock_bp) / 10_000.0
    return ScenarioResult(
        borrowing_rate_change_bp=float(inputs.policy_shock_bp) * float(inputs.pass_through),
        partial_balance_millions_cad=partial_balance,
        partial_annualized_millions_cad=annualized,
        partial_cumulative_millions_cad=annualized * years * timing_factor,
        mechanical_annualized_millions_cad=mechanical_annualized,
        mechanical_cumulative_millions_cad=mechanical_annualized * years,
        cumulative_timing_factor=timing_factor,
    )
