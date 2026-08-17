# loop-apidoc 0.38.0 release notes

Release date: 2026-08-17

## Summary

Source-risk PII gating, supplementary evidence sources, literal endpoint facts, and honest format claims

## Changed

Where 0.37.0 made the source-fact gate's blind spots visible, this release works on the
other side of the same gate: what a source may leak into the pipeline, which sources may
enter it at all, and which format claims the documentation is entitled to make.

- **Leak detection moved ahead of reading the source.** `source-risk` rules were all
  injection-shaped — they asked whether a source could *manipulate* the agent, never
  whether it could *disclose* something to it. The deterministic PII/secret detector that
  previously guarded only the output side (feedback reports, Foundry governance writes) now
  runs before extraction. Only self-evidencing material blocks: `SR-SECRET-VALUE` matches
  PEM private-key blocks and JWTs, whose structure is the evidence.
  `SR-CREDENTIAL-REFERENCE`, `SR-CONTACT-PII`, `SR-PII-VALUE`, and `SR-PAYMENT-CARD` are
  warnings — a competent API document demonstrates `Authorization: Bearer <TOKEN>`, and a
  gate that always needs a waiver is not a gate. Warnings get their own 500-finding budget
  (`SR-WARNINGS-TRUNCATED`) so a document that merely lists many contact addresses cannot
  exhaust the shared blocker cap. `CONTACT_PII`'s domain pattern became a bounded label
  structure: the old `[^\s@]+\.[^\s@]+` was quadratic over a whole document (52.7 s on
  184 KB of minified CSS), which would have let an untrusted source stall the gate meant to
  stop it. `RULESET_VERSION` 2 → 3.
- **A neighbouring number no longer hides a whole card number.**
  `PAYMENT_CARD_CANDIDATE` is greedy: an adjacent digit run was swallowed into one
  candidate, Luhn failed over the whole string, and `finditer` resumed past it — so the
  real card inside was never re-checked. Both gates missed it (`inspect-source-risk`
  SR-PAYMENT-CARD and the governance privacy gate), and #101 had just published the claim
  that card candidates are Luhn-validated. Candidates are now windowed at digit-group
  boundaries — never inside a group, because cutting into a run would invent a card rather
  than find the one the source wrote — and Luhn became two parity prefix sums, which keeps
  windowing at 1.3 s on a 5 MiB adversarial all-digit input instead of ~6 s. Rule dispatch
  moved from `rule_id` string branches to per-rule scan functions, so a typo can no longer
  silently disable filtering. `RULESET_VERSION` 3 → 4. False positives on multi-segment
  numeric sources roughly double (10% → 21% at four segments) — the unavoidable cost of
  trying multiple windows, and fail-closed in direction.
- **A third, accountable source path: supplementary carriers.** Some normative information
  exists only in a supplier's email — how keys are obtained, where the test environment
  is, what must happen before go-live. Previously either it stayed out of the pipeline and
  became `missing`, or an agent read it in and `provenance.json` claimed support from a
  source in no manifest entry. `import-supplementary-note` imports a human excerpt as
  Markdown with a content-bound `.source.json` sidecar, and the manifest marks it
  `authority: supplementary`: it can fill `missing`, it cannot carry `explicit_support`,
  and formal documentation wins any conflict. (ADR 0010)
- **A labelled method on the same line is a literal, not an inference.** The gate only
  recognized `METHOD /path`, so `|URL|<API URL>/Login|Method|GET|` produced nothing. The
  narrowing accepts exactly that shape — both label and value literal, on one line — and
  still refuses cross-line assembly, which ADR 0007 classified as inference. Five
  conditions hold the narrowing: the label must stand as its own word, the method must be
  uppercase, the value is capped at 80 characters and must be entirely a path, only a pipe
  block's first row can declare, and a declaration before any heading ends at the first
  heading. Measured across all thirteen cases' 1,189 Markdown files: one case's
  `SOURCE_FACTS_UNSCANNED` disappears, twelve cases unchanged, zero facts lost. Recognized
  is not complete — 11 of 21 URL+Method lines are read; the rest write `Method|Get|` or sit
  inside strikethrough. (ADR 0011)
