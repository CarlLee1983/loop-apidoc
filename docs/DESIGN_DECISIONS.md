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
closed until converted and re-manifested. It never rewrites evidence or echoes a matched payload;
the report retains at most 1,000 findings and uses a blocker truncation sentinel when more matches
exist, preventing bounded input from amplifying into unbounded output.
The built-in `preprocess` seam handles `.docx` as a bounded OOXML package: it scans every Word XML
part and rejects unsafe ZIP/package/XML, macro or active DDE field content, external relationships,
unsupported alternate content, and merged-cell table semantics that cannot be rendered faithfully before writing
deterministic Markdown plus source-hash provenance. Legacy `.doc`
remains outside this trusted boundary and requires an operator-controlled external conversion.

The DOCX ingestion shape and ZIP/XML fallback were adapted from
[`virgiliojr94/book-to-skill`](https://github.com/virgiliojr94/book-to-skill) revision
`efda3b2212ce1b2c052126e85e14de40a32442e8`. That project is an upstream design/code source, not
a runtime dependency or a promise to support its wider EPUB/RTF/MOBI input matrix. The local seam
deliberately tightens the boundary with bounded OOXML validation, full-batch preflight,
deterministic source provenance, and fail-closed rendering. Its MIT notice is retained in
[`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md).

The audit contract is versioned and source-bound: schema/ruleset, `max_bytes`, manifest digest,
per-source SHA-256, and a stable source-binding digest are all checked.
`assess-sources --source-risk` reinspects current bytes and embeds the matching verified audit
in the quality report, and every `assemble` requires `--source-quality`, repeats that deterministic
inspection, and revalidates its stable binding against the newly built manifest before creating a
run directory. This refuses unaudited runs but cannot prove source-read chronology outside this
process. Risk findings govern whether text may enter model context;
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

`--architecture-mode strict` is the separate blocking adapter: only a passing legacy run
whose supported plan claims all re-verify against exact evidence can produce an
unapproved Core candidate. The strict execution record and candidate release are
revalidated by Foundry before import or approval, so `--allow-failing` cannot promote a
partial, failed, or non-exact run.

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

The normative Foundry read format is deliberately versioned and fail-closed. `asset.json`
and `current.json` use strict `normative-asset/v1` and `normative-current/v1` models, and
unknown fields or unversioned legacy records are rejected rather than silently interpreted.
The current pointer binds the canonical digest of the complete asset manifest and mirrors
its summary plus per-artifact SHA-256 bindings. File artifacts bind raw bytes; directory
artifacts bind a deterministic sorted tree digest and declared kind. The shared query seam
validates identity, `APPROVED` status, summary, safe identifiers, contained non-symlink paths,
target kind, existence, and bytes before returning an asset or CLI pointer. Existing legacy
state requires explicit operator intent: `foundry approve --reapprove-legacy --by <operator>
--legacy-current-sha256 <trusted-current-digest> --legacy-asset-sha256 <trusted-asset-digest>`
must build a fresh candidate-backed v1 asset. The two exact raw-byte SHA-256 values must come
from a trusted backup/release inventory and are compared before legacy parsing. The path accepts
only an unversioned, summary-consistent legacy head. It rejects v1 or unsupported versions, never
rewrites legacy bytes, and reads never fall back to them. Normative approval publishes the new immutable asset
first and atomically advances the pointer last; a failed advance restores the previous pointer,
docset, and catalog heads so retry can proceed coherently.

Human review binds the complete candidate file set rather than a maintenance-prone artifact
allowlist. Because the persisted review decision contains that binding, its own bytes are bound
separately after the decision is written. Approval compares the exact set before and after copy,
revalidates copied strict eligibility, and includes the run descriptor plus strict execution,
release, contract, decision, evidence, claims, and relationships in the immutable asset manifest.

Every per-docset normative and feedback promotion holds a global catalog lock and a docset
governance lock from baseline/predecessor capture through staging, publication, rollback, and
cleanup. Registration participates in the same global serialization. Existing
ancestors from the project root through the asset directory must be real contained directories,
never symlinks. A lock-cleanup failure is an operational `FoundryPublicationError`, not an input
rejection. Staging, immutable publication, head restoration, and owned-output cleanup are relative
to directories pinned by the transaction. Publication ownership is captured before rename and
verified afterward, and namespace identity is checked before commit. If rollback or ownership
verification fails, both locks remain as recovery guards instead of deleting uncertain state.
A synchronous feedback promotion
failure restores the prior effective pointer and removes only the amendment and effective asset
created by that attempt, so a complete rollback permits deterministic retry.
Review baselines consume only artifact bytes resolved from the strict asset manifest, including
the required `manifest.json` and optional preparation report bindings; generic loaders never
reconstruct an unbound asset directory.

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

### 12. Separate documentary authority from implementation conformance

Supplier sources are the sole authority for normative, provider-documented claims.
Implementation Observations are immutable empirical evidence only for behavior witnessed
inside their declared Applicability Envelope. Conformance relationships (`confirms`,
`contradicts`, `inconclusive`, `out_of_scope`) therefore form a separate axis and never
change `explicit_support`, `derived_support`, or any other documentary status. This
authority split is recorded in
[ADR 0002](adr/0002-separate-documentary-and-empirical-authority.md).

The public `feedback` workflow is deliberately staged. `assess`, `propose`, and `compose`
write deterministic artifacts outside `.foundry`; `submit` persists immutable inputs as an
explicit `candidate` case; `review` can append one bound non-approval decision and corrective
route to a case with or without a proposal; a separate independent-human `approve` appends
write-once decision/amendment records and publishes an immutable exact-scope Effective release;
`current` resolves only an exact target; and `provider-erratum` writes a non-mutating
handoff to the normative pipeline. None performs provider network calls. The domain and
Core define the `ContractConformance` boundary—assess, propose, compose—while adapters own
acquisition and report/persistence I/O. Input binding, scope, conflicts, redaction version,
replay lineage, and material-claim coverage fail closed. Same-target active conflicts are
not resolved by ordering: only explicit same-scope supersession may carry prior lineage
into a replacement amendment.
Proposal time cannot precede observation completion. Non-approval review time cannot precede
observation completion or, when present, proposal creation. Governed persistence rejects
sensitive field names and obvious email/phone/national-ID/SSN/passport/Luhn-valid payment-card values; low-entropy PII is omitted, not
hashed.

Assessment makes all eight `FeedbackRoute` values reachable. Harness/fixture failures route to
implementation correction; out-of-scope and DNS/proxy/gateway failures route to environment
configuration correction; repeated network/timeout/rate-limit failures route to provider-runtime
regression review; and a policy-safe contradiction without documentary evidence routes to
extraction correction. Confirmed-only, other inconclusive, high-risk contradiction, and safe
grounded contradiction retain closed, needs-evidence, provider-clarification, and amendment-
proposal routes respectively. Only confirms/contradicts count as assessed; inconclusive and
out-of-scope targets remain untested/open.

Observation kinds are also a semantic allowlist enforced by pure
`core/conformance_policy.py`: status/success must bind the same operation's response-status
path, while response field/type must bind a matching field path in a response-referenced schema.

Proposal and Effective composition integrity uses one complete Normative-release digest:
the canonical contract, documentary fragments, and support relationships. A projected
contract digest alone is insufficient because a fragment or relationship change can alter
documentary authority without changing the projection. Exact-scope `current` resolution is
also time-bound: callers supply a timezone-aware `--at`; lookup rejects a query before
approval/composition, expiry, a base that is no longer normative current, and stale
pointer/asset bindings. Pointer `effective_asset_digest` binds the complete strict-validated
canonical EffectiveAsset, including all declared fields; unknown fields fail closed.
Asset/pointer records also digest-bind `effective-contract.json`,
`compatibility-amendment.json`, and `provenance.json`. Lookup bounds, parses, digest-checks, and
lineage-checks these bindings. Successful reads carry `valid_until`, `open_discrepancy_count`,
`stale_amendment_count`,
`untested_material_claim_count`, and `unresolved_contradiction_count`.
Governed feedback/Effective JSON is strict (`extra="forbid"`). Current accepts only `APPROVED`
and cross-validates Effective Contract identity, amendment IDs, validity/counts, approval
actor/time, and provenance approval/assessment/bundle bindings. Stale amendments represent
verifiable release/contract/source/policy/approval-time drift; expired and inapplicable are
separate. Free-text revalidation triggers remain review declarations because no external
trigger-signal contract exists. `foundry.query` is the single public read-side I/O for lineage traversal;
the deliberately shared `foundry.integrity` adapter is its bounded filesystem reader and is also
used while approval stages a new asset, never as a second public reader or legacy fallback.
Approval and user-facing lineage traversal begin with this same bound current-head read. Each
successor pairs `supersedes` with `supersedes_asset_digest`; every hop verifies the predecessor
asset digest and amendment artifact digest. A new reviewed amendment may supersede expired
lineage, but historical asset metadata/amendment/supersession tampering fails closed before it
can contaminate a later approval/composition.

A reviewed Compatibility Amendment is an expiring, exact-scope overlay, never a mutation
or a second normative source. An Effective Contract composes one immutable approved
Normative Contract release with only applicable active amendments and preserves authority
and evidence lineage on every value. The global Foundry `current` remains normative;
effective current selections are deployment/scope-specific. Conflicts, drift, expiry,
untested claims, and open discrepancies remain visible. No finite suite permits a global,
permanent, or universal “100% true” claim.

Foundry never rewrites prior normative asset bytes. A newly approved normative asset owns
its `supersedes` link and the global pointer advances only after publication. The same
write-new-then-advance rule applies to immutable scope-specific Effective releases.

A formal Provider Erratum has supplier documentary authority, so it must re-enter the full
source-risk, source-quality, extraction, verification, assembly, review, and Foundry release
pipeline. Unconfirmed but reproducible behavior can affect only a reviewed scoped Effective
Contract. Implementation-backed benchmarks remain a separate assurance lane and never
count as source-backed strict-local passes.

### 13. Let the requester direct attention without letting it direct the contract

An operator integrating a specific API usually knows, before the run starts, what it
cannot ship without. Optional focus directives carry that knowledge into the run: they
are broadcast into every extraction subagent's prompt, and each is answered exactly once
with either deterministic anchors bound to exact evidence, or a not-found outcome naming
every readable source searched. A directive's `kind` alone determines severity and its
`intent` alone determines anchor type; there is no override field, and there is no
"not applicable" outcome, because whether a directive applies is the requester's
judgement rather than the agent's.

The instruction "look harder for X" is the shape most likely to invite fabrication, so
it is paired with a deterministic gate rather than trusted. A directive never licenses
inventing an operation, a field, or an error code: when the sources are silent the
correct answer is not-found, and the resulting validation failure is the intended
signal to gather better sources. Structural problems fail before a run directory exists;
a falsified expectation fails validation instead, so the run's artifacts survive for the
operator to judge whether the provider is silent or the extraction was shallow.

Focus material is confined to the run directory and never reaches provenance, the score,
or a governed asset, so two runs over the same sources with different directives stay
comparable. That confinement, its alternatives, and the condition that would falsify it
are recorded in
[ADR 0004](adr/0004-focus-directives-never-enter-comparable-artifacts.md).

A directive asking for the provider's error codes exhaustively was, at first, satisfiable by
reporting one — real, cited, and indistinguishable in the output from a genuine sweep. The
codes a supplier source presents in an error-code table are now a deterministic lower bound on
that answer, so a short one names what it left out and where each omission is written down.
The bound derives from source structure alone; why it ignores a directive's own wording, why
it unions across sources where the endpoint index intersects, and why the general source-fact
gate deliberately does not consume it are recorded in
[ADR 0005](adr/0005-the-error-code-floor-comes-from-source-structure-alone.md).

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

1. 供應商來源是 normative、provider-documented claim 的唯一權威；未明示資訊一律保留缺口或 `null`，不可用慣例補寫。Implementation Observation 是另一條 exact-scope empirical conformance 軸。
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
12. 文件權威與實作 conformance 是兩條獨立軸：供應商來源只支援 Normative Contract；Implementation Observation 只描述精確 Applicability Envelope 內的行為，不能升格成來源支持。`feedback assess`／`propose`／`compose` 只處理被動 normalized JSON 並在 `.foundry` 外寫出產物；proposal 與 composition 綁定完整 Normative release digest（contract + documentary fragments + support relationships）。`submit` 建立 immutable `candidate` case；`review` 可對有／無 proposal 的 case 附加一次 non-approval decision 與 corrective route；另一個獨立人工 `approve` 階段才附加 write-once approval／amendment並發布 immutable exact-scope Effective release。Proposal time 不得早於 observation completion；non-approval review time 不得早於 observation completion 或既有 proposal creation。治理持久化會拒絕敏感欄位名稱與明顯 email／phone／national-ID／SSN／passport／Luhn-valid payment-card 值；低 entropy PII 省略而不 hash。八條 deterministic route 全部可達：harness／fixture、out-of-scope 或 DNS／proxy／gateway、重複 network／timeout／rate-limit、沒有 documentary evidence 的安全 contradiction 分別交給 implementation、environment、provider-runtime regression、extraction correction；其餘維持 closed／needs-evidence／provider-clarification／amendment-proposal。只有 confirms／contradicts 計入 assessed；inconclusive／out-of-scope 仍是 untested/open。Compatibility Amendment 必須有期限且綁定 scope；同 target 衝突 fail closed，除非明確同 scope supersession 保留既有 lineage。`feedback current` 要求 timezone-aware `--at`，拒絕 query time 早於 approval／composition、expired、base 非 normative current 或 stale binding；pointer 的 `effective_asset_digest` 綁定完整 current asset，另驗證三份 artifacts，成功回傳 `valid_until`、open／untested counters 與 `unresolved_contradiction_count`。每個 successor 的 `supersedes`／`supersedes_asset_digest` 成對形成 hash chain；approval 與 user-facing traversal 逐節驗證 predecessor asset／amendment digest。新 reviewed amendment 可恢復 expired lineage，但任何歷史 metadata／amendment／supersession 竄改都 fail closed，不得污染下次 approval／composition。Foundry 不改寫舊 normative asset bytes，新 asset 記錄 `supersedes` 後 pointer 才前進。全域 `current` 保持 normative，無 global Effective current，也不宣稱有限測試能證明「100% 真實」。Provider Erratum 必須重走完整 source pipeline；implementation-backed benchmark 與 source-backed strict-local lane 分開回報。

    Issue #36 的 hardened contract 另要求：Observation kind 由 pure `core/conformance_policy.py` 做語意 allowlist；governed feedback／Effective JSON 拒絕未知欄位；`current` 只接受 `APPROVED` 並 cross-validate contract identity、amendment IDs、validity/counts、approval actor/time 與 provenance approval/assessment/bundle bindings。Pointer digest 綁定包含所有宣告欄位、經 strict validation 後的 canonical asset，並揭露 digest-bound `stale_amendment_count`。Stale 只指可驗證的 release／contract／source／policy／approval-time drift，expired 與 inapplicable 分開；自由文字 revalidation triggers 只是 review declaration，沒有外部 signal contract 就不自動執行。所有 governed lineage traversal 收斂至 `foundry.query`。
13. 供應商文件同時是 untrusted model input：來源取得／前處理後，必須對 agent 實際會讀的 manifest 綁定文字包執行 `inspect-source-risk`。報告不回顯命中 payload、不改寫來源，並由 schema/ruleset、大小上限、manifest／逐來源 digest 與 stable source binding 防止 stale reuse；`assess-sources` 內嵌 audit，`assemble` 在建立 run-dir 前重驗綁定。risk finding 決定文字能否進模型，不是 API claim 的事實證據。

14. 提出者可以指導注意力,但不能指導契約內容。選填的 focus directive 會逐字進入每個擷取 subagent 的 prompt,每條恰好應答一次:要嘛給出釘在 exact evidence 上的確定性錨點,要嘛回報 not-found 並列出查過的每一份可讀來源。`kind` 是 severity 的唯一來源、`intent` 是錨點型別的唯一來源,沒有覆寫欄位,也沒有「不適用」這個結局——一條指令適不適用是提出者的判斷,不是 agent 的。「再努力找找 X」正是最容易誘發捏造的指令形式,所以它配的是確定性閘門而不是信任:來源沒寫就是 not-found,由此產生的驗證失敗正是「該補來源」的訊號。結構問題在建立 run 目錄前失敗,落空的斷言則走 validation,產物因此留得下來供人判斷是供應商真的沒寫、還是擷取不夠深。focus 材料只留在 run 目錄,不進 provenance、score 或治理資產,故同一份來源、不同指令的兩次 run 仍可比對;該約束的取捨與否證條件記在 [ADR 0004](adr/0004-focus-directives-never-enter-comparable-artifacts.md)。
