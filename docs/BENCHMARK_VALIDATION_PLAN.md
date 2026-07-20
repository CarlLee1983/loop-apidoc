# Benchmark Harness Validation

This document is the canonical contract for the `loop-apidoc` benchmark
harness. It explains what the committed fixtures prove, what CI can verify
without private or redistributability-limited source snapshots, and what must
run locally before claiming source-backed benchmark success.

The harness currently contains **thirteen unique cases**. That number counts
fixture directories, not pytest test items: one case can feed several
parametrized assertions.

## The four harness layers

The layers are cumulative, but they are not interchangeable. Report the
strongest layer that actually completed.

### 1. Committed fixture inventory

A directory under `benchmarks/` is a committed harness case when both identity
files exist:

```text
benchmarks/<case>/
├── extraction/inventory.json
└── expected/validation.expect.json
```

The committed extraction and expectation files define the case and its
source-backed assertions. Other expected declarations, such as
`expected/minimum.json`, provide the assertion thresholds used during
execution. The original source snapshot is deliberately not part of fixture
identity because `benchmarks/<case>/sources/` is operator-provided and
gitignored.

The required inventory is explicit in
`scripts/quality_gate.py::REQUIRED_BENCHMARK_CASES`. It contains:

1. `adyen-payments-multimethod`
2. `apis-guru-baseline`
3. `cybersource-payments`
4. `ecpay-creditcard-pdf`
5. `funkygames-transfer-operator`
6. `github-webhooks`
7. `jili-legacy-gaming-pdf`
8. `line-pay-online-v3`
9. `newebpay-mpg`
10. `paypal-webhooks-incomplete`
11. `rsg-game-transfer-wallet`
12. `stripe-basic-rest`
13. `tappay-backend`

`test_required_benchmark_cases_match_committed_cases` enforces exact set
parity. A committed fixture omitted from the required list fails just as a
required name with no committed fixture fails. The explicit list is a review
boundary: adding or removing a case must be intentional.

### 2. Discovery guard

`tests/test_benchmarks.py::_cases()` enumerates committed fixtures by the
identity rule above. `test_benchmark_harness_discovers_cases` confirms the
required cases remain discoverable even when every local `sources/` directory
is absent.

This guard prevents a broken discovery expression or fixture layout from
turning the benchmark suite into an empty, apparently successful test run. It
proves that fixtures were enumerated; it does not prove their source-backed
assertions ran.

### 3. Source-backed execution

`tests/test_benchmarks.py` re-runs the deterministic assemble → validate tail
from each committed extraction and checks the generated artifacts against the
case's `expected/` declarations. Among other things, the assertions cover:

- expected validation PASS or EXPECTED_FAIL status;
- the complete issue-class map, including warning drift;
- OpenAPI 3.1 validity and structural minimums;
- critical operations, provenance, examples, and integration contracts;
- preparation, scoring, diff, and Foundry behavior exercised by the case.

These assertions execute only when the original, dated
`benchmarks/<case>/sources/` snapshot is present. If the snapshot is absent,
pytest reports the source-backed assertions as skipped.

**A skip is not a pass.** A skipped case was committed and discovered, but the
source-backed assertions did not execute. Use “passed” only when the applicable
assertions ran and passed.

### 4. Strict-local preflight

Run:

```bash
uv run python scripts/quality_gate.py --strict-local
```

Strict-local is the strongest harness claim. It:

1. runs the CI-safe lint and full pytest suite, including discovery and exact
   required-inventory parity;
2. requires a non-empty `sources/` tree for every required case;
3. runs `uv run pytest tests/test_benchmarks.py -q`; and
4. rejects the run if pytest reports any benchmark skip.

“Strict-local passed” therefore means every required case had a source
snapshot, all source-backed benchmark checks ran, and no skip was reported.

## Terminology

Use these terms consistently in issues, release notes, and review comments:

| Term | Meaning |
| --- | --- |
| **Committed** | The fixture identity files exist in the repository. |
| **Discovered** | The harness enumerated the committed fixture. |
| **Skipped** | Source-backed assertions did not execute because the required source snapshot was unavailable. |
| **Passed** | The applicable assertions executed and passed. |
| **Strict-local passed** | Every required case had sources, all source-backed benchmark checks ran, and no skip was reported. |

Do not shorten “committed and discovered” to “validated,” and do not describe
a CI run containing source-related skips as benchmark success.

## CI-safe and local commands

