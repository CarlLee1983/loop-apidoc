# Calibrate the fixed-scale growth measurements in the source-risk scaling tests

## Goal

`tests/test_source_risk_scaling.py` proves that source-risk scanning grows linearly by
measuring CPU cost at N and 8N. The per-rule test calibrates N through `_calibrated()`,
so its small side is always above the noise floor. The two tests that go through
`_growth()` do not: `test_the_ratio_limit_separates_quadratic_from_linear` uses a fixed
`base_units=200`, and `test_contact_pii_scales_linearly_on_its_adversarial_shape` uses a
fixed `base_units=300`. When a runner is fast enough, the small side drops below
`MIN_MEASURABLE_SECONDS` (0.01 s) and the test fails at random without a defect. CI
failed this way on `main` at `6fefe7b` (0.0094 s) and on PR #174 (0.0086 s). On this
machine the control's small side measures about 0.015 s and the near-miss side about
0.027 s, both close to the floor.

Make `_growth()` grow its starting scale until the small side is measurable, using the
same estimator it already uses. Both tests then stay meaningful on faster hardware, and
the file's argument does not change: the 16x limit sits between linear (8x) and
O(n^1.5) (22.6x), and the quadratic control must exceed it.

## Out of Scope

- `LINEAR_RATIO_LIMIT`, `GROWTH_FACTOR`, `MIN_MEASURABLE_SECONDS`,
  `CHEAP_RULE_CPU_BUDGET`, `QUADRATIC_CONTROL`, `CSS_UNIT`, `NEAR_MISS_UNIT`, and the
  module docstring.
- `test_every_source_risk_rule_scales_linearly`, `_calibrated()`, and the
  cheap-rule budget path.
- `loop_apidoc/source_risk/` and `loop_apidoc/privacy.py`: no production code changes.
- Retrying, skipping, or marking any test as flaky.

## Acceptance Criteria

1. `git diff main...HEAD -- tests/test_source_risk_scaling.py` leaves every name listed
   in the first Out of Scope bullet byte-identical, along with the module docstring, the
   assertion `quadratic_ratio > LINEAR_RATIO_LIMIT`, and `_assert_linear()`.
2. `_growth()` starts from the `base_units` it is given. It doubles the scale until the
   small side's cost, measured by `_best_cpu_seconds` with the same `runs`, exceeds
   `MIN_MEASURABLE_SECONDS * 2`, with an upper bound on doublings. If the bound is
   reached, it still fails with the existing "低於可量測門檻" message. The large side
   is measured at `GROWTH_FACTOR` times the scale the calibration settled on.
3. A simulated fast runner is handled. With the scale forced far too small,
   `uv run python -c "import sys; sys.path.insert(0, 'tests'); import test_source_risk_scaling as t; s, l = t._growth(t.QUADRATIC_CONTROL.findall, t.CSS_UNIT, base_units=10, runs=2); print(s > 2 * t.MIN_MEASURABLE_SECONDS, l / s > t.LINEAR_RATIO_LIMIT)"`
   prints `True True`.
4. `uv run python -c "import sys; sys.path.insert(0, 'tests'); import test_source_risk_scaling as t; s, l = t._growth(t.CONTACT_PII.findall, t.NEAR_MISS_UNIT, base_units=10); print(s > 2 * t.MIN_MEASURABLE_SECONDS, l / s < t.LINEAR_RATIO_LIMIT)"`
   prints `True True`.
5. `for i in $(seq 20); do uv run pytest -q -p no:cacheprovider tests/test_source_risk_scaling.py -k "ratio_limit or adversarial_shape" || exit 1; done`
   exits 0.
6. `uv run pytest tests/test_source_risk_scaling.py --durations=5` passes, and no single
   test in that file takes more than 10 s.
7. `git diff --name-status main...HEAD` lists only
   `M tests/test_source_risk_scaling.py` and this Story file
   (`specs/stories/calibrate-source-risk-growth-measurement.md`).
8. `make verify` exits 0.
