# Product Extension Roadmap

**Status:** In progress — exact-evidence parity is complete for 2 of 7 restored
source-backed benchmarks; 5 restored cases still need claim-complete parity and 6
historical snapshots remain unavailable. Releases 0.26–0.28 delivered bounded work
outside priority 1 while that cutover path was blocked; Core remains legacy/shadow.
**Updated:** 2026-08-02

## Purpose

This roadmap records the next product extensions for `loop-apidoc` beyond its
current use as a source-grounded API-document analysis and generation pipeline.
It is a prioritisation aid, not a commitment to ship every item. All work here
remains constrained by the product's non-negotiable authority split: supplier
sources are the sole authority for normative, provider-documented API claims;
an unstated value must remain a gap or `null`, never be inferred from convention.
Implementation observations are a separate empirical axis and apply only inside
their declared Applicability Envelope.

## Current foundation

The repository already provides more than document conversion:

- bounded and reproducible source acquisition for local files, URLs, GitBook,
  and direct OpenAPI snapshots;
- deterministic pre-agent source-risk inspection, assembly, validation, scoring,
  source quality, and run diffs;
- source freshness fingerprints and batch checks;
- derived developer handoff material (Postman collection, SDK hints, and
  integration tasks);
- Foundry candidate/version/current-asset governance and a local review
  workbench; and
- a model-independent `domain/`, `core/`, and `evaluation/` architecture,
  currently exercised by the CLI through observational `--architecture-mode shadow`
  and blocking exact-evidence `--architecture-mode strict` compatibility work; and
- passive normalized-JSON implementation feedback with a staged candidate/approval
  workflow plus pure conformance/amendment/exact-scope Effective Contract domain
  operations, without changing normative documentary support.

The following priorities build on those foundations instead of duplicating
them.

### Delivered authority boundary: implementation feedback and scoped effectiveness

The product now models Normative Contract, Implementation Observation, Applicability
Envelope, Conformance Finding, Compatibility Amendment, and Effective Contract as
distinct concepts. `ContractConformance` provides deterministic `assess`, `propose`, and
`compose` operations. The public workflow exposes `feedback assess`, `propose`, `submit`,
`review`, `approve`, `compose`, `current`, and `provider-erratum`. Assessment, proposal,
composition, and erratum handoff write outside `.foundry`; `submit` persists immutable inputs
as an explicit `candidate` case. `review` may append one non-approval decision and corrective
route with or without a proposal, while a separate independent-human `approve` appends
write-once approval/amendment records and publishes an immutable exact-scope Effective
release. No feedback command performs provider network I/O.

Proposal and Effective composition bind the digest of the complete Normative release:
canonical contract, documentary fragments, and support relationships. Exact-target current
resolution requires a timezone-aware as-of value and fails closed when the query precedes
approval/composition, the Effective release is expired, its base no longer matches normative
current, or the pointer/bounded artifact
digest is stale. Successful reads expose `valid_until`, `open_discrepancy_count`, and
`untested_material_claim_count`.

Documentary grounding and implementation conformance remain separate assurance axes.
An approved, expiring amendment is an exact-scope overlay with evidence and approval
lineage; it cannot rewrite its normative base. Effective composition accepts only active
amendments matching the complete target Applicability Envelope and rejects conflicting
applicable overrides. Same-target conflict is resolved only through an explicit same-scope
supersession link that preserves prior lineage. Normative and Effective releases remain
immutable: a new release records `supersedes`, then its matching pointer advances; prior
asset bytes are not rewritten. The global current pointer remains normative, while any
effective selection is deployment/scope-specific. Bounded verification reports the
envelope, time, suite version, material-claim coverage, open discrepancies, and stale
amendments instead of claiming universal or permanent 100% truth.

A formal Provider Erratum returns to the full supplier-source pipeline before it can
supersede a Normative Contract release. Unconfirmed observed behavior can affect only a
reviewed scoped Effective Contract. Passive normalized JSON is the only observation input
in this delivery; live probes, traffic capture, and vendor-specific adapters remain
deferred. Implementation-backed benchmark results remain separate from the source-backed
strict-local lane.

### Delivered security boundary: inspect untrusted source text before model use

The compatibility workflow now treats supplier documents as untrusted data before they
enter any agent context. After acquisition/preprocess, a manifest binds the exact readable
package and `inspect-source-risk` deterministically scans UTF-8 Markdown, HTML, and OpenAPI
JSON/YAML. Raw PDF/Word, invalid UTF-8, oversized text, and other unscannable pending sources
are blockers rather than implicit exceptions. Fixed findings identify only rules, source refs,
and locators; they never reproduce the matched payload or rewrite evidence. Reports retain at
most 1,000 findings and replace further matches with a fail-closed truncation blocker.

