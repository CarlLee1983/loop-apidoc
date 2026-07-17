# Extraction schemas (loop-apidoc)

On-demand reference for the extraction contract (see SKILL.md's "Subagent contract (extraction)" section): each
**endpoint** subagent writes its own `endpoints/ep<N>.json` and returns one summary
line; **inventory** and **integration** subagents write nothing and return their JSON
object, which you (the orchestrator) write to `inventory.json` and `integration.json`
(optional). Load this while extracting (SKILL.md steps 2–4). The orchestration rules
and the read-only **subagent contract + grounding rule** live in SKILL.md — they are
not repeated here.

## Universal rules

- **English keys only** for machine fields — exactly as shown below. Localized keys
  (型態 / 必填 / 中文) on `schemas[].fields[]` or endpoint `parameters[]` are
  **hard-rejected at the assemble boundary** (exit 2); the generator would otherwise
  silently drop `type` / `required`.
- Anything a source does not state → `null` (or empty array) **and** a short label in
  `missing`. Never infer; never apply REST/OAuth/payment conventions.
- After writing each file, **parse it as JSON** before continuing.
- **Tolerated optional keys** the generator reads and the guard allows (use the
  documented keys first — these are escape hatches, not permission for localized keys):
  `enum` (inline enum list on a field/param), `location` (alias for `in`),
  `schema` (fallback for `type`).

## inventory.json

One object describing the whole API. **You** write what the single inventory subagent returns.

```json
{"title": "str|null",
 "version": "str|null",
 "overview": "str",
 "environments": [{"name":"str","base_url":"str","version":"str|null","source":"str"}],
 "security_schemes": [{"name":"str","type":"str|null","location":"str|null","details":"str|null","source":"str"}],
 "endpoints": [{"method":"str","methods":["str"],"path":"str|null","summary":"str","source":"str","server":"str|null"}],
 "schemas": [{"name":"str","fields":[{"name":"str","type":"str|null","required":"bool|null","description":"str|null"}],"enums":["str"],"constraints":"str|null","source":"str"}],
 "errors": [{"code":"str","meaning":"str","http_status":"str|null","applicable_to":["METHOD /path"],"source":"str"}],
 "operational": [{"topic":"str","detail":"str","source":"str"}],
 "missing": ["str"]}
```

- `title`: the source document/product title, **verbatim** from the source heading
  (e.g. `綠界全方位金流 API 技術文件`); `null` if none stated → becomes OpenAPI `info.title`.
- `version`: the source-stated document/API version, **verbatim** (e.g. `NDNF-1.2.2`);
  `null` if none → becomes OpenAPI `info.version`.
- Include **every** endpoint and **every** error code.
- Use legacy `method` for one operation, or additive `methods` when the same
  endpoint contract applies to multiple HTTP methods. `methods` is expanded into
  one canonical operation per method before planning; every other field in that
  entry therefore applies identically to every listed method. When methods have
  different summaries, parameters, requests, responses, security, or source
  detail, write separate single-`method` entries instead. `methods` must be a
  non-empty array of unique, non-blank strings (case-insensitive).
- `endpoints[].path` is the path **only**, always starting with `/`
  (`/hrxt/loginGame`, `/users/{userId}/orders`). The host belongs in
  `environments[].base_url` — never fold it, or a `{template}` placeholder standing for it,
  into `path`. OpenAPI 3.1 requires `paths` keys to start with `/`; `assemble` rejects
  anything else at the input boundary (`exit 2`).

  ```
  ✓ "/hrxt/loginGame"                 + environments[0].base_url = "https://api.example.com"
  ✗ "{api_url}/hrxt/loginGame"
  ✗ "https://api.example.com/hrxt/loginGame"
  ```
- A webhook/callback endpoint has `method` but `path: null` (it is delivered to a
  caller-defined URL, so it has no server path). For these, **`summary` is required**
  and is the endpoint's identity: it is how `assemble` matches an `endpoints/ep<N>.json`
  file to its `inventory.endpoints[]` entry, and how the OpenAPI `webhooks` key is named.
  Two webhooks with no `summary` are indistinguishable, and a subagent writing one
  webhook into two files would go undetected. Copy the `summary` **verbatim** from
  inventory into the endpoint file (whitespace is normalized before comparison).

  ```
  ✓ inventory: {"method":"POST","path":null,"summary":"NotifyURL 幕後付款結果通知"}
    ep7.json:  {"method":"POST","path":null,"summary":"NotifyURL 幕後付款結果通知"}
  ✗ ep7.json:  {"method":"POST","path":null}          ← rejected at the input boundary
  ```
- `endpoints[].server` (optional): when the source documents **more than one** base URL
  and states which endpoints live on which host, set `server` to the matching
  `environments[].name`. `assemble` rejects a name that resolves to no environment.
  The generator turns it into an operation-level OpenAPI `servers` entry. Omit the field
  when the source states a single host — the endpoint then inherits the root `servers`.

  ```
  environments: [{"name":"api","base_url":"https://api.example.com"},
                 {"name":"reporting","base_url":"https://report.example.com"}]
  endpoints:    [{"method":"GET","path":"/bets","server":"reporting", ...}]
  ```
- Each `source` **must start with the manifest `relative_path` of the file it came from**,
  followed by a page (`p.<N>`) or URL anchor (`#<anchor>`); anything after that is free text.
  `assemble` matches this string against `manifest.json` — a file whose citations name no
  manifest source at all is rejected at the input boundary (`exit 2`).

  ```
  ✓ "HRXT_transfer_wallet_v1.00.pdf p.10 — ## 2.4 钱包存款 注意事项"
  ✓ "paypal-webhooks-overview.md#verifying-authenticity"
  ✗ "## 2.4 钱包存款 注意事项 (line 331)"   ← names no source file
  ✗ "第 3 節"                                ← names no source file
  ```

  Single-source runs are exempt (attribution is unambiguous), but write the full form
  anyway — it stays correct when a second source is added.
- `schemas[].fields[]` uses the **English** keys `name`/`type`/`required`/`description`
  (same shape as endpoint `parameters`). Nested fields use the dotted-path convention
  (see endpoints below).
- `errors[]` records `code`, `meaning`, and `http_status`. When the source explicitly
  limits an error to operations, add `applicable_to` as exact `METHOD /path` strings
  (for example `"POST /transfers"`); otherwise leave it as `[]`. Generated OpenAPI
  exposes the complete mapping as `components.schemas.ErrorCode`: `enum` constrains the
  wire values, and its `x-loop-error-code-map` extension carries each code's `meaning`,
  `http_status`, `applicable_to`, and `source` citations losslessly — fill `meaning` and
  `source` per error, they flow verbatim into the OpenAPI document and `provenance.json`.
  An operation-level `x-loop-error-codes` extension is added only when this
  source-stated applicability is present.

## endpoints/ep<N>.json

One object per endpoint in `inventory.endpoints`. Dispatch one read-only subagent per
endpoint **in parallel** (≤6 concurrent, then batch the rest).

```json
{"method":"str","methods":["str"],"path":"str","source":"str",
 "parameters":[{"name":"str","in":"query|header|path|body|null","type":"str|null","required":"bool|null","description":"str|null"}],
 "request":{"content_type":"str|null","schema":"str|null","required":"bool|null","description":"str|null"} ,
 "responses":[{"status":"str","description":"str|null","schema":"str|null","schema_ref":"str|null"}],
 "tags":["str"],"security":["str"],
 "examples":[{}],"missing":["str"]}
```

- `request` is `null` when there is no body. Fields the source omits → `null` / empty
  array, and add them to `missing`.
- `methods` is the additive multi-method form for a shared endpoint contract. It
  has the same identical-contract constraint as `inventory.json`; use `method`
  when a detail file represents only one operation. One inventory `methods`
  entry must match exactly one detail file with the same method set; do not split
  it into separate GET/POST detail files.
- **Top-level `source` is required** — cite where this endpoint's detail lives, consistent
  with its `inventory.endpoints` entry. With multiple sources **this is the only thing
  attributing detail to the right source**; omitting it triggers `SOURCE_UNVERIFIED`.
- **`tags`**: source-stated grouping labels (e.g. `信用卡`, `電子錢包`) → OpenAPI operation
  `tags`, declared at the document root. Empty when the source groups nothing.
- **`security`**: the **exact `name`s** of the `inventory.security_schemes` entries this
  endpoint requires (e.g. `["AES256 (TradeInfo)"]`) → the operation's `security`. Empty when
  the source states no auth/signing here; never name a scheme absent from inventory.
- **`schema_ref`**: when a response body equals a named `inventory.schemas` entry, set
  `schema_ref` to that schema's **exact `name`** (OpenAPI then links via `$ref` instead of
  restating fields). `null` when no such named schema; never invent a name.
