# Design Decisions / 設計決策

**Status:** Current concise design record
**Updated:** 2026-07-30

This document is the durable record of product-level decisions for `loop-apidoc`.
It replaces the former collection of dated implementation plans and design notes.
Detailed delivery history remains available through Git; this document records the
decisions that continue to constrain the product.

## Purpose and authority

`loop-apidoc` transforms heterogeneous API-integration materials into a traceable
API-contract package: OpenAPI 3.1, a Traditional-Chinese integration guide,
provenance, validation reports, review material, and optional governed assets.
It is an evidence-to-contract system, not a convention-based API generator.

Supplier source material is the only authority for factual API claims. If a source
does not establish a value, the product records a gap or `null`; it does not infer a
REST convention, OAuth flow, request field, response shape, or operational guarantee.
Deterministic validation must fail closed when required information is missing,
conflicting, or unsupported.

## Enduring decisions

### 1. Separate product architecture from runtime adapters

The stable product architecture is:

```text
Evidence Ledger
+ Grounded Claim Graph
+ Canonical API Contract IR
+ Deterministic Assurance Engine
+ Governed Contract Registry
```

`domain/` owns the API ontology, canonical identities, immutable contract IR,
deterministic rules, and projections. `core/` owns evidence, claim reconciliation,
lifecycle and governance policies, use cases, and typed ports. `adapters/` owns
replaceable runtime details such as agents, parsers, local files, databases,
registries, and user interfaces. `evaluation/` owns immutable cases and
quality/cost/latency measurement; it cannot mutate or approve production assets.

Core and Domain do not perform filesystem, network, process, browser, model, or
database I/O. Runtime output is always a proposal. Deterministic reconciliation and
policy decide its lifecycle state.

### 2. Keep an exact evidence-to-claim chain

Evidence uses exact, typed fragments with locators and normalized-content digests. A
material claim binds to evidence through one of `explicit_support`,
`derived_support`, `contradicts`, or `insufficient`. The full trace is:

```text
claim identity/path → relationship → exact fragment → source artifact
```

A legacy whole-document citation is only `insufficient`; confidence scores or the
presence of an evidence ID never convert it into grounded support. OpenAPI, the
generated guide, and review data are projections of the Canonical API Contract IR,
never the source of truth.

Core metadata preserves a source-unstated document/API version as `null`. An
OpenAPI projection may emit the format-required `0.0.0` placeholder only with
`x-loop-status: missing-source`; the placeholder is never a source-stated
version or Core contract value.

`derived_support` is limited to versioned, allowlisted transformations that
Core recomputes from exact fragments and verifies with an input/output digest
chain. The current OpenAPI JSON Pointer mappings are operation path/method,
response status, local response/request schema `$ref` names, and request-body
property names (including array markers), plus schema-field name/type/required
facts. One local component `$ref` requires the child property or schema and its
parent context reference. The only deeper exception is an explicitly ordered,
two-hop array chain; Core receives every hop as an exact fragment and never
follows references implicitly. A malformed pointer, external/non-schema `$ref`,
incorrect claim path, missing or reordered context, or any digest mismatch is
`insufficient`; the adapter cannot promote it to support by declaration.

The reviewed agent-native boundary additionally accepts optional v1 exact-evidence
references: exact manifest source identity, typed locator, normalized-fragment SHA-256,
and material claim path. Both extraction entry points materialize and verify a supplied
reference, then resolve its path against the shared normalized-claim projection before
creating a run directory. A reference owns its declared claim path in
Core shadow. Structured JSON Pointer/table-cell evidence is compared to its parsed value.
For prose with no parsed value, a verified v1 binding is retained as the auditable
`CLAIM_BOUND_EXACT_REFERENCE` relationship: exact source identity, typed locator,
fragment digest, and one material path must all match. It is not available to legacy
source strings, and an agent must not bind a convention, default, or inference as source
evidence. Legacy `source` strings remain a compatibility input until benchmark parity
supports a production-Core cutover.

