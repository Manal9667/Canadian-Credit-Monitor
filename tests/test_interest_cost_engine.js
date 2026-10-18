const assert = require('node:assert/strict');
const { calculate } = require('../frontend/interest_cost_engine.js');

const base = { eligible_balance_millions_cad: 1000, policy_shock_bp: 100,
  exposure_share: 1, pass_through: 1, repriced_share: 1, horizon_months: 12, timing: 'start' };
assert.equal(calculate({...base, policy_shock_bp: 25}).partial_annualized_millions_cad, 2.5);
assert.equal(calculate({...base, exposure_share: .6, pass_through: .5, repriced_share: .5}).partial_annualized_millions_cad, 1.5);
assert.equal(calculate({...base, policy_shock_bp: 200, horizon_months: 6, timing: 'uniform'}).partial_cumulative_millions_cad, 5);
assert.equal(calculate({...base, policy_shock_bp: 0}).partial_annualized_millions_cad, 0);
for (const update of [{eligible_balance_millions_cad: -1}, {exposure_share: 1.1}, {pass_through: 6},
  {repriced_share: -1}, {horizon_months: 121}, {policy_shock_bp: 10001}]) {
  assert.throws(() => calculate({...base, ...update}));
}
console.log('Browser interest-cost engine checks passed.');
