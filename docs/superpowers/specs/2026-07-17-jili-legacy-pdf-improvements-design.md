# JiLi Legacy PDF Improvements Design

## Goal

Improve loop-apidoc's faithful handling and benchmarking of legacy PDF APIs that
publish one path with more than one HTTP method, omit concrete server URLs, and
lack endpoint examples.

## Scope

The change has four parts:

1. Add an additive `methods` extraction field for one source-described endpoint
   that supports several HTTP methods with the same documented contract.
2. Emit a non-blocking completeness warning when normal path operations exist
   but no source-grounded environment has a usable `base_url`.
3. Separate source-declared missing examples from unclassified absent examples
   in score evaluation, preserving the validation warning in both cases.
4. Add a JiLi legacy PDF benchmark fixture using the completed extraction,
   expected validation result, and source notes; the proprietary PDF remains
   operator-provided and gitignored.

## Multi-method extraction

`method` remains the canonical, backward-compatible single-method field.
`methods` is an optional non-empty list of HTTP method strings. A source may use
`methods` only when its request parameters, response definition, source
citation, examples, and missing declarations apply to every listed method.

The extraction boundary normalizes a multi-method inventory entry and its single
matching endpoint-detail file into one canonical entry per method before plan
building. OpenAPI, Markdown, examples, provenance, and validation therefore see
ordinary single-method operations. Cross-file verification compares expanded
identities, so one `methods: ["GET", "POST"]` detail can satisfy the matching
expanded inventory pair. Existing `method`-only files retain their exact
behavior.

Method-specific payloads are out of scope. A future `method_variants` model may
be introduced only when a source actually documents method-specific differences.

## Missing server URL

Completeness validation adds one `REQUIRED_INFO_MISSING` warning at
`servers`: when the plan contains at least one path-bearing endpoint and no
environment contains a non-empty `base_url`. Webhooks alone do not trigger it.
This is visibility only: no URL is invented, and the warning does not make
validation fail.

## Example completeness score

Validation continues to warn for every endpoint with no examples. The score
evaluator classifies an example warning as source-declared when the matching
endpoint extraction explicitly records an `examples` missing declaration. Such
findings remain in `ScoreReport.findings` but have zero score impact. An absent
example without that declaration remains a normal completeness finding with the
existing penalty. This preserves the distinction between document quality and
extraction omission without hiding either from reviewers.

## JiLi benchmark

Add `benchmarks/jili-legacy-gaming-pdf/` containing committed extraction,
expected minimums, validation expectations, and notes. The source directory is
left empty/gitignored, consistent with existing copyrighted benchmark inputs.
The case covers 25 expanded operations, MD5-based Key generation, multi-method
FreeSpin operations, a missing base URL, and expected example warnings.

## Tests and compatibility

Tests are written before production changes. They cover expanded multi-method
identity and output, the server warning boundaries, score impact for declared
versus unclassified missing examples, and benchmark fixture discovery. Existing
single-method fixtures and validation semantics remain unchanged except for the
new server warning where its documented condition applies.
