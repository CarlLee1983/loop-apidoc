# Product Extension Roadmap

**Status:** In progress — exact-evidence v1 boundary slice, the first evidence-first review slice, and governance source snapshotting are delivered; Core graduation remains proposed. The preprocess collision maintenance item was delivered on 2026-07-24.
**Updated:** 2026-07-24

## Purpose

This roadmap records the next product extensions for `loop-apidoc` beyond its
current use as a source-grounded API-document analysis and generation pipeline.
It is a prioritisation aid, not a commitment to ship every item. All work here
remains constrained by the product's non-negotiable rule: source material is
the only authority for factual API claims; an unstated value must remain a gap
or `null`, never be inferred from convention.

## Current foundation

The repository already provides more than document conversion:

- bounded and reproducible source acquisition for local files, URLs, GitBook,
  and direct OpenAPI snapshots;
- deterministic assembly, validation, scoring, source quality, and run diffs;
- source freshness fingerprints and batch checks;
- derived developer handoff material (Postman collection, SDK hints, and
  integration tasks);
- Foundry candidate/version/current-asset governance and a local review
  workbench; and
- a model-independent `domain/`, `core/`, and `evaluation/` architecture,
  currently exercised by the CLI through observational `--architecture-mode
  shadow` compatibility work.

The following priorities build on those foundations instead of duplicating
them.

## Recommended sequence

### 1. Make exact evidence first-class, then graduate Core

**Goal:** move from legacy document-level citations to deterministic,
claim-level support backed by exact source fragments.

The Canonical API Contract architecture already models the required trace:

```text
claim identity/path → relationship → exact evidence fragment → source artifact
```

However, the shipping agent-native extraction boundary is still a compatibility
adapter. When a legacy citation names only a document, the shadow bridge must
degrade it to `insufficient` or unverified support. The first strategic
extension is therefore to make a precise evidence locator and normalized
fragment digest part of the reviewed extraction contract, resolve it through
the existing fragment adapter, and require deterministic verification before a
claim is treated as explicitly supported.

After representative benchmark coverage proves parity, introduce a production
Core execution mode alongside shadow. Promote it only when its generated
projections and governance outcomes are demonstrably compatible with the
existing deterministic pipeline.

**Why first:** exact evidence is shared infrastructure for review, governance,
evaluation, and any future Core cutover. Building those features on weaker
whole-document citations would duplicate trust logic and make later migration
more expensive.

**Initial deliverables:**

1. A versioned extraction evidence-reference schema: source identity, typed
   locator, extracted fragment digest, and claim path.
2. A deterministic materialisation/verification step using
   `adapters/fragments.py`, with fail-closed diagnostics for stale, ambiguous,
   or unmatched references.
3. End-to-end benchmark cases covering explicit support, derived support,
   contradiction, and insufficient support.
4. A non-default Core execution mode with output parity comparisons; retain
   shadow until the cutover criteria have been accepted.

**Progress (2026-07-23):** extraction now accepts optional v1 `evidence[]`
references containing exact manifest source identity, typed locator, normalized fragment
digest, and material claim path. `verify-extraction` and `assemble` materialize and
verify supplied references and resolve the path against the normalized claim before a run
directory exists; shadow uses a verified reference
for its declared claim path instead of legacy fallback. This is the first boundary slice,
not Core graduation or benchmark-parity acceptance.

**Evidence relationship coverage (2026-07-23):** the evaluation replay layer now has
fixed, versioned end-to-end cases for `explicit_support`, `derived_support`,
`contradicts`, and `insufficient`. Its metrics include exact typed-relationship
classification accuracy, so an unsupported reference cannot look successful merely
because support-only metrics ignore it. These deterministic cases validate Core
semantics; they are not yet representative source-benchmark parity or a Core cutover.

**OpenAPI structural derivations (2026-07-23):** v1 exact JSON Pointer evidence can
now propose versioned mappings for operation path/method, response status, local
response/request-schema `$ref` names, and request-body property names with array
markers. A field behind one `items.$ref` additionally requires two declared exact
fragments—the parent reference and child property—which Core links and re-digests before
deriving the dotted array field. Malformed, mismatched, or incomplete inputs remain
insufficient.

