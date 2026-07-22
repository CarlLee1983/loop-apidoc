# v0.20.0 Release Publication Design

## Goal

Publish the already-versioned `v0.20.0` release with release notes that match
all user-facing behavior currently merged on `main`.

## Scope

The existing `0.20.0` notes retain the single-file preprocessing work and add
the URL-corpus enhancements merged before the tag: conservative SPA-shell
detection, the four fixed origin-relative OpenAPI/Swagger probe paths,
separate source records for identified specifications, fail-closed handling of
failed, redirected, non-spec, or undecodable candidate responses, and the
CLI stderr warning.

## Publication flow

1. Amend only `docs/RELEASE_NOTES_0.20.0.md` with the user-facing behavior.
2. Run the release checklist's tag/version, lint, test, and CI-safe quality
   checks, recording any unavailable strict-local source snapshots accurately.
3. Run `npm run release:tag -- --message "loop-apidoc 0.20.0" --dry-run` to
   validate the remote tag history without publishing.
4. After the dry-run succeeds, run the same command without `--dry-run`; its
   controlled release script pushes the current `main` head and creates the
   annotated `v0.20.0` tag.

## Constraints

- Do not run `release:prepare`: the committed package version is already
  `0.20.0`, and the command correctly rejects non-incrementing versions.
- Do not change package-version metadata.
- Never imply that headless rendering occurs automatically.
- Do not publish if any release check or dry-run fails.

## Verification

Verify `npm run tag:check`, `uv run ruff check .`, `uv run pytest --cov=loop_apidoc`, and `uv run python scripts/quality_gate.py`; perform the dry-run before the publishing invocation. Confirm the worktree is clean before the release command.
