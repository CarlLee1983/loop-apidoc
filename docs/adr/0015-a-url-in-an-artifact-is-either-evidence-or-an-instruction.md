---
status: accepted
---

# A URL in an artifact is either evidence or an instruction, and only evidence is redacted

Issue #156 asked that URL credentials stop being written verbatim into corpus, coverage and
provenance artifacts. Implementing it surfaced a distinction the pipeline had never had to name:
the same string plays two different roles in two different files, and a control that treats them
alike breaks one of them.

## Context

A supplier's documentation link is frequently signed — `?X-Amz-Signature=…`, `?token=…`. Every
acquisition path records the URL it fetched, and recorded it raw, so the credential landed in a
file on disk in plain text. Those are exactly the artifacts the repository hygiene boundary
(#149–#151, ADR 0014) exists to keep out of Git; this is the same leak arriving one layer earlier.

Redaction was implemented as a serialization-time concern: `RedactedUrl` in
`loop_apidoc/url_safety.py` is an annotated type whose `PlainSerializer` rewrites the value on the
way to disk, never in memory. In memory the URL stays whole, because a fetcher reads it off the
model *before* fetching — `gitbook_llms` reads `page.url` to issue the request — so redacting at
construction would break acquisition itself.

Applying that annotation to every URL field then broke two things, and the second is the one that
matters:

**A read-back comparison stopped matching.** `import-rendered-url` writes coverage; `scan-sources`
reads it back and matches it against the same `--url` the operator supplies, which still carries
the credential. Redacted-vs-raw never matched, and `build_manifest` raised `ManifestInputError`.
Worse, it did not take a credential to trigger: `code` is a credential key (an OAuth authorization
code), so an ordinary `?code=en` language parameter broke the pipeline too.

**`catalog.json` cannot be redacted at all.** `catalog-url` writes it and `cache-url-pages` reads it
back and *fetches every URL in it*. A redacted instruction cannot be carried out. This is not a
missing annotation; it is a different role for the same field.

## Decision

**A URL written into an artifact is evidence unless carrying it out is that artifact's purpose.**
Evidence is redacted. The one instruction artifact — `catalog.json`, and the selection derived from
it — keeps its URLs whole.

The criterion is the artifact's purpose, not merely whether something somewhere re-fetches from it,
and that distinction is load-bearing: `freshness record` reads `coverage.json` back and fetches
every URL in it. `coverage.json` is still evidence — it is the acquisition ledger, written to be
read by a reviewer — and the re-fetch is opportunistic. So it stays redacted, and `freshness record`
skips a redacted URL rather than failing on it. Nothing is lost that was not already lost: a signed
link is short-lived, so a freshness baseline resting on one stops working when the signature
expires, redaction or no redaction.

`catalog.json` is different in kind: `cache-url-pages` exists to fetch what is in it, and a redacted
instruction cannot be carried out at all.

**URL identity is redaction-invariant.** `rendered_url.canonicalize_url` redacts as part of
canonicalization, so a redacted artifact still matches the raw URL an operator typed. Redaction is
idempotent, so which side has been through it does not matter. This is what makes over-redaction
cost provenance detail and nothing else — a false positive like `?code=en` no longer breaks a flow.
The same normalization is applied in `url_corpus.find_related_pages`.

`canonicalize_url` is consequently never a URL to fetch: it has lost the credential a fetch needs.
`url_catalog` does not use it, and must not start.

## What holds the exemption, and what does not

`catalog.json` is a local run artifact and belongs under a root in
`REPOSITORY_HYGIENE_FORBIDDEN_ROOTS`, where the hygiene gate refuses to let it be committed. **That
is a convention, not a control.** `catalog-url --output` and `select-url --output` are unconstrained
paths: `--output docs/catalog.json` writes a credential-bearing file into a tracked directory and
the gate has nothing to say about it. Recorded as an open residual rather than fixed here, because
constraining the output root changes a command's contract and is a decision of its own.

`tests/test_url_redaction_contract.py` holds the other half — the exemption is a named list of
fields, and every other URL field in the package must redact or be argued onto that list.

## Alternatives rejected

**Redact everywhere, including `catalog.json`.** The cleanest security posture, and it makes the
`catalog-url` → `cache-url-pages` flow impossible for any signed link: the operator would have to
re-supply the credential at every step. The pipeline exists to work on supplier documentation that
is routinely served behind signed links, so this trades the main flow for a boundary that the
hygiene gate already holds.

**Keep an unredacted "fetch URL" beside the redacted one in every artifact.** Doubles the leak
surface while claiming to reduce it. Anything that reaches disk must be assumed to be readable.

**Redact at construction instead of at serialization.** Breaks acquisition, as above.

**Redact by re-encoding the query (`parse_qsl` + `urlencode`).** Written and rejected during #155.
It does not round-trip a real query string: `?a=1;b=2` becomes one key, `?flag` gains an `=`, `%20`
becomes `+`. A URL recorded in an artifact that no longer matches the URL fetched breaks the
content-addressing and provenance comparison the artifact exists for. The shipped helper splices
replacements into the original string instead.

## Consequences

Which *names* denote a credential stays `loop_apidoc/privacy.py`'s question — AGENTS.md makes it the
single owner of sensitive field detection, and `is_credential_key` lives there with the JWT pattern
both it and `url_safety` use. `url_safety` owns only the URL mechanics.

The key test is asymmetric by design: long unambiguous shapes match as substrings, because vendor
prefixes (`X-Amz-Signature`, `X-Goog-Signature`) defeat an exact set and the cost of a miss is a
silent leak; short ambiguous names (`key`, `code`, `auth`) match whole, because `key` would eat
`keywords` and provenance exists to be read.

Path-segment coverage is deliberately partial — AWS access key ids and JWTs only, no entropy
heuristic, which would eat a 40-hex digest, a version number and a long slug alike.

`?a=1;token=x` is redacted even though `;` has not been a query separator for `parse_qsl` since
3.9.2. The cost is a value containing a literal `;` followed by a credential-shaped name:
`?q=id;pass=through` redacts the tail. Byte-for-byte round-tripping therefore holds for every query
this finds no credential in — which is the property the artifacts depend on — rather than for every
query unconditionally.

**Redaction-invariant identity collides URLs that differ only in their credential.** Two signed
links to the same page canonicalize to one identity: `verified_rendered_url_sources` then reports
them as ambiguous, and a mapping keyed on the identity keeps one of them. That is a real cost of
making identity redaction-invariant, and it is the right trade only because the alternative — an
identity that carries the credential — is the leak this record exists to close. Two re-signed links
to the same page were never two sources.

**The citation identity is the redacted form** (issue #158, closed). `RedactedUrl` protects a
model's own serialization and nothing else, so `plan/classify.py` copying a raw `UrlSource.url` into
`manifest_source` — a plain `str` — carried the credential into `plan.json`, the validation report,
the generated Markdown and the review HTML. `UrlSource.citation_id` is now the single derivation:
`.url` is for fetching, `citation_id` is for naming, comparing and writing down.

Applying it fixed two joins that had silently stopped matching, which is the more instructive half.
Both break the same way: a value that has been through disk is redacted and its counterpart in memory
is not.

`backfill_snapshot_files` compares an in-memory manifest against a coverage ledger loaded from disk,
so it returned `None` for every signed link's snapshot binding. `check_manifest_coverage` matches a
manifest's URL sources against provenance `manifest_source`, and reaches that state only on the path
that reads both files back — `validate_run_dir`, behind the `validate` command — where the manifest
side was already redacted at write time and `manifest_source` was not. Measured on `main`:
`loop-apidoc validate` reported every signed URL source as uncited, while the same check on the
in-memory `assemble` path matched, because there both sides were still raw. Both are pinned by tests
that round-trip the models through JSON, which is what makes the disk path reproducible in a test at
all.

A third comparison, `Manifest.readable_source_identities`, is now spelled in the identity for a
different reason: it is checked against a `source` field an agent writes, and an agent only ever reads
redacted artifacts. That is an argument about agent behaviour rather than a failure anyone has
observed, and it is recorded as such.

The raw accessor is named `fetch_url` rather than `url`, while the serialized key stays `url`. A name
nothing else in the package uses turns "every read of the credential" into an exact check
(`tests/test_citation_identity_contract.py`) instead of a heuristic over the shapes someone happened
to think of, and turns a missed attribute read into an `AttributeError` instead of a leak. It does not
reach `dict(source)`, `getattr`, or `source.__dict__`, none of which occur here. Two consequences of
the rename are worth knowing: `model_dump(exclude={"url"})` no longer excludes the field — the field
name is `fetch_url` — and `model_copy(update={"url": ...})` is a silent no-op. Neither is used
anywhere in the package. The pydantic floor is `>=2.11` because `serialize_by_alias` arrived there and
an unknown config key is ignored silently; below it every manifest would be written with a `fetch_url`
key that no reader accepts.

A citation locator is prose that may quote a URL, so it goes through `redact_text`, which finds the
URLs inside a larger string and leaves the surrounding words alone. Its hard part is knowing where a
URL ends when nothing delimits it: Traditional Chinese prose puts the next sentence hard against the
link, and `,` is a legal URI character, so `?token=X,https://b/` would otherwise read as one URL.

**Known consequence of the collapse.** Two URL sources differing only in their signature now share one
identity. `shadow/bridge.py` reports the conflicting-digest case as `SOURCE_LOCATOR_AMBIGUOUS`;
`adapters/fragments.py` and `diff/compare.py`'s manifest map are plain dict comprehensions, so the
last of the two wins unconditionally and neither says so, and the generated Markdown and review HTML
list the collapsed source twice. `validate/coverage.py` de-duplicates. Deduplicating at manifest
construction with a diagnostic is the right place to fix this and is not done here; it needs an
operator to have supplied both links in one run.

`match_manifest_source` therefore matches both spellings and returns the identity: the agent quotes
what it read, and an operator writing a locator by hand has the signed link itself in front of them.

A smaller residual of the same kind: an error that reports only its exception class still chains the
original, so `raise ... from exc` keeps the full URL on `__cause__`. Harmless behind the CLI's
handlers, visible under `--pdb` or a crash reporter.

**Falsified if:** the two roles stop being distinguishable, or a control here stops being held by
something a test can check. Concretely, this decision no longer holds when a field listed in
`tests/test_url_redaction_contract.py`'s `EXEMPT_FIELDS` is read back for anything other than
fetching; when `loop_apidoc/url_catalog.py` starts writing an artifact outside the roots in
`scripts/quality_gate.py`'s `REPOSITORY_HYGIENE_FORBIDDEN_ROOTS`; when
`loop_apidoc/rendered_url.py`'s `canonicalize_url` stops redacting, so URL identity is no longer
redaction-invariant; when `loop_apidoc/url_safety.py` grows its own credential-name vocabulary
instead of calling `loop_apidoc/privacy.py`'s `is_credential_key`; when `loop_apidoc/manifest/models.py`
gives `UrlSource` a `url` attribute again, so the exact check in
`tests/test_citation_identity_contract.py` degrades to a heuristic; or when that file's `ALLOWED`
grows an entry for a module that writes the value down rather than fetching with it.
