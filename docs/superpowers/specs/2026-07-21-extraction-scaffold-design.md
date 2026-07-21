# Extraction Scaffold from Markdown Drafts Design

## Goal

Add a deterministic CLI that projects well-structured local Markdown API pages
into an **extraction-shaped scaffold** under a dedicated directory. Agents copy
and review those files into the real extraction workdir instead of re-deriving
every parameter table and fenced example from scratch.

This closes the gap between the existing non-authoritative
`extract-markdown-drafts` facts artifact and the agent-owned
`inventory.json` / `endpoints/ep<N>.json` contract used by `verify-extraction`
and `assemble`.

## Scope

In scope:

- New command `scaffold-extraction`.
- Pure projection from Markdown draft facts (reusing `scan_markdown_drafts`)
  into extraction-schema-compatible JSON files.
- Optional mechanical collection of appendix-style error-code tables that are
  **outside** any open endpoint section.
- Immutable write of `<output>/inventory.json`, `<output>/endpoints/ep<N>.json`,
  `<output>/scaffold-report.json`, and a short `<output>/README.md`.
- Skill / teaching-doc updates that insert the scaffold step and require an
  explicit agent copy into `<WORK>/` before verification.

Out of scope (deferred):

- Writing `integration.json` (signing narratives, callbacks, field conditions).
- Inferring `environments`, API hosts, HTTP status codes, or security scheme
  names.
- Treating scaffold output as a valid `--extraction` input without agent copy.
- Changing `source_facts` intersection / fail-open semantics.
- Nested example-only keys under `detail` that are absent from labelled tables
  (agents still expand those when needed).

## Relationship to Existing Pieces

| Artifact / command | Role after this change |
| --- | --- |
| `extract-markdown-drafts` | Remains a compact, line-cited facts aid. Optional before scaffold; scaffold does not require its JSON file on disk. |
| `scaffold-extraction` (new) | Writes extraction-**shaped** files under `--output` only. Never writes `<WORK>/inventory.json` or `<WORK>/endpoints/` unless that path is passed as `--output`. |
| Agent extraction | Owns authority: copy scaffold → review → fill `missing` / security / integration → `verify-extraction`. |
| `verify-extraction` / `assemble` | Unchanged contracts. Operators must not point `--extraction` at a fresh scaffold directory as the blessed path; the skill forbids it. |

Scaffold files use the **same English keys** as real extraction JSON so a
reviewed copy is assemble-ready. They do **not** add an `authoritative` key to
those JSON bodies (assemble would reject unknown required shapes / the skill
keeps schema parity). Non-authority is stated in `README.md` and
`scaffold-report.json` only.

## CLI Contract

```bash
loop-apidoc scaffold-extraction \
  --sources <SOURCES> \
  --manifest <WORK>/manifest.preflight.json \
  --output <WORK>/scaffold
```

- `--sources` — local source root named by the manifest.
- `--manifest` — manifest JSON (same usability rules as
  `extract-markdown-drafts`: only readable Markdown entries are scanned).
- `--output` — destination directory. The command creates it. If the path
  already exists and is non-empty, the command fails before writing
  (immutable collision, same spirit as gitbook cache / drafts output).

Stdout prints a concise JSON or text summary: endpoint count, field count,
example count, omitted-table count, and the output path. Exit `0` on success;
non-zero on input / collision / I/O errors.

## Output Layout

```text
<output>/
  README.md              # non-authoritative; copy-to-WORK instructions
  scaffold-report.json   # coverage stats, per-endpoint gaps, omitted tables
  inventory.json
  endpoints/
    ep00.json
    ep01.json
    …
```

Endpoint files are zero-padded in discovery order (stable sort by
`(relative_path, start_line, method, path)` across all scanned sources) so
lexicographic order matches numeric order.

## Projection Rules (fail-closed)

### inventory.json

- `title`: if the manifest includes exactly one Markdown file whose
  relative path is a package entry index (filename matches the sources-root
  stem or is the sole top-level `*.md`), use that file's first H1 text;
  otherwise `null`. Never synthesize a title from subdirectory names.
- `version`: always `null` in v1 (document versions are not mechanically
  reliable across these packages).
- `overview`: always `""` in v1, with
  `"overview not mechanically derived"` in `missing`.
- `environments`: always `[]`; add `"API base URL not stated in scanned sources"`
  to `missing` when no concrete `https://` host appears outside fenced examples
  (scaffold does not invent hosts from example placeholders such as
  `https://launch_url`).
- `security_schemes`: always `[]` in v1; agents fill after reading encryption
  pages. Report notes that signing docs were not projected.
- `endpoints[]`: one entry per draft endpoint with `method`, `path`, `summary`,
  `source`, `server: null`.
  - `summary`: prefer the nearest preceding Markdown heading text for that
    endpoint section; if the only heading is the method/path line itself, use
    that heading stripped of method/path tokens when possible, else the raw
    heading / declaration line.
  - `source`: `{relative_path} lines {start_line}-{end_line}` (and may append
    `# {heading}` when a heading exists).
- `schemas`: `[]` in v1.
- `errors[]`: optional mechanical harvest from **non-endpoint** Markdown tables
  whose headers look like `code` + meaning/说明 and whose rows are numeric
  codes. Deduplicate by code (first wins). `http_status` and `applicable_to`
  stay empty/null. If no such table exists, `errors` is `[]`.
