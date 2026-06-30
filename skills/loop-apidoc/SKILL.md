---
name: loop-apidoc
description: Produce standardized OpenAPI 3.1 + Traditional-Chinese Markdown integration docs from one or more API documentation sources (local PDF/MD/HTML or public URLs). The agent extracts, calls a deterministic CLI to assemble and validate, and on validation failure loops back to fill gaps. Use when the user wants to turn messy API integration docs into a consistent, traceable spec.
---

# loop-apidoc: source-grounded API doc generation

You turn the user's API documentation sources into standardized, traceable artifacts. **The source is the only ground truth**: anything a source does not state is `null` and recorded in `missing`. **Never speculate; never apply REST/OAuth conventions.**

## CLI invocation (`<APIDOC>`)

This skill runs on both the Claude Code plugin and the Codex CLI. Every command
below writes the CLI as `<APIDOC>`; resolve it once per shell call:

- **`$CLAUDE_PLUGIN_ROOT` is set** (Claude Code plugin) → the CLI lives in the
  bundled package: `uv run --project "$CLAUDE_PLUGIN_ROOT" loop-apidoc`.
- **otherwise** (Codex / standalone) → call the globally installed command
  `loop-apidoc` directly (`uv tool install`; see README).

For a deterministic, shell-portable (bash *and* zsh) prefix, prepend this to any
CLI line — it builds an argv array that is safe with spaces:

```bash
RUN=(loop-apidoc); [ -n "$CLAUDE_PLUGIN_ROOT" ] && RUN=(uv run --project "$CLAUDE_PLUGIN_ROOT" loop-apidoc)
"${RUN[@]}" <command> ...
```

(Do **not** use `${CLAUDE_PLUGIN_ROOT:+uv run --project "$CLAUDE_PLUGIN_ROOT"}`
inline: bash word-splits it but zsh does not, so it breaks under zsh.)

## Flow

### 1. Collect sources
- Local files: record the source directory as `<SOURCES>`.
  - MD/HTML/small PDF: subagents read the file directly.
  - **Table-heavy or large PDF**: first flatten to high-fidelity markdown —
    `<APIDOC> preprocess --sources "<SOURCES>" --out "<WORK>/sources_md"`
    (pymupdf4llm preserves tables/headings; raw PDF reads distort tables).
    Point extraction subagents at `<WORK>/sources_md`.
- Public URLs: fetch each URL as text (built-in web fetch, or a reader like
  defuddle); pass URLs via `--url`.

## Subagent contract (extraction)

You orchestrate; **read-only subagents extract**. For every extraction below,
dispatch a read-only subagent (file read + search only — **no web, no write**).
Give it: the source location (`<SOURCES>` or `<WORK>/sources_md`), the
exact JSON schema to fill, and the grounding rule. The subagent **returns the
JSON only** (no prose, no file writes). **You (the orchestrator) are the only
writer** — you write the returned JSON to disk. Grounding rule to include in every
subagent prompt: *"Fill strictly from the sources. Anything the sources do not
state → null and add a short label to `missing`. Never infer; never apply
REST/OAuth conventions. Return only the JSON object."*

### 2. Extract inventory → write `<WORK>/inventory.json`
Dispatch **one** read-only subagent (per the Subagent contract) to read every
source and **return one** JSON object with this schema. Then **you** write the
returned object to `<WORK>/inventory.json`.

```json
{"title": "str|null",
 "version": "str|null",
 "overview": "str",
 "environments": [{"name":"str","base_url":"str","version":"str|null","source":"str"}],
 "security_schemes": [{"name":"str","type":"str|null","location":"str|null","details":"str|null","source":"str"}],
 "endpoints": [{"method":"str","path":"str","summary":"str","source":"str"}],
 "schemas": [{"name":"str","fields":[{"name":"str","type":"str|null","required":"bool|null","description":"str|null"}],"enums":["str"],"constraints":"str|null","source":"str"}],
 "errors": [{"code":"str","meaning":"str","http_status":"str|null","source":"str"}],
 "operational": [{"topic":"str","detail":"str","source":"str"}],
 "missing": ["str"]}
```
`title` is the source document/product title (verbatim from the source heading, e.g. "綠界全方位金流 API 技術文件"); `null` if the source has no explicit title (it becomes OpenAPI `info.title`). `version` is the source-stated document/API version (verbatim, e.g. "NDNF-1.2.2"); `null` if none is stated (it becomes OpenAPI `info.version`). Include **every** endpoint and **every** error code. Each `source` cites the source section/page.
Each `schemas[].fields` entry uses the **English** keys `name`/`type`/`required`/`description` (the same shape as endpoint `parameters`) — do **not** substitute localized keys (e.g. 型態/必填/中文), or the generator drops the type/required. Nested fields use the dotted-path convention `Parent.Child` / `Parent[].Child` (see step 3).

