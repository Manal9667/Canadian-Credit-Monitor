/* Pure browser calculation layer; mirrors python/analysis/interest_cost_scenarios.py. */
(function (root) {
  'use strict';
  const MAX_BALANCE_MILLIONS_CAD = 1_000_000_000;
  const MAX_ABS_SHOCK_BP = 10_000;
  const MAX_PASS_THROUGH = 5;
  const MAX_HORIZON_MONTHS = 120;

  function calculate(input) {
    const fields = ['eligible_balance_millions_cad', 'policy_shock_bp', 'exposure_share', 'pass_through', 'repriced_share'];
    for (const field of fields) {
      if (typeof input[field] !== 'number' || !Number.isFinite(input[field])) throw new Error(`${field} must be a finite number.`);
    }
    const {eligible_balance_millions_cad: balance, policy_shock_bp: shock,
      exposure_share: exposure, pass_through: passThrough, repriced_share: repriced,
      horizon_months: horizon, timing} = input;
    if (balance < 0 || balance > MAX_BALANCE_MILLIONS_CAD) throw new Error(`Balance must be between 0 and ${MAX_BALANCE_MILLIONS_CAD.toLocaleString()} CAD millions.`);
    if (Math.abs(shock) > MAX_ABS_SHOCK_BP) throw new Error(`Rate shock must be between -${MAX_ABS_SHOCK_BP.toLocaleString()} and +${MAX_ABS_SHOCK_BP.toLocaleString()} bps.`);
    if (exposure < 0 || exposure > 1) throw new Error('Exposure share must be between 0% and 100%.');
    if (passThrough < 0 || passThrough > MAX_PASS_THROUGH) throw new Error('Pass-through must be between 0x and 5x.');
    if (repriced < 0 || repriced > 1) throw new Error('Repriced share must be between 0% and 100%.');
    if (!Number.isInteger(horizon) || horizon < 1 || horizon > MAX_HORIZON_MONTHS) throw new Error(`Horizon must be 1 to ${MAX_HORIZON_MONTHS} whole months.`);
    if (timing !== 'uniform' && timing !== 'start') throw new Error('Choose a supported repricing timing.');

    const rateChange = shock * passThrough / 10_000;
    const affectedBalance = balance * exposure * repriced;
    const partialAnnualized = affectedBalance * rateChange;
    const timingFactor = timing === 'uniform' ? 0.5 : 1;
    const horizonYears = horizon / 12;
    const mechanicalAnnualized = balance * shock / 10_000;
    return Object.freeze({
      borrowing_rate_change_bp: shock * passThrough,
      partial_balance_millions_cad: affectedBalance,
      partial_annualized_millions_cad: partialAnnualized,
      partial_cumulative_millions_cad: partialAnnualized * horizonYears * timingFactor,
      mechanical_annualized_millions_cad: mechanicalAnnualized,
      mechanical_cumulative_millions_cad: mechanicalAnnualized * horizonYears,
      cumulative_timing_factor: timingFactor
    });
  }

  const engine = Object.freeze({calculate});
  if (typeof module !== 'undefined' && module.exports) module.exports = engine;
  if (root) root.InterestCostEngine = engine;
})(typeof globalThis !== 'undefined' ? globalThis : this);