The versioned report records schema/ruleset, `max_bytes`, manifest digest, per-source SHA-256,
and a stable source-binding digest. `assess-sources --source-risk` verifies and embeds that
audit before extraction, and `assemble --source-quality` revalidates the embedded binding
against its rebuilt manifest before creating a run directory. This is a narrow prompt-injection
and hidden-control-text boundary for model-facing document text, not a malware scanner, content
moderation system, or new authority for API facts.

## Product and domain boundary

`loop-apidoc` remains a domain-neutral, source-grounded API contract product.
Payment and wallet integrations are an important initial vertical, but benchmark
composition does not redefine the Canonical Contract Core. Transport policy and
idempotency remain general integration semantics; amount direction and line-currency
policy belong to an optional Payment Profile governed by the same exact-evidence and
fail-closed rules. The Canonical Contract now owns those collections only through that
optional profile; v0.27 top-level names remain derived compatibility views rather than
parallel Core state.

An industry-specific typed concept is added only when it recurs across providers, has a
named downstream consumer, cannot be represented faithfully by an existing generic
constraint, and has source-backed benchmark coverage. The accepted boundary and the
compatibility treatment of the v0.27 collections are recorded in
[ADR 0001](adr/0001-keep-a-general-core-with-payment-profile.md).

## Delivery reconciliation through 0.28

The following releases were opportunistic deliveries while priority 1 could not clear
its benchmark gate. They preserved the source-grounded and fail-closed invariants, but
they did not advance Core production graduation:

- **0.26.0:** introduced the protocol-neutral `Interaction` seam and isolated,
  source-backed GraphQL SDL and AsyncAPI 3 projection compilers. They remain outside
  `assemble`, run artifacts, validation, and governance.
- **0.27.0:** added typed integration collections, operational applicability, bidirectional
  source-coverage warnings, and hollow-success-response observability. The payment-specific
  portion is now governed as an optional Payment Profile rather than a new product identity.
- **0.28.0:** added provenance-verified browser-rendered URL import and bounded
  `required_source_refs` capture guidance for sources that direct HTTP cannot obtain.

The maintained priority-1 count is therefore 13 committed benchmark cases: 7 currently
have local historical sources, of which FunkyGames and RSG have claim-complete exact
evidence; the other 5 restored cases still require parity work, and 6 historical
snapshots are unavailable. Sanitized fixtures may add a distinct CI-verifiable lane for
eligible restored sources, but cannot turn an unavailable original snapshot into a
strict-local pass.

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

**Bounded review handoff (2026-07-24):** `governance-review-plan` reads a persisted trigger
and verified immutable snapshot, rechecks every retained source digest, then writes a work-item
plan containing the changed source references, prior run reference, and required review steps.
It cannot fetch, re-extract, assemble, import, or approve a contract.

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
ambiguous diffs deliberately remain unlinked. Expiring waivers are now explicit
review-decision records, bound to a subject's supported exact claim and retained
with the governed asset; the UI refuses to apply them to insufficient or
contradictory evidence. A waiver changes no evidence relationship.

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

**Progress (2026-07-24):** `evaluate` now compares two persisted, versioned
`ReplayReport` JSON artifacts for the same case and writes
`evaluation-report.{json,md}`. It reports every quality-metric delta alongside
cost and latency deltas (unknown measurements remain `null`) and rejects
mismatched case versions. This initial operator slice never calls assemble,
Foundry import, or approval; repeatable case-set execution remains a future
extension.

## Near-term maintenance item

**Delivered (2026-07-24):** `preprocess` now preserves source-relative paths for
directory inputs, and writes `guide.pdf` as `guide.pdf.md`; this avoids both
cross-directory basename collisions and PDF/Markdown sibling collisions. It
validates the complete output mapping before writing and fails clearly if a
remaining derived-name collision exists.

**Delivered (2026-07-31):** the same `preprocess` seam now converts `.docx` to
deterministic `<name>.docx.md` plus source-hash provenance. A bounded, fail-closed
OOXML gate scans every Word XML part and rejects unsafe ZIP/package/XML, macros and active DDE
field content, external relationships, markup-compatibility alternate content, `altChunk`, and merged-cell table
semantics that cannot be rendered faithfully; every DOCX in a batch is validated before outputs
are written. The resulting Markdown still passes through the existing manifest-bound
`inspect-source-risk` gate. Legacy `.doc` remains an explicit passthrough gap.