- `operational`: `[]` in v1 (rate-limit prose stays for agents).
- `missing`: concrete labels for everything above left empty by design.

### endpoints/ep<N>.json

- `method` / `path` / `source`: from the draft endpoint; `source` matches the
  inventory citation form for that endpoint.
- `parameters[]`: one entry per draft field whose `label` is `headers`, `query`,
  or `request` (body).
  - Map label → `in`: `headers`→`header`, `query`→`query`, `request`→`body`.
  - `type` / `description`: literal table cell strings, or `null`.
  - `required`: `true`/`false` only when the required cell clearly parses
    (yes/no, true/false, 是/否, 必填/選填, Y/N); otherwise `null` and name the
    field in endpoint `missing`.
  - Do **not** invent nested `detail.*` fields from JSON examples in v1.
- `request`: if any `in:body` parameter exists or a request-labelled example
  exists →
  `{"content_type":"application/json","schema":null,"required":null,"description":null}`;
  else `null`. Content-Type header rows still appear as parameters; they do not
  alone force a non-null `request` unless a body field/example exists.
- `responses`: if any response-labelled example or response-labelled fields
  exist → `[{"status":"default","description":null,"schema":null,"schema_ref":null}]`;
  else `[]` and record missing response shape.
- `tags`: `[]` in v1 (folder names like 单一钱包 are not projected as tags
  without an explicit source label convention).
- `security`: `[]` in v1 (no scheme names invented).
- `examples[]`: for each draft example whose language is JSON-family and whose
  `content` parses with `json.loads`, emit
  `{"title": <label or "example">, "content_type":"application/json", "value": <parsed>}`.
  Non-JSON or invalid JSON fences are omitted from `examples` and listed in
  `missing` with line range — never silently dropped without a gap label.
- `missing`: required-flag gaps, response gaps, unparsed examples, etc.

### scaffold-report.json

```json
{
  "kind": "extraction_scaffold",
  "authoritative": false,
  "sources_scanned": 0,
  "endpoints": 0,
  "fields": 0,
  "examples_projected": 0,
  "examples_unparsed": 0,
  "omitted_tables": 0,
  "errors_projected": 0,
  "per_endpoint": [
    {
      "file": "endpoints/ep00.json",
      "method": "POST",
      "path": "/vg/sign-up",
      "field_count": 0,
      "example_count": 0,
      "missing": []
    }
  ]
}
```

## Agent Flow

```text
cache-gitbook-llms (when applicable)
  -> manifest
  -> extract-markdown-drafts   # optional aid
  -> scaffold-extraction --output <WORK>/scaffold
  -> agent: review scaffold; copy inventory + endpoints into <WORK>/;
            fill security_schemes, tags/security on endpoints, integration.json,
            and any missing[] items by re-reading cited sections
  -> verify-extraction
  -> assemble
```

The skill must state that `<WORK>/scaffold` is not the `--extraction` argument.

## Architecture

Prefer a small package boundary next to drafts:

- `loop_apidoc/markdown_drafts/` keeps scanning pure and non-authoritative.
- New `loop_apidoc/extraction_scaffold/` (or `markdown_drafts/scaffold.py` if
  kept tiny) owns:
  - pure `project_scaffold(draft_index) -> ScaffoldBundle`
  - read-side collect via existing manifest Markdown loader patterns
  - write-side `write_scaffold(bundle, output_dir)` as the only file I/O exit
    for this feature
- `cli.py` registers `scaffold-extraction`.

Do not feed scaffold output into Core shadow or Foundry. Do not weaken
`source_facts`: scaffold is an accelerator, not a validation authority.

## Error Handling

- Unreadable manifest / missing sources root → fail loud, write nothing.
- Non-Markdown or ignored manifest entries → skip (same as drafts collect).
- Empty usable Markdown set → fail loud (nothing to scaffold).
- Output collision (exists and non-empty) → fail before any write.
- Partial write must not leave a “successful” empty tree: write into a temp
  directory under the parent, then atomically replace/move into `--output`
  when practical; if the platform cannot rename over an existing empty dir,
  create `--output` only after the temp tree is complete.

## Testing

- Pure projection unit tests with fixture Markdown matching GitBook-style
  `<mark>\`POST\`</mark> \`/path\``, `**Body**` tables, and Success JSON fences.
- Required-cell parsing matrix (是/否, yes/no, empty → null + missing).
- Invalid JSON fence → missing entry, no crash.
- Error-code appendix table outside endpoint sections → inventory `errors`.
- CLI: writes expected files; refuses non-empty output; exit codes.
- Regression: running scaffold against the VG cached sources package yields
  20 endpoint files and non-empty parameters for pages that drafts already
  see (fixture or optional local-only test gated on present sources).

## Success Criteria

- Structured GitBook-like packages produce scaffold endpoint files whose
  table fields and parseable JSON examples cover the mechanical portion of
  what agents previously typed by hand.
- Agents spend tokens on review, security/integration, and genuine gaps — not
  on re-keying every Body row.
- `assemble` / `verify-extraction` contracts unchanged; scaffold never becomes
  a silent authority.
- Docs (`SKILL.md`, README, architecture notes) describe the copy step.

## Non-Goals Reminder

No host invention, no integration crypto projection in v1, no automatic
`detail.*` expansion from examples, no writing directly into the live
extraction workdir unless the operator passes that path as `--output`
deliberately.