### 3. Preserve the agent-native CLI as a compatibility adapter

The shipping extraction path is agent-native. The current coding agent reads sources,
coordinates read-only endpoint, inventory, and integration work, and writes the
reviewed `inventory.json` plus `endpoints/*.json` boundary. The CLI then performs the
deterministic `manifest → plan → generate → validate` back half.

`assemble` never extracts. It verifies the agent-written extraction boundary, reports
structured results through `--json`, and leaves any correction loop to the agent.
Model selection, prompt topology, run-directory shape, and command layout are runtime
choices, not product invariants.

The portable `skills/loop-apidoc/SKILL.md` remains the cross-runtime operating guide
for Claude Code and Codex. It uses the `<APIDOC>` command placeholder and
runtime-neutral descriptions of agent actions.

### 4. Make every production gate deterministic and fail closed

The extraction gate validates schemas, source references, endpoint identities,
cross-file references, source-fact completeness, and deferred-placeholder answers
before a run directory exists. Generation derives all outputs from the normalization
plan. Validation governs structure, completeness, consistency, and no-speculation
requirements by severity: a run fails whenever it has an `error` issue.

No in-code automatic correction loop may invent values. Agents re-read the relevant
source, revise the extraction JSON, and reassemble; unresolved source gaps and
conflicts remain visible.

Supplier document content is also untrusted model input. The compatibility workflow must
therefore finish acquisition/preprocessing, build a manifest for the exact readable package,
and pass deterministic `inspect-source-risk` before any router, quality reviewer, or extractor
reads source-derived text. The inspector supports bounded UTF-8 Markdown, HTML, and OpenAPI
JSON/YAML; PDF, Word, invalid UTF-8, oversized text, and other unscannable pending sources fail
closed until converted and re-manifested. It never rewrites evidence or echoes a matched payload.

The audit contract is versioned and source-bound: schema/ruleset, `max_bytes`, manifest digest,
per-source SHA-256, and a stable source-binding digest are all checked.
`assess-sources --source-risk` reinspects current bytes and embeds the matching verified audit
in the quality report, and `assemble --source-quality` repeats that deterministic inspection
and revalidates its stable binding against the newly built manifest
before creating a run directory. Risk findings govern whether text may enter model context;
they are not evidence for an API claim and do not become another source of factual truth.

### 5. Keep evidence acquisition bounded and reproducible

URL navigation first creates a bounded catalog, then explicitly selects URLs, then
caches material as local evidence. Cataloging never widens into implicit link crawling.
Cached pages retain URL, timestamp, SHA-256, extracted metadata, and coverage
information. Unrendered SPA pages receive a deliberately narrow same-origin OpenAPI
probe; non-spec responses are not treated as API evidence.

GitBook acquisition uses one `llms.txt` index, safe same-origin path filtering,
immutable sidecars, and explicit coverage. Markdown drafts and extraction scaffolds are
line-cited, non-authoritative review aids. They never replace agent source review or
become blessed extraction input without review and completion.

### 6. Keep quality signals informative, not an alternate truth source

Source-quality assessment rejects unusable source sets before assembly. Source facts
supply a conservative semantic-completeness check only when a source has reliably
structured Markdown. Preparation reports, deterministic scores, version diffs, and
freshness reports help an operator understand readiness and change; they do not
fabricate claims or silently change validation semantics.

Source-unstated deployment details such as a concrete server URL, authentication
details, or sandbox credentials remain structured governance gaps. Their absence from
an API document alone is not an integration-risk conclusion: review projections retain
their type, area, detail, and status so teams can manage them continuously and apply
risk interpretation in the downstream integration context.

The optional `--architecture-mode shadow` runs legacy manifest/plan input through the
model-independent Core and writes observational artifacts under `core/`. Shadow success
or failure never changes legacy validation, score, approval, run status, or exit code.

### 7. Govern approved contracts without mutating them