### 3. Extract each endpoint's detail → write `<WORK>/endpoints/<NN>.json`
For **every** endpoint in `inventory.endpoints`, dispatch a read-only subagent
**in parallel** (one per endpoint; batch if there are many) that returns one JSON
object with the schema below. Pass each subagent its endpoint identity
(`method`/`path`/`summary`/`source`) and the source location. **You** write each
returned object to `<WORK>/endpoints/ep<N>.json` (`ep0.json`, `ep1.json`, …).

```json
{"method":"str","path":"str","source":"str",
 "parameters":[{"name":"str","in":"query|header|path|body|null","type":"str|null","required":"bool|null","description":"str|null"}],
 "request":{"content_type":"str|null","schema":"str|null","required":"bool|null","description":"str|null"} ,
 "responses":[{"status":"str","description":"str|null","schema":"str|null","schema_ref":"str|null"}],
 "tags":["str"],"security":["str"],
 "examples":[{}],"missing":["str"]}
```
`request` is `null` when there is no body. Fields the source omits → null/empty array, and add them to `missing`.
**Nested fields**: for a field nested inside an object or array, name it with a dotted path — `Parent.Child` (nested object) or `Parent[].Child` (array of objects, e.g. `OrderDetail[].ItemName`). The generator reconstructs proper `items`/nested `object` schemas from this convention; do **not** flatten a documented array into unrelated sibling fields. This applies to both `parameters` (`in:body`) and `schemas[].fields`.
**`tags`**: source-stated grouping labels for this endpoint (e.g. a section/category title the source uses — "信用卡", "電子錢包"); they become the operation's OpenAPI `tags` and are declared at the document root. Empty when the source groups nothing.
**`security`**: the **exact `name`s** of the `inventory.security_schemes` entries this endpoint requires (e.g. `["AES256 (TradeInfo)"]`); they become the operation's `security` requirement. Empty when the source states no auth/signing for this endpoint; never list a scheme name that isn't in `inventory.security_schemes`.
**`schema_ref`**: when a response body is the structured shape you also captured as a named entry in `inventory.schemas` (e.g. the response of `取消授權` ↔ schema `取消授權回應參數（Result）`), set `schema_ref` to that schema's **exact `name`**. The OpenAPI then links the response via `$ref: #/components/schemas/...` instead of restating the field list as prose. Use `null` when no such named schema exists; never invent a name that isn't in `inventory.schemas`.
**`one_of` / `discriminator`** (optional, for polymorphic fields): an `in:body` parameter or a `schemas[].fields` entry MAY declare a union when the source documents the field as **one of** several named member shapes (e.g. a single `POST /payments` whose `paymentMethod` is one of `CardDetails` / `IdealDetails` / `ApplePayDetails`, selected by a `type` discriminator):

```json
{"name":"paymentMethod","in":"body","type":"object","required":true,
 "one_of":["CardDetails","IdealDetails","ApplePayDetails"],
 "discriminator":{"property_name":"type",
   "mapping":{"scheme":"CardDetails","ideal":"IdealDetails","applepay":"ApplePayDetails"}}}
```

- `one_of`: a list of schema **names**, each of which MUST also appear as a named entry in `inventory.schemas` (so every member is independently captured and provenance-backed). A name that isn't in `inventory.schemas` is dropped — never invent one.
- `discriminator` (optional): `property_name` is the **source-stated** discriminating property; `mapping` maps each discriminator value to a member schema **name**. Omit `discriminator` entirely when the source states no explicit discriminator.
- **Grounding rule:** declare `one_of` only when the source documents the field as one of those member shapes; never synthesize a union from REST/payment conventions. Keys are snake_case (`one_of`, `property_name`), consistent with the other extraction keys.

Top-level `source` is required: cite the source section/page/URL where this endpoint's detail lives (consistent with the matching `source` in inventory.endpoints). **With multiple sources this is the only thing attributing detail to the correct source** — omitting it triggers `SOURCE_UNVERIFIED`.

