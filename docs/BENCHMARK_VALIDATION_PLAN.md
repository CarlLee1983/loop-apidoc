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
`expected/minimum.json`, carry the exact structural counts the case produced
when it was recorded — `counts` is asserted with `==`, not as a floor, so any
movement has to appear in the diff and be explained (#126). The booleans,
`critical_operations`, and `critical_security_schemes` beside it stay presence
checks. `critical_security_schemes` names emitted
`components.securitySchemes` keys, because a count cannot tell a renamed scheme
from the required one; a human-readable name for a key belongs in
`critical_security_scheme_labels`, which is never matched against output (#137).

The original source snapshot is deliberately not part of fixture identity because `benchmarks/<case>/sources/` is operator-provided and
gitignored.

Every committed case also carries `expected/core-parity.json`. This is a
versioned declaration for the eventual Core graduation gate: it fixes the
legacy and Core verdicts, requires an exact-evidence chain for every material
claim, and disallows undeclared semantic differences. Its presence and shape
are checked without sources, so a new fixture cannot bypass the Core gate in
CI merely because its private snapshot is unavailable. The actual Core/legacy
comparison remains source-backed and is eligible for cutover only after Core
can represent every declared source gap without fabricating metadata.

A non-empty source directory merely enables the legacy source-backed checks. It
does not by itself make a case eligible for Core parity: every material claim
must still be addressable by an exact source fragment. For example, a
browser-flattened one-line rendition may preserve readable content but cannot
be assigned invented claim locators; retain it as an observed legacy replay and
obtain the original structured snapshot before declaring exact-evidence parity.
The retained FunkyGames Swagger and RSG Markdown cases are the current executable
full-parity replays; each other restored source snapshot must meet this same contract
rather than a lower, source-availability-dependent bar.

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
- OpenAPI 3.1 validity and the exact structural count snapshot;
- critical operations, provenance, examples, and integration contracts;
- preparation, scoring, diff, and Foundry behavior exercised by the case.

These assertions execute only when the original, dated
`benchmarks/<case>/sources/` snapshot **and** the passing
`benchmarks/<case>/source-quality/` audit package generated from it are both
present — `assemble` requires the audited package. If either is absent, pytest
reports the source-backed assertions as skipped.

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
3. requires a `source-quality/` audit package for every required case, naming
   the missing ones before pytest runs;
4. requires the original PDF for every case in the source-derivation lane
   (below) to be restored into `raw/`, naming the missing ones before pytest
   runs;
5. runs `uv run pytest tests/test_benchmarks.py -q`; and
6. rejects the run if pytest reports any benchmark skip.

“Strict-local passed” therefore means every required case had a source
snapshot and its audit package, every source-derivation-lane case had its
original PDF restored into `raw/`, all source-backed benchmark checks ran, and
no skip was reported.

## Supplemental sanitized-fixture lane

When an original historical snapshot cannot be redistributed, CI may exercise
a separately reviewed, redistributable subset containing only the exact source
fragments needed by committed extraction claims. Run:

```bash
uv run python scripts/quality_gate.py --sanitized-fixtures
```

This is an orthogonal CI assurance, not a fifth source-backed harness layer and
not a replacement for strict-local. Each admitted case must have:

- a reviewed entry in `SANITIZED_BENCHMARK_CASES`;
- `sanitized-fixture.json` binding the original URL, capture date, original
  SHA-256, sanitized SHA-256, retained line ranges, and
  `strict_local_eligible: false`;
- a line-preserving source under `sanitized_sources/`, so exact line locators
  retain their original coordinates while all unretained content is empty; and
- a passing legacy/Core shadow replay where every material relationship is
  explicit or derived support backed only by exact fragments.

The current pilot inventory contains `rsg-game-transfer-wallet`.
`test_required_sanitized_benchmark_cases_match_committed_descriptors` enforces
exact parity between the reviewed inventory and committed descriptors. The
sanitized replay proves only fixture-backed exact-evidence parity for the
retained claims. It does not prove that the full original document was
revalidated, restore an unavailable historical snapshot, or make the case
eligible for the phrase “strict-local passed.” The CLI rejects combining
`--strict-local` and `--sanitized-fixtures` so the two assurance claims cannot
be collapsed into one result.

## Supplemental PDF source-derivation lane

A case whose source is a PDF converts it via `preprocess` (pymupdf4llm) before its
local `sources/*.md` ever exists — that conversion step previously sat outside
every harness run. A PDF-derived case may commit `source-derivation.json`,
binding the original PDF (case-relative path under gitignored `raw/`, official
URL, capture date, SHA-256), the derived Markdown (case-relative path, SHA-256),
and the conversion tool by name. It never pins a tool version: `uv.lock` is the
sole authority for which pymupdf4llm runs (ADR 0013). The descriptor itself is
committed, but what it names is not: both `raw/` and `sources/` are gitignored,
so `derived_markdown.sha256` is the only tracked anchor for the Markdown the
harness actually reads.

This is not a fifth harness layer: it exercises the conversion step of the
existing Source-backed execution layer (§3) and grants no new evidence strength
— a declared case was already source-backed. `scripts/quality_gate.py::
SOURCE_DERIVATION_BENCHMARK_CASES` is a third reviewed inventory with the same
exact-set-parity rule as `REQUIRED_BENCHMARK_CASES` and
`SANITIZED_BENCHMARK_CASES`;
`test_required_source_derivation_benchmark_cases_match_committed_descriptors`
enforces it. `--strict-local` names a case whose original is missing from
`raw/` before it runs pytest. `tests/test_benchmarks.py` checks the local
Markdown's digest against the descriptor unconditionally, wherever that file
exists; when the original is also present in `raw/`, it additionally re-runs
`preprocess` over it and asserts the output is byte-identical to the local
Markdown. Only that re-derivation half SKIPs, like every other source-backed
assertion, when the original is absent.

The current inventory contains only `ecpay-creditcard-pdf`. `jili-legacy-gaming-pdf`'s
source is a supplier delivery with no public URL; it joins the lane only once that
file is available, and until then keeps exactly the evidence strength it already
had.

## Per-case attestation

Everything above grades the harness. None of it says, in one place a machine can
read, *which* level each individual case reached in one concrete run — and that
gap is exactly where "the benchmarks pass" gets written about a suite whose
source-backed assertions all skipped. Run:

```bash
uv run python scripts/benchmark_attestation.py \
  --mode ci-safe \
  --json-out out/benchmark-attestation.json \
  --markdown-out out/benchmark-attestation.md
```

The command is repository-level, non-interactive, and identical locally and in
CI. It is not part of `make verify`, which remains the only repository
completion contract; it produces evidence about a run, it does not gate one.

It reports every case in `REQUIRED_BENCHMARK_CASES` exactly once, from that list
alone — there is no second inventory to update — and for each case states the
assets it needs and whether they are present, which of committed, discovered,
prerequisites-unavailable, source-backed executed, sanitized-fixture executed,
exact-evidence parity and strict-local eligible/passed actually hold, and, kept
separate from all of that, whether the harness matched its expectation and
whether the resulting contract validation is `PASS` or `EXPECTED_FAIL`. An
`EXPECTED_FAIL` case can be conformant while its contract validation status
stays `FAIL`; the two are never collapsed. Harness conformance is tri-state,
because `false` has to mean the harness *contradicted* its expectation: a case
whose assertions never ran reports `not established`, never a conformance
failure and never a pass.

What actually executed is read from one pytest run's JUnit XML, never from
pytest's prose, and a result is attributed to a case only by its parametrization
id. Three test names bind an assurance level to the check that establishes it —
`test_benchmark_case`, `test_case_obeys_declared_core_parity_contract` and
`test_sanitized_fixture_proves_fixture_backed_exact_evidence_parity` — and
`tests/test_benchmark_attestation.py` fails if one is renamed, so a rename can
never silently downgrade every case to "nothing was established". Exact-evidence
parity in particular comes only from a replay *result*: every committed case
declares `require_exact_evidence_for_all_material_claims`, and that declaration
is what a case must meet, never evidence that it did.
`scripts/quality_gate.py::EXACT_EVIDENCE_PARITY_BENCHMARK_CASES` is a fourth
reviewed inventory in the same family as the three above, naming the cases with
an executable full-parity replay today.

The JSON is `benchmark-attestation/v1`, validated against a strict schema in
which an unknown field fails closed, and it binds the repository commit and
worktree state, the `loop-apidoc` version, the execution mode, and the
`core-parity`, `sanitized-fixture` and `source-derivation` contract versions.
The Markdown carries the same per-case status and the same reasons. Ordering is
deterministic and the report holds no wall-clock timestamp, so the same
revision, assets and execution results render the same document.

The command fails closed and writes nothing on a malformed, missing, stale,
tampered or self-contradictory input — an unreadable expectation, a
`current_status` that is neither `PASS` nor `FAIL`, a `core-parity.json` at the
wrong schema version or disagreeing with the expectation, a sanitized subset
whose bytes no longer match its recorded digest, a locally stale derived
Markdown, or a descriptor path escaping its case directory. Output paths are
created with `O_EXCL | O_NOFOLLOW`: an existing file or a symlink is refused, and
because the document is complete before the first byte is written a refusal
leaves nothing that could be mistaken for a result.

The report is governance evidence and never carries supplier material. Source
content and excerpts are never read into it, paths are case-relative so no local
absolute path is persisted, declared source URLs go through `redact_url`, and
any text derived from the pytest subprocess is stripped of URLs, filesystem
paths and credential-shaped values before it is stored.

On a machine without the private supplier snapshots every case correctly reports
`prerequisites unavailable`. That is the honest result, and it is never a
source-backed PASS.

## Acquisition paths outside the harness

The four layers grade *cases*. They say nothing about an acquisition path that no case
uses, and every case's sources are `.md`, `.json`, or `.yaml` — so several shipped
commands have never carried a real supplier source through this harness at all. Two
distinct states hide behind that, and they must not be described with one word, because
what would fix them differs.

**Not validated against a real source.** The code is complete and unit-tested; no case has
used it. `import-supplementary-note`, `import-rendered-url`, `select-url`,
`related-url-pages`, and the `.docx` preprocessing path are here. What is missing is a
source: the first real delivery that travels this path becomes a benchmark case and the
label goes away with it. `import-supplementary-note` is the sharpest instance, because its
output moves the validation report's per-claim `SUPPLEMENTARY_SUPPORT` warnings and the
document-quality score's source grounding — a path that changes the score, with no case.

**Outside the harness by construction.** `catalog-url`, `cache-url-pages`/`cache-url-entry`,
`snapshot-openapi-url`, and `cache-gitbook-llms` issue network requests, and a harness run
must be offline-reproducible. No quantity of real sources changes that; what is missing is a
mechanism — a replayable recording contract that stores responses as fixtures so a case can
re-run without the network. `cache-gitbook-llms` is in both states at once: no real GitBook
site has gone through end to end, and it is itself a network acquisition.

A path in either state is never described as validated, and a synthetic fixture is never
written to erase a label — the label exists precisely because no real source has arrived.
`normalize-html-snapshot`, `preprocess` (PDF), and `manifest` are not in this section: each
carries a real supplier source in at least one case.

The grading above is prose, and prose is what went unmaintained when `.docx` and GitBook
were labelled in #99 and the remaining six paths were not. The machine-readable truth is
`scripts/quality_gate.py::SOURCE_ACQUISITION_EVIDENCE_TIERS`, paired with
`NON_ACQUISITION_CLI_COMMANDS`, which names every other CLI command and why it acquires
nothing. A command carries every label its branches earn rather than the strongest one:
`preprocess` is source-backed for PDF and un-validated for `.docx`, and `cache-gitbook-llms`
is in both un-validated states. Together the two mappings classify **every** registered
command, sub-app commands included under their full invocation, and
`test_every_cli_command_is_graded_or_explicitly_excluded` fails on either direction of
drift: a new command in neither mapping, or a mapped command the CLI no longer registers.
The criterion the split follows — a command is an acquisition path when it brings supplier
material into the local, manifest-bindable corpus, or establishes that corpus — is written
beside the list, so the boundary is not something a reader has to reconstruct. The tables in
both READMEs and both operator manuals are the human-readable presentation and are checked
against the list by `tests/docs/test_acquisition_evidence_tiers.py`; they are never
generated from it.

## Terminology

Use these terms consistently in issues, release notes, and review comments:

| Term | Meaning |
| --- | --- |
| **Committed** | The fixture identity files exist in the repository. |
| **Discovered** | The harness enumerated the committed fixture. |
| **Skipped** | Source-backed assertions did not execute because the required source snapshot was unavailable. |
| **Passed** | The applicable assertions executed and passed. |
| **Strict-local passed** | Every required case had sources, all source-backed benchmark checks ran, and no skip was reported. |
| **Sanitized-fixture exact-evidence passed** | A reviewed redistributable subset replayed the retained claims with exact fragment support; this is not source-backed or strict-local success. |
| **Not validated against a real source** | A shipped path whose code is complete but which no benchmark case has ever used; the first real source along it becomes a case. |
| **Outside the harness by construction** | A path that issues network requests, so no offline-reproducible case can exercise it until a replayable recording contract exists. Never interchangeable with the row above. |
| **Prerequisites unavailable** | A required case's `sources/`, `source-quality/`, or required original document is absent, so no source-backed assertion could execute. |
| **Attested** | A per-case `benchmark-attestation/v1` report recorded which assurance level each case reached in one bound run; the attestation reports assurance, it never raises it. |
| **Source-derivation verified** | A PDF case's local Markdown matches the SHA-256 recorded in its committed `source-derivation.json`, and — when the original PDF is also present locally — was re-derived byte-identically from it; this is part of the existing source-backed layer, not new evidence strength. |

Do not shorten “committed and discovered” to “validated,” and do not describe
a CI run containing source-related skips as benchmark success.

## CI-safe and local commands

| Command | Layer verified | Source snapshots required |
| --- | --- | --- |
| `uv run pytest tests/test_benchmarks.py -k test_benchmark_harness_discovers_cases -q` | Discovery guard | No |
| `uv run pytest tests/test_quality_gate.py -k required_benchmark_cases_match_committed_cases -q` | Exact committed/required parity | No |
| `uv run python scripts/quality_gate.py` | CI-safe lint, unit/integration tests, discovery, and parity | No |
| `uv run python scripts/quality_gate.py --sanitized-fixtures` | CI-safe checks plus the reviewed sanitized exact-evidence lane | No; only committed sanitized subsets |
| `uv run pytest tests/test_benchmarks.py -q` | Source-backed execution for cases whose sources are present; absent sources skip | Yes, for a complete pass |
| `uv run pytest tests/test_benchmarks.py -k test_local_markdown_matches_recorded_source_derivation -q` | Source-derivation lane for PDF cases; Markdown digest checked whenever `sources/` is present, re-derivation additionally needs `raw/` | Yes: `sources/` for the digest check, `raw/` for re-derivation |
| `uv run python scripts/benchmark_attestation.py --json-out <path> --markdown-out <path>` | Per-case attestation of every layer reached in one run | No; unavailable prerequisites are reported as such |
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

`benchmarks/<case>/source-quality/` holds the audit package derived from that
snapshot (`manifest` → `inspect-source-risk` → `assess-sources`, see
`benchmarks/README.md`); it is regenerable and likewise gitignored.

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

7. Update the case count where the documents spell it out, and run:

   ```bash
   uv run pytest tests/docs/test_benchmark_case_count_in_docs.py -q
   ```

   That test reads the number back out of every current document and compares it
   to `REQUIRED_BENCHMARK_CASES`. Release notes and ADRs are named separately and
   pinned to the count they recorded: each states what was true or measured when
   it was written, so it must not be updated to today's number.

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
   inventory 與 committed fixture 完全一致、每個 case 都有非空來源、source-derivation
   lane 裡的每個 case 都已把原始 PDF 還原到 `raw/`，且 benchmark 測試零 skip。

另外有一條獨立、不可混稱為第五層的 sanitized-fixture CI lane：
`scripts/quality_gate.py --sanitized-fixtures` 只重播經審核、可重新散布、保留原始行號的
exact-evidence 片段。它會驗證 retained claims 的 legacy/Core parity，但不代表完整原始文件
已重新驗證，也不能稱為 source-backed 或 strict-local PASS。目前 pilot 是
`rsg-game-transfer-wallet`；受控清單與 descriptor 必須 exact parity。

另有一條同樣不算第五層的 PDF source-derivation lane：PDF 來源的 case 可額外提交
`source-derivation.json`，記錄原始 PDF（case 相對路徑，位於 gitignored 的 `raw/`、官方
URL、取得日期、SHA-256）、導出的 markdown（case 相對路徑、SHA-256）與轉檔工具名稱——
不釘版本號，因為 `uv.lock` 才是 pymupdf4llm 版本的唯一依據（ADR 0013）。描述檔本身入庫，
但它記錄的原始 PDF 與 markdown 都不入庫——`raw/` 與 `sources/` 都是 gitignored，
`derived_markdown.sha256` 才是唯一入庫的錨點。它只是把既有
「來源支撐執行」層裡本來沒被重跑過的 `preprocess` 步驟補進迴圈，不代表新的證據強度。
`scripts/quality_gate.py::SOURCE_DERIVATION_BENCHMARK_CASES` 是第三份受控清單，與既有
兩份同樣要求 exact set parity；`--strict-local` 會在跑 pytest 前先點名缺少原始 PDF 的
case。`tests/test_benchmarks.py` 只要本機 `sources/` 存在,就無條件比對其 SHA-256 與描述檔；
`raw/` 的原始檔也在時,才追加重跑一次 `preprocess`,斷言產出與本機 markdown 逐位元組相同——
只有重跑 preprocess 這半段,才比照其他來源支撐斷言在原始檔不在時 SKIP。目前只有
`ecpay-creditcard-pdf` 在此清單裡，`jili-legacy-gaming-pdf` 是供應商交件、沒有公開 URL，
要等拿到檔案才會加入。

另有一份不屬於任何一層、也不改變任何證據強度的逐案例證據報告:
`uv run python scripts/benchmark_attestation.py --json-out <路徑> --markdown-out <路徑>`。
它以 `REQUIRED_BENCHMARK_CASES` 為唯一名單,每個 required case 恰好出現一次,列出該案例
需要哪些資產、是否存在,並分別標示 committed、discovered、缺少前置條件、source-backed 已
執行、sanitized-fixture 已執行、exact-evidence parity,以及 strict-local 是否合格/通過;
harness 是否符合預期與產出的契約驗證是 `PASS` 還是 `EXPECTED_FAIL`,則分開陳述 ——
`EXPECTED_FAIL` 案例可以同時是 harness 相符與契約驗證 `FAIL`,兩者永不合併。已執行與否來自
一次 pytest 的 JUnit XML,不解析人類輸出;exact-evidence parity 只由實際重播結果建立,不從
`core-parity.json` 的期待值推測。JSON 是 `benchmark-attestation/v1`,以嚴格 schema 驗證
(未知欄位一律失敗),並綁定 repository commit、`loop-apidoc` 版本、執行模式與相關契約版本。
輸入若毀損、缺漏、過期、被竄改或自相矛盾,命令非零退出且不留下任何輸出;輸出路徑以
`O_EXCL | O_NOFOLLOW` 建立,既有檔案或 symlink 一律拒絕。報告本身不保存供應商內容、來源片段、
未遮罩憑證 URL 或本機絕對路徑。它不是 `make verify` 的一部分 —— `make verify` 仍是唯一的
完成門檻。在沒有私有來源快照的機器上,每個案例都會如實標記為「缺少前置條件」,那不是
source-backed PASS。

新增 case 時，先加入 extraction／expected 宣告，再刻意更新
`REQUIRED_BENCHMARK_CASES`，跑 exact-parity 測試，最後才在持有原始來源快照的機器上
跑 source-backed 與 strict-local。找不到歷史來源時，不得用新版文件、合成資料或錯誤
頁面頂替；應記錄缺口、跑確定性 CI 檢查，並對本次變更做合法的來源支撐 spot-check。