## Defer protocol main-flow integration until preceding blockers are resolved

Do not add GraphQL or AsyncAPI as conditional branches in the current
HTTP/OpenAPI-oriented compatibility model. The protocol/transport seam and isolated
projection compilers are retained, but functional integration into CLI commands, run
artifacts, validation, diff/score, Foundry, and governance is sequenced after the domain
boundary, roadmap/documentation governance, and priority-1 benchmark CI work are resolved.

**Design accepted (2026-07-24):**
[Protocol Expansion Design](PROTOCOL_EXPANSION_DESIGN.md) defines the staged
Core seam, output artifact contract, HTTP parity gate, and the separate
GraphQL/AsyncAPI vertical slices. Implementation begins with the seam and its
HTTP compatibility proof; the two new formats remain gated on real source sets
and confirmed downstream consumers.

**Progress (2026-07-24):** a GitHub public GraphQL schema and a pinned OGC AsyncAPI
conformance example support separate minimal GraphQL SDL and AsyncAPI 3 projection
adapters. The associated tooling consumers establish format-level testability, not a
reason to bypass higher-priority product work.

**Sequencing decision (revised 2026-07-30):** keep the compiler seam and regression
tests stable, but freeze functional GraphQL/AsyncAPI integration. No CLI, run artifact,
validation, diff/score, or Foundry path should be added until a named real downstream
consumer provides its source set and acceptance contract. The GitHub and OGC fixtures
establish format-level testability only; they do not establish product demand or an
end-to-end grounding contract. Record the consumer and acceptance criteria in this
roadmap or a dedicated ADR before resuming implementation.

## Decision rule

Start with priority 1. It adds the evidence precision that every subsequent
extension needs, while retaining the product's fail-closed source-grounding
guarantee. Priorities 2 through 5 can be planned independently after their
shared evidence contract is established.

---

## 繁體中文摘要

這份文件記錄 `loop-apidoc` 在「來源依據式 API 文件分析／生成」之外可延伸的產品方向。
所有延伸均受同一原則約束：來源沒有明示的資訊，一律保留為缺口或 `null`，不可用慣例推測。
產品維持領域中立；支付／錢包是重要的首個垂直領域，其中 amount direction 與 line-currency
policy 屬選填 Payment Profile，不因現有 benchmark 組成而變成通用核心的必要語意。

實作回饋已加入為獨立的 conformance 權威軸：`feedback assess`／`propose`／`submit`／
`review`／`approve`／`compose`／`current`／`provider-erratum` 形成完整 public workflow；不做
provider network I/O。`submit` 建立 immutable `candidate` case；`review` 可對有／無 proposal
的 case 附加一次 non-approval decision 與 corrective route，另一個獨立人工 `approve` 階段
才附加 write-once approval／amendment 並發布 immutable exact-scope Effective release。
`ContractConformance` 的純 `assess`／`propose`／`compose` 邊界維持 exact scope、expiry、
conflict 與 lineage；同 target 衝突只允許明確同 scope supersession。Normative／Effective
舊 asset bytes 不改寫，新 asset 記錄 `supersedes` 後 pointer 才前進。Compatibility
Amendment 不改寫 normative base，Effective Contract 只對一個精確 Applicability Envelope
成立；proposal／composition 綁定完整 Normative release digest（contract + documentary
fragments + support relationships）。`feedback current` 要求 timezone-aware as-of，拒絕
query time 早於 approval／composition、expired、base 非 normative current 或
pointer／bounded artifact digest stale，成功結果揭露
`valid_until`、open／untested、stale amendment 與 unresolved contradiction counters。全域
`current` 維持 normative。正式 Provider Erratum 重走完整 source pipeline，而
implementation-backed benchmark 與 source-backed strict-local 分開計算；有限測試不會被
描述成普遍、永久的「100% 真實」。

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

0.26–0.28 在 P1 benchmark gate 受阻期間交付了 protocol seam、typed integration／雙向
coverage 與 browser-rendered URL import；這些是守住 source-grounded 原則的繞道交付，不算
Core 畢業進度。目前 13 個 benchmark 中有 7 份歷史來源可用，FunkyGames／RSG 已完成
claim-complete exact evidence，另 5 份待補，6 份歷史快照不可得。

GraphQL／AsyncAPI 的 protocol seam 與獨立 compiler 已保留；先完成產品邊界、策略文件 gate
與 benchmark CI 問題，再依既有 staged artifact／validation contract 接入 CLI 與主流程。

**建議順序：**先做第 1 項，因為它是後續所有擴充共享的可信證據基礎。