- **Response status formalization**: `status` is an OpenAPI response key. Copy a documented
  HTTP status when the provider states one. When the provider documents a universal
  success/failure envelope but is silent about HTTP status, set `status: "default"` and
  cite the envelope/schema; this is a faithful OpenAPI formalization, not a claim that the
  provider returned a particular HTTP status. Do not leave `responses` empty merely because
  no numeric status was published.
- **`examples`**: when the source shows a concrete request or response payload (JSON block,
  `code`/`Response` table row, or formatted example under 「响应」/「请求」), copy it **verbatim**
  into `examples[]`. Prefer one entry per stated example; parse JSON when the source gives
  valid JSON, otherwise keep the source string. Use English keys:

  ```json
  {"title": "Response success (code=1000)", "content_type": "application/json",
   "value": {"code": 1000, "msg": "Success.", "data": {}}}
  ```

  `title` is optional; `content_type` matches the endpoint's request/response format.
  **Do not leave `examples` empty when the source section documents an example** — empty
  `examples` with a documented response is an extraction gap (completeness warning). Only
  leave `examples: []` and record the gap in `missing` when the source is genuinely silent
  (no example body, no sample values). Never invent values to fill examples.

### Nested fields (dotted path)

For a field nested inside an object or array, name it with a dotted path —
`Parent.Child` (nested object) or `Parent[].Child` (array of objects, e.g.
`OrderDetail[].ItemName`). The generator reconstructs proper `items` / nested `object`
schemas from this; do **not** flatten a documented array into unrelated siblings.
Applies to both `parameters` (`in:body`) and `schemas[].fields`.