**FunkyGames source-backed parity (2026-07-23):** the retained Swagger snapshot now has
exact v1 evidence for every material claim: all 27 operations, 95 request-body fields and
required flags, and all schema fields, including bounded one- and two-hop component-ref
chains. The replay result is legacy `passed` / Core `accept`, with 92/92 Core claims
supported and zero insufficient relationships. This proves one source-backed benchmark;
it is not the product-wide cutover: six historical benchmark source snapshots are still
unavailable for the required strict-local zero-skip parity gate, and five restored cases
still need claim-complete exact-evidence parity.

**RSG source-backed parity (2026-07-23):** the operator supplied the original RSG
documentation URL. Its fetched raw HTML has the same SHA-256 as the historical RSG
snapshot, and normalization produces a structured, line-addressable Markdown derivative.
The benchmark now binds all 33 material claims to verified v1 fragments and replays as
legacy `passed` / Core `accept`, with zero unverified claims. For prose-only fragments,
the claim-level binding is recorded as `CLAIM_BOUND_EXACT_REFERENCE`; it is fail-closed on
source identity, locator, digest, and claim path, while a legacy page/line citation remains
insufficient. This clears RSG only; it does not substitute a newer source for any of the
six unavailable historical snapshots or lower the parity bar for the five other restored
cases.

### 2. Continuous source and contract governance

**Goal:** turn one-off analysis runs into a controlled update cycle.

The required primitives already exist: `record-fingerprint`,
`check-freshness`, `check-freshness-batch`, run-to-run `diff`, Foundry
candidate import, and human approval. A new orchestration layer can connect
them without automatically publishing a contract:

```text
scheduled freshness check
  → source-change alert and reproducible evidence snapshot
  → agent/human extraction review
  → assemble and impact diff
  → Foundry candidate and explicit human approval
```

Source change detection must never regenerate or approve a contract by itself;
it only creates a bounded review trigger.

**Progress (2026-07-24):** `governance-scan` now translates an existing
`freshness-watchlist.json` batch scan into a persisted `governance-trigger.{json,md}`
report. Changed sources are `review_required`; unreadable or inconclusive items are
`attention_required`. The command deliberately performs no extraction, generation,
Foundry import, or approval. It is the bounded trigger at the start of the proposed
cycle; reproducible source snapshotting and the subsequent human/agent workflow remain
future slices.

**Reproducible source snapshotting (2026-07-24):** `governance-scan --snapshot-dir`
now retains only the raw bytes classified as changed in that same scan, as an immutable,
content-addressed evidence pack (`governance-snapshot.json` plus `sources/<sha256>.source`).
This avoids a second fetch between detection and review; unchanged, inconclusive, and failed
sources are not represented, and the command still performs no extraction, generation,
Foundry import, or approval. Re-extraction and explicit human approval remain separate future
steps.

### 3. Evidence-first review experience

**Goal:** shorten human verification without weakening approval authority.

Extend the local review workbench so a reviewer can navigate from an OpenAPI
field, validation finding, or run diff to its claim relationship and exact
source fragment. The workbench should surface missing, conflicting, and
insufficient evidence as such, rather than hiding it behind a confidence score.
Structured review decisions and policy-bound, expiring waivers may be added,
but a waiver must never convert unsupported source material into a supported
claim.

**Progress (2026-07-24):** the local Foundry review workbench now attaches
Core evidence relationships to validation findings with the same OpenAPI target.
Reviewers can expand `explicit_support`, `derived_support`, `contradicts`, or
`insufficient` relationships
to see the exact fragment locator, normalized-fragment digest, and retained
excerpt, and can open the retained `core/evidence.json` and
`core/projections/review-data.json` artifacts. These artifacts participate in
the review binding digest, so an existing decision becomes stale if its
evidence changes. Operation-level HTTP diffs map to evidence only when their
method/path location has one exact Core target; field-level or otherwise
ambiguous diffs deliberately remain unlinked. Waivers remain a future slice.

