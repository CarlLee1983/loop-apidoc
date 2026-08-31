# loop-apidoc 0.41.0 release notes

Release date: 2026-08-31

## Summary

Bound where acquisition connects and what it records: one egress gate for every outbound fetch, and URL credentials redacted out of every artifact.

## Changed

- Every outbound fetch now passes a single egress gate (`loop_apidoc/url_safety.py`). A URL is
  fetched only when its scheme is HTTP(S), it carries no userinfo, and *every* address it resolves
  to is globally routable — every, not any, because a name resolving to one public and one private
  address is the standard bypass. Multicast, the NAT64 and 6to4 translation ranges and cloud
  metadata endpoints are excluded beyond `ipaddress.is_global`. The check runs in a request event
  hook, so it covers each redirect hop and a fetcher cannot forget it, and `trust_env=False` keeps a
  proxy environment variable from routing a fetch past the criterion. Acquisition commands surface a
  refusal with a non-zero exit; `manifest --url`'s best-effort probe records it as a note with no
  digest, like any other fetch failure.
- A credential carried in a source URL no longer reaches an artifact. A signed documentation link is
  fetched with its credential intact and recorded as `?X-Amz-Signature=[REDACTED]` in `corpus.json`,
  coverage ledgers, provenance sidecars, OpenAPI snapshots and command output. Replacements are
  spliced into the original string rather than re-encoded, so a URL carrying no credential
  round-trips byte for byte and content-addressing is unaffected. Parameter names are matched
  fail-safe, so an ordinary parameter whose name resembles a credential is redacted too; that costs
  provenance readability and nothing else, because URL identity is redaction-invariant.
- The generated plan, validation report, Markdown and `review.html` now name a URL source by its
  redacted citation identity. `UrlSource.fetch_url` is for issuing the request and
  `UrlSource.citation_id` is for naming, comparing and writing down; the serialized `manifest.json`
  key is unchanged.
- Fixed two comparisons that silently stopped matching once acquisition artifacts became redacted:
  snapshot backfill returned no binding for a signed link, and `loop-apidoc validate` reported every
  signed URL source as uncited. Both compared a value read back from disk against its counterpart
  still held in memory.
- The navigation catalog (`catalog.json`) deliberately keeps whole URLs, because `cache-url-pages`
  reads it back and fetches from it: there a URL is an instruction rather than evidence, and a
  redacted instruction cannot be carried out. Treat it as credential-bearing and keep it out of
  version control, as the repository-hygiene roots already require. The reasoning is recorded in
  `docs/adr/0015-a-url-in-an-artifact-is-either-evidence-or-an-instruction.md`.
- Repository hygiene is now a reviewed inventory that `.gitignore` prevents and the quality gate
  detects, reading from one source (`REPOSITORY_HYGIENE_FORBIDDEN_ROOTS`). Local run artifacts
  previously tracked on `main` were removed from the current tree; history cleanup is in progress
  with the hosting provider and is not yet complete. `docs/adr/0014-...md` records that decision and
  its open residual.
- Minimum supported pydantic is now 2.11.

## Strategy impact

- [ ] None — <explain why no strategy document changed>
- [x] Updated — `docs/DESIGN_DECISIONS.md` (decision 5 now states the egress criterion and the
  evidence-versus-instruction rule for written URLs) and `docs/PRODUCT_EXTENSION_ROADMAP.md` (a
  second delivered security boundary, covering where acquisition may connect and what it may
  record). Teaching and promotion docs updated in the same release: `README.md`, `README.en.md`,
  `docs/index.html`, `docs/index.en.html`, `docs/introduction.html`, `docs/introduction.en.html`,
  `docs/onboarding.html`, `docs/onboarding.en.html`, `docs/operator-manual.html`,
  `docs/operator-manual.en.html`, `docs/architecture-manual.html`,
  `docs/architecture-manual.en.html`, `docs/ARCHITECTURE.md`.

## Validation

- `npm run tag:check`
- `uv run ruff check .`
- `uv run pytest --cov=loop_apidoc`
- `uv run python scripts/quality_gate.py`
- `npm run docs:check`