**Async notifications / callbacks / webhooks** (server POSTs to a caller-supplied URL, e.g. payment-result notifications): keep `method`, set `path` to `null`. These become OpenAPI 3.1 top-level `webhooks` (named by summary), no fixed URL needed. `responses` holds what the receiver must reply (e.g. `1|OK`). **Multiple callbacks sharing the same (method, null) are distinguished only by their `source`** — give every callback detail the correct `source`.

### 4. Extract integration mechanics → write `<WORK>/integration.json`

Dispatch one read-only subagent to read the sections describing encryption,
signing, callbacks, and cross-field conditions. It returns **only** this JSON
object (no prose, no file writes); you write it to `<WORK>/integration.json` beside
`inventory.json`. Anything the sources do not state → `null` and add a label to
`missing`. Never infer crypto/callback details from REST/payment conventions.

```json
{
  "version": "1.0",
  "crypto": [
    {
      "name": "str",
      "purpose": "request|response|callback|signature|null",
      "algorithm": "str|null",
      "mode": "str|null",
      "padding": "str|null",
      "encoding": "str|null",
      "key_source": {"key": "str|null", "iv": "str|null", "note": "str|null"},
      "payload_assembly": [{"step": 1, "desc": "str", "fields": ["str"]}],
      "verify": {"field": "str|null", "method": "str|null", "desc": "str|null"},
      "source": "str"
    }
  ],
  "callbacks": [
    {
      "name": "str",
      "trigger": "str|null",
      "transport": "str|null",
      "payload_ref": "schemas.{name}|null",
      "verification": "str|null",
      "expected_response": "str|null",
      "source": "str"
    }
  ],
  "field_conditions": [
    {"scope": "str|null", "rule": "str", "when": "str|null", "then_required": ["str"], "source": "str"}
  ],
  "test_cases": [
    {"name": "str", "operation_ref": "paths.{path}.{method}|null", "request": {}, "response": {}, "source": "str"}
  ],
  "missing": [{"area": "str", "detail": "str"}]
}
```

- `payload_assembly`: the ordered steps for building the string to encrypt/sign
  (the signature chain). Only include what the source states.
- `payload_ref` / `operation_ref`: point to an existing `inventory.schemas` name
  or `paths.{path}.{method}`; `null` if no match.
- `source`: required per entry — cites the source section/page/URL.
- If the sources describe **no** integration mechanics, omit `integration.json`
  entirely (do not write an empty file).

### 5. Assemble + validate
```bash
<APIDOC> assemble \
  --sources "<SOURCES>" --extraction "<WORK>" --output "<OUT>" --json
```
Parse the JSON on stdout: `ok`, `run_dir`, `review_html`, `report.issues`.

### 6. Correction loop (max 3 rounds)
- `ok == true` → report the `openapi.yaml` / `api-guide.zh-TW.md` / `review.html` / `provenance.json` / `validation/report.md` inside `run_dir` (point the user at `review.html` for an offline, at-a-glance review of scope/sources/gaps), done.
- `ok == false` → read `report.issues` (`code`/`severity`/`location`/`evidence`/
  `suggested_fix`, plus optional `target_file`/`field_path`/`requery_scope`).
  **Prefer the structured fields when present**: `target_file` names where to edit
  (`inventory.json`, `integration.json`, or `endpoints/` — the directory, since the
  exact `ep<N>.json` isn't derivable; match it by `requery_scope`'s path.method),
  `field_path` the field inside it, and `requery_scope` the bounded source area to
  re-read. Fall back to parsing `location` only when these are `null`. Then
  **dispatch a targeted read-only subagent to re-read only that scope** and return
  the corrected JSON, **you** overwrite the named file, and return to step 5.
- On `REQUIRED_INFO_MISSING` at `integration.crypto`: the source mentions
  encryption/signing but no crypto detail was extracted — re-read the relevant
  section and overwrite `integration.json`, then re-run assemble.
- On `OUTPUT_MISMATCH` at `integration.*`: a `payload_ref`/`operation_ref` does
  not resolve — fix the reference to an existing schema/operation.
- Still FAIL after 3 consecutive rounds → present the remaining gaps/conflicts to the user. **Do not hard-code fill-ins.**

## Important
- Use a dedicated working dir for `<WORK>` (may live in a scratch area outside `<OUT>`).
- Each round overwrites the same `inventory.json` / `endpoints/*.json` / `integration.json`, then re-runs assemble.
- Exit codes: 0=PASS, 1=validation FAIL, 2=extraction input file error (fix the JSON you wrote).
