# Design Decisions / 設計決策

**Status:** Current concise design record
**Updated:** 2026-07-23

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

The reviewed agent-native boundary additionally accepts optional v1 exact-evidence
references: exact manifest source identity, typed locator, normalized-fragment SHA-256,
and material claim path. Both extraction entry points materialize and verify a supplied
reference, then resolve its path against the shared normalized-claim projection before
creating a run directory. A reference owns its declared claim path in
Core shadow; deterministic Core comparison, rather than the agent's declaration, still
decides the relationship. Legacy `source` strings remain a compatibility input until
benchmark parity supports a production-Core cutover.

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
metadata only; it does not replace documentation review.

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
6. 擷取 gate、validation 與 no-speculation 規則一律 fail closed；分數、diff、freshness 與 preparation 是品質訊號，不是另一個事實來源。
7. Foundry 以候選、版本化 asset 與 `current` 管理契約；本機 review 工作台只在人工明確核准後升級，並如實標示 `needs_follow_up`。
8. benchmark、release 與對外文件都是產品契約；來源快照缺失或測試 skip 都不能宣稱通過。