### Polymorphic union (`one_of` / `discriminator`) — optional

An `in:body` parameter or a `schemas[].fields` entry MAY declare a union when the source
documents the field as **one of** several named member shapes:

```json
{"name":"paymentMethod","in":"body","type":"object","required":true,
 "one_of":["CardDetails","IdealDetails","ApplePayDetails"],
 "discriminator":{"property_name":"type",
   "mapping":{"scheme":"CardDetails","ideal":"IdealDetails","applepay":"ApplePayDetails"}}}
```

- `one_of`: schema **names**, each of which MUST also appear in `inventory.schemas` (so every
  member is independently captured and provenance-backed). A name not in `inventory.schemas`
  is dropped — never invent one.
- `discriminator` (optional): `property_name` is the **source-stated** discriminating property;
  `mapping` maps each discriminator value to a member schema **name**. Omit `discriminator`
  entirely when the source states no explicit discriminator.
- **Grounding:** declare `one_of` only when the source documents the field as one of those
  member shapes; never synthesize a union from REST/payment conventions. Keys are snake_case.

### Async notifications / callbacks / webhooks

Server POSTs to a caller-supplied URL (e.g. payment-result notifications): keep `method`,
set `path` to `null`. These become OpenAPI 3.1 top-level **`webhooks`** (named by summary),
no fixed URL needed. `responses` holds what the receiver must reply (e.g. `1|OK`).
**`summary` is the identity for null-path endpoints** (see above) — two callbacks sharing
`(method, null)` are only distinguished by `summary`, so give every callback a distinct,
verbatim-matching `summary` in both `inventory.json` and its `endpoints/ep<N>.json`. Still
give every callback detail the correct `source`.

### File naming & count check

- Preserve inventory order; **zero-pad** the index so lexicographic order matches numeric
  order: `ep00.json`, `ep01.json`, … (assemble reads `endpoints/*.json` by sorted filename,
  so unpadded `ep10.json` would sort before `ep2.json`). Endpoints are matched downstream by
  `method`/`path`, so a stray order is not fatal — padding just keeps it readable.
- Before assembling, verify `len(endpoints/*.json) == len(inventory.endpoints)` and that each
  file's `method`/`path`/`source` matches its inventory entry. Fix mismatches by re-reading
  that endpoint scope; do **not** renumber files to hide a mismatch.

## integration.json (optional)

One object for encryption, signing, callbacks, and cross-field conditions. Dispatch one
read-only subagent over the relevant sections.

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

- `payload_assembly`: the ordered steps for building the string to encrypt/sign (the
  signature chain). Only include what the source states.
- `payload_ref` / `operation_ref`: point to an existing `inventory.schemas` name or
  `paths.{path}.{method}`; `null` if no match. An unresolved ref triggers `OUTPUT_MISMATCH`
  (auto-fixable — correct the reference).
- `verify.field`: when a crypto entry signs/encrypts a value that travels in a request field,
  name that field so the signature is wired into the request example.
- `source`: required per entry, in the same `<relative_path> p.<N>` form as inventory
  (see above). Each entry's `source` is carried through to `integration-contract.json`
  alongside a `provenance_target` for reverse lookup.
- **Omit-vs-empty:** if the sources describe **no** integration mechanics, **omit
  `integration.json` entirely** (do not write an empty file). If they mention
  encryption/signing/callbacks/conditions/test-cases but omit required details, **write the
  file with the stated facts plus `missing` entries** — do not omit it just because detail is
  incomplete.
