---
name: loop-apidoc
description: Produce standardized OpenAPI 3.1 + Traditional-Chinese Markdown integration docs from one or more API documentation sources (local PDF/MD/HTML or public URLs). The agent extracts, calls a deterministic CLI to assemble and validate, and on validation failure loops back to fill gaps. Use when the user wants to turn messy API integration docs into a consistent, traceable spec.
---

# loop-apidoc: source-grounded API doc generation

You turn the user's API documentation sources into standardized, traceable artifacts. **The source is the only ground truth**: anything a source does not state is `null` and recorded in `missing`. **Never speculate; never apply REST/OAuth conventions.**

The CLI runs from this plugin's bundled package. Always invoke:

```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" loop-apidoc <command> ...
```

## Flow

### 1. Collect sources
- Local files: record the source directory as `<SOURCES>`.
  - MD/HTML/small PDF: subagents read the file directly with Read.
  - **Table-heavy or large PDF**: first flatten to high-fidelity markdown —
    `uv run --project "${CLAUDE_PLUGIN_ROOT}" loop-apidoc preprocess --sources "<SOURCES>" --out "<WORK>/sources_md"`
    (pymupdf4llm preserves tables/headings; raw PDF reads distort tables).
    Point extraction subagents at `<WORK>/sources_md`.
- Public URLs: fetch as text with WebFetch or defuddle; pass URLs via `--url`.

## Subagent contract (extraction)

You orchestrate; **read-only subagents extract**. For every extraction below,
dispatch a subagent restricted to read-only tools (Read/Grep/Glob — **no web, no
write**). Give it: the source location (`<SOURCES>` or `<WORK>/sources_md`), the
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
 "schemas": [{"name":"str","fields":[{}],"enums":["str"],"constraints":"str|null","source":"str"}],
 "errors": [{"code":"str","meaning":"str","http_status":"str|null","source":"str"}],
 "operational": [{"topic":"str","detail":"str","source":"str"}],
 "missing": ["str"]}
```
`title` is the source document/product title (verbatim from the source heading, e.g. "綠界全方位金流 API 技術文件"); `null` if the source has no explicit title (it becomes OpenAPI `info.title`). `version` is the source-stated document/API version (verbatim, e.g. "NDNF-1.2.2"); `null` if none is stated (it becomes OpenAPI `info.version`). Include **every** endpoint and **every** error code. Each `source` cites the source section/page.

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
Top-level `source` is required: cite the source section/page/URL where this endpoint's detail lives (consistent with the matching `source` in inventory.endpoints). **With multiple sources this is the only thing attributing detail to the correct source** — omitting it triggers `SOURCE_UNVERIFIED`.

**Async notifications / callbacks / webhooks** (server POSTs to a caller-supplied URL, e.g. payment-result notifications): keep `method`, set `path` to `null`. These become OpenAPI 3.1 top-level `webhooks` (named by summary), no fixed URL needed. `responses` holds what the receiver must reply (e.g. `1|OK`). **Multiple callbacks sharing the same (method, null) are distinguished only by their `source`** — give every callback detail the correct `source`.

### 4. Assemble + validate
```bash
uv run --project "${CLAUDE_PLUGIN_ROOT}" loop-apidoc assemble \
  --sources "<SOURCES>" --extraction "<WORK>" --output "<OUT>" --json
```
Parse the JSON on stdout: `ok`, `run_dir`, `report.issues`.

### 5. Correction loop (max 3 rounds)
- `ok == true` → report the `openapi.yaml` / `api-guide.zh-TW.md` / `provenance.json` / `validation/report.md` inside `run_dir`, done.
- `ok == false` → read `report.issues` (`code`/`severity`/`location`/`evidence`/
  `suggested_fix`); from `location` identify the inventory field or the endpoint
  at fault, **dispatch a targeted read-only subagent to re-read only the relevant
  source** and return the corrected JSON, then **you** overwrite `inventory.json`
  or the matching `endpoints/<NN>.json` and return to step 4.
- Still FAIL after 3 consecutive rounds → present the remaining gaps/conflicts to the user. **Do not hard-code fill-ins.**

## Important
- Use a dedicated working dir for `<WORK>` (may live in a scratch area outside `<OUT>`).
- Each round overwrites the same `inventory.json` / `endpoints/*.json`, then re-runs assemble.
- Exit codes: 0=PASS, 1=validation FAIL, 2=extraction input file error (fix the JSON you wrote).
