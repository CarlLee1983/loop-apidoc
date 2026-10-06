# Split loop_apidoc/domain/projections.py into one module per projection compiler

## Goal

`loop_apidoc/domain/projections.py` is 844 lines and holds five projection compilers
(OpenAPI, GraphQL, AsyncAPI, review, provenance) next to the contract they share. Move
each projection family into its own module under `loop_apidoc/domain/`:

- `projections.py` keeps the shared contract and helpers: `UnsupportedProjectionError`,
  `ProjectionInput`, `ProjectionCompiler`, `Projection`, `_MISSING_SOURCE_STATUS`,
  `_COMPONENT_SCHEMA_NAME_RE`, `_field_schema`, `_require_component_schema_names`,
  `_component_schema_ref`, `_canonical_json`, and `_projection_input`.
- `openapi_projection.py` holds `OpenApiProjectionCompiler` and its helpers.
- `graphql_projection.py` holds `GraphqlProjectionCompiler` and its helpers.
- `asyncapi_projection.py` holds `AsyncApiProjectionCompiler` and its helpers, including
  `_asyncapi_action`.
- `trace_projections.py` holds `ReviewProjectionCompiler`, `ProvenanceProjectionCompiler`,
  and the trace and binding helpers.

The contract types keep their import path, so the seven core and adapter importers of
`Projection`, `ProjectionInput`, and `ProjectionCompiler` do not change. Compiler
importers move to the new paths. ADR 0017 guards the GraphQL and AsyncAPI compilers by
naming `loop_apidoc/domain/projections.py`. After the move that path would still exist
but no longer hold them, so the boundary test would keep passing while the ADR guarded
the wrong file. The ADR's path markers therefore move with the code. The decision does
not change.

## Out of Scope

- Any behaviour change, renamed definition, or changed signature.
- Re-exports or compatibility aliases in `projections.py` for names that moved.
- ADR 0017's decision, title, and every sentence of its `**Falsified if:**` paragraph
  other than the path that names where the compilers live.
- `loop_apidoc/cli.py` and every other module over 800 lines.
- Test changes other than import lines.

## Acceptance Criteria

1. `wc -l` reports at most 800 lines for `loop_apidoc/domain/projections.py` and each of
   the four new modules.
2. Every top-level function, class, and assignment defined in
   `git show 6fefe7b:loop_apidoc/domain/projections.py` is defined exactly once across
   the five modules. A Python `ast` script over those files shows this, and it is
   included in the completion report.
3. `loop_apidoc/domain/projections.py` imports none of the four new modules, and none
   of the four new modules imports another, except that `trace_projections.py` may
   import `asyncapi_projection.py`.
4. `git grep -n 'from loop_apidoc.domain.projections import'` shows only
   `Projection`, `ProjectionInput`, `ProjectionCompiler`, `UnsupportedProjectionError`,
   and private helpers imported by the new modules. Compilers are imported from their
   new modules in `loop_apidoc/shadow/runner.py`, `tests/domain/test_projections.py`,
   `tests/core/test_service_persistence.py`, and
   `tests/integration/test_evidence_to_release.py`.
5. `git diff main...HEAD -- tests/` changes import lines only, and
   `uv run pytest tests/domain tests/core tests/shadow tests/integration -q` passes.
6. In ADR 0017's `**Falsified if:**` paragraph, `loop_apidoc/domain/projections.py` is
   replaced by `loop_apidoc/domain/graphql_projection.py` and
   `loop_apidoc/domain/asyncapi_projection.py`. `git diff main...HEAD -- docs/adr/` shows
   no other change.
7. The ADR 0017 row of `docs/ARCHITECTURE.md`'s `## 決策邊界` satisfies
   `tests/docs/test_adr_boundary_list.py`, and no other line of `docs/ARCHITECTURE.md`
   changes.
8. `git diff --name-status main...HEAD` lists only `M loop_apidoc/domain/projections.py`,
   the four `A loop_apidoc/domain/*_projection*.py` modules,
   `M loop_apidoc/shadow/runner.py`, the three test files in criterion 4,
   `M docs/adr/0017-graphql-and-asyncapi-stay-out-of-the-run-until-a-named-consumer-exists.md`,
   `M docs/ARCHITECTURE.md`, and this Story file
   (`specs/stories/split-domain-projections.md`).
9. `make verify` exits 0.