| Command | Layer verified | Source snapshots required |
| --- | --- | --- |
| `uv run pytest tests/test_benchmarks.py -k test_benchmark_harness_discovers_cases -q` | Discovery guard | No |
| `uv run pytest tests/test_quality_gate.py -k required_benchmark_cases_match_committed_cases -q` | Exact committed/required parity | No |
| `uv run python scripts/quality_gate.py` | CI-safe lint, unit/integration tests, discovery, and parity | No |
| `uv run pytest tests/test_benchmarks.py -q` | Source-backed execution for cases whose sources are present; absent sources skip | Yes, for a complete pass |
| `uv run python scripts/quality_gate.py --strict-local` | All four layers, with sources present and zero skips | Yes, for all thirteen cases |

The full benchmark module creates more than thirteen pytest items because each
fixture is used by multiple tests. Read the pytest summary for failures and
skips; do not infer the case count from the item count.

## Source snapshot rules

Source documents are the only source of truth. Store the original, dated
snapshot at:

```text
benchmarks/<case>/sources/
```

The directory is gitignored because some upstream documents are copyrighted,
access-controlled, or unsuitable for redistribution. Keep the case's
`notes.md` source URL, download date, document version, format, and scope
accurate enough to identify the snapshot.

If a historical snapshot is unavailable:

1. record which snapshot is unavailable and why;
2. run the deterministic CI-safe discovery and exact-parity checks;
3. perform a targeted source-backed spot-check for the changed behavior when a
   legitimate matching snapshot is available; and
4. report that strict-local could not be completed.

Never substitute a newer document, a synthetic fixture, or an upstream error
page merely to make the harness run. Those bytes are different evidence and
cannot revalidate the historical extraction.

## Adding a benchmark case

Adding a case widens a reviewed contract. Use this sequence:

1. Add `benchmarks/<case>/extraction/inventory.json`, endpoint extraction
   files, optional `integration.json`, and the expected declarations.
2. Confirm the case satisfies the fixture identity rule: both
   `extraction/inventory.json` and `expected/validation.expect.json` exist.
3. Add the case ID to `REQUIRED_BENCHMARK_CASES` intentionally.
4. Run the exact-parity regression:

   ```bash
   uv run pytest \
     tests/test_quality_gate.py::test_required_benchmark_cases_match_committed_cases \
     -q
   ```

5. With the original source snapshot present, run:

   ```bash
   uv run pytest tests/test_benchmarks.py -q
   ```

6. Run strict-local only on a machine holding all required snapshots:

   ```bash
   uv run python scripts/quality_gate.py --strict-local
   ```

The exact-parity test must fail between steps 1 and 3. That RED result proves a
new committed fixture cannot silently widen discovery without also widening the
required release inventory.

## Maintaining expected declarations

The harness is source-grounded, not snapshot-blind. Update an expected
declaration only after determining why behavior changed:

- If the source and intended contract did not change, treat output drift as a
  regression and fix the pipeline.
- If an original source snapshot legitimately changed, preserve the new dated
  evidence and document the reason before updating expectations.
- If a source conflict or required omission is intentional, keep the case
  fail-closed and declare the expected issue classes instead of weakening the
  assertion.

Do not infer missing fields from REST, OAuth, payment, or webhook conventions.
Anything the source does not state remains missing.

## 繁體中文摘要

Benchmark harness 分成四層，不能混為一談：

1. **已提交 fixture 清單**：case 目錄同時具有
   `extraction/inventory.json` 與
   `expected/validation.expect.json`；目前是十三個唯一 case。
2. **探索守門**：即使本機沒有 `sources/`，測試仍要找得到所有已提交 case，避免
   harness 靜默變成空集合。
3. **來源支撐執行**：只有原始、具日期的
   `benchmarks/<case>/sources/` 快照存在時，assemble 與產物斷言才會執行；缺來源是
   SKIP，不是 PASS。
4. **strict-local 預檢**：`scripts/quality_gate.py --strict-local` 要求 required
   inventory 與 committed fixture 完全一致、每個 case 都有非空來源，且 benchmark
   測試零 skip。

新增 case 時，先加入 extraction／expected 宣告，再刻意更新
`REQUIRED_BENCHMARK_CASES`，跑 exact-parity 測試，最後才在持有原始來源快照的機器上
跑 source-backed 與 strict-local。找不到歷史來源時，不得用新版文件、合成資料或錯誤
頁面頂替；應記錄缺口、跑確定性 CI 檢查，並對本次變更做合法的來源支撐 spot-check。