### 4. Downstream engineering enforcement

**Goal:** let consuming teams safely act on approved contracts.

The existing `handoff/` pack is a starting point. Add optional adapters that:

- generate contract-test scaffolds only from explicitly documented requests,
  responses, and test cases;
- expose a CI-friendly gate over the Foundry current asset and classified
  breaking changes; and
- create reviewable downstream update tasks when a contract version changes.

These outputs remain derived aids. `openapi.yaml` and the integration contract
continue to be the contract sources; secrets, undocumented test data, and
expected behavior must remain explicit gaps.

### 5. Runtime evaluation laboratory

**Goal:** compare extraction runtimes rigorously before they influence
production proposals.

`evaluation/` already has immutable evaluation cases, replay, claim and
relationship metrics, plus cost and latency comparison. Complete this as an
operator-facing evaluation workflow: versioned cases, repeatable runtime runs,
and reports that compare precision, recall, support-relationship accuracy,
cost, and latency. Evaluation stays isolated from production mutation and
approval.

## Near-term maintenance item

**Delivered (2026-07-24):** `preprocess` now preserves source-relative paths for
directory inputs, and writes `guide.pdf` as `guide.pdf.md`; this avoids both
cross-directory basename collisions and PDF/Markdown sibling collisions. It
validates the complete output mapping before writing and fails clearly if a
remaining derived-name collision exists.

## Defer protocol expansion until its seam is designed

Do not add GraphQL or AsyncAPI as conditional branches in the current
HTTP/OpenAPI-oriented model. First introduce a clear protocol/transport seam in
the Canonical API Contract IR, then implement protocol-specific adapters and
projections behind that interface. Supporting a second protocol is justified
only when there are real source sets and downstream consumers for it.

## Decision rule

Start with priority 1. It adds the evidence precision that every subsequent
extension needs, while retaining the product's fail-closed source-grounding
guarantee. Priorities 2 through 5 can be planned independently after their
shared evidence contract is established.

---

## 繁體中文摘要

這份文件記錄 `loop-apidoc` 在「來源依據式 API 文件分析／生成」之外可延伸的產品方向。
所有延伸均受同一原則約束：來源沒有明示的資訊，一律保留為缺口或 `null`，不可用慣例推測。

1. **先讓精確證據成為 extraction 正式契約，再逐步讓 Core 接管。**
   目前 CLI 的 legacy citation 常停留在文件層級；應加入來源 identity、locator、fragment
   digest 與 claim path，經由 deterministic fragment verification 才能取得
   `explicit_support`。這是 review、governance、evaluation 與 Core 正式切換的共同基礎。
2. **持續性的來源與契約治理。**
   已有 freshness、diff、Foundry；可串成定期偵測來源變更、建立審核觸發、重新擷取、比較
   impact、人工核准的流程。偵測到來源變更不可自動發布契約。
3. **證據優先的人工審核介面。**
   讓 reviewer 從 OpenAPI 欄位、validation finding 或 diff 直接跳到 claim 與原文片段；缺漏、
   衝突、不足證據要如實顯示。waiver 不能把無來源支持的主張變成 supported。
4. **下游工程執行與 CI gate。**
   以既有 handoff 為基礎，加入只依明示契約產生的 contract-test scaffold、針對 Foundry
   current／breaking change 的 CI gate，以及可審核的下游更新工作。
5. **Runtime 評測實驗室。**
   利用現有 `evaluation/` 的 replay、準確度、成本與延遲衡量，完成可重複比較不同 runtime 的
   operator workflow；評測不可影響 production contract 或核准。

另有一個低風險維護項：修正 `preprocess` 將不同子目錄同名來源展平後可能覆寫的問題。

暫不直接加入 GraphQL／AsyncAPI；目前模型偏 HTTP/OpenAPI，應先在 Canonical API Contract IR
設計 protocol/transport seam，再以獨立 adapter 與 projection 支援第二種協定。

**建議順序：**先做第 1 項，因為它是後續所有擴充共享的可信證據基礎。
