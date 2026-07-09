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
 "endpoints": [{"method":"str","path":"str","summary":"str","source":"str"}],
 "schemas": [{"name":"str","fields":[{"name":"str","type":"str|null","required":"bool|null","description":"str|null"}],"enums":["str"],"constraints":"str|null","source":"str"}],
 "errors": [{"code":"str","meaning":"str","http_status":"str|null","source":"str"}],
 "operational": [{"topic":"str","detail":"str","source":"str"}],
 "missing": ["str"]}
```

- `title`: the source document/product title, **verbatim** from the source heading
  (e.g. `綠界全方位金流 API 技術文件`); `null` if none stated → becomes OpenAPI `info.title`.
- `version`: the source-stated document/API version, **verbatim** (e.g. `NDNF-1.2.2`);
  `null` if none → becomes OpenAPI `info.version`.
- Include **every** endpoint and **every** error code.
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

## endpoints/ep<N>.json

One object per endpoint in `inventory.endpoints`. Dispatch one read-only subagent per
endpoint **in parallel** (≤6 concurrent, then batch the rest).

```json
{"method":"str","path":"str","source":"str",
 "parameters":[{"name":"str","in":"query|header|path|body|null","type":"str|null","required":"bool|null","description":"str|null"}],
 "request":{"content_type":"str|null","schema":"str|null","required":"bool|null","description":"str|null"} ,
 "responses":[{"status":"str","description":"str|null","schema":"str|null","schema_ref":"str|null"}],
 "tags":["str"],"security":["str"],
 "examples":[{}],"missing":["str"]}
```

- `request` is `null` when there is no body. Fields the source omits → `null` / empty
  array, and add them to `missing`.
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
**Multiple callbacks sharing the same `(method, null)` are distinguished only by their
`source`** — give every callback detail the correct `source`.

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