Foundry imports a completed run as a candidate, and explicit approval copies it to a
self-contained versioned asset before updating the deterministic `current` pointer. The
product never rewrites a candidate's OpenAPI, integration contract, provenance,
validation report, or generated review page during governance.

The local `review` workbench is loopback-only, token-protected, and single-user. It
compares a candidate with the current asset (or a baseline), persists a structured
decision and handoff bound to exact artifact digests, and requires an explicit human
approval to promote the candidate. Validation failures, low scores, high-impact
differences, and unresolved work may be approved only as `needs_follow_up`; they never
become a false validation pass.

### 8. Treat benchmarks, releases, and documentation as contracts

Benchmark fixtures have an explicit reviewed inventory. A skipped source-backed case is
not a pass, and only a zero-skip strict-local run can be reported as such. Never replace
unavailable historical source snapshots with newer, synthetic, or error-page content.

Any user-visible command, output, workflow, or governance change updates its teaching
and operator documentation in the same change. Release automation synchronizes version
metadata only; it does not replace documentation review. A change that introduces a
subsystem, changes product direction, or changes roadmap priority must also update the
relevant strategy documents. Every release note explicitly selects either no strategy
impact with a reason or lists the updated strategy documents; release publication fails
before external actions when that declaration is unresolved.

### 9. Make silent source and response omissions observable

Coverage is bidirectional. Provenance must reject claims that lack source support, and
validation must also warn when a supported, readable source contributes no material
citation. The generated guide distinguishes all run inputs from sources actually cited.
Successful path responses that contain no usable schema fields remain valid OpenAPI but
surface as completeness warnings; score reports publish operation, hollow-operation, and
response-field counts without changing the validation severity gate.

Source-stated global and cross-endpoint business rules belong in `operational[]`.
Optional `applies_to[]` references are resolved against real operations and structural
fields at the extraction boundary. The always-written `integration-contract.json`
preserves these rules as a downstream machine contract instead of requiring SDK tooling
to rebuild them from the human Markdown guide.

Stable wallet/payment semantics use dedicated typed collections in optional
`integration.json`: `transport[]`, `amount_direction[]`, `idempotency[]`, and
`line_currency_policy[]`. Their operation references resolve at the extraction gate,
their claims enter the canonical projection, and every output entry retains source and
provenance links. The source-only invariant still wins over a plausible domain
inference: a request without a currency field does not establish a single-currency
line. Without an explicit policy statement, `policy` remains `null` and the uncertainty
is recorded in `missing`.

### 10. Keep a domain-neutral core and make payment an optional profile

`loop-apidoc` remains a general source-grounded API contract product. Payment and
wallet documents are an important initial vertical, not the definition of the whole
product. Transport policy and idempotency are general integration semantics;
amount direction and line-currency policy belong to an optional Payment Profile.
The Canonical Contract stores those two collections only inside `PaymentProfile`;
legacy top-level names are derived compatibility views, never parallel state. A
contract with no payment semantics has no profile.

New industry-specific typed concepts enter a profile only when they recur across
providers, have a named downstream consumer, cannot be represented faithfully by an
existing generic constraint, and have source-backed benchmark coverage. They never
become required facts for contracts outside that profile. The accepted rationale and
compatibility consequence are recorded in
[ADR 0001](adr/0001-keep-a-general-core-with-payment-profile.md).

### 11. Freeze protocol integration until a named consumer establishes demand

Keep `GraphqlProjectionCompiler` and `AsyncApiProjectionCompiler` as deterministic,
tested Core seams. Do not expose a GraphQL/AsyncAPI CLI, run directory, validation path,
diff/score behavior, or Foundry lifecycle until a named downstream consumer supplies a
real source set and an explicit acceptance contract. Do not add protocol conditionals to
the HTTP/OpenAPI extraction or generation compatibility adapter.

The public GitHub and OGC fixtures establish format-level compiler testability only.
They do not establish product demand, end-to-end exact-evidence coverage, or adequate
format validation. Resuming integration requires recording the consumer and its source-
backed acceptance criteria here or in a dedicated ADR before implementation begins.