- **Spreadsheets are refused by name, with a next step.** `.xlsx`/`.xls` fell through to
  UNKNOWN and the operator saw only "unsupported format". They are now
  `SourceFormat.SPREADSHEET`, still refused, with a per-format remedy stored once in
  `manifest/formats.py` and read by all four reporting points (preparation report, coverage
  warning, score finding, `preprocess` passthrough). The preparation entry previously named
  an action the pipeline cannot perform ("Convert unsupported inputs during preprocess" —
  preprocess only byte-copies these). Not building a converter is a decision, not a
  backlog item: merged cells, formulas, and multiple sheets turn "convert to a Markdown
  table" into a chain of judgements, each an opportunity to manufacture a fact, and under a
  fail-closed gate a fabricated fact blocks a correct extraction. (ADR 0012, which also
  records `.doc`)
- **`.docx` and GitBook are labelled as not validated against a real source.** Both code
  paths are complete — the OOXML subsystem has DDE field scanning, markup alternatives,
  merged cells, external-content checks, staged publish and rollback; GitBook has its own
  command, URL/SHA-256 sidecar, and coverage. But no benchmark case has a Word or GitBook
  source and every DOCX under `tests/` is synthesised in `tmp_path`, so their evidence
  strength is exactly a skipped case's. This repo has always been strict with that
  vocabulary, so both paths now carry the label in the places a reader meets first: both
  READMEs, the landing and intro pages, both operator manuals, the roadmap, and the
  benchmark-vocabulary rule in `AGENTS.md`. The label is removed when the first real Word
  delivery or GitBook site arrives as a benchmark case in the same change.
- **Teaching and promotion docs swept for source-acceptance drift.** Both operator manuals
  and both architecture manuals gained the new source-risk rules and the supplementary
  path; the onboarding tour's freshness description, manifest module description, CLI
  command cards, package-boundary table, and pipeline diagram were corrected; the intro's
  unreconstructible "28 CLI commands" count became a claim that does not need re-counting
  every release.

### Migration

`RULESET_VERSION` moved 2 → 4 and `.xls`/`.xlsx` now hash a different
`source_format.value` into `source_binding_digest`. Existing `source-risk` and
`source-quality` artifacts are therefore stale: `assess-sources`/`assemble` reject them as
a binding or inspection mismatch. Re-run `inspect-source-risk` and then `assess-sources`.
The thirteen gitignored benchmark source-quality packages were rebuilt through the real CLI
chain.

## Strategy impact

- [ ] None — <explain why no strategy document changed>
- [x] Updated — `docs/PRODUCT_EXTENSION_ROADMAP.md` (source-acquisition scope; `.docx` and
  GitBook status entries) and `docs/DESIGN_DECISIONS.md` (source-risk and governance gap
  sections). New accepted records: ADR 0010 (supplementary carriers), ADR 0011 (labelled
  method literal), ADR 0012 (no converter for legacy Word or spreadsheets); ADR 0009
  amended.

## Validation

- `npm run tag:check` — every tag matches the SemVer policy, no ordering anomaly.
- `uv run ruff check .` — pass.
- `npm run docs:check` — pass.
- `uv run pytest --cov=loop_apidoc` — pass, total coverage 93.54% (floor 92.5%).
- `uv run python scripts/quality_gate.py` — pass in CI-safe mode.
- `uv run python scripts/quality_gate.py --strict-local` — **pass with zero skips**: all
  thirteen required cases have non-empty operator source snapshots and rebuilt
  source-quality packages, exact required/committed parity holds, and every benchmark check
  executed.

Not run for this release: the manual artifact eyeball spot-check of a fresh representative
run, and `--sanitized-fixtures` (this release changes no exact-evidence materialization,
Core parity, or sanitized-fixture contract).