## Canonical operational references

- [Architecture](ARCHITECTURE.md) — component boundaries, data flow, and seams.
- [Correction loop](CORRECTION_LOOP.md) — operator response to validation issues.
- [Benchmark validation plan](BENCHMARK_VALIDATION_PLAN.md) — benchmark contract.
- [Release checklist](RELEASE_CHECKLIST.md) — release and documentation checks.
- [Portable agent skill](../skills/loop-apidoc/SKILL.md) — source-grounded extraction
  workflow.
- [AGENTS.md](../AGENTS.md) — repository guidance, I/O boundaries, and package
  responsibilities.

---

## 繁體中文摘要

這份文件是 `loop-apidoc` 長期有效的設計決策摘要；歷史實作細節由 Git 保留。核心原則如下：

1. 供應商來源是唯一事實依據；未明示資訊一律保留缺口或 `null`，不可用慣例補寫。
2. 穩定產品架構以 Evidence Ledger、Grounded Claim Graph、Canonical API Contract IR、Deterministic Assurance Engine 與 Governed Contract Registry 為核心；runtime 是可替換 adapter。
3. 每一項 material claim 都必須可追到 exact evidence fragment；整份文件引用只能是 `insufficient`，不是來源支持。
4. 現行 agent-native CLI 是相容層：agent 擷取 JSON，CLI 確定性地組裝、生成與驗證；`assemble` 不擷取也不自動修正。
5. URL、GitBook、Markdown draft 與 scaffold 都是受限且可重現的證據輔助；draft/scaffold 絕不取代人或 agent 的來源覆核。
6. 擷取 gate、validation 與 no-speculation 規則一律 fail closed；分數、diff、freshness 與 preparation 是品質訊號，不是另一個事實來源。文件未提供 Server URL、authentication details 或 sandbox credentials 時，保留為可持續管理的治理缺口，不單憑缺席判定為整合風險。
7. Foundry 以候選、版本化 asset 與 `current` 管理契約；本機 review 工作台只在人工明確核准後升級，並如實標示 `needs_follow_up`。
8. benchmark、release 與對外文件都是產品契約；來源快照缺失或測試 skip 都不能宣稱通過。
9. coverage 必須雙向：無來源支持的 claim 要攔截，supported/readable 卻零實質引用的來源也要告警；成功 response 無可用 schema 欄位同樣要在 validation／score 可見。跨端點 operational 規則則透過驗證過的 `applies_to[]` 與固定產生的 `integration-contract.json` 交付下游；transport、金額方向、冪等與線路幣別使用專屬 typed collection，且 request 缺少 currency 欄位絕不視為單幣別證據。
10. 產品維持領域中立；支付／錢包是重要的首個垂直領域，但不是整個產品定義。transport policy 與 idempotency 屬通用整合語意，amount direction 與 line-currency policy 則屬選填 Payment Profile。新的產業專屬 typed concept 必須符合跨供應商重現、具名下游 consumer、無法由既有通用 constraint 忠實表達及具來源支撐 benchmark 等准入條件。
11. GraphQL／AsyncAPI 保留確定性、可測試的 Core compiler seam，但在具名下游 consumer 提供真實來源集與明確驗收契約前，凍結 CLI、run、validation、diff／score 與 Foundry 整合；公開 fixture 只能證明格式 compiler 可測，不能代替產品需求或端到端 exact-evidence coverage。
12. 供應商文件同時是 untrusted model input：來源取得／前處理後，必須對 agent 實際會讀的 manifest 綁定文字包執行 `inspect-source-risk`。報告不回顯命中 payload、不改寫來源，並由 schema/ruleset、大小上限、manifest／逐來源 digest 與 stable source binding 防止 stale reuse；`assess-sources` 內嵌 audit，`assemble` 在建立 run-dir 前重驗綁定。risk finding 決定文字能否進模型，不是 API claim 的事實證據。
